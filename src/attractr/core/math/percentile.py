"""Robust percentile of the non-zero values of a large array without sorting.

A 4096-bin log-spaced histogram of the values gives the percentile to ~0.1 % accuracy in
O(n) time and O(1) memory — this is what lets tiled renders share one global normaliser
(each tile contributes its histogram; the bins are merged, then the percentile is read).
"""

from __future__ import annotations

import numpy as np

N_BINS = 4096


def log_bins(vmax: float) -> np.ndarray:
    """Bin edges on ``log1p`` scale covering ``[0, vmax]``."""
    top = np.log1p(max(vmax, 1e-12))
    return np.expm1(np.linspace(0.0, top, N_BINS + 1))


def density_histogram(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    nz = values[values > 0]
    hist, _ = np.histogram(nz, bins=edges)
    return hist.astype(np.int64)


def percentile_from_histogram(hist: np.ndarray, edges: np.ndarray, pct: float) -> float:
    total = int(hist.sum())
    if total == 0:
        return 1.0
    target = pct * total
    cdf = np.cumsum(hist)
    idx = int(np.searchsorted(cdf, target, side="left"))
    idx = min(idx, len(edges) - 2)
    # linear interpolation inside the bin
    prev = cdf[idx - 1] if idx > 0 else 0
    inside = hist[idx]
    frac = (target - prev) / inside if inside > 0 else 0.0
    return float(edges[idx] + frac * (edges[idx + 1] - edges[idx]))


def robust_percentile(values: np.ndarray, pct: float) -> float:
    """Percentile ``pct`` (0..1) of the non-zero entries of ``values`` (exact for small
    arrays, histogram-based for large ones)."""
    nz = values[values > 0]
    if nz.size == 0:
        return 1.0
    if nz.size <= 262_144:
        return float(np.percentile(nz, pct * 100.0))
    edges = log_bins(float(nz.max()))
    return percentile_from_histogram(density_histogram(nz, edges), edges, pct)
