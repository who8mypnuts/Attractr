"""Density → [0, 1] tone mapping shared by all styles."""

from __future__ import annotations

import numpy as np

from attractr.core.math.percentile import robust_percentile
from attractr.core.render.settings import Look


def normaliser(count: np.ndarray, percentile: float) -> float:
    """The count value mapped to full brightness (robust percentile of non-empty pixels)."""
    p = robust_percentile(count, min(max(percentile, 0.5), 1.0))
    return max(p, 1e-9)


def log_density(count: np.ndarray, norm: float) -> np.ndarray:
    """Chaoscope 'Gas' law: log(1 + c) / log(1 + P), clipped to 1."""
    return np.clip(np.log1p(count) / np.log1p(norm), 0.0, 1.0).astype(np.float32)


def root_density(count: np.ndarray, norm: float, power: float = 0.25) -> np.ndarray:
    """'Dust' law: (c / P)^power — emphasises sparse regions."""
    return np.clip(np.power(np.maximum(count, 0.0) / norm, power), 0.0, 1.0).astype(np.float32)


def apply_curve(d: np.ndarray, look: Look) -> np.ndarray:
    """Gamma, brightness, contrast S-curve and inversion (in place on a copy)."""
    out = d.astype(np.float32, copy=True)
    if look.gamma != 1.0 and look.gamma > 0:
        np.power(out, look.gamma, out=out)
    if look.brightness != 1.0:
        out *= look.brightness
    if look.contrast != 0.0:
        k = float(np.clip(look.contrast, -0.99, 0.99))
        # smooth S-curve around 0.5; negative k flattens
        x = out - 0.5
        out = 0.5 + x * (1 + k) / (1 + k * np.abs(x) * 2)
    np.clip(out, 0.0, 1.0, out=out)
    if look.invert:
        out = 1.0 - out
    return out


def equalize(d: np.ndarray, mask: np.ndarray, bins: int = 1024) -> np.ndarray:
    """Histogram equalisation of the non-empty pixels ("Full range")."""
    vals = d[mask]
    if vals.size == 0:
        return d
    hist, edges = np.histogram(vals, bins=bins, range=(0.0, 1.0))
    cdf = np.cumsum(hist).astype(np.float64)
    cdf /= cdf[-1]
    idx = np.clip((d * (bins - 1)).astype(np.int32), 0, bins - 1)
    out = d.copy()
    out[mask] = cdf[idx[mask]].astype(np.float32)
    return out


def base_density(count: np.ndarray, look: Look, norm: float) -> np.ndarray:
    if look.style == "dust":
        return root_density(count, norm)
    return log_density(count, norm)
