"""Outputs of the accumulation stage."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from attractr.core.render.settings import RenderSettings


@dataclass(frozen=True)
class Framing:
    """Bounding sphere of the attractor in world space (rotation-invariant)."""

    center: tuple[float, float, float]
    radius: float
    bbox_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # optional 2-D tight fit applied on top (fit = "bbox"): extra zoom and pan offsets
    fit_zoom: float = 1.0
    fit_pan: tuple[float, float] = (0.0, 0.0)


@dataclass
class RenderStats:
    engine: str = ""
    device: str = ""
    precision: str = "fp64"
    iterations_requested: int = 0
    iterations_done: int = 0
    points_plotted: float = 0.0  # total splat weight that landed in-bounds
    restarts: int = 0
    trajectories: int = 0
    warmup_steps: int = 0
    passes: int = 0
    tiles: int = 1
    tiles_done: int = 0  # complete tiles in a partial result (0 = uniform partial)
    finished_early: bool = False  # soft-stopped ("Finish now")
    elapsed: float = 0.0
    accumulate_seconds: float = 0.0
    framing_seconds: float = 0.0
    compile_seconds: float = 0.0
    # derived from the buffers (filled by stats.summarize)
    nonzero_pixels: int = 0
    coverage: float = 0.0
    max_count: float = 0.0
    mean_count: float = 0.0
    median_count: float = 0.0
    percentile_count: float = 0.0
    entropy_bits: float = 0.0
    density_histogram: list[int] = field(default_factory=list)  # 64 log-spaced bins
    density_histogram_edges: list[float] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def points_per_second(self) -> float:
        return self.iterations_done / self.accumulate_seconds if self.accumulate_seconds > 0 else 0.0


@dataclass
class RenderResult:
    settings: RenderSettings
    count: np.ndarray  # float32 [H, W]
    framing: Framing
    stats: RenderStats
    depth_sum: np.ndarray | None = None  # float32 [H, W] — Σ depth (divide by count for mean)
    zmin: np.ndarray | None = None  # float32 [H, W] — nearest depth, +inf where empty
    cv_sum: np.ndarray | None = None  # float32 [H, W] — Σ colour value
    complete: bool = True  # False for progressive partial results

    @property
    def width(self) -> int:
        return self.count.shape[1]

    @property
    def height(self) -> int:
        return self.count.shape[0]

    def mean_depth(self) -> np.ndarray | None:
        if self.depth_sum is None:
            return None
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(self.count > 0, self.depth_sum / np.maximum(self.count, 1e-30), 0.0)

    def mean_cv(self) -> np.ndarray | None:
        if self.cv_sum is None:
            return None
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(self.count > 0, self.cv_sum / np.maximum(self.count, 1e-30), 0.0)
