"""CPU reference engine (numba, fp64 state, multi-threaded private histograms)."""

from __future__ import annotations

import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import numba
import numpy as np

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.jobs.cancel import NEVER, CancelToken
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.accumulators import needs_for
from attractr.core.render.camera import Camera
from attractr.core.render.checkpoint import Checkpoint
from attractr.core.render.engines.base import Engine, EngineCaps, PassSink, resume_plan
from attractr.core.render.engines.cpu_compile import kernel_module
from attractr.core.render.engines.state import seed_from_points
from attractr.core.render.framing import compute_framing
from attractr.core.render.result import Framing, RenderResult, RenderStats
from attractr.core.render.settings import RenderSettings
from attractr.core.render.stats import summarize

MEMORY_BUDGET_BYTES = int(float(os.environ.get("ATTRACTR_CPU_BUDGET_MB", "1024")) * 1024 * 1024)
TARGET_PASS_SECONDS = 0.35
WARMUP_CHUNK = 100
ACCUM_WARMUP = 64  # steps after seeding from on-attractor points


def splat_kernel(r: int) -> np.ndarray:
    """Soft-disk kernel of radius r, flattened, weights summing to 1 (r = 0 → [1])."""
    if r <= 0:
        return np.ones(1, dtype=np.float64)
    kn = 2 * r + 1
    k = np.zeros((kn, kn), dtype=np.float64)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d2 = dx * dx + dy * dy
            if d2 <= r * r + r:
                k[dy + r, dx + r] = max(0.0, 1.0 - math.sqrt(d2) / (r + 1))
    k /= k.sum()
    return k.ravel()


def apply_lock(framing: Framing, cam: Camera) -> Framing:
    """Replace the fitted sphere by the camera's locked one (animations)."""
    if not cam.locked:
        return framing
    return Framing(tuple(cam.lock_center), float(cam.lock_radius), framing.bbox_min, framing.bbox_max)  # type: ignore[arg-type]


def effective_camera(cam: Camera, framing: Framing) -> Camera:
    """Camera with the 2-D tight-fit (if any) folded into zoom/pan."""
    if framing.fit_zoom == 1.0 and framing.fit_pan == (0.0, 0.0):
        return cam
    # fit_pan is already expressed in final image fractions (it includes fit_zoom)
    return replace(cam, zoom=cam.zoom * framing.fit_zoom,
                   pan_u=cam.pan_u + framing.fit_pan[0],
                   pan_v=cam.pan_v + framing.fit_pan[1])


def escape_config(spec: AttractorSpec) -> np.ndarray:
    """Kernel constants for escape-time systems: region box, bailout², max_iter, min_iter."""
    r = list(spec.region) + [0.0] * (6 - len(spec.region))
    return np.array([*r[:6], float(spec.bailout) ** 2, float(spec.max_iter), float(spec.min_iter)], dtype=np.float64)


def downsample(buf: np.ndarray, ss: int, mode: str) -> np.ndarray:
    if ss == 1:
        return buf
    H, W = buf.shape[0] // ss, buf.shape[1] // ss
    blocks = buf[: H * ss, : W * ss].reshape(H, ss, W, ss)
    return blocks.min(axis=(1, 3)) if mode == "min" else blocks.sum(axis=(1, 3))


class CpuEngine(Engine):
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
        t_start = time.perf_counter()
        q = settings.quality
        look = settings.look
        tracker = tracker or ProgressTracker(None)
        stats = RenderStats(engine=self.id, device=self.probe().device, precision="fp64")

        # ── compile ────────────────────────────────────────────────────────────
        t0 = time.perf_counter()
        cf = spec.compiled(q.integrator)
        needs = needs_for(look)
        mod = kernel_module(cf, (int(needs.depth), int(needs.zmin), int(needs.color), int(q.splat_radius)))
        stats.compile_seconds = time.perf_counter() - t0
        tracker.update(0.0, "compiled")

        params = spec.params_array(settings.param_dict)
        dt = float(q.dt) if q.dt else spec.dt
        substeps = max(1, int(q.substeps))
        warmup = spec.warmup  # framing warm-up (transient discard)
        ss = max(1, int(q.supersample))
        W, H = int(q.width), int(q.height)
        Ws, Hs = W * ss, H * ss

        # ── framing ────────────────────────────────────────────────────────────
        t0 = time.perf_counter()
        framing, sample_pts = compute_framing(spec, params, dt, substeps, warmup, q.seed, settings.camera, W, H)
        stats.framing_seconds = time.perf_counter() - t0
        framing = apply_lock(framing, settings.camera)
        if resume is not None and not resume.uniform:
            raise ValueError("this checkpoint holds complete GPU tiles; resume it with the engine that made it")
        plan = resume_plan(spec.iteration_budget(q.iterations), q.seed, resume)
        framing = plan.framing or framing
        cancel.check()
        cam = effective_camera(settings.camera, framing)
        R = cam.matrix().ravel().astype(np.float64)
        cx, cy, focal = cam.projection_constants(Ws, Hs)
        center = np.asarray(framing.center, dtype=np.float64)
        inv_radius = 1.0 / framing.radius

        # ── buffers & threads ──────────────────────────────────────────────────
        T = self._thread_count(Ws, Hs, needs.buffer_count)
        dummy = np.zeros((1, 1, 1), dtype=np.float32)
        cnt = np.zeros((T, Hs, Ws), dtype=np.float32)
        dep = np.zeros((T, Hs, Ws), dtype=np.float32) if needs.depth else dummy
        zmn = np.full((T, Hs, Ws), np.inf, dtype=np.float32) if needs.zmin else dummy
        cvb = np.zeros((T, Hs, Ws), dtype=np.float32) if needs.color else dummy
        restarts = np.zeros(T, dtype=np.int64)
        plotted = np.zeros(T, dtype=np.float64)

        n_traj = q.trajectories or max(1024, T * 4096)
        # trajectories start on the attractor (framing sample) → short decorrelation warm-up
        st = seed_from_points(n_traj, plan.seed, sample_pts, framing.radius * 1e-2)
        warmup = int(q.warmup) if q.warmup is not None else ACCUM_WARMUP
        ic = np.asarray(spec.ic, dtype=np.float64)
        esc = escape_config(spec)
        kern = splat_kernel(q.splat_radius)
        gap_fill = 1 if (q.gap_fill and spec.plots_continuous) else 0
        stats.trajectories = n_traj
        stats.warmup_steps = warmup
        budget = plan.budget
        stats.iterations_requested = spec.iteration_budget(q.iterations)

        pool = ThreadPoolExecutor(max_workers=T) if T > 1 else None

        def run_slice(t: int, steps: int, t0: float, plot: int) -> None:
            lo, hi = (t * n_traj) // T, ((t + 1) * n_traj) // T
            mod.accumulate(
                t, lo, hi,
                st.X, st.Y, st.Z, st.W, st.SEC, st.RS, st.PU, st.PV, st.PC, st.HAVE, st.DXp, st.DYp, st.DZp,
                params, dt, substeps, steps, t0,
                R, center, inv_radius, cx, cy, focal, cam.perspective, Ws, Hs,
                kern, gap_fill, needs.color_code, plot,
                cnt, dep, zmn, cvb, restarts, plotted, ic, spec.jitter,
                st.SX, st.SY, st.SZ, st.EMODE, st.ECNT, st.ENREP, esc,
            )

        def run(steps: int, t0: float, plot: int) -> None:
            if pool is None:
                run_slice(0, steps, t0, plot)
                return
            futures = [pool.submit(run_slice, t, steps, t0, plot) for t in range(T)]
            for f in futures:
                f.result()

        # ── warm-up (not plotted) ──────────────────────────────────────────────
        t_acc = time.perf_counter()
        done = 0
        while done < warmup:
            cancel.check()
            k = min(WARMUP_CHUNK, warmup - done)
            run(k, float(done), 0)
            done += k
            tracker.update(0.05 * done / max(warmup, 1), "warming up")
        st.reset_history()

        # ── accumulation passes ────────────────────────────────────────────────
        total_steps = math.ceil(budget / n_traj)
        steps_done = 0
        steps_per_pass = 8
        passes = 0
        last_partial = time.perf_counter()
        while steps_done < total_steps:
            cancel.check()
            if cancel.finishing:
                stats.finished_early = True
                stats.notes.append(f"Finished early on request at {100 * steps_done / total_steps:.0f} % of the budget.")
                break
            k = min(steps_per_pass, total_steps - steps_done)
            tp = time.perf_counter()
            run(k, float(done + steps_done), 1)
            dtp = time.perf_counter() - tp
            steps_done += k
            passes += 1
            if dtp > 0:
                steps_per_pass = int(min(max(4, k * TARGET_PASS_SECONDS / dtp), 4096))
            frac = steps_done / total_steps
            tracker.update(0.05 + 0.93 * frac, f"pass {passes} · {steps_done * n_traj / 1e6:.1f} M points")
            if sink is not None and (time.perf_counter() - last_partial > 1.0 or steps_done >= total_steps):
                last_partial = time.perf_counter()
                stats.iterations_done = steps_done * n_traj
                stats.accumulate_seconds = time.perf_counter() - t_acc
                partial = self._assemble(settings, framing, stats, cnt, dep, zmn, cvb, needs, ss, complete=False)
                sink(plan.finish(partial), frac)

        if pool is not None:
            pool.shutdown(wait=True)
        stats.accumulate_seconds = time.perf_counter() - t_acc
        stats.iterations_done = steps_done * n_traj
        stats.passes = passes
        stats.restarts = int(restarts.sum())
        stats.points_plotted = float(plotted.sum())
        result = plan.finish(self._assemble(settings, framing, stats, cnt, dep, zmn, cvb, needs, ss, complete=True))
        summarize(result, look.percentile)
        stats.elapsed = time.perf_counter() - t_start
        tracker.update(1.0, "accumulated", force=True)
        return result

    # ── helpers ────────────────────────────────────────────────────────────────
    def _thread_count(self, Ws: int, Hs: int, nbuf: int) -> int:
        per_thread = Ws * Hs * 4 * nbuf
        t = numba.get_num_threads()
        by_mem = max(1, MEMORY_BUDGET_BYTES // max(per_thread, 1))
        return int(max(1, min(t, by_mem)))

    @staticmethod
    def _assemble(settings, framing, stats, cnt, dep, zmn, cvb, needs, ss, complete) -> RenderResult:
        count = downsample(cnt.sum(axis=0, dtype=np.float64), ss, "sum").astype(np.float32)
        depth = downsample(dep.sum(axis=0, dtype=np.float64), ss, "sum").astype(np.float32) if needs.depth else None
        zmin = downsample(zmn.min(axis=0), ss, "min").astype(np.float32) if needs.zmin else None
        cv = downsample(cvb.sum(axis=0, dtype=np.float64), ss, "sum").astype(np.float32) if needs.color else None
        return RenderResult(settings, count, framing, stats, depth, zmin, cv, complete)
