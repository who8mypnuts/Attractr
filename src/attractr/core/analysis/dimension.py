"""Fractal dimension estimates of a point cloud."""

from __future__ import annotations

import numpy as np


def box_counting_dimension(pts: np.ndarray, scales: int = 6) -> float:
    """Box-counting (Minkowski) dimension of an [n, d] point cloud; NaN if too few points."""
    good = pts[np.all(np.isfinite(pts), axis=1)]
    if good.shape[0] < 100:
        return float("nan")
    lo = good.min(axis=0)
    span = float((good.max(axis=0) - lo).max()) or 1.0
    unit = (good - lo) / span
    xs, ys = [], []
    for k in range(2, 2 + scales):
        n = 2**k
        idx = np.minimum((unit * n).astype(np.int64), n - 1)
        occupied = len(np.unique(idx, axis=0)) if idx.shape[1] > 1 else len(np.unique(idx))
        xs.append(np.log(n))
        ys.append(np.log(occupied))
    slope = np.polyfit(xs, ys, 1)[0]
    return float(slope)


def correlation_dimension(pts: np.ndarray, n_sample: int = 2000, seed: int = 1) -> float:
    """Grassberger–Procaccia correlation dimension from pairwise distances of a sub-sample."""
    good = pts[np.all(np.isfinite(pts), axis=1)]
    if good.shape[0] < 200:
        return float("nan")
    rng = np.random.default_rng(seed)
    sub = good[rng.choice(good.shape[0], min(n_sample, good.shape[0]), replace=False)]
    d = np.sqrt(((sub[:, None, :] - sub[None, :, :]) ** 2).sum(-1))
    d = d[np.triu_indices(len(sub), 1)]
    d = d[d > 0]
    if d.size < 100:
        return float("nan")
    rs = np.exp(np.linspace(np.log(np.percentile(d, 2)), np.log(np.percentile(d, 40)), 8))
    c = np.array([(d < r).mean() for r in rs])
    m = c > 0
    if m.sum() < 3:
        return float("nan")
    return float(np.polyfit(np.log(rs[m]), np.log(c[m]), 1)[0])
