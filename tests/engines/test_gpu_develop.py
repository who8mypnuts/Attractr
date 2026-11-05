"""The GPU develop pass must reproduce the NumPy developer (skipped without OpenGL 4.3)."""

from dataclasses import replace

import numpy as np
import pytest

from attractr.core.render.develop import gpu_develop
from attractr.core.render.develop.developer import develop
from attractr.core.render.framing import Framing
from attractr.core.render.result import RenderResult, RenderStats
from attractr.core.render.settings import Background, Look, RenderSettings


def _synthetic(w=640, h=480, seed=3) -> RenderResult:
    rng = np.random.default_rng(seed)
    count = rng.exponential(20.0, (h, w)).astype(np.float32)
    count[rng.random((h, w)) < 0.3] = 0.0
    depth = (rng.random((h, w), dtype=np.float32) - 0.5) * count
    cv = rng.random((h, w), dtype=np.float32) * count
    return RenderResult(RenderSettings(), count, Framing((0, 0, 0), 1.0), RenderStats(), depth_sum=depth, cv_sum=cv)


@pytest.mark.parametrize("style", ["gas", "dust", "light", "plasma"])
@pytest.mark.parametrize("bg", ["solid", "transparent", "gradient"])
def test_gpu_develop_matches_cpu(style, bg):
    from attractr.core.render.engines import selector

    if not selector.probe("gl_compute").available:
        pytest.skip("no OpenGL 4.3")
    res = _synthetic()
    look = Look(style=style, color_source="speed", depth_cue=0.7, gamma=0.8, contrast=0.3, invert=bg == "gradient",
                background=Background(mode=bg, color=(0.1, 0.0, 0.2), color2=(0.2, 0.2, 0.0)))
    assert gpu_develop.applicable(res, look)
    cpu = develop(res, look, gpu="off")
    gpu = develop(res, look, gpu="force")
    assert gpu.rgba.shape == cpu.rgba.shape
    diff = np.abs(gpu.rgba - cpu.rgba)
    assert diff.max() < 0.02 and (diff > 1 / 255).mean() < 0.01


def test_gpu_develop_not_applicable_falls_back():
    res = _synthetic(64, 64)
    look = Look(style="solid")
    assert not gpu_develop.applicable(res, look)
    assert gpu_develop.develop_gpu(res, look, 1.0, look.gradient.lut(64)) is None
    dev = develop(res, replace(look, style="liquid"), gpu="force")
    assert dev.rgba.shape == (64, 64, 4)
