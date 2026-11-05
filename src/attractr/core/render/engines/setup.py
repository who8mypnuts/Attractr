"""The engine-independent part of a render: framing, camera, colour range, budgets.

Every engine (CPU, GL compute, OpenCL, GL points) needs the same ~20 derived values before
it can iterate — computed here exactly once, so the engines only differ in how they run
the kernel.  :func:`prepare` also fills the timing / budget fields of the
:class:`RenderStats` it is given.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, replace

import numpy as np

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.formula.compile import CompiledFormula
from attractr.core.jobs.cancel import NEVER, CancelToken
from attractr.core.render.accumulators import Needs, color_value_range, needs_for
from attractr.core.render.camera import Camera
from attractr.core.render.checkpoint import Checkpoint
from attractr.core.render.engines.base import ResumePlan, resume_plan
from attractr.core.render.framing import compute_framing
from attractr.core.render.result import Framing, RenderStats
from attractr.core.render.settings import Look, Quality, RenderSettings

ACCUM_WARMUP = 64  # decorrelation steps after seeding trajectories from the framing sample
DEFAULT_CV_RANGE = (-4.0, 4.0)  # colour-value encoding range when no colour buffer is needed


def apply_lock(framing: Framing, cam: Camera) -> Framing:
    """Replace the fitted sphere by the camera's locked one (animations)."""
    if not cam.locked:
        return framing
    return Framing(tuple(cam.lock_center), float(cam.lock_radius), framing.bbox_min, framing.bbox_max)  # type: ignore[arg-type]


def effective_camera(cam: Camera, framing: Framing) -> Camera:
    """Camera with the 2-D tight fit (if any) folded into zoom / pan."""
    if framing.fit_zoom == 1.0 and framing.fit_pan == (0.0, 0.0):
        return cam
    # fit_pan is already expressed in final image fractions (it includes fit_zoom)
    return replace(cam, zoom=cam.zoom * framing.fit_zoom,
                   pan_u=cam.pan_u + framing.fit_pan[0], pan_v=cam.pan_v + framing.fit_pan[1])


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


def padded_splat_kernel(r: int, size: int = 81) -> np.ndarray:
    """The splat kernel as the fixed-size float32 array the GPU kernels take (radius ≤ 4)."""
    kern = np.zeros(size, dtype=np.float32)
    k = splat_kernel(r).astype(np.float32)
    kern[: k.size] = k
    return kern


def escape_config(spec: AttractorSpec) -> np.ndarray:
    """Kernel constants for escape-time systems: region box, bailout², max_iter, min_iter."""
    r = list(spec.region) + [0.0] * (6 - len(spec.region))
    return np.array([*r[:6], float(spec.bailout) ** 2, float(spec.max_iter), float(spec.min_iter)], dtype=np.float64)


@dataclass(frozen=True)
class RenderPlan:
    """Everything derived from the settings that an engine needs to iterate and project.

    Attributes:
        settings, spec: what is rendered.
        quality, look, needs: shortcuts into the settings (``needs`` = which planes to keep).
        params: parameter vector in the spec's order.
        dt, substeps: integrator controls (maps: ``dt`` unused).
        ss, width, height: output size and supersampling factor.
        buf_width, buf_height: accumulation buffer size (output × ss).
        framing, sample_pts: bounding sphere (after locks / checkpoint) and the framing sample.
        camera: camera with the 2-D fit folded in; ``rotation`` its 3×3 matrix.
        cx, cy, focal: projection constants in accumulation-buffer pixels.
        cv_range: colour-value range ``(lo, hi)`` used to encode colour sums.
        resume: remaining budget, trajectory seed and checkpoint to merge.
        warmup_steps: decorrelation steps before plotting.
        escape: escape-time kernel constants (see :func:`escape_config`).
    """

    settings: RenderSettings
    spec: AttractorSpec
    quality: Quality
    look: Look
    needs: Needs
    params: np.ndarray
    dt: float
    substeps: int
    ss: int
    width: int
    height: int
    buf_width: int
    buf_height: int
    framing: Framing
    sample_pts: np.ndarray
    camera: Camera
    rotation: np.ndarray
    cx: float
    cy: float
    focal: float
    cv_range: tuple[float, float]
    resume: ResumePlan
    warmup_steps: int
    escape: np.ndarray

    @property
    def gap_fill(self) -> bool:
        return bool(self.quality.gap_fill and self.spec.plots_continuous)

    @property
    def budget(self) -> int:
        """Iterations still to accumulate (the full budget minus a resumed checkpoint's)."""
        return self.resume.budget

    def total_steps(self, n_traj: int) -> int:
        """Kernel steps per trajectory that spend :attr:`budget`."""
        return -(-self.budget // max(n_traj, 1))  # ceil division


def prepare(settings: RenderSettings, spec: AttractorSpec, cf: CompiledFormula, stats: RenderStats,
            resume: Checkpoint | None = None, cancel: CancelToken = NEVER) -> RenderPlan:
    """Compute the :class:`RenderPlan` for a render and record its timings in ``stats``.

    Raises:
        Cancelled: when ``cancel`` was triggered while framing.
    """
    q, look = settings.quality, settings.look
    params = spec.params_array(settings.param_dict)
    dt = float(q.dt) if q.dt else spec.dt
    substeps = max(1, int(q.substeps))
    ss = max(1, int(q.supersample))
    width, height = int(q.width), int(q.height)
    buf_w, buf_h = width * ss, height * ss

    t0 = time.perf_counter()
    framing, sample_pts = compute_framing(spec, params, dt, substeps, spec.warmup, q.seed, settings.camera, width, height)
    stats.framing_seconds = time.perf_counter() - t0
    framing = apply_lock(framing, settings.camera)
    plan = resume_plan(spec.iteration_budget(q.iterations), q.seed, resume)
    framing = plan.framing or framing
    cancel.check()

    cam = effective_camera(settings.camera, framing)
    cx, cy, focal = cam.projection_constants(buf_w, buf_h)
    needs = needs_for(look)
    cv_range = (color_value_range(needs.color_code, sample_pts, framing, cam.matrix(), params, cf.color_fn)
                if needs.color else DEFAULT_CV_RANGE)
    stats.iterations_requested = spec.iteration_budget(q.iterations)
    stats.warmup_steps = int(q.warmup) if q.warmup is not None else ACCUM_WARMUP
    return RenderPlan(
        settings, spec, q, look, needs, params, dt, substeps, ss, width, height, buf_w, buf_h,
        framing, sample_pts, cam, cam.matrix(), cx, cy, focal, (float(cv_range[0]), float(cv_range[1])),
        plan, stats.warmup_steps, escape_config(spec),
    )
