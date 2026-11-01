"""Statistics derived from accumulation buffers (the nerd layer)."""

from __future__ import annotations

import numpy as np

from attractr.core.math.percentile import robust_percentile
from attractr.core.render.result import RenderResult

HIST_BINS = 64


def summarize(result: RenderResult, percentile: float = 0.998) -> None:
    """Fill the derived fields of ``result.stats`` in place."""
    st = result.stats
    cnt = result.count
    nz = cnt[cnt > 0]
    st.nonzero_pixels = int(nz.size)
    st.coverage = float(nz.size) / float(cnt.size) if cnt.size else 0.0
    if nz.size == 0:
        st.max_count = st.mean_count = st.median_count = st.percentile_count = 0.0
        st.entropy_bits = 0.0
        st.density_histogram = []
        st.density_histogram_edges = []
        return
    st.max_count = float(nz.max())
    st.mean_count = float(nz.mean())
    st.median_count = float(np.median(nz)) if nz.size <= 4_000_000 else float(robust_percentile(cnt, 0.5))
    st.percentile_count = float(robust_percentile(cnt, percentile))
    p = nz.astype(np.float64)
    p /= p.sum()
    st.entropy_bits = float(-(p * np.log2(p)).sum())
    edges = np.expm1(np.linspace(0.0, np.log1p(st.max_count), HIST_BINS + 1))
    hist, _ = np.histogram(nz, bins=edges)
    st.density_histogram = [int(v) for v in hist]
    st.density_histogram_edges = [float(v) for v in edges]
