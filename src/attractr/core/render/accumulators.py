"""Which accumulation buffers a (style, colour source) combination needs, and the integer
codes shared with every kernel (numba / GLSL / OpenCL)."""

from __future__ import annotations

from dataclasses import dataclass

from attractr.core.render.settings import Look

COLOR_CODES = {
    "density": 0, "x": 1, "y": 2, "z": 3, "depth": 4, "speed": 5, "radius": 6,
    "index": 7, "curvature": 8, "formula": 9,
}


@dataclass(frozen=True)
class Needs:
    depth: bool  # Σ depth per pixel
    zmin: bool  # nearest depth per pixel
    color: bool  # Σ colour-value per pixel
    color_code: int

    @property
    def buffer_count(self) -> int:
        return 1 + int(self.depth) + int(self.zmin) + int(self.color)


def needs_for(look: Look) -> Needs:
    style = look.style
    depth = style in ("liquid",) or (look.depth_cue > 0 and style in ("gas", "dust", "plasma", "light"))
    zmin = style in ("liquid", "solid")
    src = look.color_source
    if style == "light" and src == "density":
        src = "speed"  # Light defaults to speed colouring (Android behaviour)
    color = src != "density"
    return Needs(depth, zmin, color, COLOR_CODES[src])


def color_value_range(code: int, sample_pts, framing, camera_matrix, params=None, color_fn=None) -> tuple[float, float]:
    """Estimate the [lo, hi] range of a colour source from the framing sample so GPU
    engines can encode it in fixed point with full resolution (the develop stage
    re-normalises by the 1–99 % percentiles anyway)."""
    import numpy as np

    pts = sample_pts[np.all(np.isfinite(sample_pts), axis=1)]
    if pts.shape[0] < 4 or code == 0:
        return -4.0, 4.0
    unit = (pts - np.asarray(framing.center)) / framing.radius
    q = unit @ np.asarray(camera_matrix).T
    if code in (1, 2, 3, 4):
        v = q[:, {1: 0, 2: 1, 3: 2, 4: 2}[code]]
    elif code == 5:
        d = np.diff(unit, axis=0)
        v = np.sqrt((d * d).sum(1))
        v = v[v < np.percentile(v, 99.5) * 4 + 1e-12] if v.size else v
    elif code == 6:
        v = np.sqrt((q * q).sum(1))
    elif code in (7, 8):
        return 0.0, 1.0
    elif code == 9 and color_fn is not None:
        step = max(1, pts.shape[0] // 4096)
        sub = pts[::step]
        v = np.array([color_fn(float(x), float(y), float(z), params) for x, y, z in sub])
    else:
        return -4.0, 4.0
    v = v[np.isfinite(v)]
    if v.size < 4:
        return -4.0, 4.0
    lo, hi = float(np.percentile(v, 0.5)), float(np.percentile(v, 99.5))
    if hi - lo < 1e-12:
        hi = lo + 1e-6
    pad = (hi - lo) * 0.05
    return lo - pad, hi + pad
