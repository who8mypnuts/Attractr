"""Random parameter search ("Search" from the classic Chaoscope): keep parameter sets whose
dynamics are chaotic and whose rendering covers enough of the frame."""

from __future__ import annotations

import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np

from attractr.core.analysis.lyapunov import largest_exponent
from attractr.core.attractors.spec import AttractorSpec
from attractr.core.jobs.cancel import NEVER, CancelToken
from attractr.core.render.framing import framing_from_points, sample_attractor


@dataclass(frozen=True)
class SearchHit:
    params: dict[str, float]
    lyapunov: float
    spread: float  # fraction of finite sample points (boundedness)
    dimension_hint: float


def random_params(spec: AttractorSpec, rng: random.Random, locked: dict[str, float] | None = None,
                  around: dict[str, float] | None = None, radius: float = 1.0) -> dict[str, float]:
    """Uniform in the soft range, or a perturbation of ``around`` with ``radius`` (fraction of range)."""
    out: dict[str, float] = {}
    for p in spec.params:
        if locked and p.name in locked:
            out[p.name] = locked[p.name]
            continue
        if around is not None and radius < 1.0:
            c = around.get(p.name, p.default)
            v = p.clamp(c + rng.uniform(-1, 1) * radius * p.span)
        else:
            v = rng.uniform(p.lo, p.hi)
        out[p.name] = float(round(v)) if p.is_int else v
    return out


def evaluate(spec: AttractorSpec, params: dict[str, float], dt: float | None = None, seed: int = 1,
             steps: int = 3000) -> SearchHit | None:
    """Quick dynamics check; None when the system diverges or is not chaotic."""
    p = spec.params_array(params)
    dt_ = float(dt) if dt else spec.dt
    pts = sample_attractor(spec, p, dt_, 1, min(spec.warmup, 2000), seed, n_traj=64, steps=64)
    finite = np.all(np.isfinite(pts), axis=1)
    spread = float(finite.mean())
    if spread < 0.6:
        return None
    fr = framing_from_points(pts)
    if fr.radius < 1e-6 or fr.radius > 1e5:
        return None
    # a collapsed attractor (fixed point / tiny cycle) has almost no spatial variance
    good = pts[finite]
    if good.shape[0] > 10 and float(good.std(axis=0).max()) < 1e-6 * fr.radius:
        return None
    lam = largest_exponent(spec, params, dt=dt_, steps=steps, seed=seed)
    if lam.diverged or lam.classification != "chaotic":
        return None
    return SearchHit(params, lam.exponent, spread, float("nan"))


def search(spec: AttractorSpec, *, count: int = 12, seed: int | None = None, dt: float | None = None,
           locked: dict[str, float] | None = None, around: dict[str, float] | None = None, radius: float = 1.0,
           max_tries: int = 400, cancel: CancelToken = NEVER,
           on_progress: Callable[[int, int], None] | None = None) -> Iterator[SearchHit]:
    """Yield up to ``count`` chaotic parameter sets."""
    rng = random.Random(seed)
    found = 0
    for i in range(max_tries):
        cancel.check()
        if on_progress:
            on_progress(i, found)
        params = random_params(spec, rng, locked, around, radius)
        hit = evaluate(spec, params, dt, seed=rng.randrange(1, 1 << 30))
        if hit is not None:
            found += 1
            yield hit
            if found >= count:
                return
