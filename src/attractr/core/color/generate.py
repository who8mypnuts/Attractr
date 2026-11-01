"""Random / harmonious gradient generators for the editor's Randomize button."""

from __future__ import annotations

import random

import numpy as np

from attractr.core.color.gradient import Gradient, Stop
from attractr.core.color.interpolation import hsv_to_rgb

SCHEMES = ("analogous", "complementary", "triadic", "monochrome", "rainbow")


def random_gradient(scheme: str = "analogous", n_stops: int = 5, dark_start: bool = True, rng: random.Random | None = None) -> Gradient:
    rng = rng or random.Random()
    base_h = rng.random()
    if scheme == "complementary":
        hues = [base_h + (0.5 if i % 2 else 0.0) + rng.uniform(-0.04, 0.04) for i in range(n_stops)]
    elif scheme == "triadic":
        hues = [base_h + (i % 3) / 3 + rng.uniform(-0.03, 0.03) for i in range(n_stops)]
    elif scheme == "monochrome":
        hues = [base_h + rng.uniform(-0.02, 0.02) for _ in range(n_stops)]
    elif scheme == "rainbow":
        hues = [base_h + i / n_stops for i in range(n_stops)]
    else:
        hues = [base_h + (i - n_stops / 2) * 0.06 + rng.uniform(-0.02, 0.02) for i in range(n_stops)]
    stops = []
    for i, h in enumerate(hues):
        t = i / (n_stops - 1)
        v = t**0.8 if dark_start else 0.55 + 0.45 * t
        s = 0.9 - 0.6 * t**2 if dark_start else 0.8 - 0.5 * t
        rgb = hsv_to_rgb(np.array([[h % 1.0, s, v]]))[0]
        if dark_start and i == 0:
            rgb = rgb * 0.05
        stops.append(Stop(t, float(rgb[0]), float(rgb[1]), float(rgb[2])))
    return Gradient(tuple(stops), "oklab", scheme == "rainbow", f"Random {scheme}")
