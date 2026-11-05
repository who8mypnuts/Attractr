"""Tile layout, host planes and the interleaved schedule (pure Python, no GPU)."""

import numpy as np
import pytest

from attractr.core.jobs.cancel import Cancelled, CancelToken
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.accumulators import needs_for
from attractr.core.render.engines.tiling import (
    INTERLEAVE_ROUNDS,
    MIN_FINISH_STEPS,
    HostPlanes,
    Tile,
    TileSchedule,
    check_resume_tiling,
    downsample,
    largest_tile,
    tile_layout,
    tile_side,
)
from attractr.core.render.result import Framing, RenderStats
from attractr.core.render.settings import Look, RenderSettings


def test_tile_side_and_layout():
    assert tile_side(256 * 256 * 8, 8, 1000, 700) == 256  # budget → 256² tiles
    assert tile_side(10**12, 8, 1000, 700) == 1000  # fits → one tile of the larger side
    assert tile_side(10**12, 8, 1000, 700, max_side=512) == 512
    tiles = tile_layout(500, 380, 256)
    assert tiles == [Tile(0, 0, 256, 256), Tile(256, 0, 244, 256), Tile(0, 256, 256, 124), Tile(256, 256, 244, 124)]
    assert largest_tile(tiles) == (256, 256) and tiles[3].pixels == 244 * 124


def test_downsample_never_aliases_and_keeps_sums():
    buf = np.arange(16, dtype=np.float32).reshape(4, 4)
    same = downsample(buf, 1, "sum")
    assert same is not buf and np.array_equal(same, buf)
    summed = downsample(buf, 2, "sum")
    assert summed.shape == (2, 2) and summed.sum() == buf.sum() and summed.dtype == np.float32
    assert downsample(buf, 2, "min")[0, 0] == 0.0


def test_host_planes_slabs_and_assemble():
    needs = needs_for(Look(style="liquid", color_source="speed"))
    planes = HostPlanes(8, 6, needs)
    assert [n for n, _ in planes.planes()] == ["count", "depth", "zmin", "cv"]
    tile = Tile(4, 2, 4, 4)
    assert np.isinf(planes.slab("zmin", tile, fresh=True)).all() and planes.slab("count", tile, fresh=True).sum() == 0
    planes.store("count", tile, np.ones(16, dtype=np.float32))
    assert planes.count.sum() == 16 and planes.slab("count", tile).sum() == 16
    res = planes.assemble(RenderSettings(), Framing((0, 0, 0), 1.0), RenderStats(), 2, complete=False)
    assert res.count.shape == (3, 4) and res.count.sum() == 16 and res.count is not planes.count and not res.complete


class _FakeVisitor:
    """Records the calls a schedule makes; every pass takes ``seconds``."""

    def __init__(self, seconds: float = 0.0) -> None:
        self.calls: list[tuple] = []
        self.seconds = seconds

    def select(self, index, tile, fresh):
        self.calls.append(("select", index, fresh))

    def warm_up(self, index, steps):
        self.calls.append(("warm", index, steps))

    def run_pass(self, index, steps):
        self.calls.append(("pass", index, steps))

    def readback(self, index, tile):
        self.calls.append(("read", index))


def _schedule(tiles, total=100, rounds_expected=None):
    return TileSchedule(tiles, total, n_traj=10, warmup_steps=5, max_steps=40, initial_steps=40)


def test_schedule_interleaves_rounds_uniformly():
    tiles = tile_layout(512, 256, 256)
    sched = _schedule(tiles)
    vis = _FakeVisitor()
    fracs = []
    sched.run(vis, CancelToken(), ProgressTracker(None), RenderStats(), fracs.append)
    assert sched.rounds == INTERLEAVE_ROUNDS
    assert [p.steps_done for p in sched.progress.values()] == [100, 100]
    assert len(fracs) == INTERLEAVE_ROUNDS and fracs[-1] == pytest.approx(1.0)
    # each tile is warmed exactly once, on its first (fresh) visit
    assert [c for c in vis.calls if c[0] == "warm"] == [("warm", 0, 5), ("warm", 1, 5)]
    assert [c for c in vis.calls if c[0] == "select"][:2] == [("select", 0, True), ("select", 1, True)]
    assert sched.effective_total_steps == 100


def test_schedule_soft_finish_is_uniform_and_hard_cancel_raises():
    tiles = tile_layout(512, 256, 256)
    sched = _schedule(tiles, total=1000)
    tok = CancelToken()

    class Finisher(_FakeVisitor):
        def run_pass(self, index, steps):
            super().run_pass(index, steps)
            if len([c for c in self.calls if c[0] == "pass"]) == 5:
                tok.finish()

    stats = RenderStats()
    sched.run(Finisher(), tok, ProgressTracker(None), stats)
    done = [p.steps_done for p in sched.progress.values()]
    assert stats.finished_early and sched.finish_at is not None
    assert max(done) == min(done) >= MIN_FINISH_STEPS  # uniform: the tile behind catches up
    assert sched.effective_total_steps == sched.finish_at
    tok2 = CancelToken()
    tok2.cancel()
    with pytest.raises(Cancelled):
        _schedule(tiles).run(_FakeVisitor(), tok2, ProgressTracker(None), RenderStats())


def test_single_tile_emits_partials_per_pass():
    sched = _schedule(tile_layout(256, 256, 256), total=80)
    fracs = []
    sched.run(_FakeVisitor(), CancelToken(), ProgressTracker(None), RenderStats(), fracs.append)
    assert sched.rounds == 1 and fracs and fracs[-1] == pytest.approx(1.0)


def test_check_resume_tiling():
    class Ck:
        uniform, tiles = False, 3

    with pytest.raises(ValueError):
        check_resume_tiling(Ck(), 4)
    check_resume_tiling(Ck(), 3)
    check_resume_tiling(None, 4)
