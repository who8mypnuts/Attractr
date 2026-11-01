"""Background layers (solid, gradient, image, procedural) as float RGBA images."""

from __future__ import annotations

import numpy as np

from attractr.core.render.settings import Background


def make_background(bg: Background, width: int, height: int) -> np.ndarray:
    """Return float32 RGBA [H, W, 4] in 0..1 (alpha 0 for transparent)."""
    out = np.empty((height, width, 4), dtype=np.float32)
    if bg.mode == "transparent":
        out[:] = 0.0
        return out
    if bg.mode == "gradient":
        t = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
        c0 = np.asarray(bg.color, dtype=np.float32)
        c1 = np.asarray(bg.color2, dtype=np.float32)
        out[..., :3] = c0 * (1 - t) + c1 * t
        out[..., 3] = 1.0
        return out
    if bg.mode == "image" and bg.image_path:
        try:
            from attractr.core.render.develop.image_bg import load_cover
            out[..., :3] = load_cover(bg.image_path, width, height)
            out[..., 3] = 1.0
            return out
        except Exception:  # noqa: BLE001 — fall back to the solid colour
            pass
    if bg.mode == "procedural":
        from attractr.core.render.develop.procedural import procedural_background
        out[..., :3] = procedural_background(bg.procedural, width, height, bg.seed, bg.color)
        out[..., 3] = 1.0
        return out
    out[..., :3] = np.asarray(bg.color, dtype=np.float32)
    out[..., 3] = 1.0
    return out
