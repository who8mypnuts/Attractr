"""CPU reference engine (numba, fp64 state, multi-threaded private histograms)."""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor

import numba
import numpy as np

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.jobs.cancel import NEVER, CancelToken
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.checkpoint import Checkpoint
from attractr.core.render.engines.base import Engine, EngineCaps, PassSink
from attractr.core.render.engines.cpu_compile import kernel_module
from attractr.core.render.engines.setup import RenderPlan, prepare, splat_kernel
from attractr.core.render.engines.state import TrajectoryState, seed_from_points
from attractr.core.render.engines.tiling import Tile, TileSchedule, downsample
from attractr.core.render.result import RenderResult, RenderStats
from attractr.core.render.settings import RenderSettings
from attractr.core.render.stats import summarize

MEMORY_BUDGET_BYTES = int(float(os.environ.get("ATTRACTR_CPU_BUDGET_MB", "1024")) * 1024 * 1024)
TARGET_PASS_SECONDS = 0.35
WARMUP_CHUNK = 100
MIN_STEPS_PER_PASS, MAX_STEPS_PER_PASS, INITIAL_STEPS_PER_PASS = 4, 4096, 8


def cpu_budget() -> int:
    """Bytes the per-thread accumulation buffers may take: the env override, else a quarter of
    the currently available RAM (so an A3 render never pushes the machine into swap)."""
    if os.environ.get("ATTRACTR_CPU_BUDGET_MB"):
        return MEMORY_BUDGET_BYTES
    try:
        import psutil

        avail = int(psutil.virtual_memory().available)
    except Exception:  # noqa: BLE001 — psutil missing or unsupported platform
        return MEMORY_BUDGET_BYTES
    return int(min(max(avail * 0.25, 512 * 1024 * 1024), 8 * 1024**3))


def _sum_slices(buf: np.ndarray) -> np.ndarray:
    """Σ over the per-thread axis with one full-size float32 result (no float64 temporary)."""
    if buf.shape[0] == 1:
        return buf[0]
    out = buf[0].copy()
    for t in range(1, buf.shape[0]):
        np.add(out, buf[t], out=out)
    return out


class _ThreadBuffers:
    """Per-thread accumulation planes ``[T, H, W]`` (private histograms, summed at the end).
    Planes the look does not need are 1×1×1 dummies the kernel never touches."""

    def __init__(self, threads: int, buf_w: int, buf_h: int, needs) -> None:
        self.needs = needs
        dummy = np.zeros((1, 1, 1), dtype=np.float32)
        shape = (threads, buf_h, buf_w)
        self.cnt = np.zeros(shape, dtype=np.float32)
        self.dep = np.zeros(shape, dtype=np.float32) if needs.depth else dummy
        self.zmn = np.full(shape, np.inf, dtype=np.float32) if needs.zmin else dummy
        self.cvb = np.zeros(shape, dtype=np.float32) if needs.color else dummy
        self.restarts = np.zeros(threads, dtype=np.int64)
        self.plotted = np.zeros(threads, dtype=np.float64)

    def assemble(self, plan: RenderPlan, stats: RenderStats, complete: bool) -> RenderResult:
        """Sum the thread slices (float32 — exact up to 2²⁴ points per pixel) and box-filter."""
        needs, ss = self.needs, plan.ss
        return RenderResult(
            plan.settings, downsample(_sum_slices(self.cnt), ss, "sum"), plan.framing, stats,
            downsample(_sum_slices(self.dep), ss, "sum") if needs.depth else None,
            downsample(self.zmn.min(axis=0), ss, "min").astype(np.float32) if needs.zmin else None,
            downsample(_sum_slices(self.cvb), ss, "sum") if needs.color else None,
            complete,
        )


class CpuEngine(Engine):
    """Reference engine: numba kernels, float64 state, one private histogram per thread."""
    id = "cpu"
    name = "CPU (numba)"

    def probe(self) -> EngineCaps:
        return EngineCaps(self.id, self.name, device=f"{numba.get_num_threads()} threads", fp64=True)

    # ── main entry ─────────────────────────────────────────────────────────────
    def accumulate(
        self,
        settings: RenderSettings,
        spec: AttractorSpec,
        *,
        sink: PassSink | None = None,
        cancel: CancelToken = NEVER,
        tracker: ProgressTracker | None = None,
        resume: Checkpoint | None = None,
    ) -> RenderResult:
        """Accumulate ``settings`` on the CPU (see :class:`Engine.accumulate`); tiled checkpoints are refused."""
        if resume is not None and not resume.uniform:
            raise ValueError("this checkpoint holds complete GPU tiles; resume it with the engine that made it")
        t_start = time.perf_counter()
        q = settings.quality
        tracker = tracker or ProgressTracker(None)
        stats = RenderStats(engine=self.id, device=self.probe().device, precision="fp64")

        t0 = time.perf_counter()
        cf = spec.compiled(q.integrator)
        plan = prepare(settings, spec, cf, stats, resume, cancel)
        needs = plan.needs
        mod = kernel_module(cf, (int(needs.depth), int(needs.zmin), int(needs.color), int(q.splat_radius)))
        stats.compile_seconds = time.perf_counter() - t0
        tracker.update(0.0, "compiled")

        threads = self._thread_count(plan.buf_width, plan.buf_height, needs.buffer_count)
        n_traj = q.trajectories or max(1024, threads * 4096)
        stats.trajectories = n_traj
        run = _CpuAccumulation(mod, plan, n_traj, threads)
        # the whole buffer is one "tile": the schedule supplies pass adaptation, soft finish and pacing
        schedule = TileSchedule([Tile(0, 0, plan.buf_width, plan.buf_height)], plan.total_steps(n_traj), n_traj, plan.warmup_steps,
                                min_steps=MIN_STEPS_PER_PASS, max_steps=MAX_STEPS_PER_PASS, initial_steps=INITIAL_STEPS_PER_PASS,
                                target_pass_seconds=TARGET_PASS_SECONDS, partial_base_seconds=1.0)
        t_acc = time.perf_counter()

        def emit_partial(fraction: float) -> None:
            stats.iterations_done = schedule.min_steps_done * n_traj
            stats.accumulate_seconds = time.perf_counter() - t_acc
            sink(plan.resume.finish(run.bufs.assemble(plan, stats, complete=False)), fraction)

        try:
            schedule.run(run, cancel, tracker, stats, emit_partial if sink is not None else None)
        finally:
            run.close()

        stats.accumulate_seconds = time.perf_counter() - t_acc
        stats.iterations_done = schedule.effective_total_steps * n_traj
        stats.restarts = int(run.bufs.restarts.sum())
        stats.points_plotted = float(run.bufs.plotted.sum())
        result = plan.resume.finish(run.bufs.assemble(plan, stats, complete=True))
        summarize(result, settings.look.percentile)
        stats.elapsed = time.perf_counter() - t_start
        tracker.update(1.0, "accumulated", force=True)
        return result

    # ── helpers ────────────────────────────────────────────────────────────────
    @staticmethod
    def _thread_count(buf_w: int, buf_h: int, planes: int) -> int:
        """Threads such that the private histograms stay within :func:`cpu_budget`."""
        per_thread = buf_w * buf_h * 4 * planes
        by_mem = max(1, cpu_budget() // max(per_thread, 1))
        return int(max(1, min(numba.get_num_threads(), by_mem)))


class _CpuAccumulation:
    """:class:`TileVisitor` of the CPU engine (one tile = the whole buffer): trajectories,
    per-thread buffers and the worker pool that runs the generated ``accumulate`` kernel
    over disjoint trajectory slices."""

    def __init__(self, mod, plan: RenderPlan, n_traj: int, threads: int) -> None:
        self.mod, self.plan, self.n_traj, self.threads = mod, plan, n_traj, threads
        self.bufs = _ThreadBuffers(threads, plan.buf_width, plan.buf_height, plan.needs)
        # trajectories start on the attractor (framing sample) → short decorrelation warm-up
        self.st: TrajectoryState = seed_from_points(n_traj, plan.resume.seed, plan.sample_pts, plan.framing.radius * 1e-2)
        self.pool = ThreadPoolExecutor(max_workers=threads) if threads > 1 else None
        self.t_base = 0.0  # iteration index continues across warm-up and passes (t_step)
        self.kern = splat_kernel(plan.quality.splat_radius)
        self.rotation = plan.rotation.ravel().astype(np.float64)
        self.center = np.asarray(plan.framing.center, dtype=np.float64)
        self.ic = np.asarray(plan.spec.ic, dtype=np.float64)

    # ── TileVisitor ────────────────────────────────────────────────────────────
    def select(self, index: int, tile: Tile, fresh: bool) -> None:
        """Nothing to bind: the buffers are host arrays and there is a single tile."""

    def warm_up(self, index: int, steps: int) -> None:
        """Unplotted decorrelation steps, then forget the previous points so no gap-fill
        segment crosses the warm-up boundary."""
        while steps > 0:
            k = min(WARMUP_CHUNK, steps)
            self._run(k, plot=0)
            steps -= k
        self.st.reset_history()

    def run_pass(self, index: int, steps: int) -> None:
        """Plot ``steps`` steps on every thread (synchronous)."""
        self._run(steps, plot=1)

    def readback(self, index: int, tile: Tile) -> None:
        """Nothing to copy: the accumulation buffers already live on the host."""

    def close(self) -> None:
        """Shut the worker pool down."""
        if self.pool is not None:
            self.pool.shutdown(wait=True)

    # ── kernel launches ────────────────────────────────────────────────────────
    def _run(self, steps: int, plot: int) -> None:
        """Advance every trajectory ``steps`` steps on all threads (``plot`` 0 = warm-up, 1 = accumulate)."""
        if self.pool is None:
            self._slice(0, steps, plot)
        else:
            for f in [self.pool.submit(self._slice, t, steps, plot) for t in range(self.threads)]:
                f.result()
        self.t_base += steps * self.plan.substeps  # the kernel advances t_step once per sub-step

    def _slice(self, t: int, steps: int, plot: int) -> None:
        """Run the kernel for thread ``t``'s trajectory slice."""
        p, st, b, n = self.plan, self.st, self.bufs, self.n_traj
        lo, hi = (t * n) // self.threads, ((t + 1) * n) // self.threads
        self.mod.accumulate(
            t, lo, hi,
            st.X, st.Y, st.Z, st.W, st.SEC, st.RS, st.PU, st.PV, st.PC, st.HAVE, st.DXp, st.DYp, st.DZp,
            p.params, p.dt, p.substeps, steps, self.t_base,
            self.rotation, self.center, 1.0 / p.framing.radius, p.cx, p.cy, p.focal, p.camera.perspective, p.buf_width, p.buf_height,
            self.kern, int(p.gap_fill), p.needs.color_code, plot,
            b.cnt, b.dep, b.zmn, b.cvb, b.restarts, b.plotted, self.ic, p.spec.jitter,
            st.SX, st.SY, st.SZ, st.EMODE, st.ECNT, st.ENREP, p.escape,
        )
