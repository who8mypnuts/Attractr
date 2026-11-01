"""Tiny PIL-based plots for reports (no matplotlib dependency)."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw


def histogram_plot(counts: list[int], edges: list[float], path: str | Path, size=(640, 220)) -> Path:
    W, H = size
    img = Image.new("RGB", (W, H), (14, 14, 20))
    d = ImageDraw.Draw(img)
    m = max(counts) if counts else 1
    n = len(counts)
    pad = 36
    bw = (W - 2 * pad) / max(n, 1)
    for i, c in enumerate(counts):
        h = 0 if c == 0 else (math.log1p(c) / math.log1p(m)) * (H - 2 * pad)
        x0 = pad + i * bw
        d.rectangle([x0, H - pad - h, x0 + bw - 1, H - pad], fill=(79, 195, 247))
    d.line([pad, H - pad, W - pad, H - pad], fill=(90, 90, 110))
    d.line([pad, pad, pad, H - pad], fill=(90, 90, 110))
    d.text((pad, 8), "pixels (log scale) vs density bin (log-spaced)", fill=(180, 180, 200))
    if edges:
        d.text((pad, H - pad + 6), f"{edges[0]:.0f}", fill=(150, 150, 170))
        d.text((W - pad - 40, H - pad + 6), f"{edges[-1]:.0f}", fill=(150, 150, 170))
    img.save(path)
    return Path(path)
