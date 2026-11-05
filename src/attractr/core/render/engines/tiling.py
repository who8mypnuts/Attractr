"""Tiled, interleaved accumulation shared by the GPU engines.

A GPU engine owns device resources and knows how to advance trajectories; everything
about *scheduling* is here and identical for all of them:

* :func:`tile_side` / :func:`tile_layout` — split a buffer into square tiles that fit the
  memory budget;
* :class:`HostPlanes` — the full-resolution host copies of the accumulation planes, the
  per-tile slab transfers and the box-filtered :class:`RenderResult`;
* :class:`TileSchedule` — visits every tile in rounds (uniform progress), adapts the
  steps per pass to a target wall-time, honours *Finish now*, paces partial results and
  reports progress.  The engine plugs in through the small :class:`TileVisitor` protocol.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from attractr.core.jobs.cancel import CancelToken
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.accumulators import Needs
from attractr.core.render.engines.base import PartialPacer
from attractr.core.render.result import Framing, RenderResult, RenderStats
from attractr.core.render.settings import RenderSettings

log = logging.getLogger(__name__)

INTERLEAVE_ROUNDS = 8  # tiled renders visit every tile this many times so progress stays uniform
MIN_FINISH_STEPS = 16  # "Finish now" never leaves a tile with fewer steps than this
MAX_TILE_SIDE = 4096  # larger tiles gain nothing and make allocation / transfer failures likelier
PLANE_NAMES = ("count", "depth", "zmin", "cv")
PLANE_FILL = {"count": 0.0, "depth": 0.0, "zmin": np.inf, "cv": 0.0}


# ── tiles ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Tile:
    """A rectangle of the accumulation buffer (pixel units, origin top-left)."""

    x: int
    y: int
    w: int
    h: int

    @property
    def pixels(self) -> int:
        return self.w * self.h

    @property
    def rows(self) -> slice:
        return slice(self.y, self.y + self.h)

    @property
    def cols(self) -> slice:
        return slice(self.x, self.x + self.w)


def tile_side(budget_bytes: int, bytes_per_pixel: int, buf_w: int, buf_h: int, max_side: int = MAX_TILE_SIDE) -> int:
    """Square tile side (multiple of 256, ≤ ``max_side``) whose planes fit ``budget_bytes``;
    the whole buffer when it fits."""
    side = int(math.sqrt(budget_bytes / max(bytes_per_pixel, 1)))
    side = max(256, min(side, max_side) // 256 * 256)
    return side if max(buf_w, buf_h) > side else max(buf_w, buf_h)


def tile_layout(buf_w: int, buf_h: int, side: int) -> list[Tile]:
    """Row-major tiles covering ``buf_w × buf_h``; edge tiles are clipped."""
    return [Tile(x, y, min(side, buf_w - x), min(side, buf_h - y)) for y in range(0, buf_h, side) for x in range(0, buf_w, side)]


def largest_tile(tiles: list[Tile]) -> tuple[int, int]:
    return max(t.w for t in tiles), max(t.h for t in tiles)


def check_resume_tiling(resume, n_tiles: int) -> None:
    """A legacy *tiled* checkpoint can only continue on the same tile layout.

    Raises:
        ValueError: when ``resume`` holds complete tiles of a different layout.
    """
    if resume is not None and not resume.uniform and resume.tiles != n_tiles:
        raise ValueError(f"checkpoint has {resume.tiles} tiles but this device would use {n_tiles}; resume on the same engine/device")


# ── host planes ─────────────────────────────────────────────────────────────────


def downsample(buf: np.ndarray, ss: int, mode: str) -> np.ndarray:
    """Box-filter a supersampled plane to output resolution **without a full-size temporary**:
    sums are accumulated in float64 inside the reduction while the input stays float32 (a
    10k × 7k A3 buffer is 280 MB; a float64 copy would add 560 MB).  Always returns a new
    array, so results never alias an engine's live buffers."""
    if ss == 1:
        return np.array(buf, dtype=np.float32, copy=True)
    H, W = buf.shape[0] // ss, buf.shape[1] // ss
    blocks = buf[: H * ss, : W * ss].reshape(H, ss, W, ss)
    if mode == "min":
        return blocks.min(axis=(1, 3))
    return blocks.sum(axis=(1, 3), dtype=np.float64).astype(np.float32)


class HostPlanes:
    """Full-resolution host copies of the accumulation planes a look needs.

    ``count`` always exists; ``depth`` (Σ depth), ``zmin`` (nearest depth) and ``cv``
    (Σ colour value) only when :class:`Needs` asks for them (``None`` otherwise).
    """

    def __init__(self, buf_w: int, buf_h: int, needs: Needs) -> None:
        self.needs = needs
        self.count = np.zeros((buf_h, buf_w), dtype=np.float32)
        self.depth = np.zeros((buf_h, buf_w), dtype=np.float32) if needs.depth else None
        self.zmin = np.full((buf_h, buf_w), np.inf, dtype=np.float32) if needs.zmin else None
        self.cv = np.zeros((buf_h, buf_w), dtype=np.float32) if needs.color else None

    def planes(self) -> list[tuple[str, np.ndarray]]:
        """``(name, array)`` for every allocated plane, in :data:`PLANE_NAMES` order."""
        return [(n, a) for n in PLANE_NAMES if (a := getattr(self, n)) is not None]

    def slab(self, name: str, tile: Tile, fresh: bool = False) -> np.ndarray:
        """Contiguous float32 copy of a plane's tile — the fill value when ``fresh``."""
        if fresh:
            return np.full((tile.h, tile.w), PLANE_FILL[name], dtype=np.float32)
        return np.ascontiguousarray(getattr(self, name)[tile.rows, tile.cols], dtype=np.float32)

    def store(self, name: str, tile: Tile, data: np.ndarray) -> None:
        """Write a tile's data (any shape with ``tile.pixels`` elements) into a plane."""
        getattr(self, name)[tile.rows, tile.cols] = data.reshape(tile.h, tile.w)

    def assemble(self, settings: RenderSettings, framing: Framing, stats: RenderStats, ss: int, complete: bool) -> RenderResult:
        """Box-filter the planes to output resolution into a (never aliased) result."""
        return RenderResult(
            settings, downsample(self.count, ss, "sum"), framing, stats,
            downsample(self.depth, ss, "sum") if self.depth is not None else None,
            downsample(self.zmin, ss, "min") if self.zmin is not None else None,
            downsample(self.cv, ss, "sum") if self.cv is not None else None,
            complete,
        )


# ── schedule ────────────────────────────────────────────────────────────────────


class TileVisitor(Protocol):
    """What an engine must provide to :meth:`TileSchedule.run`."""

    def select(self, index: int, tile: Tile, fresh: bool) -> None:
        """Make ``tile`` current: bind its trajectory state and restore its accumulators
        (``fresh`` → initial values, the tile has not been visited yet)."""

    def warm_up(self, index: int, steps: int) -> None:
        """Advance the current tile's trajectories ``steps`` times without plotting."""

    def run_pass(self, index: int, steps: int) -> None:
        """Plot ``steps`` steps of the current tile and wait for the device to finish."""

    def readback(self, index: int, tile: Tile) -> None:
        """Copy the current tile's accumulators into the host planes."""


@dataclass
class _TileProgress:
    """Per-tile bookkeeping of the schedule."""

    steps_done: int = 0
    warmed: bool = False


@dataclass
class TileSchedule:
    """Round-robin schedule over tiles with uniform progress and a soft stop.

    Attributes:
        tiles: the layout (see :func:`tile_layout`).
        total_steps: kernel steps every tile must reach.
        n_traj: trajectories per tile (progress messages and ``iterations_done``).
        warmup_steps: unplotted decorrelation steps on a tile's first visit.
        skip_tiles: leading tiles that are complete in a legacy checkpoint.
        min_steps, max_steps, initial_steps: bounds of the adaptive steps-per-pass.
        target_pass_seconds: wall time one pass aims for.
        partial_base_seconds: minimum interval between partial results.
    """

    tiles: list[Tile]
    total_steps: int
    n_traj: int
    warmup_steps: int
    skip_tiles: int = field(default=0, kw_only=True)
    min_steps: int = field(default=4, kw_only=True)
    max_steps: int = field(default=256, kw_only=True)
    initial_steps: int = field(default=16, kw_only=True)
    target_pass_seconds: float = field(default=0.3, kw_only=True)
    partial_base_seconds: float = field(default=0.5, kw_only=True)

    def __post_init__(self) -> None:
        self.active = [i for i in range(len(self.tiles)) if i >= self.skip_tiles]
        self.rounds = 1 if len(self.active) <= 1 else INTERLEAVE_ROUNDS
        self.progress = {i: _TileProgress() for i in self.active}
        self.finish_at: int | None = None
        self.passes = 0
        self.steps_per_pass = self.initial_steps

    # ── bookkeeping ────────────────────────────────────────────────────────────
    @property
    def steps_all(self) -> int:
        return max(1, self.total_steps * len(self.active))

    @property
    def done_steps_all(self) -> int:
        return sum(p.steps_done for p in self.progress.values())

    @property
    def min_steps_done(self) -> int:
        """Steps every tile has reached — what a uniform partial result contains."""
        return min((p.steps_done for p in self.progress.values()), default=0)

    @property
    def effective_total_steps(self) -> int:
        """Steps actually accumulated per tile (``total_steps`` unless finished early)."""
        return self.finish_at if self.finish_at is not None else self.total_steps

    def _request_finish(self, stats: RenderStats) -> None:
        """Soft stop: every tile ends at the step count the most advanced tile has reached
        (tiles behind catch up within the current round), never below :data:`MIN_FINISH_STEPS`."""
        ahead = max((p.steps_done for p in self.progress.values()), default=0)
        self.finish_at = min(self.total_steps, max(ahead, MIN_FINISH_STEPS))
        stats.finished_early = True
        stats.notes.append(f"Finished early on request at {100 * self.finish_at / self.total_steps:.0f} % of the budget.")

    def _adapt(self, steps: int, seconds: float) -> None:
        """Re-target the steps per pass so one pass takes about ``target_pass_seconds``."""
        if seconds > 0:
            self.steps_per_pass = int(min(max(self.min_steps, steps * self.target_pass_seconds / seconds), self.max_steps))

    # ── driver ─────────────────────────────────────────────────────────────────
    def run(self, visitor: TileVisitor, cancel: CancelToken, tracker: ProgressTracker, stats: RenderStats,
            emit_partial: Callable[[float], None] | None = None) -> None:
        """Accumulate every active tile to :attr:`effective_total_steps`.

        ``emit_partial(fraction)`` is called (after the host planes have been refreshed)
        once per round for multi-tile renders and, for a single tile, whenever the pacer
        allows — the caller builds the partial :class:`RenderResult` from the host planes.
        Raises :class:`Cancelled` on a hard cancel; a soft ``cancel.finish()`` returns early
        with every tile at the same reduced step count.
        """
        pacer = PartialPacer(self.partial_base_seconds)
        per_pass = emit_partial if (emit_partial is not None and len(self.active) == 1) else None
        for rnd in range(self.rounds):
            for index in self.active:
                if self.progress[index].steps_done < self._round_target(rnd) or not self.progress[index].warmed:
                    cancel.check()
                    self._visit(visitor, index, rnd, cancel, tracker, stats, pacer, per_pass)
            if emit_partial is not None and per_pass is None:
                with pacer:
                    emit_partial(self.done_steps_all / self.steps_all)
            if self.finish_at is not None and all(p.steps_done >= self.finish_at for p in self.progress.values()):
                break
        stats.passes = self.passes

    def _visit(self, visitor: TileVisitor, index: int, rnd: int, cancel: CancelToken, tracker: ProgressTracker,
               stats: RenderStats, pacer: PartialPacer, emit_partial: Callable[[float], None] | None) -> None:
        """Bring one tile up to this round's target (warming it up on its first visit)."""
        tile, prog = self.tiles[index], self.progress[index]
        visitor.select(index, tile, fresh=not prog.warmed)
        if not prog.warmed:
            visitor.warm_up(index, self.warmup_steps)
            prog.warmed = True
        while prog.steps_done < self._round_target(rnd):
            cancel.check()
            if cancel.finishing and self.finish_at is None:
                self._request_finish(stats)
                continue  # the target may now be lower than the progress
            steps = min(self.steps_per_pass, self._round_target(rnd) - prog.steps_done, self.max_steps)
            t0 = time.perf_counter()
            visitor.run_pass(index, steps)
            self._adapt(steps, time.perf_counter() - t0)
            prog.steps_done += steps
            self.passes += 1
            self._report(tracker, index, rnd)
            if emit_partial is not None and (pacer.due() or prog.steps_done >= self.total_steps):
                visitor.readback(index, tile)
                with pacer:
                    emit_partial(self.done_steps_all / self.steps_all)
        visitor.readback(index, tile)

    def _round_target(self, rnd: int) -> int:
        """Steps a tile must reach by the end of round ``rnd`` (capped by a soft finish)."""
        target = math.ceil(self.total_steps * (rnd + 1) / self.rounds)
        return min(target, self.finish_at) if self.finish_at is not None else target

    def _report(self, tracker: ProgressTracker, index: int, rnd: int) -> None:
        """Progress message for the tracker."""
        frac = self.done_steps_all / self.steps_all
        tracker.update(0.05 + 0.9 * frac,
                       f"tile {index + 1}/{len(self.tiles)} · round {rnd + 1}/{self.rounds} · pass {self.passes} · "
                       f"{self.done_steps_all * self.n_traj / 1e6:.1f} M points")
