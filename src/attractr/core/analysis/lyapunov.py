"""Largest Lyapunov exponent (Benettin two-trajectory renormalisation)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.render.engines.cpu_compile import kernel_module
from attractr.core.render.framing import sample_attractor


@dataclass(frozen=True)
class LyapunovResult:
    exponent: float  # per unit time (flows) or per iteration (maps)
    classification: str  # chaotic | quasi-periodic | periodic | divergent
    steps: int
    diverged: bool

    @property
    def label(self) -> str:
        if self.diverged:
            return "divergent"
        return self.classification


def largest_exponent(
    spec: AttractorSpec,
    params: dict[str, float] | None = None,
    *,
    dt: float | None = None,
    substeps: int = 1,
    steps: int = 20000,
    integrator: str = "rk4",
    seed: int = 1,
    d0: float = 1e-8,
) -> LyapunovResult:
    """Estimate λ₁ from one trajectory that starts on the attractor."""
    if spec.is_escape:
        return LyapunovResult(float("nan"), "escape-time", 0, False)
    cf = spec.compiled(integrator)
    mod = kernel_module(cf)
    p = spec.params_array(params)
    dt_ = float(dt) if dt else spec.dt
    pts = sample_attractor(spec, p, dt_, substeps, spec.warmup, seed, n_traj=64, steps=64)
    states = pts[:, :4]
    good = states[np.all(np.isfinite(states), axis=1)]
    if good.shape[0] == 0:
        return LyapunovResult(float("nan"), "divergent", 0, True)
    x0, y0, z0, w0 = (float(v) for v in _typical_state(good))
    scale = max(float(np.abs(good).max()), 1e-6)
    rs = np.array([(seed * 7919 + 1) & 0xFFFFFFFF, (seed * 104729 + 3) & 0xFFFFFFFF], dtype=np.uint32)
    renorm_every = 1 if spec.kind != "flow" else 5
    total, renorms, diverged = mod.lyapunov_kernel(x0, y0, z0, w0, p, rs, dt_, substeps, steps, d0 * scale, renorm_every)
    if diverged or renorms == 0:
        return LyapunovResult(float("nan"), "divergent", steps, True)
    per_step = total / (renorms * renorm_every * substeps)
    lam = per_step / dt_ if spec.kind == "flow" else per_step
    thresh = 0.005 if spec.kind == "flow" else 0.002
    if lam > thresh:
        cls = "chaotic"
    elif lam > -thresh:
        cls = "quasi-periodic"
    else:
        cls = "periodic"  # negative exponent: a limit cycle or a fixed point
    return LyapunovResult(float(lam), cls, steps, False)


def _typical_state(states: np.ndarray) -> np.ndarray:
    """The sampled state whose distance from the cloud's median centre is closest to the
    median distance — a point squarely on the attractor rather than one of the outliers a
    few escaping seeds leave behind."""
    center = np.median(states, axis=0)
    d = np.sqrt(((states - center) ** 2).sum(axis=1))
    return states[int(np.argmin(np.abs(d - np.median(d))))]
