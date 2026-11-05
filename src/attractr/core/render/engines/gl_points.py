"""``gl_points`` — OpenGL 3.3 fallback engine (macOS, old drivers, no compute shaders).

Trajectories live in textures (one texel each).  Every pass: a fragment shader advances
all trajectories one step (ping-pong render targets), then a vertex shader reads the new
positions and scatters one point per trajectory into a float framebuffer with additive
blending (or ``GL_MIN`` blending for the nearest-depth buffer).  Flows optionally draw a
line from the previous to the new position (gap filling) with weight 1/length.

Limitations versus the compute engines: nearest-pixel splat (use supersampling for
anti-aliasing), fp32 only, no restart counting.
"""

from __future__ import annotations

import logging
import math
import time

import moderngl
import numpy as np

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.formula.codegen_glsl import generate_gpu_source
from attractr.core.jobs.cancel import NEVER, CancelToken
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.accumulators import needs_for
from attractr.core.render.checkpoint import Checkpoint
from attractr.core.render.engines import selector
from attractr.core.render.engines.base import Engine, EngineCaps, PassSink, resume_plan
from attractr.core.render.engines.cpu_numba import apply_lock, downsample, effective_camera
from attractr.core.render.engines.gl_common import (
    GLSL_PRECISION_FP32,
    GLContextPool,
    GLUnavailable,
    query_info,
    read_shader,
)
from attractr.core.render.engines.state import seed_from_points
from attractr.core.render.framing import compute_framing
from attractr.core.render.result import RenderResult, RenderStats
from attractr.core.render.settings import RenderSettings
from attractr.core.render.stats import summarize

log = logging.getLogger(__name__)

TEX_W = 256
TEX_H = 256
TARGET_PASS_SECONDS = 0.25
TILE_MAX = 4096
ACCUM_WARMUP = 64
INTERLEAVE_ROUNDS = 8
MIN_FINISH_STEPS = 16

QUAD_VERT = """#version 330
void main() {
    vec2 p = vec2((gl_VertexID == 1) ? 3.0 : -1.0, (gl_VertexID == 2) ? 3.0 : -1.0);
    gl_Position = vec4(p, 0.0, 1.0);
}
"""


def _assemble(name: str, cf, integrator: str) -> str:
    src = read_shader(name)
    gen = generate_gpu_source(cf.program, cf.analysis, integrator if cf.kind == "flow" else "rk4", "glsl")
    return (src.replace("__NPARAMS__", str(max(1, len(cf.param_names))))
            .replace("//__PRECISION__", GLSL_PRECISION_FP32)
            .replace("//__PRELUDE__", read_shader("prelude.glsl"))
            .replace("//__STEP__", gen))


def _set(prog, name, value) -> None:
    if name in prog:
        prog[name].value = value


def _write(prog, name, data: bytes) -> None:
    if name in prog:
        prog[name].write(data)


class _Programs:
    def __init__(self, ctx, cf, integrator: str) -> None:
        try:
            self.update = ctx.program(vertex_shader=QUAD_VERT, fragment_shader=_assemble("points_update.frag", cf, integrator))
            self.draw = ctx.program(vertex_shader=_assemble("points_draw.vert", cf, integrator), fragment_shader=read_shader("points_draw.frag"))
        except Exception as exc:  # noqa: BLE001
            raise GLUnavailable(f"gl_points shaders failed to compile: {exc}") from exc
        self.vao_quad = ctx.vertex_array(self.update, [])
        self.vao_points = ctx.vertex_array(self.draw, [])


class GLPointsEngine(Engine):
    id = "gl_points"
    name = "GPU points (OpenGL 3.3 fallback)"

    def __init__(self) -> None:
        self.pool = GLContextPool(330)
        self._programs: dict[tuple, _Programs] = {}
        self._info = None

    def probe(self) -> EngineCaps:
        try:
            ctx = self.pool.get()
        except GLUnavailable as exc:
            return EngineCaps(self.id, self.name, available=False, notes=[str(exc)])
        info = query_info(ctx)
        self._info = info
        ok = ctx.version_code >= 330
        notes = ["point splats + float blending"] if ok else ["OpenGL 3.3 required"]
        return EngineCaps(self.id, self.name, device=f"{info.renderer} ({info.vendor})", available=ok, fp64=False,
                          compute=False, max_size=info.max_texture_size, notes=notes)

    def supports(self, spec: AttractorSpec) -> bool:
        # the vertex-shader plotter cannot run state-changing section events or escape-time systems
        return not spec.analysis.has_event and spec.kind != "escape"

    def close(self) -> None:
        self.pool.release_all()

    # ── accumulate ─────────────────────────────────────────────────────────────
    def accumulate(self, settings: RenderSettings, spec: AttractorSpec, *, sink: PassSink | None = None,
                   cancel: CancelToken = NEVER, tracker: ProgressTracker | None = None,
                   resume: Checkpoint | None = None) -> RenderResult:
        t_start = time.perf_counter()
        tracker = tracker or ProgressTracker(None)
        q, look = settings.quality, settings.look
        ctx = self.pool.get()
        info = self._info or query_info(ctx)
        stats = RenderStats(engine=self.id, device=info.renderer, precision="fp32")
        if q.splat_radius > 0:
            stats.notes.append("gl_points ignores the splat radius (nearest-pixel points; use supersampling)")

        t0 = time.perf_counter()
        cf = spec.compiled(q.integrator)
        key = (id(ctx), cf.source_hash, q.integrator)
        if key not in self._programs:
            self._programs[key] = _Programs(ctx, cf, q.integrator)
        prog = self._programs[key]
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
        R = cam.matrix().astype(np.float32)
        cx, cy, focal = cam.projection_constants(Ws, Hs)
        needs = needs_for(look)
        n_traj = TEX_W * TEX_H
        stats.trajectories = n_traj
        budget = plan.budget
        stats.iterations_requested = spec.iteration_budget(q.iterations)
        stats.warmup_steps = int(q.warmup) if q.warmup is not None else ACCUM_WARMUP
        gap_fill = bool(q.gap_fill and spec.plots_continuous)

        pbuf = np.zeros(max(1, len(cf.param_names)), dtype=np.float32)
        pbuf[: params.size] = params
        for pr in (prog.update, prog.draw):
            _write(pr, "u_p", pbuf.tobytes())
        _set(prog.update, "u_substeps", substeps)
        _set(prog.update, "u_dt", float(dt))
        _set(prog.update, "u_ic", tuple(float(v) for v in spec.ic))
        _set(prog.update, "u_jitter", float(spec.jitter))
        _set(prog.draw, "u_tex_w", TEX_W)
        _write(prog.draw, "u_R", R.T.tobytes())
        _set(prog.draw, "u_center", tuple(float(c) for c in framing.center))
        _set(prog.draw, "u_inv_radius", float(1.0 / framing.radius))
        _set(prog.draw, "u_focal", float(focal))
        _set(prog.draw, "u_persp", float(cam.perspective))
        _set(prog.draw, "u_color_code", int(needs.color_code))
        _set(prog.draw, "u_inv_n", float(1.0 / n_traj))

        tile = min(TILE_MAX, info.max_texture_size)
        tiles = [(tx, ty, min(tile, Ws - tx), min(tile, Hs - ty)) for ty in range(0, Hs, tile) for tx in range(0, Ws, tile)]
        stats.tiles = len(tiles)
        if resume is not None and not resume.uniform and resume.tiles != len(tiles):
            raise ValueError(f"checkpoint has {resume.tiles} tiles but this device would use {len(tiles)}; resume on the same engine/device")
        count_full = np.zeros((Hs, Ws), dtype=np.float32)
        depth_full = np.zeros((Hs, Ws), dtype=np.float32) if needs.depth else None
        zmin_full = np.full((Hs, Ws), np.inf, dtype=np.float32) if needs.zmin else None
        cv_full = np.zeros((Hs, Ws), dtype=np.float32) if needs.color else None

        total_steps = math.ceil(budget / n_traj)
        done_all = 0
        passes = 0
        t_acc = time.perf_counter()
        last_partial = time.perf_counter()
        active = [ti for ti in range(len(tiles)) if ti >= plan.skip_tiles]
        steps_all = max(1, total_steps * len(active))
        rounds = 1 if len(active) <= 1 else INTERLEAVE_ROUNDS
        finish_at: int | None = None

        # per-tile trajectory textures persist across rounds; accumulators are re-created per visit
        tile_state: dict[int, dict] = {}
        for ti in active:
            st = seed_from_points(n_traj, plan.seed, sample_pts, framing.radius * 1e-2)
            state = np.zeros((n_traj, 4), dtype=np.float32)
            state[:, 0], state[:, 1], state[:, 2], state[:, 3] = st.X, st.Y, st.Z, st.W
            tex_state = [ctx.texture((TEX_W, TEX_H), 4, state.tobytes(), dtype="f4") for _ in range(2)]
            tex_rng = [ctx.texture((TEX_W, TEX_H), 1, st.RS.astype(np.uint32).tobytes(), dtype="u4") for _ in range(2)]
            tex_old = ctx.texture((TEX_W, TEX_H), 4, np.zeros((n_traj, 4), dtype=np.float32).tobytes(), dtype="f4")
            for t_ in tex_state + tex_rng + [tex_old]:
                t_.filter = (moderngl.NEAREST, moderngl.NEAREST)
            tile_state[ti] = {
                "state": tex_state, "rng": tex_rng, "old": tex_old,
                "fbo": [ctx.framebuffer(color_attachments=[tex_state[i], tex_rng[i], tex_old]) for i in range(2)],
                "cur": 0, "t_base": 0.0, "steps_done": 0, "warmed": False,
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
                    tex_acc = ctx.texture((tw, th), 4, dtype="f4")
                    tex_zmin = ctx.texture((tw, th), 4, dtype="f4")
                    fbo_acc = ctx.framebuffer(color_attachments=[tex_acc])
                    fbo_zmin = ctx.framebuffer(color_attachments=[tex_zmin])
                    if rnd == 0:
                        fbo_acc.clear(0.0, 0.0, 0.0, 0.0)
                        fbo_zmin.clear(1e30, 0.0, 0.0, 0.0)
                    else:  # restore the accumulators of this tile from the host copies
                        acc = np.zeros((th, tw, 4), dtype=np.float32)
                        acc[..., 0] = count_full[ty : ty + th, tx : tx + tw]
                        if depth_full is not None:
                            acc[..., 1] = depth_full[ty : ty + th, tx : tx + tw]
                        if cv_full is not None:
                            acc[..., 2] = cv_full[ty : ty + th, tx : tx + tw]
                        tex_acc.write(acc.tobytes())
                        zb = np.zeros((th, tw, 4), dtype=np.float32)
                        zb[..., 0] = 1e30 if zmin_full is None else np.where(np.isfinite(zmin_full[ty : ty + th, tx : tx + tw]), zmin_full[ty : ty + th, tx : tx + tw], 1e30)
                        tex_zmin.write(zb.tobytes())
                    _set(prog.draw, "u_size", (float(tw), float(th)))
                    _set(prog.draw, "u_c", (float(cx - tx), float(cy - ty)))

                    def update(ts=ts) -> None:
                        cur = ts["cur"]
                        nxt = 1 - cur
                        ts["state"][cur].use(0)
                        ts["rng"][cur].use(1)
                        _set(prog.update, "u_state", 0)
                        _set(prog.update, "u_rng", 1)
                        _set(prog.update, "u_t0", float(ts["t_base"]))
                        ts["t_base"] += substeps
                        ts["fbo"][nxt].use()
                        ctx.disable(moderngl.BLEND)
                        ctx.viewport = (0, 0, TEX_W, TEX_H)
                        prog.vao_quad.render(moderngl.TRIANGLES, vertices=3)
                        ts["cur"] = nxt

                    def draw(ts=ts, tw=tw, th=th, fbo_acc=fbo_acc, fbo_zmin=fbo_zmin) -> None:
                        ts["state"][ts["cur"]].use(0)
                        ts["old"].use(1)
                        _set(prog.draw, "u_state", 0)
                        _set(prog.draw, "u_old", 1)
                        ctx.enable(moderngl.BLEND)
                        ctx.blend_func = moderngl.ONE, moderngl.ONE
                        ctx.viewport = (0, 0, tw, th)
                        mode = moderngl.LINES if gap_fill else moderngl.POINTS
                        nverts = 2 * n_traj if gap_fill else n_traj
                        _set(prog.draw, "u_line", 1 if gap_fill else 0)
                        fbo_acc.use()
                        ctx.blend_equation = moderngl.FUNC_ADD
                        _set(prog.draw, "u_mode", 0)
                        prog.vao_points.render(mode, vertices=nverts)
                        if needs.zmin:
                            fbo_zmin.use()
                            ctx.blend_equation = moderngl.MIN
                            _set(prog.draw, "u_mode", 1)
                            prog.vao_points.render(mode, vertices=nverts)
                            ctx.blend_equation = moderngl.FUNC_ADD

                    def readback(tex_acc=tex_acc, tex_zmin=tex_zmin, tx=tx, ty=ty, tw=tw, th=th) -> None:
                        acc = np.frombuffer(tex_acc.read(), dtype=np.float32).reshape(th, tw, 4)
                        count_full[ty : ty + th, tx : tx + tw] = acc[..., 0]
                        if depth_full is not None:
                            depth_full[ty : ty + th, tx : tx + tw] = acc[..., 1]
                        if cv_full is not None:
                            cv_full[ty : ty + th, tx : tx + tw] = acc[..., 2]
                        if zmin_full is not None:
                            z = np.frombuffer(tex_zmin.read(), dtype=np.float32).reshape(th, tw, 4)[..., 0]
                            zmin_full[ty : ty + th, tx : tx + tw] = np.where(z > 1e29, np.inf, z)

                    try:
                        ctx.point_size = 1.0
                        if not ts["warmed"]:
                            for _ in range(stats.warmup_steps):
                                update()
                            ts["warmed"] = True
                        batch = 8
                        while ts["steps_done"] < round_target:
                            cancel.check()
                            if cancel.finishing and finish_at is None:  # soft stop: every tile ends at this count
                                finish_at = max(ts["steps_done"], min(total_steps, MIN_FINISH_STEPS))
                                round_target = min(round_target, finish_at)
                                stats.finished_early = True
                                stats.notes.append(f"Finished early on request at {100 * finish_at / total_steps:.0f} % of the budget.")
                                if ts["steps_done"] >= round_target:
                                    break
                            k = min(batch, round_target - ts["steps_done"])
                            tp = time.perf_counter()
                            for _ in range(k):
                                update()
                                draw()
                            ctx.finish()
                            dtp = time.perf_counter() - tp
                            ts["steps_done"] += k
                            done_all += k
                            passes += k
                            if dtp > 0:
                                batch = int(min(max(2, k * TARGET_PASS_SECONDS / dtp), 512))
                            frac = done_all / steps_all
                            tracker.update(0.05 + 0.9 * frac, f"tile {ti + 1}/{len(tiles)} · round {rnd + 1}/{rounds} · {done_all * n_traj / 1e6:.1f} M points")
                            if sink is not None and len(active) == 1 and (time.perf_counter() - last_partial > 0.5 or ts["steps_done"] >= total_steps):
                                readback()
                                emit_partial(frac)
                        readback()
                    finally:
                        for r in (fbo_acc, fbo_zmin, tex_acc, tex_zmin):
                            r.release()
                if sink is not None and len(active) > 1:
                    emit_partial(done_all / steps_all)
                if finish_at is not None and all(t["steps_done"] >= finish_at for t in tile_state.values()):
                    break
        finally:
            for ts in tile_state.values():
                for r in (*ts["fbo"], ts["old"], *ts["state"], *ts["rng"]):
                    r.release()
        if finish_at is not None:
            total_steps = finish_at

        stats.accumulate_seconds = time.perf_counter() - t_acc
        stats.iterations_done = total_steps * n_traj
        stats.tiles_done = 0
        stats.passes = passes
        stats.points_plotted = float(count_full.sum())
        result = plan.finish(self._assemble(settings, framing, stats, count_full, depth_full, zmin_full, cv_full, ss, True))
        summarize(result, look.percentile)
        stats.elapsed = time.perf_counter() - t_start
        tracker.update(1.0, "accumulated", force=True)
        return result

    @staticmethod
    def _assemble(settings, framing, stats, count, depth, zmin, cv, ss, complete) -> RenderResult:
        c = downsample(count.astype(np.float64), ss, "sum").astype(np.float32)
        d = downsample(depth.astype(np.float64), ss, "sum").astype(np.float32) if depth is not None else None
        z = downsample(zmin, ss, "min").astype(np.float32) if zmin is not None else None
        v = downsample(cv.astype(np.float64), ss, "sum").astype(np.float32) if cv is not None else None
        return RenderResult(settings, c, framing, stats, d, z, v, complete)


selector.register("gl_points", GLPointsEngine)
