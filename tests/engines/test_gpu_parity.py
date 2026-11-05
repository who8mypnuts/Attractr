"""Statistical parity between the GPU engines and the CPU reference (skipped when a GPU
engine is unavailable on the test machine)."""

import numpy as np
import pytest

from attractr.core.attractors.registry import registry
from attractr.core.render.engines import selector
from attractr.core.render.pipeline import default_settings
from attractr.core.render.settings import Quality


def _js_divergence(a: np.ndarray, b: np.ndarray) -> float:
    a = a / a.sum()
    b = b / b.sum()
    m = 0.5 * (a + b)
    with np.errstate(divide="ignore", invalid="ignore"):
        ka = np.where(a > 0, a * np.log2(a / m), 0.0).sum()
        kb = np.where(b > 0, b * np.log2(b / m), 0.0).sum()
    return float(0.5 * ka + 0.5 * kb)


@pytest.mark.parametrize("precision", ["fp32", "fp64"])
@pytest.mark.parametrize("engine_id", ["gl_compute", "opencl"])
@pytest.mark.parametrize("aid", ["clifford", "lorenz", "barnsley_fern"])
def test_gpu_matches_cpu(engine_id, aid, precision):
    caps = selector.probe(engine_id)
    if not caps.available:
        pytest.skip(f"{engine_id} unavailable: {caps.notes}")
    if precision == "fp64" and not caps.fp64:
        pytest.skip("no fp64")
    spec = registry.get(aid)
    s = default_settings(spec, Quality(width=128, height=128, points_per_pixel=6, precision=precision))
    gpu = selector.get_engine(engine_id).accumulate(s, spec)
    assert gpu.stats.precision == precision
    cpu = selector.get_engine("cpu").accumulate(s, spec)
    assert abs(gpu.stats.coverage - cpu.stats.coverage) < 0.03
    assert _js_divergence(gpu.count, cpu.count) < 0.05


@pytest.mark.parametrize("aid", ["clifford", "lorenz"])
def test_gl_points_matches_cpu_loosely(aid):
    """The GL 3.3 engine uses nearest-pixel points, so it only matches statistically."""
    caps = selector.probe("gl_points")
    if not caps.available:
        pytest.skip(f"gl_points unavailable: {caps.notes}")
    spec = registry.get(aid)
    s = default_settings(spec, Quality(width=128, height=128, points_per_pixel=12))
    gpu = selector.get_engine("gl_points").accumulate(s, spec)
    cpu = selector.get_engine("cpu").accumulate(s, spec)
    assert gpu.stats.engine == "gl_points"
    assert abs(gpu.stats.coverage - cpu.stats.coverage) < 0.08
    assert _js_divergence(gpu.count, cpu.count) < 0.15
