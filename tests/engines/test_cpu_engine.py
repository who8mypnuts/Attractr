import numpy as np

from attractr.core.analysis.lyapunov import largest_exponent
from attractr.core.attractors.registry import registry
from attractr.core.render.develop.developer import develop
from attractr.core.render.engines.cpu_numba import CpuEngine
from attractr.core.render.pipeline import default_settings
from attractr.core.render.settings import Quality


def _settings(aid, **kw):
    q = Quality(width=96, height=96, points_per_pixel=4, **kw)
    return default_settings(registry.get(aid), q)


def test_cpu_render_is_deterministic():
    s = _settings("clifford")
    eng = CpuEngine()
    a = eng.accumulate(s, registry.get("clifford"))
    b = eng.accumulate(s, registry.get("clifford"))
    assert np.array_equal(a.count, b.count)
    assert a.stats.coverage > 0.05 and a.stats.restarts == 0


def test_develop_all_styles():
    s = _settings("lorenz")
    res = CpuEngine().accumulate(s, registry.get("lorenz"))
    from dataclasses import replace

    for style in ("gas", "dust", "light", "liquid", "solid", "plasma"):
        look = replace(s.look, style=style)
        # liquid/solid need depth buffers → re-accumulate with that look
        r = res if style in ("gas", "dust", "plasma") else CpuEngine().accumulate(replace(s, look=look), registry.get("lorenz"))
        dev = develop(r, look)
        assert dev.rgba.shape == (96, 96, 4)
        assert np.isfinite(dev.rgba).all() and dev.rgba.max() > 0.1


def test_lyapunov_matches_literature():
    lam = largest_exponent(registry.get("henon"), steps=20000)
    assert abs(lam.exponent - 0.419) < 0.03
    lam = largest_exponent(registry.get("lorenz"), steps=20000)
    assert abs(lam.exponent - 0.906) < 0.1
