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
from attractr.core.render.checkpoint import Checkpoint
from attractr.core.render.engines import selector
from attractr.core.render.engines.base import Engine, EngineCaps, PassSink, resume_plan
from attractr.core.render.engines.cpu_numba import apply_lock, downsample, effective_camera, escape_config, splat_kernel
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
INTERLEAVE_ROUNDS = 8  # tiled renders visit every tile this many times so progress stays uniform
MIN_FINISH_STEPS = 16

PARAMS_DTYPE = np.dtype([
    ("steps", "i4"), ("substeps", "i4"), ("splat_r", "i4"), ("gap_fill", "i4"), ("color_code", "i4"),
    ("want_depth", "i4"), ("want_zmin", "i4"), ("want_color", "i4"), ("do_plot", "i4"),
    ("w", "i4"), ("h", "i4"), ("n", "i4"),
    ("dt", "f4"), ("inv_radius", "f4"), ("cx", "f4"), ("cy", "f4"), ("focal", "f4"), ("persp", "f4"),
    ("jitter", "f4"), ("inv_n", "f4"), ("cv_lo", "f4"), ("cv_inv_range", "f4"), ("t0", "f4"),
    ("R", "f4", (9,)), ("center", "f4", (3,)), ("ic", "f4", (4,)),
    ("esc_lo", "f4", (3,)), ("esc_hi", "f4", (3,)), ("esc_cfg", "f4", (3,)),
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

    def _program(self, cf, integrator: str, fp64: bool = False):
        import pyopencl as cl

        key = f"{cf.source_hash}:{integrator}:{int(fp64)}"
        if key in self._programs:
            return self._programs[key]
        gen = generate_gpu_source(cf.program, cf.analysis, integrator if cf.kind == "flow" else "rk4", "opencl")
        header = (
            "#pragma OPENCL EXTENSION cl_khr_fp64 : enable\ntypedef double real;\ntypedef double4 real4;\n#define R(x) ((real)(x))\n"
            if fp64 else "typedef float real;\ntypedef float4 real4;\n#define R(x) ((real)(x))\n"
        )
        src = self._kernel_src.replace("//__PRECISION__", header).replace("//__PRELUDE__", self._prelude).replace("//__STEP__", gen)
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
                   cancel: CancelToken = NEVER, tracker: ProgressTracker | None = None,
                   resume: Checkpoint | None = None) -> RenderResult:
        import pyopencl as cl

        t_start = time.perf_counter()
        tracker = tracker or ProgressTracker(None)
        q, look = settings.quality, settings.look
        ctx, queue = self._ensure()
        fp64 = q.precision == "fp64" and "cl_khr_fp64" in self._device.extensions
        if q.precision == "fp64" and not fp64:
            log.warning("fp64 requested but the OpenCL device lacks cl_khr_fp64; using fp32")
        stats = RenderStats(engine=self.id, device=self._device.name.strip(), precision="fp64" if fp64 else "fp32")

        t0 = time.perf_counter()
        cf = spec.compiled(q.integrator)
        k_iterate, k_merge = self._program(cf, q.integrator, fp64)
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
        plan = resume_plan(spec.iteration_budget(q.iterations), q.seed, resume)
        framing = plan.framing or framing
        cancel.check()
        cam = effective_camera(settings.camera, framing)
        R = cam.matrix().astype(np.float32).ravel()
        cx, cy, focal = cam.projection_constants(Ws, Hs)
        needs = needs_for(look)

        n_traj = q.trajectories or 65536
        n_traj = int(math.ceil(n_traj / 128) * 128)
        stats.trajectories = n_traj
        budget = plan.budget
        stats.iterations_requested = spec.iteration_budget(q.iterations)
        stats.warmup_steps = int(q.warmup) if q.warmup is not None else ACCUM_WARMUP

        tile = self._tile_size(Ws, Hs, needs.buffer_count)
        tiles = [(tx, ty, min(tile, Ws - tx), min(tile, Hs - ty)) for ty in range(0, Hs, tile) for tx in range(0, Ws, tile)]
        stats.tiles = len(tiles)
        if resume is not None and not resume.uniform and resume.tiles != len(tiles):
            raise ValueError(f"checkpoint has {resume.tiles} tiles but this device would use {len(tiles)}; resume on the same engine/device")
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
        P["gap_fill"] = 1 if (q.gap_fill and spec.plots_continuous) else 0
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
        esc_cfg = escape_config(spec)
        P["esc_lo"], P["esc_hi"], P["esc_cfg"] = esc_cfg[0:6:2], esc_cfg[1:6:2], esc_cfg[6:9]

        total_steps = math.ceil(budget / n_traj)
        done_all = 0
        passes = 0
        restarts_total = 0
        plotted_total = 0.0
        steps_per_pass = 16
        t_acc = time.perf_counter()
        last_partial = time.perf_counter()
        active = [ti for ti in range(len(tiles)) if ti >= plan.skip_tiles]
        steps_all = max(1, total_steps * len(active))
        rounds = 1 if len(active) <= 1 else INTERLEAVE_ROUNDS
        finish_at: int | None = None
        zeros4 = np.zeros((n_traj, 4), dtype=np.float32)

        # per-tile trajectory state persists across rounds; the big accumulators are re-created per visit
        tile_state: dict[int, dict] = {}
        for ti in active:
            st = seed_from_points(n_traj, plan.seed, sample_pts, framing.radius * 1e-2)
            state = np.zeros((n_traj, 4), dtype=np.float64 if fp64 else np.float32)
            state[:, 0], state[:, 1], state[:, 2], state[:, 3] = st.X, st.Y, st.Z, st.W
            tile_state[ti] = {
                "state": cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=state),
                "rng": cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=st.RS.astype(np.uint32)),
                "prev": cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=zeros4),
                "prevd": cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=zeros4),
                "stats": cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=np.zeros(4, dtype=np.uint32)),
                "esc": cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=st.escape_state()),
                "t_base": 0.0, "steps_done": 0, "warmed": False,
            }

        def emit_partial(frac: float) -> None:
            nonlocal last_partial
            last_partial = time.perf_counter()
            stats.iterations_done = min(t["steps_done"] for t in tile_state.values()) * n_traj if tile_state else 0
            stats.accumulate_seconds = time.perf_counter() - t_acc
            sink(plan.finish(self._assemble(settings, framing, stats, count_full, depth_full, zmin_full, cv_full, ss, False)), frac)

        try:
            for rnd in range(rounds):
                round_target = math.ceil(total_steps * (rnd + 1) / rounds)
                for ti in active:
                    tx, ty, tw, th = tiles[ti]
                    ts = tile_state[ti]
                    if finish_at is not None:
                        round_target = min(round_target, finish_at)
                    if ts["steps_done"] >= round_target and ts["warmed"]:
                        continue
                    cancel.check()
                    npix = tw * th
                    u_zero = np.zeros(npix, dtype=np.uint32)
                    u_inf = np.full(npix, 0xFFFFFFFF, dtype=np.uint32)

                    def slab(src, fill):
                        if src is None or rnd == 0:
                            return np.full(npix, fill, dtype=np.float32)
                        return np.ascontiguousarray(src[ty : ty + th, tx : tx + tw], dtype=np.float32).ravel()

                    b_cnt = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=u_zero)
                    b_dep = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=u_zero)
                    b_zmn = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=u_inf)
                    b_cvb = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=u_zero)
                    a_cnt = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=slab(count_full, 0.0))
                    a_dep = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=slab(depth_full, 0.0))
                    a_zmn = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=slab(zmin_full, np.inf))
                    a_cv = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=slab(cv_full, 0.0))
                    P["w"], P["h"] = tw, th
                    P["cx"], P["cy"] = cx - tx, cy - ty
                    b_P = cl.Buffer(ctx, mf.READ_ONLY, size=P.nbytes)
                    b_state, b_rng, b_prev, b_prevd, b_stats = (ts[k] for k in ("state", "rng", "prev", "prevd", "stats"))

                    def dispatch(steps: int, plot: int, ts=ts, b_P=b_P, bufs=(b_state, b_rng, b_prev, b_prevd, b_stats, b_cnt, b_dep, b_zmn, b_cvb)) -> None:
                        P["steps"], P["do_plot"], P["t0"] = steps, plot, ts["t_base"]
                        ts["t_base"] += steps * substeps
                        cl.enqueue_copy(queue, b_P, P)
                        k_iterate(queue, (n_traj,), (128,), *bufs, b_P, b_kern, b_p, ts["esc"])

                    def merge(npix=npix, bufs=(b_cnt, b_dep, b_zmn, b_cvb, a_cnt, a_dep, a_zmn, a_cv)) -> None:
                        gsz = int(math.ceil(npix / 256) * 256)
                        k_merge(queue, (gsz,), (256,), *bufs,
                                np.int32(npix), np.int32(needs.depth), np.int32(needs.zmin), np.int32(needs.color),
                                np.float32(cv_lo), np.float32(cv_hi - cv_lo))

                    def readback(npix=npix, tx=tx, ty=ty, tw=tw, th=th, bufs=(a_cnt, a_dep, a_zmn, a_cv)) -> None:
                        def rd(buf):
                            out = np.empty(npix, dtype=np.float32)
                            cl.enqueue_copy(queue, out, buf)
                            return out.reshape(th, tw)

                        queue.finish()
                        count_full[ty : ty + th, tx : tx + tw] = rd(bufs[0])
                        if depth_full is not None:
                            depth_full[ty : ty + th, tx : tx + tw] = rd(bufs[1])
                        if zmin_full is not None:
                            zmin_full[ty : ty + th, tx : tx + tw] = rd(bufs[2])
                        if cv_full is not None:
                            cv_full[ty : ty + th, tx : tx + tw] = rd(bufs[3])

                    try:
                        if not ts["warmed"]:
                            warm = stats.warmup_steps
                            while warm > 0:
                                k = min(warm, MAX_STEPS_PER_PASS)
                                dispatch(k, 0)
                                warm -= k
                            cl.enqueue_copy(queue, b_prev, zeros4)
                            ts["warmed"] = True
                        while ts["steps_done"] < round_target:
                            cancel.check()
                            if cancel.finishing and finish_at is None:  # soft stop: every tile ends at this count
                                finish_at = max(ts["steps_done"], min(total_steps, MIN_FINISH_STEPS))
                                round_target = min(round_target, finish_at)
                                stats.finished_early = True
                                stats.notes.append(f"Finished early on request at {100 * finish_at / total_steps:.0f} % of the budget.")
                                if ts["steps_done"] >= round_target:
                                    break
                            k = min(steps_per_pass, round_target - ts["steps_done"], MAX_STEPS_PER_PASS)
                            tp = time.perf_counter()
                            dispatch(k, 1)
                            merge()
                            queue.finish()
                            dtp = time.perf_counter() - tp
                            ts["steps_done"] += k
                            done_all += k
                            passes += 1
                            if dtp > 0:
                                steps_per_pass = int(min(max(4, k * TARGET_PASS_SECONDS / dtp), MAX_STEPS_PER_PASS))
                            frac = done_all / steps_all
                            tracker.update(0.05 + 0.9 * frac, f"tile {ti + 1}/{len(tiles)} · round {rnd + 1}/{rounds} · pass {passes} · {done_all * n_traj / 1e6:.1f} M points")
                            if sink is not None and len(active) == 1 and (time.perf_counter() - last_partial > 0.5 or ts["steps_done"] >= total_steps):
                                readback()
                                emit_partial(frac)
                        readback()
                    finally:
                        for b in (b_cnt, b_dep, b_zmn, b_cvb, a_cnt, a_dep, a_zmn, a_cv, b_P):
                            b.release()
                if sink is not None and len(active) > 1:
                    emit_partial(done_all / steps_all)
                if finish_at is not None and all(t["steps_done"] >= finish_at for t in tile_state.values()):
                    break
            for ts in tile_state.values():
                sv = np.zeros(4, dtype=np.uint32)
                cl.enqueue_copy(queue, sv, ts["stats"])
                queue.finish()
                restarts_total += int(sv[0])
                plotted_total += (int(sv[2]) * 4294967296.0 + int(sv[1])) / 16.0
        finally:
            for ts in tile_state.values():
                for key in ("state", "rng", "prev", "prevd", "stats", "esc"):
                    ts[key].release()
            b_kern.release()
            b_p.release()
        if finish_at is not None:
            total_steps = finish_at

        stats.accumulate_seconds = time.perf_counter() - t_acc
        stats.iterations_done = total_steps * n_traj
        stats.tiles_done = 0
        stats.passes = passes
        stats.restarts = restarts_total
        stats.points_plotted = plotted_total
        result = plan.finish(self._assemble(settings, framing, stats, count_full, depth_full, zmin_full, cv_full, ss, True))
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
