"""Checkpoint round-trip, soft finish and resume on the CPU engine."""

from dataclasses import replace

import numpy as np

from attractr.core.attractors.registry import registry
from attractr.core.jobs.cancel import CancelToken
from attractr.core.render.checkpoint import Checkpoint
from attractr.core.render.pipeline import accumulate, default_settings
from attractr.core.render.settings import Quality


def _settings():
    spec = registry.get("clifford")
    s = default_settings(spec, Quality(width=96, height=96, points_per_pixel=200, engine="cpu"))
    return replace(s, look=replace(s.look, color_source="speed", style="liquid"))


def test_finish_now_and_resume_reproduce_the_full_budget(tmp_path):
    s = _settings()
    full = accumulate(s, engine="cpu")
    tok = CancelToken()
    saved = {}

    def sink(res, frac):
        if "ck" not in saved and 0.0 < frac < 1.0:
            saved["ck"] = Checkpoint.from_result(res)
            tok.finish()

    part = accumulate(s, engine="cpu", cancel=tok, sink=sink)
    if "ck" not in saved:  # the render was too quick for a mid-way partial on this machine
        return
    assert part.stats.finished_early and part.complete
    ck = saved["ck"]
    path = ck.save(tmp_path / "x.npz")
    ck2 = Checkpoint.load(path)
    assert ck2.uniform and ck2.iterations_done == ck.iterations_done and ck2.framing == ck.framing
    np.testing.assert_array_equal(ck2.count, ck.count)
    res = accumulate(s, engine="cpu", resume=ck2)
    assert res.stats.iterations_done == full.stats.iterations_done
    assert abs(res.count.sum() - full.count.sum()) / full.count.sum() < 0.02
    assert res.zmin is not None and np.isfinite(res.zmin).any()
    assert any("Resumed" in n for n in res.stats.notes)


def test_checkpoint_size_mismatch_is_rejected(tmp_path):
    s = _settings()
    res = accumulate(replace(s, quality=replace(s.quality, points_per_pixel=2)), engine="cpu")
    ck = Checkpoint.from_result(res)
    other = replace(s, quality=replace(s.quality, width=64, points_per_pixel=2))
    try:
        accumulate(other, engine="cpu", resume=ck)
    except ValueError as exc:
        assert "size" in str(exc)
    else:
        raise AssertionError("expected a size mismatch error")


def test_resume_with_different_supersampling_and_splat():
    """Buffers are stored at output resolution, so the remaining budget may use another
    supersampling factor / splat radius; only the pixel size is fixed."""
    s = _settings()
    base = replace(s, quality=replace(s.quality, points_per_pixel=40, supersample=2))
    full = accumulate(base, engine="cpu")
    half = accumulate(replace(base, quality=replace(base.quality, points_per_pixel=20)), engine="cpu")
    ck = Checkpoint.from_result(half)
    resumed = accumulate(replace(base, quality=replace(base.quality, supersample=1, splat_radius=1)), engine="cpu", resume=ck)
    assert resumed.stats.iterations_done == full.stats.iterations_done
    assert abs(resumed.count.sum() - full.count.sum()) / full.count.sum() < 0.03
