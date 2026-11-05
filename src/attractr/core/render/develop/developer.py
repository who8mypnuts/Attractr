"""Development stage: RenderResult + Look → RGBA image (float, then 8/16-bit)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from attractr.core.render.develop import gpu_develop
from attractr.core.render.develop.background import make_background
from attractr.core.render.develop.styles import STYLES, make_context, percentile_norm
from attractr.core.render.result import RenderResult
from attractr.core.render.settings import Look

LUT_SIZE = 1024


@dataclass
class Developed:
    rgba: np.ndarray  # float32 [H, W, 4] straight (non-premultiplied) alpha, 0..1
    norm: float  # count value mapped to full brightness

    @property
    def width(self) -> int:
        return self.rgba.shape[1]

    @property
    def height(self) -> int:
        return self.rgba.shape[0]

    def to_uint8(self, dither: bool = True, seed: int = 1) -> np.ndarray:
        return quantize(self.rgba, 255, dither, seed).astype(np.uint8)

    def to_uint16(self, dither: bool = True, seed: int = 1) -> np.ndarray:
        return quantize(self.rgba, 65535, dither, seed).astype(np.uint16)


def quantize(rgba: np.ndarray, maxval: int, dither: bool, seed: int) -> np.ndarray:
    v = rgba * maxval
    if dither:
        rng = np.random.default_rng(seed)
        v = v + rng.random(v.shape, dtype=np.float32) - 0.5
    return np.clip(np.rint(v), 0, maxval)


def develop(result: RenderResult, look: Look | None = None, *, gpu: str = "auto") -> Developed:
    """``gpu``: "auto" (GPU compute pass for large images when available), "off" or "force"."""
    look = look or result.settings.look
    norm = percentile_norm(result.count, look.percentile)
    lut = look.gradient.lut(LUT_SIZE, look.phase, look.cycles)
    if gpu != "off" and (gpu == "force" or gpu_develop.wanted(result, look)):
        rgba = gpu_develop.develop_gpu(result, look, norm, lut)
        if rgba is not None:
            return Developed(rgba, norm)
    return develop_cpu(result, look, norm, lut)


def develop_cpu(result: RenderResult, look: Look, norm: float, lut: np.ndarray) -> Developed:
    ctx = make_context(result, look, norm, lut)
    rgb, alpha = STYLES.get(look.style, STYLES["gas"])(ctx)
    rgb = rgb.astype(np.float32, copy=False)
    alpha = np.clip(alpha.astype(np.float32, copy=False), 0.0, 1.0)
    bg = make_background(look.background, result.width, result.height)
    out = np.empty((result.height, result.width, 4), dtype=np.float32)
    a = alpha[..., None]
    out[..., :3] = rgb * a + bg[..., :3] * (1.0 - a) * bg[..., 3:4] if look.background.mode == "transparent" else rgb * a + bg[..., :3] * (1.0 - a)
    out[..., 3] = alpha + bg[..., 3] * (1.0 - alpha)
    if look.background.mode == "transparent":
        # straight alpha: un-premultiply the colour where alpha > 0
        nz = out[..., 3] > 1e-6
        out[..., :3][nz] /= out[..., 3:4][nz]
    np.clip(out, 0.0, 1.0, out=out)
    return Developed(out, norm)
