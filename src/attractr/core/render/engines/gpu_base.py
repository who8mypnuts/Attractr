"""Template for the tiled GPU engines (GL compute, OpenCL, GL points).

:meth:`TiledGpuEngine.accumulate` is the one render loop: open the device → compile →
:func:`prepare` the plan → lay out tiles → run the :class:`TileSchedule` with the engine's
:class:`TileVisitor` → assemble the result.  Subclasses only supply the device-specific
pieces through the abstract hooks.
"""

from __future__ import annotations

import logging
import time
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.jobs.cancel import NEVER, CancelToken
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.checkpoint import Checkpoint
from attractr.core.render.engines.base import Engine, PassSink
from attractr.core.render.engines.setup import RenderPlan, prepare
from attractr.core.render.engines.tiling import (
    HostPlanes,
    Tile,
    TileSchedule,
    TileVisitor,
    check_resume_tiling,
    largest_tile,
    tile_layout,
    tile_side,
)
from attractr.core.render.result import RenderResult, RenderStats
from attractr.core.render.settings import RenderSettings
from attractr.core.render.stats import summarize

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PassTuning:
    """Bounds of the adaptive steps-per-pass loop (see :class:`TileSchedule`)."""

    min_steps: int = 4
    max_steps: int = 256
    initial_steps: int = 16
    target_seconds: float = 0.3


@dataclass
class DeviceSession:
    """What :meth:`TiledGpuEngine._open` returns.

    Attributes:
        stats: the render's statistics record, pre-filled with device and precision.
        device: the engine-specific handle (context, compiled kernels, precision …) that the
            engine's visitor understands.
        max_tile: the largest tile side the device allows (texture size limit).
    """

    stats: RenderStats
    device: Any
    max_tile: int


class TiledGpuEngine(Engine):
    """Shared accumulation loop; see the module docstring."""

    tuning = PassTuning()
    tile_budget_bytes: int | None = None  # fixed tile budget (tests / diagnostics); None = from device memory

    # ── hooks ──────────────────────────────────────────────────────────────────
    @abstractmethod
    def _open(self, settings: RenderSettings, spec: AttractorSpec, tracker: ProgressTracker) -> DeviceSession:
        """Acquire the device, compile the kernels for ``spec`` and record device / precision."""

    @abstractmethod
    def _trajectory_count(self, settings: RenderSettings) -> int:
        """Trajectories per tile (rounded to the device's work-group size)."""

    @abstractmethod
    def _budget_bytes(self) -> int:
        """Bytes one render may spend on tile buffers (see ``gl_common.gpu_budget``)."""

    @abstractmethod
    def _bytes_per_pixel(self, plan: RenderPlan) -> int:
        """Device memory per tile pixel for this plan's planes."""

    @abstractmethod
    def _visitor(self, session: DeviceSession, plan: RenderPlan, planes: HostPlanes, n_traj: int,
                 active: list[int], tile_size: tuple[int, int]) -> TileVisitor:
        """The device-side :class:`TileVisitor`; it must also offer ``release()`` and
        ``collect_stats() -> (restarts, plotted)``."""

    # ── template ───────────────────────────────────────────────────────────────
    def accumulate(self, settings: RenderSettings, spec: AttractorSpec, *, sink: PassSink | None = None,
                   cancel: CancelToken = NEVER, tracker: ProgressTracker | None = None,
                   resume: Checkpoint | None = None) -> RenderResult:
        """The shared tiled render loop (see :class:`Engine.accumulate` for the contract)."""
        t_start = time.perf_counter()
        tracker = tracker or ProgressTracker(None)
        t0 = time.perf_counter()
        session = self._open(settings, spec, tracker)
        stats = session.stats
        stats.compile_seconds = time.perf_counter() - t0

        plan = prepare(settings, spec, spec.compiled(settings.quality.integrator), stats, resume, cancel)
        n_traj = self._trajectory_count(settings)
        stats.trajectories = n_traj
        tiles = self._tiles(plan, session.max_tile, stats)
        check_resume_tiling(resume, len(tiles))
        planes = HostPlanes(plan.buf_width, plan.buf_height, plan.needs)
        tuning = self.tuning
        schedule = TileSchedule(tiles, plan.total_steps(n_traj), n_traj, plan.warmup_steps, skip_tiles=plan.resume.skip_tiles,
                                min_steps=tuning.min_steps, max_steps=tuning.max_steps, initial_steps=tuning.initial_steps,
                                target_pass_seconds=tuning.target_seconds)
        t_acc = time.perf_counter()

        def emit_partial(fraction: float) -> None:
            """Hand a uniform partial result (checkpoint merged) to the sink."""
            stats.iterations_done = schedule.min_steps_done * n_traj
            stats.accumulate_seconds = time.perf_counter() - t_acc
            sink(plan.resume.finish(planes.assemble(settings, plan.framing, stats, plan.ss, False)), fraction)

        visitor = self._visitor(session, plan, planes, n_traj, schedule.active, largest_tile(tiles))
        try:
            schedule.run(visitor, cancel, tracker, stats, emit_partial if sink is not None else None)
            stats.restarts, stats.points_plotted = visitor.collect_stats()
        finally:
            visitor.release()

        stats.accumulate_seconds = time.perf_counter() - t_acc
        stats.iterations_done = schedule.effective_total_steps * n_traj  # per-pixel budget: every tile runs it
        result = plan.resume.finish(planes.assemble(settings, plan.framing, stats, plan.ss, True))
        summarize(result, settings.look.percentile)
        stats.elapsed = time.perf_counter() - t_start
        tracker.update(1.0, "accumulated", force=True)
        return result

    def _tiles(self, plan: RenderPlan, max_tile: int, stats: RenderStats) -> list[Tile]:
        """Tile layout within the memory budget, logged so out-of-memory crashes can be diagnosed."""
        budget = self.tile_budget_bytes or self._budget_bytes()
        bpp = self._bytes_per_pixel(plan)
        tiles = tile_layout(plan.buf_width, plan.buf_height, tile_side(budget, bpp, plan.buf_width, plan.buf_height, max_tile))
        stats.tiles = len(tiles)
        tw, th = largest_tile(tiles)
        log.info("%s: %d×%d (ss %d) → %d tile(s) of ≤ %d×%d, GPU budget %d MB, %d MB of tile buffers",
                 self.id, plan.buf_width, plan.buf_height, plan.ss, len(tiles), tw, th, budget // 2**20, tw * th * bpp // 2**20)
        return tiles
