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
from attractr.core.render.engines import selector
from attractr.core.render.engines.base import Engine, EngineCaps, PassSink
from attractr.core.render.engines.cpu_numba import apply_lock, downsample, effective_camera, splat_kernel
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


def _set(prog, name: str, value) -> None:
    """Set a uniform if the compiler kept it (unused uniforms are optimised away)."""
    if name in prog:
        prog[name].value = value


def _write(prog, name: str, data: bytes) -> None:
    if name in prog:
        prog[name].write(data)


class _Programs:
    """Compiled shaders for one (formula, integrator) on one context."""

    def __init__(self, ctx, cf, integrator: str) -> None:
        self.iterate = compile_compute(ctx, assemble_iterate_shader(cf, integrator), "iterate shader")
        self.merge = compile_compute(ctx, read_shader("merge.comp"), "merge shader")


class GLComputeEngine(Engine):
    id = "gl_compute"
    name = "GPU compute (OpenGL 4.3)"
    precision_profile = False

    def __init__(self) -> None:
        self.pool = GLContextPool(430)
        self._programs: dict[tuple[int, str], _Programs] = {}
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
    ) -> RenderResult:
        t_start = time.perf_counter()
        tracker = tracker or ProgressTracker(None)
        q, look = settings.quality, settings.look
        ctx = self.pool.get()
        info = self._info or query_info(ctx)
        stats = RenderStats(engine=self.id, device=info.renderer, precision="fp32")

        t0 = time.perf_counter()
        cf = spec.compiled(q.integrator)
        key = (id(ctx), cf.source_hash)
        if key not in self._programs:
            self._programs[key] = _Programs(ctx, cf, q.integrator)
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
        cancel.check()
        cam = effective_camera(settings.camera, framing)
        R = cam.matrix().astype(np.float32)
        cx, cy, focal = cam.projection_constants(Ws, Hs)
        needs = needs_for(look)

        n_traj = q.trajectories or DEFAULT_TRAJECTORIES
        n_traj = int(math.ceil(n_traj / LOCAL_SIZE) * LOCAL_SIZE)
        groups = n_traj // LOCAL_SIZE
        stats.trajectories = n_traj
        stats.iterations_requested = q.iterations
        stats.warmup_steps = int(q.warmup) if q.warmup is not None else ACCUM_WARMUP

        # ── tiles ──────────────────────────────────────────────────────────────
        tile = self._tile_size(Ws, Hs, needs.buffer_count, info.max_texture_size)
        tiles = [(tx, ty, min(tile, Ws - tx), min(tile, Hs - ty)) for ty in range(0, Hs, tile) for tx in range(0, Ws, tile)]
        stats.tiles = len(tiles)

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
        _set(it, "u_gap_fill", 1 if (q.gap_fill and spec.is_flow) else 0)
        _set(it, "u_color_code", int(needs.color_code))
        _set(it, "u_ic", tuple(float(v) for v in spec.ic))
        _set(it, "u_jitter", float(spec.jitter))
        _set(it, "u_inv_n", float(1.0 / n_traj))
        cv_lo, cv_hi = color_value_range(needs.color_code, sample_pts, framing, cam.matrix(), params, cf.color_fn) if needs.color else (-4.0, 4.0)
        _set(it, "u_cv_range", (float(cv_lo), float(1.0 / (cv_hi - cv_lo))))
        _set(prog.merge, "u_cv_range", (float(cv_lo), float(cv_hi - cv_lo)))
        pbuf = np.zeros(max(1, len(cf.param_names)), dtype=np.float32)
        pbuf[: params.size] = params
        _write(it, "u_p", pbuf.tobytes())

        total_steps = max(1, math.ceil(q.iterations / n_traj))
        t_acc = time.perf_counter()
        restarts_total = 0
        plotted_total = 0.0
        passes = 0
        steps_per_pass = 16
        last_partial = time.perf_counter()
        done_steps_all = 0
        steps_all = total_steps * len(tiles)

        for ti, (tx, ty, tw, th) in enumerate(tiles):
            cancel.check()
            # trajectories restart identically per tile → deterministic, seamless tiles
            st = seed_from_points(n_traj, q.seed, sample_pts, framing.radius * 1e-2)
            state = np.zeros((n_traj, 4), dtype=np.float32)
            state[:, 0], state[:, 1], state[:, 2] = st.X, st.Y, st.Z
            b_state = ctx.buffer(state.tobytes())
            b_rng = ctx.buffer(st.RS.astype(np.uint32).tobytes())
            b_prev = ctx.buffer(np.zeros((n_traj, 4), dtype=np.float32).tobytes())
            b_prevd = ctx.buffer(np.zeros((n_traj, 4), dtype=np.float32).tobytes())
            b_stats = ctx.buffer(np.zeros(4, dtype=np.uint32).tobytes())
            imgs = self._make_images(ctx, tw, th, needs)
            try:
                b_state.bind_to_storage_buffer(0)
                b_rng.bind_to_storage_buffer(1)
                b_prev.bind_to_storage_buffer(2)
                b_prevd.bind_to_storage_buffer(3)
                b_stats.bind_to_storage_buffer(4)
                for u, (tex, _) in enumerate(imgs["uint"]):
                    tex.bind_to_image(u, read=True, write=True)
                _set(it, "u_size", (tw, th))
                _set(it, "u_c", (float(cx - tx), float(cy - ty)))

                def dispatch(steps: int, plot: int) -> None:
                    _set(it, "u_steps", int(steps))
                    _set(it, "u_flags", (int(needs.depth), int(needs.zmin), int(needs.color), plot))
                    it.run(group_x=groups)
                    ctx.memory_barrier()

                def merge() -> None:
                    m = prog.merge
                    for u, (tex, _) in enumerate(imgs["uint"]):
                        tex.bind_to_image(u, read=True, write=True)
                    for u, (tex, _) in enumerate(imgs["float"]):
                        tex.bind_to_image(4 + u, read=True, write=True)
                    _set(m, "u_size", (tw, th))
                    _set(m, "u_flags", (int(needs.depth), int(needs.zmin), int(needs.color), 0))
                    m.run(group_x=(tw + 15) // 16, group_y=(th + 15) // 16)
                    ctx.memory_barrier()

                # warm-up (not plotted)
                warm = stats.warmup_steps
                while warm > 0:
                    k = min(warm, MAX_STEPS_PER_PASS)
                    dispatch(k, 0)
                    warm -= k
                b_prev.write(np.zeros((n_traj, 4), dtype=np.float32).tobytes())
                # passes
                steps_done = 0
                while steps_done < total_steps:
                    cancel.check()
                    k = min(steps_per_pass, total_steps - steps_done, MAX_STEPS_PER_PASS)
                    tp = time.perf_counter()
                    dispatch(k, 1)
                    merge()
                    ctx.finish()
                    dtp = time.perf_counter() - tp
                    steps_done += k
                    done_steps_all += k
                    passes += 1
                    if dtp > 0:
                        steps_per_pass = int(min(max(4, k * TARGET_PASS_SECONDS / dtp), MAX_STEPS_PER_PASS))
                    frac = done_steps_all / steps_all
                    tracker.update(0.05 + 0.9 * frac, f"tile {ti + 1}/{len(tiles)} · pass {passes} · {done_steps_all * n_traj / 1e6:.1f} M points")
                    if sink is not None and len(tiles) == 1 and (time.perf_counter() - last_partial > 0.5 or steps_done >= total_steps):
                        last_partial = time.perf_counter()
                        self._readback(imgs, needs, count_full, depth_full, zmin_full, cv_full, tx, ty, tw, th)
                        partial = self._assemble(settings, framing, stats, count_full, depth_full, zmin_full, cv_full, ss, False)
                        sink(partial, frac)
                self._readback(imgs, needs, count_full, depth_full, zmin_full, cv_full, tx, ty, tw, th)
                s = np.frombuffer(b_stats.read(), dtype=np.uint32)
                restarts_total += int(s[0])
                plotted_total += (int(s[2]) * 4294967296.0 + int(s[1])) / 16.0
            finally:
                for tex, _ in imgs["uint"] + imgs["float"]:
                    tex.release()
                for b in (b_state, b_rng, b_prev, b_prevd, b_stats):
                    b.release()

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
