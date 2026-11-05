"""OpenGL 4.3 compute engines: ``gl_compute`` (interactive) and ``gl_precision`` (tiled,
supersampled, splat kernels, checkpointed passes).  Same shader core, different defaults.

Accumulation happens in fixed-point uint images per pass (imageAtomicAdd), merged into
float32 accumulators by ``merge.comp`` after every pass — so precision matches the CPU
engine while staying within GL 4.3 core features.
"""

from __future__ import annotations

import logging
import math
import os
import time

import numpy as np

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.jobs.cancel import NEVER, CancelToken
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.accumulators import color_value_range, needs_for
from attractr.core.render.checkpoint import Checkpoint
from attractr.core.render.engines import selector
from attractr.core.render.engines.base import Engine, EngineCaps, PassSink, resume_plan
from attractr.core.render.engines.cpu_numba import apply_lock, downsample, effective_camera, escape_config, splat_kernel
from attractr.core.render.engines.gl_common import (
    GLContextPool,
    GLUnavailable,
    assemble_iterate_shader,
    compile_compute,
    micro_benchmark,
    probe_compute,
    query_info,
    read_shader,
)
from attractr.core.render.engines.state import seed_from_points
from attractr.core.render.framing import compute_framing
from attractr.core.render.result import RenderResult, RenderStats
from attractr.core.render.settings import RenderSettings
from attractr.core.render.stats import summarize

log = logging.getLogger(__name__)

LOCAL_SIZE = 128
DEFAULT_TRAJECTORIES = 65536
MAX_STEPS_PER_PASS = 256  # keeps 24.8 fixed-point sums below 2^32 per pass
TARGET_PASS_SECONDS = 0.3
TILE_BUDGET_BYTES = int(float(os.environ.get("ATTRACTR_GPU_BUDGET_MB", "768")) * 1024 * 1024)
ACCUM_WARMUP = 64
INTERLEAVE_ROUNDS = 8  # tiled renders visit every tile this many times so progress stays uniform
MIN_FINISH_STEPS = 16  # "Finish now" never leaves a tile with fewer steps than this


def _set(prog, name: str, value) -> None:
    """Set a uniform if the compiler kept it (unused uniforms are optimised away)."""
    if name in prog:
        prog[name].value = value


def _write(prog, name: str, data: bytes) -> None:
    if name in prog:
        prog[name].write(data)


class _Programs:
    """Compiled shaders for one (formula, integrator, precision) on one context."""

    def __init__(self, ctx, cf, integrator: str, fp64: bool) -> None:
        self.iterate = compile_compute(ctx, assemble_iterate_shader(cf, integrator, fp64), "iterate shader")
        self.merge = compile_compute(ctx, read_shader("merge.comp"), "merge shader")
        self.fp64 = fp64


def resolve_precision(requested: str, caps_fp64: bool, final: bool) -> bool:
    """``auto`` → fp32 (fp64 is 2–32× slower on consumer GPUs); ``fp64`` only when supported."""
    if requested == "fp64":
        return bool(caps_fp64)
    return False


class GLComputeEngine(Engine):
    id = "gl_compute"
    name = "GPU compute (OpenGL 4.3)"
    precision_profile = False

    def __init__(self) -> None:
        self.pool = GLContextPool(430)
        self._programs: dict[tuple, _Programs] = {}
        self._info = None

    # ── probe ──────────────────────────────────────────────────────────────────
    def probe(self) -> EngineCaps:
        try:
            ctx = self.pool.get()
        except GLUnavailable as exc:
            return EngineCaps(self.id, self.name, available=False, notes=[str(exc)])
        info = query_info(ctx)
        self._info = info
        ok, msg = probe_compute(ctx)
        caps = EngineCaps(self.id, self.name, device=f"{info.renderer} ({info.vendor})", available=ok,
                          fp64=info.fp64, compute=True, max_size=info.max_texture_size, notes=[msg])
        if ok:
            caps.mpts_per_second = micro_benchmark(ctx)
        return caps

    def close(self) -> None:
        self.pool.release_all()

    # ── accumulate ─────────────────────────────────────────────────────────────
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
        tracker = tracker or ProgressTracker(None)
        q, look = settings.quality, settings.look
        ctx = self.pool.get()
        info = self._info or query_info(ctx)
        fp64 = resolve_precision(q.precision, info.fp64, self.precision_profile)
        if q.precision == "fp64" and not fp64:
            log.warning("fp64 requested but GL_ARB_gpu_shader_fp64 is not available; using fp32")
        stats = RenderStats(engine=self.id, device=info.renderer, precision="fp64" if fp64 else "fp32")

        t0 = time.perf_counter()
        cf = spec.compiled(q.integrator)
        key = (id(ctx), cf.source_hash, q.integrator, fp64)
        if key not in self._programs:
            self._programs[key] = _Programs(ctx, cf, q.integrator, fp64)
        prog = self._programs[key]
        stats.compile_seconds = time.perf_counter() - t0
        tracker.update(0.0, "shaders ready")

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
        R = cam.matrix().astype(np.float32)
        cx, cy, focal = cam.projection_constants(Ws, Hs)
        needs = needs_for(look)

        n_traj = q.trajectories or DEFAULT_TRAJECTORIES
        n_traj = int(math.ceil(n_traj / LOCAL_SIZE) * LOCAL_SIZE)
        groups = n_traj // LOCAL_SIZE
        stats.trajectories = n_traj
        budget = plan.budget
        stats.iterations_requested = spec.iteration_budget(q.iterations)
        stats.warmup_steps = int(q.warmup) if q.warmup is not None else ACCUM_WARMUP

        # ── tiles ──────────────────────────────────────────────────────────────
        tile = self._tile_size(Ws, Hs, needs.buffer_count, info.max_texture_size)
        tiles = [(tx, ty, min(tile, Ws - tx), min(tile, Hs - ty)) for ty in range(0, Hs, tile) for tx in range(0, Ws, tile)]
        stats.tiles = len(tiles)
        if resume is not None and not resume.uniform and resume.tiles != len(tiles):
            raise ValueError(f"checkpoint has {resume.tiles} tiles but this device would use {len(tiles)}; resume on the same engine/device")

        count_full = np.zeros((Hs, Ws), dtype=np.float32)
        depth_full = np.zeros((Hs, Ws), dtype=np.float32) if needs.depth else None
        zmin_full = np.full((Hs, Ws), np.inf, dtype=np.float32) if needs.zmin else None
        cv_full = np.zeros((Hs, Ws), dtype=np.float32) if needs.color else None

        # ── uniforms that do not change per tile ───────────────────────────────
        it = prog.iterate
        _set(it, "u_substeps", substeps)
        _set(it, "u_dt", float(dt))
        _write(it, "u_R", R.T.tobytes())  # GLSL mat3 is column-major → transpose
        _set(it, "u_center", tuple(float(c) for c in framing.center))
        _set(it, "u_inv_radius", float(1.0 / framing.radius))
        _set(it, "u_focal", float(focal))
        _set(it, "u_persp", float(cam.perspective))
        _set(it, "u_splat_r", int(q.splat_radius))
        kern = np.zeros(81, dtype=np.float32)
        k = splat_kernel(q.splat_radius).astype(np.float32)
        kern[: k.size] = k
        _write(it, "u_kern", kern.tobytes())
        _set(it, "u_gap_fill", 1 if (q.gap_fill and spec.plots_continuous) else 0)
        _set(it, "u_color_code", int(needs.color_code))
        _set(it, "u_ic", tuple(float(v) for v in spec.ic))
        esc_cfg = escape_config(spec)
        _set(it, "u_esc_lo", tuple(float(v) for v in esc_cfg[0:6:2]))
        _set(it, "u_esc_hi", tuple(float(v) for v in esc_cfg[1:6:2]))
        _set(it, "u_esc_cfg", tuple(float(v) for v in esc_cfg[6:9]))
        _set(it, "u_jitter", float(spec.jitter))
        _set(it, "u_inv_n", float(1.0 / n_traj))
        cv_lo, cv_hi = color_value_range(needs.color_code, sample_pts, framing, cam.matrix(), params, cf.color_fn) if needs.color else (-4.0, 4.0)
        _set(it, "u_cv_range", (float(cv_lo), float(1.0 / (cv_hi - cv_lo))))
        _set(prog.merge, "u_cv_range", (float(cv_lo), float(cv_hi - cv_lo)))
        pbuf = np.zeros(max(1, len(cf.param_names)), dtype=np.float32)
        pbuf[: params.size] = params
        _write(it, "u_p", pbuf.tobytes())

        total_steps = math.ceil(budget / n_traj)
        t_acc = time.perf_counter()
        restarts_total = 0
        plotted_total = 0.0
        passes = 0
        steps_per_pass = 16
        last_partial = time.perf_counter()
        done_steps_all = 0
        active = [ti for ti in range(len(tiles)) if ti >= plan.skip_tiles]  # complete tiles of a legacy checkpoint are skipped
        steps_all = max(1, total_steps * len(active))
        rounds = 1 if len(active) <= 1 else INTERLEAVE_ROUNDS
        finish_at: int | None = None  # per-tile step count everything stops at after "Finish now"

        # per-tile trajectory state lives for the whole render (small); the big images are
        # re-created per visit, so tiles are interleaved in rounds and progress uniformly
        tile_state: dict[int, dict] = {}
        for ti in active:
            st = seed_from_points(n_traj, plan.seed, sample_pts, framing.radius * 1e-2)
            state = np.zeros((n_traj, 4), dtype=np.float64 if fp64 else np.float32)
            state[:, 0], state[:, 1], state[:, 2], state[:, 3] = st.X, st.Y, st.Z, st.W
            tile_state[ti] = {
                "state": ctx.buffer(state.tobytes()), "rng": ctx.buffer(st.RS.astype(np.uint32).tobytes()),
                "prev": ctx.buffer(np.zeros((n_traj, 4), dtype=np.float32).tobytes()),
                "prevd": ctx.buffer(np.zeros((n_traj, 4), dtype=np.float32).tobytes()),
                "stats": ctx.buffer(np.zeros(4, dtype=np.uint32).tobytes()),
                "esc": ctx.buffer(st.escape_state().tobytes()),
                "t_base": 0.0, "steps_done": 0, "warmed": False,
            }

        def emit_partial(frac: float) -> None:
            nonlocal last_partial
            last_partial = time.perf_counter()
            stats.iterations_done = min(t["steps_done"] for t in tile_state.values()) * n_traj if tile_state else 0
            stats.accumulate_seconds = time.perf_counter() - t_acc
            partial = self._assemble(settings, framing, stats, count_full, depth_full, zmin_full, cv_full, ss, False)
            sink(plan.finish(partial), frac)

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
                    imgs = self._make_images(ctx, tw, th, needs)
                    try:
                        if rnd > 0:  # restore this tile's accumulators from the host copies
                            self._upload(imgs, needs, count_full, depth_full, zmin_full, cv_full, tx, ty, tw, th)
                        ts["state"].bind_to_storage_buffer(0)
                        ts["rng"].bind_to_storage_buffer(1)
                        ts["prev"].bind_to_storage_buffer(2)
                        ts["prevd"].bind_to_storage_buffer(3)
                        ts["stats"].bind_to_storage_buffer(4)
                        ts["esc"].bind_to_storage_buffer(5)
                        for u, (tex, _) in enumerate(imgs["uint"]):
                            tex.bind_to_image(u, read=True, write=True)
                        _set(it, "u_size", (tw, th))
                        _set(it, "u_c", (float(cx - tx), float(cy - ty)))

                        def dispatch(steps: int, plot: int, ts=ts) -> None:
                            _set(it, "u_steps", int(steps))
                            _set(it, "u_t0", float(ts["t_base"]))
                            _set(it, "u_flags", (int(needs.depth), int(needs.zmin), int(needs.color), plot))
                            it.run(group_x=groups)
                            ctx.memory_barrier()
                            ts["t_base"] += steps * substeps

                        def merge(imgs=imgs, tw=tw, th=th) -> None:
                            m = prog.merge
                            for u, (tex, _) in enumerate(imgs["uint"]):
                                tex.bind_to_image(u, read=True, write=True)
                            for u, (tex, _) in enumerate(imgs["float"]):
                                tex.bind_to_image(4 + u, read=True, write=True)
                            _set(m, "u_size", (tw, th))
                            _set(m, "u_flags", (int(needs.depth), int(needs.zmin), int(needs.color), 0))
                            m.run(group_x=(tw + 15) // 16, group_y=(th + 15) // 16)
                            ctx.memory_barrier()

                        if not ts["warmed"]:  # warm-up (not plotted)
                            warm = stats.warmup_steps
                            while warm > 0:
                                k = min(warm, MAX_STEPS_PER_PASS)
                                dispatch(k, 0)
                                warm -= k
                            ts["prev"].write(np.zeros((n_traj, 4), dtype=np.float32).tobytes())
                            ts["warmed"] = True
                        # passes up to this round's target
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
                            ctx.finish()
                            dtp = time.perf_counter() - tp
                            ts["steps_done"] += k
                            done_steps_all += k
                            passes += 1
                            if dtp > 0:
                                steps_per_pass = int(min(max(4, k * TARGET_PASS_SECONDS / dtp), MAX_STEPS_PER_PASS))
                            frac = done_steps_all / steps_all
                            tracker.update(0.05 + 0.9 * frac, f"tile {ti + 1}/{len(tiles)} · round {rnd + 1}/{rounds} · pass {passes} · {done_steps_all * n_traj / 1e6:.1f} M points")
                            if sink is not None and len(active) == 1 and (time.perf_counter() - last_partial > 0.5 or ts["steps_done"] >= total_steps):
                                self._readback(imgs, needs, count_full, depth_full, zmin_full, cv_full, tx, ty, tw, th)
                                emit_partial(frac)
                        self._readback(imgs, needs, count_full, depth_full, zmin_full, cv_full, tx, ty, tw, th)
                    finally:
                        for tex, _ in imgs["uint"] + imgs["float"]:
                            tex.release()
                if sink is not None and len(active) > 1:  # all tiles are at the same fraction: a uniform partial
                    emit_partial(done_steps_all / steps_all)
                if finish_at is not None and all(t["steps_done"] >= finish_at for t in tile_state.values()):
                    break
            for ts in tile_state.values():
                sv = np.frombuffer(ts["stats"].read(), dtype=np.uint32)
                restarts_total += int(sv[0])
                plotted_total += (int(sv[2]) * 4294967296.0 + int(sv[1])) / 16.0
        finally:
            for ts in tile_state.values():
                for key in ("state", "rng", "prev", "prevd", "stats", "esc"):
                    ts[key].release()
        if finish_at is not None:
            total_steps = finish_at

        stats.accumulate_seconds = time.perf_counter() - t_acc
        stats.iterations_done = total_steps * n_traj  # effective per-pixel budget (each tile runs it)
        stats.tiles_done = 0
        stats.passes = passes
        stats.restarts = restarts_total
        stats.points_plotted = plotted_total
        result = plan.finish(self._assemble(settings, framing, stats, count_full, depth_full, zmin_full, cv_full, ss, True))
        summarize(result, look.percentile)
        stats.elapsed = time.perf_counter() - t_start
        tracker.update(1.0, "accumulated", force=True)
        return result

    # ── helpers ────────────────────────────────────────────────────────────────
    @staticmethod
    def _tile_size(Ws: int, Hs: int, nbuf: int, max_tex: int) -> int:
        bytes_per_px = 4 * (nbuf + 4)  # uint pass images (4) + float accumulators
        side = int(math.sqrt(TILE_BUDGET_BYTES / bytes_per_px))
        side = min(side, max_tex, 8192)
        side = max(256, (side // 256) * 256)
        return max(side, 256) if max(Ws, Hs) > side else max(Ws, Hs)

    @staticmethod
    def _make_images(ctx, w: int, h: int, needs):
        uint_imgs = []
        for idx in range(4):
            tex = ctx.texture((w, h), 1, dtype="u4")
            fill = np.full(w * h, 0xFFFFFFFF if idx == 2 else 0, dtype=np.uint32)
            tex.write(fill.tobytes())
            uint_imgs.append((tex, idx))
        float_imgs = []
        for idx in range(4):
            tex = ctx.texture((w, h), 1, dtype="f4")
            fill = np.full(w * h, np.inf if idx == 2 else 0.0, dtype=np.float32)
            tex.write(fill.tobytes())
            float_imgs.append((tex, idx))
        return {"uint": uint_imgs, "float": float_imgs}

    @staticmethod
    def _upload(imgs, needs, count, depth, zmin, cv, tx, ty, tw, th) -> None:
        """Inverse of :meth:`_readback`: restore a tile's float accumulators from the host copies."""
        def write(i, src):
            imgs["float"][i][0].write(np.ascontiguousarray(src[ty : ty + th, tx : tx + tw], dtype=np.float32).tobytes())

        write(0, count)
        if depth is not None:
            write(1, depth)
        if zmin is not None:
            write(2, zmin)
        if cv is not None:
            write(3, cv)

    @staticmethod
    def _readback(imgs, needs, count, depth, zmin, cv, tx, ty, tw, th) -> None:
        def read(i):
            return np.frombuffer(imgs["float"][i][0].read(), dtype=np.float32).reshape(th, tw)

        count[ty : ty + th, tx : tx + tw] = read(0)
        if depth is not None:
            depth[ty : ty + th, tx : tx + tw] = read(1)
        if zmin is not None:
            zmin[ty : ty + th, tx : tx + tw] = read(2)
        if cv is not None:
            cv[ty : ty + th, tx : tx + tw] = read(3)

    @staticmethod
    def _assemble(settings, framing, stats, count, depth, zmin, cv, ss, complete) -> RenderResult:
        c = downsample(count.astype(np.float64), ss, "sum").astype(np.float32)
        d = downsample(depth.astype(np.float64), ss, "sum").astype(np.float32) if depth is not None else None
        z = downsample(zmin, ss, "min").astype(np.float32) if zmin is not None else None
        v = downsample(cv.astype(np.float64), ss, "sum").astype(np.float32) if cv is not None else None
        return RenderResult(settings, c, framing, stats, d, z, v, complete)


class GLPrecisionEngine(GLComputeEngine):
    """Same shader core; selected for final renders.  Tiles + supersampling come from the
    settings; this profile additionally forces splat anti-aliasing when none was asked."""

    id = "gl_precision"
    name = "GPU precision (OpenGL 4.3 compute, tiled)"
    precision_profile = True


selector.register("gl_compute", GLComputeEngine)
selector.register("gl_precision", GLPrecisionEngine)
