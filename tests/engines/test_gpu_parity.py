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


def test_tiled_render_is_interleaved_and_uniform(monkeypatch):
    """Tiles are visited in rounds: partials, checkpoints and 'Finish now' are uniform."""
    from dataclasses import replace

    from attractr.core.jobs.cancel import CancelToken
    from attractr.core.render.engines import gl_engines
    from attractr.core.render.pipeline import accumulate

    caps = selector.probe("gl_compute")
    if not caps.available:
        pytest.skip(f"gl_compute unavailable: {caps.notes}")
    monkeypatch.setattr(gl_engines, "TILE_BUDGET_BYTES", 256 * 256 * 4 * 8)  # → 4 tiles of 256²
    spec = registry.get("clifford")
    s = default_settings(spec, Quality(width=512, height=512, points_per_pixel=20, engine="gl_compute"))
    s = replace(s, look=replace(s.look, style="liquid"))
    tok = CancelToken()
    fracs = []

    def sink(res, frac):
        fracs.append(frac)
        if frac > 0.3 and not tok.finishing:
            tok.finish()

    res = accumulate(s, engine="gl_compute", cancel=tok, sink=sink)
    assert res.stats.tiles == 4 and res.stats.finished_early
    assert fracs[:2] == [0.125, 0.25]  # one uniform partial per round
    q = [res.count[:256, :256].sum(), res.count[:256, 256:].sum(), res.count[256:, :256].sum(), res.count[256:, 256:].sum()]
    full = accumulate(s, engine="gl_compute")
    f = [full.count[:256, :256].sum(), full.count[:256, 256:].sum(), full.count[256:, :256].sum(), full.count[256:, 256:].sum()]
    ratios = [a / b for a, b in zip(q, f, strict=True)]
    assert max(ratios) - min(ratios) < 0.05 and 0.25 < ratios[0] < 0.6


@pytest.mark.parametrize("engine_id", ["gl_compute", "opencl"])
def test_escape_kind_gpu_matches_cpu(engine_id):
    caps = selector.probe(engine_id)
    if not caps.available:
        pytest.skip(f"{engine_id} unavailable: {caps.notes}")
    spec = registry.get("buddhabrot")
    s = default_settings(spec, Quality(width=96, height=96, points_per_pixel=60))
    gpu = selector.get_engine(engine_id).accumulate(s, spec)
    cpu = selector.get_engine("cpu").accumulate(s, spec)
    assert abs(gpu.stats.coverage - cpu.stats.coverage) < 0.08
    assert _js_divergence(gpu.count, cpu.count) < 0.08
    assert not selector.get_engine("gl_points").supports(spec) if "gl_points" in selector.engine_ids() else True
