"""OpenCL engine (``opencl``): the GL compute algorithm on any OpenCL 1.2 device — GPUs
from every vendor, and CPUs through POCL / Intel runtimes.  Ships by default; degrades to
"unavailable" when no platform is present."""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import Any

import numpy as np

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.formula.codegen_glsl import generate_gpu_source
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.engines import selector
from attractr.core.render.engines.base import EngineCaps
from attractr.core.render.engines.gl_common import (
    DEFAULT_GPU_BUDGET,
    MAX_GPU_BUDGET,
    MIN_GPU_BUDGET,
    host_memory_budget,
    read_shader,
)
from attractr.core.render.engines.gpu_base import DeviceSession, PassTuning, TiledGpuEngine
from attractr.core.render.engines.setup import RenderPlan, padded_splat_kernel
from attractr.core.render.engines.state import seed_from_points
from attractr.core.render.engines.tiling import MAX_TILE_SIDE, PLANE_FILL, PLANE_NAMES, HostPlanes, Tile
from attractr.core.render.result import RenderStats
from attractr.core.render.settings import RenderSettings

log = logging.getLogger(__name__)

LOCAL_SIZE = 128
DEFAULT_TRAJECTORIES = 65536
MAX_STEPS_PER_PASS = 256
TARGET_PASS_SECONDS = 0.3
DEVICE_MEMORY_FRACTION = 0.25  # of the device's global memory one render may use for tile buffers

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
    """The most capable device: GPUs before CPUs, then the most compute units."""
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


class OpenCLEngine(TiledGpuEngine):
    """OpenCL engine (``opencl``); see the module docstring."""
    id = "opencl"
    name = "OpenCL"
    tuning = PassTuning(max_steps=MAX_STEPS_PER_PASS, target_seconds=TARGET_PASS_SECONDS)

    def __init__(self) -> None:
        self._ctx = None
        self._queue = None
        self._device = None
        self._programs: dict[str, tuple] = {}
        self._prelude = read_shader("prelude.cl")
        self._kernel_src = read_shader("iterate.cl")

    def _ensure(self):
        """The (lazily created) context and command queue."""
        if self._ctx is None:
            import pyopencl as cl

            self._device = _pick_device()
            self._ctx = cl.Context([self._device])
            self._queue = cl.CommandQueue(self._ctx)
        return self._ctx, self._queue

    def probe(self) -> EngineCaps:
        """Pick a device and build a trivial kernel; never raises."""
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
        """Build (and cache) the iterate / merge kernels for ``cf`` at the given precision."""
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

    # ── TiledGpuEngine hooks ───────────────────────────────────────────────────
    def _open(self, settings: RenderSettings, spec: AttractorSpec, tracker: ProgressTracker) -> DeviceSession:
        """Context, queue and compiled kernels for ``spec`` at the requested precision."""
        q = settings.quality
        ctx, queue = self._ensure()
        fp64 = q.precision == "fp64" and "cl_khr_fp64" in self._device.extensions
        if q.precision == "fp64" and not fp64:
            log.warning("fp64 requested but the OpenCL device lacks cl_khr_fp64; using fp32")
        stats = RenderStats(engine=self.id, device=self._device.name.strip(), precision="fp64" if fp64 else "fp32")
        cf = spec.compiled(q.integrator)
        kernels = self._program(cf, q.integrator, fp64)
        tracker.update(0.0, "kernels ready")
        return DeviceSession(stats, _CLDevice(ctx, queue, kernels, fp64), MAX_TILE_SIDE)

    def _trajectory_count(self, settings: RenderSettings) -> int:
        return int(math.ceil((settings.quality.trajectories or DEFAULT_TRAJECTORIES) / LOCAL_SIZE) * LOCAL_SIZE)

    def _budget_bytes(self) -> int:
        """The env override, else a fraction of the device's global memory (free memory is not
        queryable in OpenCL); CPU devices use the host budget."""
        override = os.environ.get("ATTRACTR_GPU_BUDGET_MB")
        if override:
            try:
                return int(float(override) * 1024 * 1024)
            except ValueError:
                pass
        dev = self._device
        if dev is None:
            return DEFAULT_GPU_BUDGET
        if dev.type & _cl_device_type_cpu():
            return host_memory_budget()
        return int(min(max(int(dev.global_mem_size) * DEVICE_MEMORY_FRACTION, MIN_GPU_BUDGET), MAX_GPU_BUDGET))

    def _bytes_per_pixel(self, plan: RenderPlan) -> int:
        return 4 * 2 * plan.needs.buffer_count  # a uint pass buffer and a float accumulator per plane

    def _visitor(self, session: DeviceSession, plan: RenderPlan, planes: HostPlanes, n_traj: int,
                 active: list[int], tile_size: tuple[int, int]) -> _CLTileVisitor:
        return _CLTileVisitor(session.device, plan, planes, n_traj, active, tile_size)


@dataclass
class _CLDevice:
    """Per-render device handle: context, command queue, (iterate, merge) kernels, precision."""

    ctx: Any
    queue: Any
    kernels: tuple
    fp64: bool


def _cl_device_type_cpu() -> int:
    """``cl.device_type.CPU`` (imported lazily so the module loads without pyopencl)."""
    import pyopencl as cl

    return cl.device_type.CPU


def _kernel_params(plan: RenderPlan, n_traj: int) -> np.ndarray:
    """The ``Params`` struct the kernels read (per-tile and per-pass fields are filled later)."""
    cv_lo, cv_hi = plan.cv_range
    P = np.zeros(1, dtype=PARAMS_DTYPE)
    P["substeps"] = plan.substeps
    P["splat_r"] = int(plan.quality.splat_radius)
    P["gap_fill"] = int(plan.gap_fill)
    P["color_code"] = plan.needs.color_code
    P["want_depth"], P["want_zmin"], P["want_color"] = int(plan.needs.depth), int(plan.needs.zmin), int(plan.needs.color)
    P["n"] = n_traj
    P["dt"] = plan.dt
    P["inv_radius"] = 1.0 / plan.framing.radius
    P["focal"] = plan.focal
    P["persp"] = plan.camera.perspective
    P["jitter"] = plan.spec.jitter
    P["inv_n"] = 1.0 / n_traj
    P["cv_lo"], P["cv_inv_range"] = cv_lo, 1.0 / (cv_hi - cv_lo)
    P["R"] = plan.rotation.astype(np.float32).ravel()
    P["center"] = np.asarray(plan.framing.center, dtype=np.float32)
    P["ic"] = np.asarray(plan.spec.ic, dtype=np.float32)
    P["esc_lo"], P["esc_hi"], P["esc_cfg"] = plan.escape[0:6:2], plan.escape[1:6:2], plan.escape[6:9]
    return P


class _CLTileVisitor:
    """:class:`TileVisitor` for OpenCL: per-tile trajectory buffers, one shared set of pass /
    accumulator buffers sized for the largest tile (``pyopencl.MemoryError`` → CPU fallback)."""

    PLANE_BUFFERS = ("count", "depth", "zmin", "cv")

    def __init__(self, device: _CLDevice, plan: RenderPlan, planes: HostPlanes, n_traj: int, active: list[int],
                 tile_size: tuple[int, int]) -> None:
        import pyopencl as cl

        self.cl, self.ctx, self.queue = cl, device.ctx, device.queue
        self.k_iterate, self.k_merge = device.kernels
        self.plan, self.planes, self.n_traj, self.fp64 = plan, planes, n_traj, device.fp64
        self.npix_max = tile_size[0] * tile_size[1]
        self.P = _kernel_params(plan, n_traj)
        mf = cl.mem_flags
        pbuf = np.zeros(max(1, plan.params.size), dtype=np.float32)
        pbuf[: plan.params.size] = plan.params
        self.b_kern = cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=padded_splat_kernel(plan.quality.splat_radius))
        self.b_p = cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=pbuf)
        self.b_P = cl.Buffer(self.ctx, mf.READ_ONLY, size=self.P.nbytes)
        self.pass_bufs: list | None = None  # uint pass buffers, one per plane (placeholders when unused)
        self.acc_bufs: list | None = None  # float accumulators, same order
        self.state: dict[int, dict] = {}
        self._current: tuple[int, Tile] | None = None
        self._create_tile_state(active)

    def _create_tile_state(self, indices: list[int]) -> None:
        """Seed each active tile's trajectories into device buffers."""
        cl, mf, plan, n = self.cl, self.cl.mem_flags, self.plan, self.n_traj
        zeros4 = np.zeros((n, 4), dtype=np.float32)
        for index in indices:
            st = seed_from_points(n, plan.resume.seed, plan.sample_pts, plan.framing.radius * 1e-2)
            state = np.zeros((n, 4), dtype=np.float64 if self.fp64 else np.float32)
            state[:, 0], state[:, 1], state[:, 2], state[:, 3] = st.X, st.Y, st.Z, st.W
            self.state[index] = {
                "state": cl.Buffer(self.ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=state),
                "rng": cl.Buffer(self.ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=st.RS.astype(np.uint32)),
                "prev": cl.Buffer(self.ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=zeros4),
                "prevd": cl.Buffer(self.ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=zeros4),
                "stats": cl.Buffer(self.ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=np.zeros(4, dtype=np.uint32)),
                "esc": cl.Buffer(self.ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=st.escape_state()),
                "t_base": 0.0,
            }

    def _make_plane_buffers(self) -> None:
        """Pass (uint) + accumulator (float) buffers for the largest tile; unneeded planes are
        16-byte placeholders."""
        cl, mf = self.cl, self.cl.mem_flags
        wanted = [True, bool(self.plan.needs.depth), bool(self.plan.needs.zmin), bool(self.plan.needs.color)]
        made: list = []
        try:
            for idx, want in enumerate(wanted):
                n = self.npix_max if want else 4
                made.append(cl.Buffer(self.ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=np.full(n, 0xFFFFFFFF if idx == 2 else 0, dtype=np.uint32)))
            for idx, want in enumerate(wanted):
                n = self.npix_max if want else 4
                made.append(cl.Buffer(self.ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=np.full(n, PLANE_FILL[PLANE_NAMES[idx]], dtype=np.float32)))
        except Exception:
            for b in made:
                b.release()
            raise
        self.pass_bufs, self.acc_bufs = made[:4], made[4:]

    # ── TileVisitor ────────────────────────────────────────────────────────────
    def select(self, index: int, tile: Tile, fresh: bool) -> None:
        """Restore the tile's accumulators into the shared buffers and set the tile parameters."""
        if self.acc_bufs is None:
            self._make_plane_buffers()
        for name, _ in self.planes.planes():  # restore the accumulators (pass buffers are zeroed by merge)
            self.cl.enqueue_copy(self.queue, self.acc_bufs[PLANE_NAMES.index(name)], self.planes.slab(name, tile, fresh).ravel())
        self.P["w"], self.P["h"] = tile.w, tile.h
        self.P["cx"], self.P["cy"] = self.plan.cx - tile.x, self.plan.cy - tile.y
        self._current = (index, tile)

    def warm_up(self, index: int, steps: int) -> None:
        """Unplotted steps (in kernel-sized chunks), then forget the previous points."""
        while steps > 0:
            k = min(steps, MAX_STEPS_PER_PASS)
            self._dispatch(index, k, plot=0)
            steps -= k
        self.cl.enqueue_copy(self.queue, self.state[index]["prev"], np.zeros((self.n_traj, 4), dtype=np.float32))

    def run_pass(self, index: int, steps: int) -> None:
        """Plot ``steps`` steps, merge the pass buffers into the accumulators, wait."""
        self._dispatch(index, steps, plot=1)
        self._merge()
        self.queue.finish()

    def readback(self, index: int, tile: Tile) -> None:
        """Copy the tile's accumulators into the host planes."""
        self.queue.finish()
        for name, _ in self.planes.planes():
            out = np.empty(tile.pixels, dtype=np.float32)
            self.cl.enqueue_copy(self.queue, out, self.acc_bufs[PLANE_NAMES.index(name)])
            self.planes.store(name, tile, out)

    # ── internals ──────────────────────────────────────────────────────────────
    def _dispatch(self, index: int, steps: int, plot: int) -> None:
        """One iterate-kernel launch of ``steps`` steps for the tile's trajectories."""
        ts = self.state[index]
        self.P["steps"], self.P["do_plot"], self.P["t0"] = steps, plot, ts["t_base"]
        ts["t_base"] += steps * self.plan.substeps
        self.cl.enqueue_copy(self.queue, self.b_P, self.P)
        self.k_iterate(self.queue, (self.n_traj,), (LOCAL_SIZE,), ts["state"], ts["rng"], ts["prev"], ts["prevd"], ts["stats"],
                       *self.pass_bufs, self.b_P, self.b_kern, self.b_p, ts["esc"])

    def _merge(self) -> None:
        """Add the fixed-point pass buffers into the float accumulators and clear them."""
        assert self._current is not None
        _, tile = self._current
        needs, cv_lo, cv_hi = self.plan.needs, *self.plan.cv_range
        gsz = int(math.ceil(tile.pixels / 256) * 256)
        self.k_merge(self.queue, (gsz,), (256,), *self.pass_bufs, *self.acc_bufs,
                     np.int32(tile.pixels), np.int32(needs.depth), np.int32(needs.zmin), np.int32(needs.color),
                     np.float32(cv_lo), np.float32(cv_hi - cv_lo))

    def collect_stats(self) -> tuple[int, float]:
        """(restarts, plotted weight) summed over the tiles' device counters."""
        restarts, plotted = 0, 0.0
        for ts in self.state.values():
            sv = np.zeros(4, dtype=np.uint32)
            self.cl.enqueue_copy(self.queue, sv, ts["stats"])
            self.queue.finish()
            restarts += int(sv[0])
            plotted += (int(sv[2]) * 4294967296.0 + int(sv[1])) / 16.0
        return restarts, plotted

    def release(self) -> None:
        """Free every device buffer owned here (safe to call twice)."""
        for b in (self.pass_bufs or []) + (self.acc_bufs or []) + [self.b_kern, self.b_p, self.b_P]:
            b.release()
        self.pass_bufs = self.acc_bufs = None
        for ts in self.state.values():
            for key in ("state", "rng", "prev", "prevd", "stats", "esc"):
                ts[key].release()
        self.state.clear()


selector.register("opencl", OpenCLEngine)
