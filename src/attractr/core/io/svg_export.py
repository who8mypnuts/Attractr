"""Vector export: one trajectory of the current view as SVG polylines (flows) or dots
(maps / IFS / sections) — for plotters, laser cutters and vector illustration.

The projection is exactly the render's: the same framing (bounding sphere + 2-D fit),
camera and pixel size as ``settings.quality``, so the SVG overlays the raster render."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from attractr.core.render.engines.cpu_numba import apply_lock, effective_camera
from attractr.core.render.framing import compute_framing, sample_attractor
from attractr.core.render.pipeline import resolve_spec
from attractr.core.render.settings import RenderSettings


def trace(settings: RenderSettings, points: int = 20000, seed: int | None = None) -> tuple[np.ndarray, bool]:
    """Projected pixel coordinates ``[n, 2]`` (NaN rows mark trajectory restarts) of one
    trajectory after the attractor's warm-up, plus whether consecutive points form a curve."""
    spec = resolve_spec(settings)
    if spec.is_escape:
        raise ValueError("escape-time systems have no single orbit to trace")
    q = settings.quality
    params = spec.params_array(settings.param_dict)
    dt = float(q.dt) if q.dt else spec.dt
    substeps = max(1, int(q.substeps))
    framing, _ = compute_framing(spec, params, dt, substeps, spec.warmup, q.seed, settings.camera, q.width, q.height)
    framing = apply_lock(framing, settings.camera)
    cam = effective_camera(settings.camera, framing)
    pts = sample_attractor(spec, params, dt, substeps, spec.warmup, q.seed if seed is None else seed, n_traj=1, steps=points)
    plotted = pts[:, 4:7]
    unit = (plotted - np.asarray(framing.center)) / framing.radius
    u, v, _ = cam.project(np.nan_to_num(unit), q.width, q.height)
    uv = np.stack([u, v], axis=1)
    uv[~np.all(np.isfinite(plotted), axis=1)] = np.nan
    return uv, spec.plots_continuous


def svg_document(uv: np.ndarray, width: int, height: int, continuous: bool, *, stroke: str = "#ffffff",
                 stroke_width: float = 0.6, background: str | None = "#000000", opacity: float = 0.8) -> str:
    """Build the SVG text. Runs between NaN rows become separate polylines; for discrete
    systems every point is a small filled circle."""
    head = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
    if background:
        head.append(f'<rect width="100%" height="100%" fill="{background}"/>')
    style = f'fill="none" stroke="{stroke}" stroke-width="{stroke_width:g}" stroke-opacity="{opacity:g}" stroke-linecap="round" stroke-linejoin="round"'
    body: list[str] = [f"<g {style}>"]
    finite = np.all(np.isfinite(uv), axis=1)
    if continuous:
        # split into runs of consecutive finite points
        idx = np.flatnonzero(np.diff(np.concatenate([[False], finite, [False]]).astype(np.int8)))
        for start, stop in zip(idx[::2], idx[1::2], strict=True):
            if stop - start < 2:
                continue
            run = uv[start:stop]
            body.append('<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in run) + '"/>')
    else:
        pts = uv[finite]
        inside = (pts[:, 0] >= -1) & (pts[:, 0] <= width + 1) & (pts[:, 1] >= -1) & (pts[:, 1] <= height + 1)
        r = max(stroke_width * 0.5, 0.05)
        body.append(f'<g fill="{stroke}" fill-opacity="{opacity:g}" stroke="none">')
        body.extend(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:g}"/>' for x, y in pts[inside])
        body.append("</g>")
    body.append("</g>")
    return "\n".join(head + body + ["</svg>"]) + "\n"


def write_svg(settings: RenderSettings, path: str | Path, points: int = 20000, **style) -> Path:
    uv, continuous = trace(settings, points)
    q = settings.quality
    bg = settings.look.background
    if "background" not in style:
        style["background"] = None if bg.mode == "transparent" else _hex(bg.color)
    if "stroke" not in style:
        style["stroke"] = "#000000" if settings.look.invert else "#ffffff"
    path = Path(path)
    path.write_text(svg_document(uv, q.width, q.height, continuous, **style), encoding="utf-8")
    return path


def _hex(rgb) -> str:
    return "#" + "".join(f"{int(round(min(max(c, 0.0), 1.0) * 255)):02x}" for c in rgb[:3])
