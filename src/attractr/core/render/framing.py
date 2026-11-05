"""Scene framing: the attractor's bounding sphere (and optional 2-D tight fit).

The sphere is rotation-invariant, so a camera orbit never changes the apparent size —
this is what keeps turntable animations from "breathing" (see source_analysis A3).
"""

from __future__ import annotations

import math

import numpy as np

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.jobs.cancel import NEVER, CancelToken
from attractr.core.render.camera import Camera
from attractr.core.render.engines.cpu_compile import kernel_module
from attractr.core.render.engines.state import seed_trajectories
from attractr.core.render.result import Framing

SAMPLE_TRAJECTORIES = 256  # few trajectories × many steps: time coverage matters more
SAMPLE_STEPS = 512  # than spatial spread (flows wander slowly onto the attractor)
PCT_LO, PCT_HI = 0.1, 99.9
MARGIN = 1.03
MAX_SETTLE_ROUNDS = 10  # extra warm-up rounds while the bounding sphere still changes
SETTLE_TOL = 0.04


def sample_attractor(
    spec: AttractorSpec, params: np.ndarray, dt: float, substeps: int, warmup: int,
    seed: int, n_traj: int = SAMPLE_TRAJECTORIES, steps: int = SAMPLE_STEPS,
    cancel: CancelToken = NEVER,
) -> np.ndarray:
    """Return ``[n_traj·steps, 7]`` rows ``(x, y, z, w, px, py, pz)``: the state (used to seed
    trajectories) and the plotted point (used for framing; NaN where nothing is plotted).

    The transient is discarded adaptively: after ``warmup`` steps we keep advancing in
    chunks until the sampled bounding sphere stops changing (slowly unfolding systems
    such as Rössler need far longer than a fixed step count)."""
    cf = spec.compiled(integrator="rk4")
    mod = kernel_module(cf)
    st = seed_trajectories(n_traj, seed, spec.ic, spec.jitter)
    ic = np.asarray(spec.ic, dtype=np.float64)
    restarts = np.zeros(n_traj, dtype=np.int64)
    chunk = 64
    scratch = np.empty((n_traj * chunk, 7), dtype=np.float64)
    t_done = 0

    def advance(nsteps: int) -> None:
        nonlocal t_done
        done = 0
        while done < nsteps:
            cancel.check()
            k = min(chunk, nsteps - done)
            mod.sample_points(st.X, st.Y, st.Z, st.W, st.SEC, st.RS, params, dt, substeps, k, float(t_done),
                              scratch[: n_traj * k], restarts, ic, spec.jitter)
            done += k
            t_done += k

    def sample() -> np.ndarray:
        nonlocal t_done
        out = np.empty((n_traj * steps, 7), dtype=np.float64)
        before = restarts.copy()
        mod.sample_points(st.X, st.Y, st.Z, st.W, st.SEC, st.RS, params, dt, substeps, steps, float(t_done),
                          out, restarts, ic, spec.jitter)
        t_done += steps
        _drop_escapees(out.reshape(n_traj, steps, 7), restarts != before)
        return out

    advance(warmup)
    pts = sample()
    prev = framing_from_points(pts)
    for _ in range(MAX_SETTLE_ROUNDS):
        advance(warmup)
        pts = sample()
        cur = framing_from_points(pts)
        shift = math.dist(cur.center, prev.center)
        if abs(cur.radius - prev.radius) <= SETTLE_TOL * cur.radius and shift <= SETTLE_TOL * cur.radius:
            break
        prev = cur
    return pts


ESCAPEE_RATIO = 20.0  # a trajectory wandering this many times further out than the median is leaving


def _drop_escapees(rows: np.ndarray, escaped: np.ndarray) -> None:
    """Blank (NaN) the trajectories that diverged during the sample or are clearly on their way
    out (their extent dwarfs the median trajectory's), so a few seeds outside a small basin of
    attraction cannot blow up the framing.  ``rows`` is ``[n_traj, steps, 7]``; never blanks
    more than half of the trajectories."""
    n = rows.shape[0]
    with np.errstate(invalid="ignore"):
        extent = np.nanmax(np.abs(rows[:, :, :4]), axis=(1, 2))
    finite = np.isfinite(extent)
    if finite.sum() < 4:
        return
    med = float(np.median(extent[finite]))
    far = finite & (extent > ESCAPEE_RATIO * max(med, 1e-12))
    bad = escaped | far
    if 0 < bad.sum() <= n // 2:
        rows[bad] = np.nan


def plotted(pts: np.ndarray) -> np.ndarray:
    """The finite plotted points of a framing sample (columns 4..7, or 0..3 for plain clouds)."""
    p = pts[:, 4:7] if pts.shape[1] >= 7 else pts[:, :3]
    return p[np.all(np.isfinite(p), axis=1)]


def framing_from_points(pts: np.ndarray) -> Framing:
    good = plotted(pts)
    if good.shape[0] < 8:
        return Framing((0.0, 0.0, 0.0), 1.0)
    lo = np.percentile(good, PCT_LO, axis=0)
    hi = np.percentile(good, PCT_HI, axis=0)
    center = (lo + hi) * 0.5
    d = np.sqrt(((good - center) ** 2).sum(axis=1))
    radius = float(np.percentile(d, PCT_HI)) * MARGIN
    if not math.isfinite(radius) or radius < 1e-9:
        radius = 1.0
    return Framing(tuple(float(c) for c in center), radius, tuple(float(v) for v in lo), tuple(float(v) for v in hi))


def fit_2d(framing: Framing, camera: Camera, pts: np.ndarray, width: int, height: int, margin: float = 0.03) -> Framing:
    """Tight 2-D fit: extra zoom/pan so the projected cloud fills the frame (camera.fit == "bbox")."""
    good = plotted(pts)
    if good.shape[0] < 8:
        return framing
    unit = (good - np.asarray(framing.center)) / framing.radius
    cam1 = Camera(rotation=camera.rotation, zoom=1.0, perspective=camera.perspective)
    u, v, _ = cam1.project(unit, width, height)
    u0, u1 = np.percentile(u, [PCT_LO, PCT_HI])
    v0, v1 = np.percentile(v, [PCT_LO, PCT_HI])
    if u1 - u0 < 1e-9 or v1 - v0 < 1e-9:
        return framing
    sx = width * (1 - 2 * margin) / (u1 - u0)
    sy = height * (1 - 2 * margin) / (v1 - v0)
    s = min(sx, sy)
    # centre of the fitted bbox → image centre; pan is a fraction of the image size
    cu, cv = (u0 + u1) * 0.5, (v0 + v1) * 0.5
    pan_u = (width * 0.5 - (width * 0.5 + (cu - width * 0.5) * s)) / width
    pan_v = (height * 0.5 - (height * 0.5 + (cv - height * 0.5) * s)) / height
    return Framing(framing.center, framing.radius, framing.bbox_min, framing.bbox_max, float(s), (float(pan_u), float(pan_v)))


_cache: dict[tuple, tuple[Framing, np.ndarray]] = {}
_CACHE_MAX = 64


def _cached(spec: AttractorSpec, params: tuple[float, ...], dt: float, substeps: int, warmup: int, seed: int):
    key = (spec.content_hash, params, dt, substeps, warmup, seed)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    pts = sample_attractor(spec, np.asarray(params, dtype=np.float64), dt, substeps, warmup, seed)
    val = (framing_from_points(pts), pts)
    if len(_cache) >= _CACHE_MAX:
        _cache.pop(next(iter(_cache)))
    _cache[key] = val
    return val


def compute_framing(
    spec: AttractorSpec, params: np.ndarray, dt: float, substeps: int, warmup: int, seed: int,
    camera: Camera | None = None, width: int = 1, height: int = 1,
) -> tuple[Framing, np.ndarray]:
    """Cached bounding-sphere framing (+ 2-D fit when ``camera.fit == 'bbox'``).
    Returns ``(framing, sample_points)``."""
    fr, pts = _cached(spec, tuple(float(v) for v in params), float(dt), int(substeps), int(warmup), int(seed))
    if camera is not None and camera.fit == "bbox":
        fr = fit_2d(fr, camera, pts, width, height)
    return fr, pts
