"""The six render styles.  Each returns premultiplied-free ``(rgb, alpha)`` float32 arrays
given a :class:`DevelopContext`; the developer composites them over the background."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from attractr.core.math.percentile import robust_percentile
from attractr.core.render.develop import lighting
from attractr.core.render.develop.tonemap import apply_curve, base_density, equalize
from attractr.core.render.result import RenderResult
from attractr.core.render.settings import Look


@dataclass
class DevelopContext:
    result: RenderResult
    look: Look
    norm: float
    lut: np.ndarray  # [N, 4] float32
    mask: np.ndarray  # count > 0
    density: np.ndarray  # tone-mapped + curves, in [0, 1]


def sample_lut(lut: np.ndarray, t: np.ndarray) -> np.ndarray:
    n = lut.shape[0]
    idx = np.clip((t * (n - 1) + 0.5).astype(np.int32), 0, n - 1)
    return lut[idx]


def make_context(result: RenderResult, look: Look, norm: float, lut: np.ndarray) -> DevelopContext:
    mask = result.count > 0
    d = base_density(result.count, look, norm)
    if look.equalize:
        d = equalize(d, mask)
    d = apply_curve(d, look)
    d[~mask] = 0.0 if not look.invert else 1.0
    return DevelopContext(result, look, norm, lut, mask, d)


def color_index(ctx: DevelopContext) -> np.ndarray | None:
    """Palette index from the colour-value buffer (robust 1–99 % range), or None."""
    cv = ctx.result.mean_cv()
    if cv is None:
        return None
    vals = cv[ctx.mask]
    if vals.size == 0:
        return None
    lo, hi = np.percentile(vals, [1.0, 99.0])
    if hi - lo < 1e-12:
        hi = lo + 1.0
    return np.clip((cv - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)


def depth_factor(ctx: DevelopContext, strength: float) -> np.ndarray:
    """1 near … (1 − strength) far, from the mean depth buffer."""
    md = ctx.result.mean_depth()
    if md is None or strength <= 0:
        return np.ones_like(ctx.density)
    vals = md[ctx.mask]
    if vals.size == 0:
        return np.ones_like(ctx.density)
    lo, hi = np.percentile(vals, [1.0, 99.0])
    if hi - lo < 1e-9:
        return np.ones_like(ctx.density)
    dn = np.clip((md - lo) / (hi - lo), 0.0, 1.0)  # 0 near … 1 far (depth grows away)
    return (1.0 - strength * 0.8 * dn).astype(np.float32)


# ── styles ──────────────────────────────────────────────────────────────────────


def style_gas(ctx: DevelopContext) -> tuple[np.ndarray, np.ndarray]:
    d = ctx.density * depth_factor(ctx, ctx.look.depth_cue if ctx.result.depth_sum is not None else 0.0)
    ci = color_index(ctx)
    if ci is None:
        rgba = sample_lut(ctx.lut, d)
        return rgba[..., :3], rgba[..., 3] * d
    rgba = sample_lut(ctx.lut, ci)
    return rgba[..., :3] * d[..., None], rgba[..., 3] * d


style_dust = style_gas  # differs only in base_density()


def style_light(ctx: DevelopContext) -> tuple[np.ndarray, np.ndarray]:
    ci = color_index(ctx)
    if ci is None:
        ci = ctx.density
    rgba = sample_lut(ctx.lut, ci)
    b = ctx.density * depth_factor(ctx, ctx.look.depth_cue if ctx.result.depth_sum is not None else 0.0)
    rgb = rgba[..., :3] * b[..., None]
    if ctx.look.glow > 0:
        rgb = rgb + bloom(rgb, ctx.look.glow)
    return np.clip(rgb, 0, 1), np.clip(b * 1.5, 0, 1)


def style_plasma(ctx: DevelopContext) -> tuple[np.ndarray, np.ndarray]:
    t = np.mod(ctx.density * ctx.look.bands, 1.0)
    rgba = sample_lut(ctx.lut, t)
    soft = np.clip(ctx.density * 2.0, 0.0, 1.0)
    rgb = rgba[..., :3] * soft[..., None]
    if ctx.look.glow > 0:
        rgb = rgb + bloom(rgb, ctx.look.glow)
    return np.clip(rgb, 0, 1), soft


def _surface_lighting(ctx: DevelopContext, mask: np.ndarray):
    zmin = ctx.result.zmin
    if zmin is None:
        ones = np.ones_like(ctx.density)
        return ones, np.zeros_like(ctx.density)
    ppu = min(ctx.result.width, ctx.result.height) * 0.12  # relief scale: pixels per unit of depth (gentler than true scale)
    h = lighting.height_field(zmin, mask, ppu)
    n = lighting.normals(h)
    return lighting.shade(n, ctx.look.light)


def style_liquid(ctx: DevelopContext) -> tuple[np.ndarray, np.ndarray]:
    d = ctx.density * depth_factor(ctx, max(ctx.look.depth_cue, 0.3))
    rgba = sample_lut(ctx.lut, d)
    diff, spec = _surface_lighting(ctx, ctx.mask)
    rgb = rgba[..., :3] * diff[..., None] + spec[..., None] * np.asarray(ctx.look.light.color, np.float32)
    return np.clip(rgb, 0, 1), np.clip(d * 2.0, 0, 1)


def style_solid(ctx: DevelopContext) -> tuple[np.ndarray, np.ndarray]:
    surf = ctx.density > ctx.look.solid_threshold
    md = ctx.result.mean_depth()
    zmin = ctx.result.zmin
    if zmin is not None and surf.any():
        zv = zmin[surf]
        lo, hi = np.percentile(zv, [1.0, 99.0])
        t = 1.0 - np.clip((zmin - lo) / max(hi - lo, 1e-9), 0, 1)  # near = 1
    elif md is not None:
        t = ctx.density
    else:
        t = ctx.density
    rgba = sample_lut(ctx.lut, np.where(surf, 0.25 + 0.75 * t, 0.0).astype(np.float32))
    diff, spec = _surface_lighting(ctx, surf)
    rgb = rgba[..., :3] * diff[..., None] + spec[..., None] * np.asarray(ctx.look.light.color, np.float32)
    # anti-aliased edge: ramp alpha over a small density band around the threshold
    band = max(ctx.look.solid_threshold * 0.5, 1e-3)
    alpha = np.clip((ctx.density - ctx.look.solid_threshold + band) / band, 0.0, 1.0)
    return np.clip(rgb, 0, 1), alpha.astype(np.float32)


def bloom(rgb: np.ndarray, amount: float) -> np.ndarray:
    """Cheap separable box-blur bloom on a half-resolution copy."""
    small = rgb[::2, ::2]
    k = max(1, int(3 * amount * 4))
    pad = np.pad(small, ((k, k), (k, k), (0, 0)), mode="edge")
    cs = np.cumsum(np.cumsum(pad, axis=0), axis=1)
    n = 2 * k + 1
    box = (cs[n:, n:] - cs[:-n, n:] - cs[n:, :-n] + cs[:-n, :-n]) / (n * n)
    up = np.repeat(np.repeat(box, 2, axis=0), 2, axis=1)[: rgb.shape[0], : rgb.shape[1]]
    return up * amount


STYLES = {
    "gas": style_gas,
    "dust": style_dust,
    "light": style_light,
    "liquid": style_liquid,
    "solid": style_solid,
    "plasma": style_plasma,
}


def percentile_norm(count: np.ndarray, pct: float) -> float:
    return max(robust_percentile(count, pct), 1e-9)
