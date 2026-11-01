"""Easing functions for keyframe interpolation (t in 0..1 → 0..1)."""

from __future__ import annotations

import math
from collections.abc import Callable

EASINGS = ("linear", "ease_in", "ease_out", "ease_in_out", "smooth", "hold", "bezier")


def linear(t: float) -> float:
    return t


def ease_in(t: float) -> float:
    return t * t


def ease_out(t: float) -> float:
    return 1 - (1 - t) ** 2


def ease_in_out(t: float) -> float:
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2


def smooth(t: float) -> float:
    return t * t * (3 - 2 * t)


def hold(t: float) -> float:
    return 0.0 if t < 1.0 else 1.0


def cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> Callable[[float], float]:
    """CSS-style cubic-bezier easing (solve x(t) = x by Newton iterations)."""

    def bx(s: float) -> float:
        return 3 * (1 - s) ** 2 * s * x1 + 3 * (1 - s) * s * s * x2 + s**3

    def by(s: float) -> float:
        return 3 * (1 - s) ** 2 * s * y1 + 3 * (1 - s) * s * s * y2 + s**3

    def f(x: float) -> float:
        s = x
        for _ in range(8):
            dx = bx(s) - x
            d = 3 * (1 - s) ** 2 * x1 + 6 * (1 - s) * s * (x2 - x1) + 3 * s * s * (1 - x2)
            if abs(d) < 1e-9:
                break
            s -= dx / d
            s = min(max(s, 0.0), 1.0)
        return by(s)

    return f


def get_easing(name: str, bezier: tuple[float, float, float, float] | None = None) -> Callable[[float], float]:
    if name == "bezier" and bezier:
        return cubic_bezier(*bezier)
    return {"linear": linear, "ease_in": ease_in, "ease_out": ease_out, "ease_in_out": ease_in_out, "smooth": smooth, "hold": hold}.get(name, linear)


def loop_time(t: float, duration: float, mode: str) -> float:
    """Map an absolute time onto the timeline for loop / ping-pong playback."""
    if duration <= 0:
        return 0.0
    if mode == "loop":
        return t % duration
    if mode == "pingpong":
        c = t % (2 * duration)
        return c if c <= duration else 2 * duration - c
    return min(max(t, 0.0), duration)


__all__ = ["EASINGS", "get_easing", "loop_time", "math"]
