"""Cheap reduced-size copies of accumulation results (progress thumbnails)."""

from __future__ import annotations

import math

import numpy as np

from attractr.core.render.result import RenderResult


def _block(buf: np.ndarray, f: int, mode: str) -> np.ndarray:
    """Box-reduce a plane by an integer factor (sum or min)."""
    H, W = buf.shape[0] // f, buf.shape[1] // f
    blocks = buf[: H * f, : W * f].reshape(H, f, W, f)
    out = blocks.min(axis=(1, 3)) if mode == "min" else blocks.sum(axis=(1, 3), dtype=np.float64)
    return out.astype(np.float32)


def shrink_result(result: RenderResult, max_side: int = 256) -> RenderResult:
    """Box-filter every buffer by an integer factor so the longer side is ≤ ``max_side``
    (counts are summed, nearest depth is min-pooled) — developing the copy costs
    milliseconds regardless of the render size."""
    f = max(1, math.ceil(max(result.width, result.height) / max_side))
    if f == 1:
        return result
    return RenderResult(
        result.settings, _block(result.count, f, "sum"), result.framing, result.stats,
        _block(result.depth_sum, f, "sum") if result.depth_sum is not None else None,
        _block(result.zmin, f, "min") if result.zmin is not None else None,
        _block(result.cv_sum, f, "sum") if result.cv_sum is not None else None,
        result.complete,
    )
