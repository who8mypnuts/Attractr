"""Quick dynamics probe used by the formula editor badge and the search feature."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from attractr.core.analysis.dimension import box_counting_dimension
from attractr.core.analysis.lyapunov import largest_exponent
from attractr.core.attractors.spec import AttractorSpec
from attractr.core.render.framing import framing_from_points, sample_attractor


@dataclass(frozen=True)
class ProbeResult:
    lyapunov: float
    classification: str
    radius: float
    box_dimension: float
    restart_fraction: float

    def as_dict(self) -> dict:
        return {
            "Largest Lyapunov exponent λ₁": self.lyapunov,
            "Classification": self.classification,
            "Box-counting dimension (3-D cloud)": self.box_dimension,
            "Bounding radius": self.radius,
        }


def probe(spec: AttractorSpec, params: dict[str, float] | None = None, dt: float | None = None,
          steps: int = 6000, seed: int = 1) -> ProbeResult:
    p = spec.params_array(params)
    dt_ = float(dt) if dt else spec.dt
    pts = sample_attractor(spec, p, dt_, 1, spec.warmup, seed, n_traj=128, steps=128)
    finite = np.all(np.isfinite(pts), axis=1)
    fr = framing_from_points(pts)
    lam = largest_exponent(spec, params, dt=dt_, steps=steps, seed=seed)
    dim = box_counting_dimension(pts[finite]) if finite.sum() > 100 else float("nan")
    cls = lam.label
    if finite.mean() < 0.5:
        cls = "divergent"
    return ProbeResult(lam.exponent, cls, fr.radius, dim, 1.0 - float(finite.mean()))
