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
from dataclasses import dataclass
from typing import Any

import numpy as np

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.accumulators import Needs
from attractr.core.render.engines import selector
from attractr.core.render.engines.base import EngineCaps
from attractr.core.render.engines.gl_common import (
    GLContextPool,
    GLInfo,
    GLUnavailable,
    alloc_texture,
    assemble_iterate_shader,
    compile_compute,
    gpu_budget,
    host_memory_budget,
    is_software_renderer,
    micro_benchmark,
    probe_compute,
    query_info,
    read_shader,
)
from attractr.core.render.engines.gpu_base import DeviceSession, PassTuning, TiledGpuEngine
from attractr.core.render.engines.setup import RenderPlan, padded_splat_kernel
from attractr.core.render.engines.state import seed_from_points
from attractr.core.render.engines.tiling import MAX_TILE_SIDE, PLANE_NAMES, HostPlanes, Tile
from attractr.core.render.result import RenderStats
from attractr.core.render.settings import RenderSettings

log = logging.getLogger(__name__)

LOCAL_SIZE = 128
DEFAULT_TRAJECTORIES = 65536
MAX_STEPS_PER_PASS = 256  # keeps 24.8 fixed-point sums below 2^32 per pass
TARGET_PASS_SECONDS = 0.3


def _set(prog, name: str, value) -> None:
    """Set a uniform if the compiler kept it (unused uniforms are optimised away)."""
    if name in prog:
        prog[name].value = value


def _write(prog, name: str, data: bytes) -> None:
    """Write raw bytes into a uniform (matrices / arrays) if the compiler kept it."""
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


@dataclass
class _GLDevice:
    """Per-render device handle: the context, its capabilities, the compiled shaders."""

    ctx: Any
    info: GLInfo
    prog: _Programs
    fp64: bool
    cf: Any


class GLComputeEngine(TiledGpuEngine):
    """Interactive GL 4.3 compute engine (``gl_compute``); see the module docstring."""
    id = "gl_compute"
    name = "GPU compute (OpenGL 4.3)"
    precision_profile = False
    tuning = PassTuning(max_steps=MAX_STEPS_PER_PASS, target_seconds=TARGET_PASS_SECONDS)

    def __init__(self) -> None:
        self.pool = GLContextPool(430)
        self._programs: dict[tuple, _Programs] = {}
        self._info: GLInfo | None = None

    # ── probe ──────────────────────────────────────────────────────────────────
    def probe(self) -> EngineCaps:
        """Create the context, run the atomics self-test and a micro-benchmark; never raises."""
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

    # ── TiledGpuEngine hooks ───────────────────────────────────────────────────
    def _open(self, settings: RenderSettings, spec: AttractorSpec, tracker: ProgressTracker) -> DeviceSession:
        """Context + capabilities + compiled shaders for ``spec`` at the requested precision."""
        q = settings.quality
        ctx = self.pool.get()
        info = self._info or query_info(ctx)
        fp64 = resolve_precision(q.precision, info.fp64, self.precision_profile)
        if q.precision == "fp64" and not fp64:
            log.warning("fp64 requested but GL_ARB_gpu_shader_fp64 is not available; using fp32")
        stats = RenderStats(engine=self.id, device=info.renderer, precision="fp64" if fp64 else "fp32")
        cf = spec.compiled(q.integrator)
        key = (id(ctx), cf.source_hash, q.integrator, fp64)
        if key not in self._programs:
            self._programs[key] = _Programs(ctx, cf, q.integrator, fp64)
        tracker.update(0.0, "shaders ready")
        return DeviceSession(stats, _GLDevice(ctx, info, self._programs[key], fp64, cf), min(info.max_texture_size, MAX_TILE_SIDE))

    def _trajectory_count(self, settings: RenderSettings) -> int:
        return int(math.ceil((settings.quality.trajectories or DEFAULT_TRAJECTORIES) / LOCAL_SIZE) * LOCAL_SIZE)

    def _budget_bytes(self) -> int:
        """Tile-image budget from free VRAM (host RAM for software renderers, env override first)."""
        ctx = self.pool.get()
        info = self._info or query_info(ctx)
        if is_software_renderer(info.renderer):
            return host_memory_budget()
        return gpu_budget(ctx, os.environ.get("ATTRACTR_GPU_BUDGET_MB"))

    def _bytes_per_pixel(self, plan: RenderPlan) -> int:
        return image_bytes_per_pixel(plan.needs)

    def _visitor(self, session: DeviceSession, plan: RenderPlan, planes: HostPlanes, n_traj: int,
                 active: list[int], tile_size: tuple[int, int]) -> _GLTileVisitor:
        return _GLTileVisitor(session.device, plan, planes, n_traj, active, tile_size)


def _set_render_uniforms(prog: _Programs, plan: RenderPlan, cf, n_traj: int) -> None:
    """Uniforms that stay constant for the whole render."""
    it = prog.iterate
    cv_lo, cv_hi = plan.cv_range
    _set(it, "u_substeps", plan.substeps)
    _set(it, "u_dt", float(plan.dt))
    _write(it, "u_R", plan.rotation.astype(np.float32).T.tobytes())  # GLSL mat3 is column-major → transpose
    _set(it, "u_center", tuple(float(c) for c in plan.framing.center))
    _set(it, "u_inv_radius", float(1.0 / plan.framing.radius))
    _set(it, "u_focal", float(plan.focal))
    _set(it, "u_persp", float(plan.camera.perspective))
    _set(it, "u_splat_r", int(plan.quality.splat_radius))
    _write(it, "u_kern", padded_splat_kernel(plan.quality.splat_radius).tobytes())
    _set(it, "u_gap_fill", int(plan.gap_fill))
    _set(it, "u_color_code", int(plan.needs.color_code))
    _set(it, "u_ic", tuple(float(v) for v in plan.spec.ic))
    _set(it, "u_esc_lo", tuple(float(v) for v in plan.escape[0:6:2]))
    _set(it, "u_esc_hi", tuple(float(v) for v in plan.escape[1:6:2]))
    _set(it, "u_esc_cfg", tuple(float(v) for v in plan.escape[6:9]))
    _set(it, "u_jitter", float(plan.spec.jitter))
    _set(it, "u_inv_n", float(1.0 / n_traj))
    _set(it, "u_cv_range", (cv_lo, 1.0 / (cv_hi - cv_lo)))
    _set(prog.merge, "u_cv_range", (cv_lo, cv_hi - cv_lo))
    pbuf = np.zeros(max(1, len(cf.param_names)), dtype=np.float32)
    pbuf[: plan.params.size] = plan.params
    _write(it, "u_p", pbuf.tobytes())


def image_bytes_per_pixel(needs: Needs) -> int:
    """Bytes of pass + accumulator images per tile pixel (a uint and a float per needed plane)."""
    return 4 * 2 * needs.buffer_count


class _TileImages:
    """One set of tile images sized for the largest tile, reused by every tile and round:
    fixed-point pass images (uint) and float accumulators for the planes the look needs;
    unused image units get a 1×1 dummy.  Allocation failures surface as
    :class:`GLUnavailable` (→ CPU fallback) instead of a driver abort later on."""

    def __init__(self, ctx, w: int, h: int, needs: Needs) -> None:
        wanted = [True, bool(needs.depth), bool(needs.zmin), bool(needs.color)]
        self.uint: list = []
        self.float: list = []
        self.fbo: list = []
        self._owned: list = []
        try:
            dummy_u = alloc_texture(ctx, (1, 1), 1, "u4", "allocating a dummy image")
            dummy_f = alloc_texture(ctx, (1, 1), 1, "f4", "allocating a dummy image")
            self._owned += [dummy_u, dummy_f]
            for idx in range(4):
                if wanted[idx]:
                    tex = alloc_texture(ctx, (w, h), 1, "u4", "allocating a pass image")
                    tex.write(np.full(w * h, 0xFFFFFFFF if idx == 2 else 0, dtype=np.uint32).tobytes())
                    self._owned.append(tex)
                    self.uint.append(tex)
                else:
                    self.uint.append(dummy_u)
            for idx in range(4):
                if wanted[idx]:
                    tex = alloc_texture(ctx, (w, h), 1, "f4", "allocating an accumulator image")
                    fbo = ctx.framebuffer(color_attachments=[tex])
                    self._owned += [tex, fbo]
                    self.float.append(tex)
                    self.fbo.append(fbo)
                else:
                    self.float.append(dummy_f)
                    self.fbo.append(None)
            ctx.finish()
        except Exception:
            self.release()
            raise

    def bind(self, merge: bool = False) -> None:
        """Bind the pass images to units 0–3 (and, for the merge shader, the accumulators to 4–7)."""
        for u, tex in enumerate(self.uint):
            tex.bind_to_image(u, read=True, write=True)
        if merge:
            for u, tex in enumerate(self.float):
                tex.bind_to_image(4 + u, read=True, write=True)

    def upload(self, planes: HostPlanes, tile: Tile, fresh: bool) -> None:
        """Restore a tile's accumulators (initial values when ``fresh``) into the shared images."""
        for name, _ in planes.planes():
            self.float[PLANE_NAMES.index(name)].write(planes.slab(name, tile, fresh).tobytes(), viewport=(0, 0, tile.w, tile.h))

    def readback(self, planes: HostPlanes, tile: Tile) -> None:
        """Copy the float accumulators of ``tile`` from the shared images into the host planes."""
        for name, _ in planes.planes():
            raw = self.fbo[PLANE_NAMES.index(name)].read(viewport=(0, 0, tile.w, tile.h), components=1, dtype="f4")
            planes.store(name, tile, np.frombuffer(raw, dtype=np.float32))

    def release(self) -> None:
        """Free every GL object owned here (safe to call twice)."""
        for r in reversed(self._owned):
            r.release()
        self._owned.clear()


class _GLTileVisitor:
    """:class:`TileVisitor` for the compute engines: per-tile trajectory buffers on the device,
    one shared image set (allocated on first use), dispatch + merge per pass."""

    def __init__(self, device: _GLDevice, plan: RenderPlan, planes: HostPlanes, n_traj: int, active: list[int],
                 image_size: tuple[int, int]) -> None:
        self.ctx, self.prog, self.fp64 = device.ctx, device.prog, device.fp64
        self.plan, self.planes, self.n_traj = plan, planes, n_traj
        self.groups = n_traj // LOCAL_SIZE
        self.image_size = image_size
        self.images: _TileImages | None = None
        self.state: dict[int, dict] = {}
        self._current: tuple[int, Tile] | None = None
        _set_render_uniforms(device.prog, plan, device.cf, n_traj)
        self._create_tile_state(active)

    def _create_tile_state(self, indices: list[int]) -> None:
        """Seed the trajectories of every active tile (identical seeds → seamless tiles)."""
        plan, n = self.plan, self.n_traj
        for index in indices:
            st = seed_from_points(n, plan.resume.seed, plan.sample_pts, plan.framing.radius * 1e-2)
            state = np.zeros((n, 4), dtype=np.float64 if self.fp64 else np.float32)
            state[:, 0], state[:, 1], state[:, 2], state[:, 3] = st.X, st.Y, st.Z, st.W
            self.state[index] = {
                "state": self.ctx.buffer(state.tobytes()), "rng": self.ctx.buffer(st.RS.astype(np.uint32).tobytes()),
                "prev": self.ctx.buffer(np.zeros((n, 4), dtype=np.float32).tobytes()),
                "prevd": self.ctx.buffer(np.zeros((n, 4), dtype=np.float32).tobytes()),
                "stats": self.ctx.buffer(np.zeros(4, dtype=np.uint32).tobytes()),
                "esc": self.ctx.buffer(st.escape_state().tobytes()),
                "t_base": 0.0,
            }

    # ── TileVisitor ────────────────────────────────────────────────────────────
    def select(self, index: int, tile: Tile, fresh: bool) -> None:
        """Bind the tile's trajectory buffers, restore its accumulators and set the tile uniforms."""
        if self.images is None:  # allocated on first use so a failure is raised from inside the schedule
            self.images = _TileImages(self.ctx, *self.image_size, self.plan.needs)
        self.images.upload(self.planes, tile, fresh)
        ts = self.state[index]
        for binding, key in enumerate(("state", "rng", "prev", "prevd", "stats", "esc")):
            ts[key].bind_to_storage_buffer(binding)
        self.images.bind()
        _set(self.prog.iterate, "u_size", (tile.w, tile.h))
        _set(self.prog.iterate, "u_c", (float(self.plan.cx - tile.x), float(self.plan.cy - tile.y)))
        self._current = (index, tile)

    def warm_up(self, index: int, steps: int) -> None:
        """Unplotted steps (in kernel-sized chunks), then forget the previous points."""
        while steps > 0:
            k = min(steps, MAX_STEPS_PER_PASS)
            self._dispatch(index, k, plot=0)
            steps -= k
        self.state[index]["prev"].write(np.zeros((self.n_traj, 4), dtype=np.float32).tobytes())

    def run_pass(self, index: int, steps: int) -> None:
        """Plot ``steps`` steps, merge the fixed-point pass images into the accumulators, wait."""
        self._dispatch(index, steps, plot=1)
        self._merge()
        self.ctx.finish()

    def readback(self, index: int, tile: Tile) -> None:
        """Copy the float accumulators of ``tile`` from the shared images into the host planes."""
        assert self.images is not None
        self.images.readback(self.planes, tile)

    # ── internals ──────────────────────────────────────────────────────────────
    def _dispatch(self, index: int, steps: int, plot: int) -> None:
        """One iterate-shader dispatch of ``steps`` steps for the tile's trajectories."""
        it, needs, ts = self.prog.iterate, self.plan.needs, self.state[index]
        _set(it, "u_steps", int(steps))
        _set(it, "u_t0", float(ts["t_base"]))
        _set(it, "u_flags", (int(needs.depth), int(needs.zmin), int(needs.color), plot))
        it.run(group_x=self.groups)
        self.ctx.memory_barrier()
        ts["t_base"] += steps * self.plan.substeps

    def _merge(self) -> None:
        """Add the pass images into the float accumulators and clear them (merge.comp)."""
        assert self.images is not None and self._current is not None
        m, needs, (_, tile) = self.prog.merge, self.plan.needs, self._current
        self.images.bind(merge=True)
        _set(m, "u_size", (tile.w, tile.h))
        _set(m, "u_flags", (int(needs.depth), int(needs.zmin), int(needs.color), 0))
        m.run(group_x=(tile.w + 15) // 16, group_y=(tile.h + 15) // 16)
        self.ctx.memory_barrier()

    def collect_stats(self) -> tuple[int, float]:
        """(restarts, plotted weight) summed over the tiles' device counters."""
        restarts, plotted = 0, 0.0
        for ts in self.state.values():
            sv = np.frombuffer(ts["stats"].read(), dtype=np.uint32)
            restarts += int(sv[0])
            plotted += (int(sv[2]) * 4294967296.0 + int(sv[1])) / 16.0
        return restarts, plotted

    def release(self) -> None:
        """Free every GL object owned here (safe to call twice)."""
        if self.images is not None:
            self.images.release()
            self.images = None
        for ts in self.state.values():
            for key in ("state", "rng", "prev", "prevd", "stats", "esc"):
                ts[key].release()
        self.state.clear()


class GLPrecisionEngine(GLComputeEngine):
    """Same shader core; selected for final renders.  Tiles + supersampling come from the
    settings; this profile additionally forces splat anti-aliasing when none was asked."""

    id = "gl_precision"
    name = "GPU precision (OpenGL 4.3 compute, tiled)"
    precision_profile = True


selector.register("gl_compute", GLComputeEngine)
selector.register("gl_precision", GLPrecisionEngine)
