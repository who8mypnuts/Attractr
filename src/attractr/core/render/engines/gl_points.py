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
import os
from dataclasses import dataclass
from typing import Any

import moderngl
import numpy as np

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.formula.codegen_glsl import generate_gpu_source
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.engines import selector
from attractr.core.render.engines.base import EngineCaps
from attractr.core.render.engines.gl_common import (
    GLSL_PRECISION_FP32,
    GLContextPool,
    GLUnavailable,
    alloc_texture,
    gpu_budget,
    host_memory_budget,
    is_software_renderer,
    query_info,
    read_shader,
)
from attractr.core.render.engines.gpu_base import DeviceSession, PassTuning, TiledGpuEngine
from attractr.core.render.engines.setup import RenderPlan
from attractr.core.render.engines.state import seed_from_points
from attractr.core.render.engines.tiling import HostPlanes, Tile
from attractr.core.render.result import RenderStats
from attractr.core.render.settings import RenderSettings

log = logging.getLogger(__name__)

TEX_W = 256  # trajectories live in a 256×256 RGBA32F texture (65 536 of them)
TEX_H = 256
TARGET_PASS_SECONDS = 0.25
MAX_STEPS_PER_PASS = 512
TILE_MAX = 4096
TARGET_BYTES_PER_PIXEL = 32  # two RGBA32F render targets
NO_DEPTH = 1e30  # "no point yet" sentinel of the MIN-blended depth target

QUAD_VERT = """#version 330
void main() {
    vec2 p = vec2((gl_VertexID == 1) ? 3.0 : -1.0, (gl_VertexID == 2) ? 3.0 : -1.0);
    gl_Position = vec4(p, 0.0, 1.0);
}
"""


def _assemble(name: str, cf, integrator: str) -> str:
    """Fill a shader template with the precision header, prelude and generated step()."""
    src = read_shader(name)
    gen = generate_gpu_source(cf.program, cf.analysis, integrator if cf.kind == "flow" else "rk4", "glsl")
    return (src.replace("__NPARAMS__", str(max(1, len(cf.param_names))))
            .replace("//__PRECISION__", GLSL_PRECISION_FP32)
            .replace("//__PRELUDE__", read_shader("prelude.glsl"))
            .replace("//__STEP__", gen))


def _set(prog, name, value) -> None:
    """Set a uniform the compiler kept (unused uniforms are optimised away)."""
    if name in prog:
        prog[name].value = value


def _write(prog, name, data: bytes) -> None:
    """Write raw bytes into a uniform (matrices / arrays) if the compiler kept it."""
    if name in prog:
        prog[name].write(data)


class _Programs:
    """Compiled update (fragment) and draw (vertex) programs for one formula on one context."""
    def __init__(self, ctx, cf, integrator: str) -> None:
        try:
            self.update = ctx.program(vertex_shader=QUAD_VERT, fragment_shader=_assemble("points_update.frag", cf, integrator))
            self.draw = ctx.program(vertex_shader=_assemble("points_draw.vert", cf, integrator), fragment_shader=read_shader("points_draw.frag"))
        except Exception as exc:  # noqa: BLE001
            raise GLUnavailable(f"gl_points shaders failed to compile: {exc}") from exc
        self.vao_quad = ctx.vertex_array(self.update, [])
        self.vao_points = ctx.vertex_array(self.draw, [])


class GLPointsEngine(TiledGpuEngine):
    """OpenGL 3.3 fallback engine (``gl_points``); see the module docstring."""
    id = "gl_points"
    name = "GPU points (OpenGL 3.3 fallback)"
    tuning = PassTuning(min_steps=2, max_steps=MAX_STEPS_PER_PASS, initial_steps=8, target_seconds=TARGET_PASS_SECONDS)

    def __init__(self) -> None:
        self.pool = GLContextPool(330)
        self._programs: dict[tuple, _Programs] = {}
        self._info = None

    def probe(self) -> EngineCaps:
        """Create the context and check for OpenGL 3.3; never raises."""
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

    # ── TiledGpuEngine hooks ───────────────────────────────────────────────────
    def _open(self, settings: RenderSettings, spec: AttractorSpec, tracker: ProgressTracker) -> DeviceSession:
        """Context + compiled programs for ``spec`` (fp32 only)."""
        q = settings.quality
        ctx = self.pool.get()
        info = self._info or query_info(ctx)
        stats = RenderStats(engine=self.id, device=info.renderer, precision="fp32")
        if q.splat_radius > 0:
            stats.notes.append("gl_points ignores the splat radius (nearest-pixel points; use supersampling)")
        cf = spec.compiled(q.integrator)
        key = (id(ctx), cf.source_hash, q.integrator)
        if key not in self._programs:
            self._programs[key] = _Programs(ctx, cf, q.integrator)
        tracker.update(0.0, "shaders ready")
        return DeviceSession(stats, _PointsDevice(ctx, self._programs[key], cf), min(TILE_MAX, info.max_texture_size))

    def _trajectory_count(self, settings: RenderSettings) -> int:
        return TEX_W * TEX_H  # fixed by the state-texture size

    def _budget_bytes(self) -> int:
        """Render-target budget from free VRAM (host RAM for software renderers, env override first)."""
        ctx = self.pool.get()
        info = self._info or query_info(ctx)
        if is_software_renderer(info.renderer):
            return host_memory_budget()
        return gpu_budget(ctx, os.environ.get("ATTRACTR_GPU_BUDGET_MB"))

    def _bytes_per_pixel(self, plan: RenderPlan) -> int:
        return TARGET_BYTES_PER_PIXEL

    def _visitor(self, session: DeviceSession, plan: RenderPlan, planes: HostPlanes, n_traj: int,
                 active: list[int], tile_size: tuple[int, int]) -> _PointsTileVisitor:
        return _PointsTileVisitor(session.device, plan, planes, n_traj, active, tile_size)


@dataclass
class _PointsDevice:
    """Per-render device handle: context, compiled update / draw programs, compiled formula."""

    ctx: Any
    prog: _Programs
    cf: Any


def _set_render_uniforms(prog: _Programs, plan: RenderPlan, cf, n_traj: int) -> None:
    """Uniforms that stay constant for the whole render."""
    pbuf = np.zeros(max(1, len(cf.param_names)), dtype=np.float32)
    pbuf[: plan.params.size] = plan.params
    for pr in (prog.update, prog.draw):
        _write(pr, "u_p", pbuf.tobytes())
    _set(prog.update, "u_substeps", plan.substeps)
    _set(prog.update, "u_dt", float(plan.dt))
    _set(prog.update, "u_ic", tuple(float(v) for v in plan.spec.ic))
    _set(prog.update, "u_jitter", float(plan.spec.jitter))
    _set(prog.draw, "u_tex_w", TEX_W)
    _write(prog.draw, "u_R", plan.rotation.astype(np.float32).T.tobytes())
    _set(prog.draw, "u_center", tuple(float(c) for c in plan.framing.center))
    _set(prog.draw, "u_inv_radius", float(1.0 / plan.framing.radius))
    _set(prog.draw, "u_focal", float(plan.focal))
    _set(prog.draw, "u_persp", float(plan.camera.perspective))
    _set(prog.draw, "u_color_code", int(plan.needs.color_code))
    _set(prog.draw, "u_inv_n", float(1.0 / n_traj))


class _PointsTileVisitor:
    """:class:`TileVisitor` for the point-splat engine: ping-pong state textures per tile and one
    shared pair of RGBA32F render targets (Σ count / depth / colour, and nearest depth)."""

    def __init__(self, device: _PointsDevice, plan: RenderPlan, planes: HostPlanes, n_traj: int, active: list[int],
                 target_size: tuple[int, int]) -> None:
        self.ctx, self.prog, self.plan, self.planes, self.n_traj = device.ctx, device.prog, plan, planes, n_traj
        self.target_size = target_size
        self.targets: tuple | None = None  # (tex_acc, tex_zmin, fbo_acc, fbo_zmin)
        self.state: dict[int, dict] = {}
        self._current: tuple[int, Tile] | None = None
        _set_render_uniforms(device.prog, plan, device.cf, n_traj)
        self._create_tile_state(active)

    def collect_stats(self) -> tuple[int, float]:
        """(restarts, plotted weight): the point shader keeps no counters, so plotted = Σ count."""
        return 0, float(self.planes.count.sum())

    def _create_tile_state(self, indices: list[int]) -> None:
        """Seed each active tile's trajectories into its ping-pong state / RNG textures."""
        plan, n = self.plan, self.n_traj
        for index in indices:
            st = seed_from_points(n, plan.resume.seed, plan.sample_pts, plan.framing.radius * 1e-2)
            state = np.zeros((n, 4), dtype=np.float32)
            state[:, 0], state[:, 1], state[:, 2], state[:, 3] = st.X, st.Y, st.Z, st.W
            tex_state = [self.ctx.texture((TEX_W, TEX_H), 4, state.tobytes(), dtype="f4") for _ in range(2)]
            tex_rng = [self.ctx.texture((TEX_W, TEX_H), 1, st.RS.astype(np.uint32).tobytes(), dtype="u4") for _ in range(2)]
            tex_old = self.ctx.texture((TEX_W, TEX_H), 4, np.zeros((n, 4), dtype=np.float32).tobytes(), dtype="f4")
            for t in tex_state + tex_rng + [tex_old]:
                t.filter = (moderngl.NEAREST, moderngl.NEAREST)
            self.state[index] = {
                "state": tex_state, "rng": tex_rng, "old": tex_old,
                "fbo": [self.ctx.framebuffer(color_attachments=[tex_state[i], tex_rng[i], tex_old]) for i in range(2)],
                "cur": 0, "t_base": 0.0,
            }

    def _make_targets(self) -> None:
        """Allocate the shared accumulation / depth render targets (sized for the largest tile)."""
        w, h = self.target_size
        tex_acc = alloc_texture(self.ctx, (w, h), 4, "f4", "allocating the accumulation target")
        try:
            tex_zmin = alloc_texture(self.ctx, (w, h), 4, "f4", "allocating the depth target")
        except Exception:
            tex_acc.release()
            raise
        self.targets = (tex_acc, tex_zmin, self.ctx.framebuffer(color_attachments=[tex_acc]), self.ctx.framebuffer(color_attachments=[tex_zmin]))

    # ── TileVisitor ────────────────────────────────────────────────────────────
    def select(self, index: int, tile: Tile, fresh: bool) -> None:
        """Point the render targets at ``tile``, restore (or clear) its accumulators, set tile uniforms."""
        if self.targets is None:
            self._make_targets()
        tex_acc, tex_zmin, fbo_acc, fbo_zmin = self.targets
        fbo_acc.viewport = fbo_zmin.viewport = (0, 0, tile.w, tile.h)  # edge tiles use a corner of the shared targets
        if fresh:
            fbo_acc.clear(0.0, 0.0, 0.0, 0.0)
            fbo_zmin.clear(NO_DEPTH, 0.0, 0.0, 0.0)
        else:
            tex_acc.write(self._packed_accumulators(tile).tobytes(), viewport=(0, 0, tile.w, tile.h))
            tex_zmin.write(self._packed_zmin(tile).tobytes(), viewport=(0, 0, tile.w, tile.h))
        _set(self.prog.draw, "u_size", (float(tile.w), float(tile.h)))
        _set(self.prog.draw, "u_c", (float(self.plan.cx - tile.x), float(self.plan.cy - tile.y)))
        self._current = (index, tile)

    def warm_up(self, index: int, steps: int) -> None:
        """Advance the tile's trajectories without drawing."""
        for _ in range(steps):
            self._update(index)

    def run_pass(self, index: int, steps: int) -> None:
        """``steps`` × (advance + splat) and wait for the GPU."""
        for _ in range(steps):
            self._update(index)
            self._draw(index)
        self.ctx.finish()

    def readback(self, index: int, tile: Tile) -> None:
        """Unpack the RGBA render targets of ``tile`` into the host planes."""
        assert self.targets is not None
        _, _, fbo_acc, fbo_zmin = self.targets
        acc = np.frombuffer(fbo_acc.read(viewport=(0, 0, tile.w, tile.h), components=4, dtype="f4"), dtype=np.float32).reshape(tile.h, tile.w, 4)
        planes = self.planes
        planes.store("count", tile, acc[..., 0])
        if planes.depth is not None:
            planes.store("depth", tile, acc[..., 1])
        if planes.cv is not None:
            planes.store("cv", tile, acc[..., 2])
        if planes.zmin is not None:
            z = np.frombuffer(fbo_zmin.read(viewport=(0, 0, tile.w, tile.h), components=4, dtype="f4"), dtype=np.float32).reshape(tile.h, tile.w, 4)[..., 0]
            planes.store("zmin", tile, np.where(z > NO_DEPTH * 0.1, np.inf, z))

    # ── internals ──────────────────────────────────────────────────────────────
    def _packed_accumulators(self, tile: Tile) -> np.ndarray:
        """RGBA texel layout of the accumulation target: (count, Σdepth, Σcolour, unused)."""
        acc = np.zeros((tile.h, tile.w, 4), dtype=np.float32)
        acc[..., 0] = self.planes.slab("count", tile)
        if self.planes.depth is not None:
            acc[..., 1] = self.planes.slab("depth", tile)
        if self.planes.cv is not None:
            acc[..., 2] = self.planes.slab("cv", tile)
        return acc

    def _packed_zmin(self, tile: Tile) -> np.ndarray:
        """RGBA texel layout of the depth target (nearest depth in .r, :data:`NO_DEPTH` where empty)."""
        zb = np.full((tile.h, tile.w, 4), 0.0, dtype=np.float32)
        if self.planes.zmin is None:
            zb[..., 0] = NO_DEPTH
        else:
            z = self.planes.slab("zmin", tile)
            zb[..., 0] = np.where(np.isfinite(z), z, NO_DEPTH)
        return zb

    def _update(self, index: int) -> None:
        """Advance every trajectory one step (ping-pong between the two state textures)."""
        ts = self.state[index]
        cur, nxt = ts["cur"], 1 - ts["cur"]
        ts["state"][cur].use(0)
        ts["rng"][cur].use(1)
        _set(self.prog.update, "u_state", 0)
        _set(self.prog.update, "u_rng", 1)
        _set(self.prog.update, "u_t0", float(ts["t_base"]))
        ts["t_base"] += self.plan.substeps
        ts["fbo"][nxt].use()
        self.ctx.disable(moderngl.BLEND)
        self.ctx.viewport = (0, 0, TEX_W, TEX_H)
        self.prog.vao_quad.render(moderngl.TRIANGLES, vertices=3)
        ts["cur"] = nxt

    def _draw(self, index: int) -> None:
        """Splat every trajectory's current point (additive) and nearest depth (MIN blending)."""
        assert self.targets is not None
        ts = self.state[index]
        _, _, fbo_acc, fbo_zmin = self.targets
        ts["state"][ts["cur"]].use(0)
        ts["old"].use(1)
        _set(self.prog.draw, "u_state", 0)
        _set(self.prog.draw, "u_old", 1)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.ONE, moderngl.ONE
        gap_fill = self.plan.gap_fill
        mode = moderngl.LINES if gap_fill else moderngl.POINTS
        nverts = 2 * self.n_traj if gap_fill else self.n_traj
        _set(self.prog.draw, "u_line", 1 if gap_fill else 0)
        fbo_acc.use()
        self.ctx.blend_equation = moderngl.FUNC_ADD
        _set(self.prog.draw, "u_mode", 0)
        self.prog.vao_points.render(mode, vertices=nverts)
        if self.planes.zmin is not None:
            fbo_zmin.use()
            self.ctx.blend_equation = moderngl.MIN
            _set(self.prog.draw, "u_mode", 1)
            self.prog.vao_points.render(mode, vertices=nverts)
            self.ctx.blend_equation = moderngl.FUNC_ADD

    def release(self) -> None:
        """Free every GL object owned here (safe to call twice)."""
        for r in self.targets or ():
            r.release()
        self.targets = None
        for ts in self.state.values():
            for r in (*ts["fbo"], ts["old"], *ts["state"], *ts["rng"]):
                r.release()
        self.state.clear()


selector.register("gl_points", GLPointsEngine)
