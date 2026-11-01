"""OpenCL engine (``opencl``): the GL compute algorithm on any OpenCL 1.2 device — GPUs
from every vendor, and CPUs through POCL / Intel runtimes.  Ships by default; degrades to
"unavailable" when no platform is present."""

from __future__ import annotations

import logging
import math
import os
import time

import numpy as np

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.formula.codegen_glsl import generate_gpu_source
from attractr.core.jobs.cancel import NEVER, CancelToken
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.accumulators import color_value_range, needs_for
from attractr.core.render.engines import selector
from attractr.core.render.engines.base import Engine, EngineCaps, PassSink
from attractr.core.render.engines.cpu_numba import apply_lock, downsample, effective_camera, splat_kernel
from attractr.core.render.engines.gl_common import read_shader
from attractr.core.render.engines.state import seed_from_points
from attractr.core.render.framing import compute_framing
from attractr.core.render.result import RenderResult, RenderStats
from attractr.core.render.settings import RenderSettings
from attractr.core.render.stats import summarize

log = logging.getLogger(__name__)

MAX_STEPS_PER_PASS = 256
TARGET_PASS_SECONDS = 0.3
TILE_BUDGET_BYTES = int(float(os.environ.get("ATTRACTR_GPU_BUDGET_MB", "768")) * 1024 * 1024)
ACCUM_WARMUP = 64

PARAMS_DTYPE = np.dtype([
    ("steps", "i4"), ("substeps", "i4"), ("splat_r", "i4"), ("gap_fill", "i4"), ("color_code", "i4"),
    ("want_depth", "i4"), ("want_zmin", "i4"), ("want_color", "i4"), ("do_plot", "i4"),
    ("w", "i4"), ("h", "i4"), ("n", "i4"),
    ("dt", "f4"), ("inv_radius", "f4"), ("cx", "f4"), ("cy", "f4"), ("focal", "f4"), ("persp", "f4"),
    ("jitter", "f4"), ("inv_n", "f4"), ("cv_lo", "f4"), ("cv_inv_range", "f4"),
    ("R", "f4", (9,)), ("center", "f4", (3,)), ("ic", "f4", (3,)),
])


def _pick_device():
    import pyopencl as cl

    best = None
    for plat in cl.get_platforms():
        for dev in plat.get_devices():
            score = (2 if dev.type & cl.device_type.GPU else 1, dev.max_compute_units)
            if best is None or score > best[0]:
                best = (score, dev)
    if best is None:
        raise RuntimeError("no OpenCL devices found")
    return best[1]


class OpenCLEngine(Engine):
    id = "opencl"
    name = "OpenCL"

    def __init__(self) -> None:
        self._ctx = None
        self._queue = None
        self._device = None
        self._programs: dict[str, tuple] = {}
        self._prelude = read_shader("prelude.cl")
        self._kernel_src = read_shader("iterate.cl")

    def _ensure(self):
        if self._ctx is None:
            import pyopencl as cl

            self._device = _pick_device()
            self._ctx = cl.Context([self._device])
            self._queue = cl.CommandQueue(self._ctx)
        return self._ctx, self._queue

    def probe(self) -> EngineCaps:
        try:
            import pyopencl as cl  # noqa: F401

            ctx, queue = self._ensure()
            dev = self._device
            fp64 = "cl_khr_fp64" in dev.extensions
            caps = EngineCaps(self.id, self.name, device=f"{dev.name.strip()} ({dev.platform.name.strip()})",
                              available=True, fp64=fp64, compute=True, max_size=16384,
                              notes=[f"{dev.max_compute_units} compute units, {dev.global_mem_size // (1024 * 1024)} MB"])
            return caps
        except Exception as exc:  # noqa: BLE001
            return EngineCaps(self.id, self.name, available=False, notes=[f"OpenCL unavailable: {exc}"])

    def _program(self, cf, integrator: str):
        import pyopencl as cl

        key = cf.source_hash
        if key in self._programs:
            return self._programs[key]
        gen = generate_gpu_source(cf.program, cf.analysis, integrator if cf.kind == "flow" else "rk4", "opencl")
        src = self._kernel_src.replace("//__PRELUDE__", self._prelude).replace("//__STEP__", gen)
        try:
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                prog = cl.Program(self._ctx, src).build(options=["-cl-fast-relaxed-math", "-w"])
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"OpenCL kernel build failed: {exc}") from exc
        kernels = (cl.Kernel(prog, "iterate"), cl.Kernel(prog, "merge"))
        self._programs[key] = kernels
        return kernels

    # ── accumulate ─────────────────────────────────────────────────────────────
    def accumulate(self, settings: RenderSettings, spec: AttractorSpec, *, sink: PassSink | None = None,
                   cancel: CancelToken = NEVER, tracker: ProgressTracker | None = None) -> RenderResult:
        import pyopencl as cl

        t_start = time.perf_counter()
        tracker = tracker or ProgressTracker(None)
        q, look = settings.quality, settings.look
        ctx, queue = self._ensure()
        stats = RenderStats(engine=self.id, device=self._device.name.strip(), precision="fp32")

        t0 = time.perf_counter()
        cf = spec.compiled(q.integrator)
        k_iterate, k_merge = self._program(cf, q.integrator)
        stats.compile_seconds = time.perf_counter() - t0

        params = spec.params_array(settings.param_dict)
        dt = float(q.dt) if q.dt else spec.dt
        substeps = max(1, int(q.substeps))
        ss = max(1, int(q.supersample))
        W, H = int(q.width), int(q.height)
        Ws, Hs = W * ss, H * ss
        t0 = time.perf_counter()
        framing, sample_pts = compute_framing(spec, params, dt, substeps, spec.warmup, q.seed, settings.camera, W, H)
        stats.framing_seconds = time.perf_counter() - t0
        framing = apply_lock(framing, settings.camera)
        cancel.check()
        cam = effective_camera(settings.camera, framing)
        R = cam.matrix().astype(np.float32).ravel()
        cx, cy, focal = cam.projection_constants(Ws, Hs)
        needs = needs_for(look)

        n_traj = q.trajectories or 65536
        n_traj = int(math.ceil(n_traj / 128) * 128)
        stats.trajectories = n_traj
        stats.iterations_requested = q.iterations
        stats.warmup_steps = int(q.warmup) if q.warmup is not None else ACCUM_WARMUP

        tile = self._tile_size(Ws, Hs, needs.buffer_count)
        tiles = [(tx, ty, min(tile, Ws - tx), min(tile, Hs - ty)) for ty in range(0, Hs, tile) for tx in range(0, Ws, tile)]
        stats.tiles = len(tiles)
        count_full = np.zeros((Hs, Ws), dtype=np.float32)
        depth_full = np.zeros((Hs, Ws), dtype=np.float32) if needs.depth else None
        zmin_full = np.full((Hs, Ws), np.inf, dtype=np.float32) if needs.zmin else None
        cv_full = np.zeros((Hs, Ws), dtype=np.float32) if needs.color else None

        mf = cl.mem_flags
        kern = np.zeros(81, dtype=np.float32)
        kk = splat_kernel(q.splat_radius).astype(np.float32)
        kern[: kk.size] = kk
        b_kern = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=kern)
        pbuf = np.zeros(max(1, params.size), dtype=np.float32)
        pbuf[: params.size] = params
        b_p = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=pbuf)

        P = np.zeros(1, dtype=PARAMS_DTYPE)
        P["substeps"] = substeps
        P["splat_r"] = int(q.splat_radius)
        P["gap_fill"] = 1 if (q.gap_fill and spec.is_flow) else 0
        P["color_code"] = needs.color_code
        P["want_depth"], P["want_zmin"], P["want_color"] = int(needs.depth), int(needs.zmin), int(needs.color)
        P["n"] = n_traj
        P["dt"] = dt
        P["inv_radius"] = 1.0 / framing.radius
        P["focal"] = focal
        P["persp"] = cam.perspective
        P["jitter"] = spec.jitter
        P["inv_n"] = 1.0 / n_traj
        cv_lo, cv_hi = color_value_range(needs.color_code, sample_pts, framing, cam.matrix(), params, cf.color_fn) if needs.color else (-4.0, 4.0)
        P["cv_lo"], P["cv_inv_range"] = cv_lo, 1.0 / (cv_hi - cv_lo)
        P["R"] = R
        P["center"] = np.asarray(framing.center, dtype=np.float32)
        P["ic"] = np.asarray(spec.ic, dtype=np.float32)

        total_steps = max(1, math.ceil(q.iterations / n_traj))
        steps_all = total_steps * len(tiles)
        done_all = 0
        passes = 0
        restarts_total = 0
        plotted_total = 0.0
        steps_per_pass = 16
        t_acc = time.perf_counter()
        last_partial = time.perf_counter()

        for ti, (tx, ty, tw, th) in enumerate(tiles):
            cancel.check()
            st = seed_from_points(n_traj, q.seed, sample_pts, framing.radius * 1e-2)
            state = np.zeros((n_traj, 4), dtype=np.float32)
            state[:, 0], state[:, 1], state[:, 2] = st.X, st.Y, st.Z
            npix = tw * th
            b_state = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=state)
            b_rng = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=st.RS.astype(np.uint32))
            zeros4 = np.zeros((n_traj, 4), dtype=np.float32)
            b_prev = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=zeros4)
            b_prevd = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=zeros4)
            b_stats = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=np.zeros(4, dtype=np.uint32))
            u_zero = np.zeros(npix, dtype=np.uint32)
            u_inf = np.full(npix, 0xFFFFFFFF, dtype=np.uint32)
            f_zero = np.zeros(npix, dtype=np.float32)
            f_inf = np.full(npix, np.inf, dtype=np.float32)
            b_cnt = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=u_zero)
            b_dep = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=u_zero)
            b_zmn = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=u_inf)
            b_cvb = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=u_zero)
            a_cnt = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=f_zero)
            a_dep = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=f_zero)
            a_zmn = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=f_inf)
            a_cv = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=f_zero)
            P["w"], P["h"] = tw, th
            P["cx"], P["cy"] = cx - tx, cy - ty
            b_P = cl.Buffer(ctx, mf.READ_ONLY, size=P.nbytes)

            def dispatch(steps: int, plot: int) -> None:
                P["steps"], P["do_plot"] = steps, plot
                cl.enqueue_copy(queue, b_P, P)
                k_iterate(queue, (n_traj,), (128,), b_state, b_rng, b_prev, b_prevd, b_stats,
                          b_cnt, b_dep, b_zmn, b_cvb, b_P, b_kern, b_p)

            def merge() -> None:
                gsz = int(math.ceil(npix / 256) * 256)
                k_merge(queue, (gsz,), (256,), b_cnt, b_dep, b_zmn, b_cvb, a_cnt, a_dep, a_zmn, a_cv,
                        np.int32(npix), np.int32(needs.depth), np.int32(needs.zmin), np.int32(needs.color),
                        np.float32(cv_lo), np.float32(cv_hi - cv_lo))

            def readback() -> None:
                def rd(buf):
                    out = np.empty(npix, dtype=np.float32)
                    cl.enqueue_copy(queue, out, buf)
                    return out.reshape(th, tw)

                queue.finish()
                count_full[ty : ty + th, tx : tx + tw] = rd(a_cnt)
                if depth_full is not None:
                    depth_full[ty : ty + th, tx : tx + tw] = rd(a_dep)
                if zmin_full is not None:
                    zmin_full[ty : ty + th, tx : tx + tw] = rd(a_zmn)
                if cv_full is not None:
                    cv_full[ty : ty + th, tx : tx + tw] = rd(a_cv)

            try:
                warm = stats.warmup_steps
                while warm > 0:
                    k = min(warm, MAX_STEPS_PER_PASS)
                    dispatch(k, 0)
                    warm -= k
                cl.enqueue_copy(queue, b_prev, zeros4)
                steps_done = 0
                while steps_done < total_steps:
                    cancel.check()
                    k = min(steps_per_pass, total_steps - steps_done, MAX_STEPS_PER_PASS)
                    tp = time.perf_counter()
                    dispatch(k, 1)
                    merge()
                    queue.finish()
                    dtp = time.perf_counter() - tp
                    steps_done += k
                    done_all += k
                    passes += 1
                    if dtp > 0:
                        steps_per_pass = int(min(max(4, k * TARGET_PASS_SECONDS / dtp), MAX_STEPS_PER_PASS))
                    frac = done_all / steps_all
                    tracker.update(0.05 + 0.9 * frac, f"tile {ti + 1}/{len(tiles)} · pass {passes} · {done_all * n_traj / 1e6:.1f} M points")
                    if sink is not None and len(tiles) == 1 and (time.perf_counter() - last_partial > 0.5 or steps_done >= total_steps):
                        last_partial = time.perf_counter()
                        readback()
                        sink(self._assemble(settings, framing, stats, count_full, depth_full, zmin_full, cv_full, ss, False), frac)
                readback()
                s = np.zeros(4, dtype=np.uint32)
                cl.enqueue_copy(queue, s, b_stats)
                queue.finish()
                restarts_total += int(s[0])
                plotted_total += (int(s[2]) * 4294967296.0 + int(s[1])) / 16.0
            finally:
                for b in (b_state, b_rng, b_prev, b_prevd, b_stats, b_cnt, b_dep, b_zmn, b_cvb, a_cnt, a_dep, a_zmn, a_cv, b_P):
                    b.release()
        b_kern.release()
        b_p.release()

        stats.accumulate_seconds = time.perf_counter() - t_acc
        stats.iterations_done = total_steps * n_traj
        stats.passes = passes
        stats.restarts = restarts_total
        stats.points_plotted = plotted_total
        result = self._assemble(settings, framing, stats, count_full, depth_full, zmin_full, cv_full, ss, True)
        summarize(result, look.percentile)
        stats.elapsed = time.perf_counter() - t_start
        tracker.update(1.0, "accumulated", force=True)
        return result

    @staticmethod
    def _tile_size(Ws: int, Hs: int, nbuf: int) -> int:
        side = int(math.sqrt(TILE_BUDGET_BYTES / (4 * (nbuf + 4))))
        side = max(256, min(side, 8192) // 256 * 256)
        return side if max(Ws, Hs) > side else max(Ws, Hs)

    @staticmethod
    def _assemble(settings, framing, stats, count, depth, zmin, cv, ss, complete) -> RenderResult:
        c = downsample(count.astype(np.float64), ss, "sum").astype(np.float32)
        d = downsample(depth.astype(np.float64), ss, "sum").astype(np.float32) if depth is not None else None
        z = downsample(zmin, ss, "min").astype(np.float32) if zmin is not None else None
        v = downsample(cv.astype(np.float64), ss, "sum").astype(np.float32) if cv is not None else None
        return RenderResult(settings, c, framing, stats, d, z, v, complete)


selector.register("opencl", OpenCLEngine)
