"""Procedural backgrounds ported from the Android themes: stars, forest, ocean, aurora.

Deterministic for a given seed so exports match the preview pixel-for-pixel."""

from __future__ import annotations

import numpy as np

NAMES = ("stars", "forest", "ocean", "aurora")


def _grid(width: int, height: int):
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    return x / max(width - 1, 1), y / max(height - 1, 1)


def _vertical(c_top, c_bottom, width, height):
    _, v = _grid(width, height)
    top = np.asarray(c_top, np.float32)
    bot = np.asarray(c_bottom, np.float32)
    return top * (1 - v[..., None]) + bot * v[..., None]


def _stars(width, height, rng, base):
    img = _vertical((0.02, 0.02, 0.07), (0.0, 0.0, 0.02), width, height)
    n = int(width * height / 900)
    xs = rng.integers(0, width, n)
    ys = rng.integers(0, height, n)
    mag = rng.random(n) ** 3
    img[ys, xs] = np.maximum(img[ys, xs], mag[:, None] * np.array([0.9, 0.95, 1.0], np.float32))
    # a soft nebula glow
    u, v = _grid(width, height)
    cx, cy = rng.random(), rng.random()
    glow = np.exp(-((u - cx) ** 2 + (v - cy) ** 2) / 0.08) * 0.12
    img += glow[..., None] * np.array([0.35, 0.2, 0.6], np.float32)
    return img


def _forest(width, height, rng, base):
    img = _vertical((0.0, 0.08, 0.02), (0.0, 0.02, 0.0), width, height)
    u, v = _grid(width, height)
    for _ in range(6):
        cx, w = rng.random(), 0.05 + rng.random() * 0.15
        band = np.exp(-((u - cx) / w) ** 2) * (0.5 + 0.5 * v) * 0.08
        img += band[..., None] * np.array([0.1, 0.5, 0.15], np.float32)
    return img


def _ocean(width, height, rng, base):
    img = _vertical((0.0, 0.05, 0.12), (0.0, 0.01, 0.04), width, height)
    u, v = _grid(width, height)
    waves = 0.03 * np.sin(u * 25 + v * 6 + rng.random() * 6.28) * np.sin(v * 15)
    img += waves[..., None] * np.array([0.2, 0.6, 1.0], np.float32)
    return img


def _aurora(width, height, rng, base):
    img = _vertical((0.02, 0.02, 0.06), (0.0, 0.0, 0.02), width, height)
    u, v = _grid(width, height)
    for k in range(3):
        phase = rng.random() * 6.28
        curtain = np.exp(-((v - 0.35 - 0.12 * np.sin(u * 4 + phase + k)) / 0.09) ** 2)
        col = np.array([(0.1, 0.8, 0.4), (0.3, 0.2, 0.9), (0.1, 0.6, 0.9)][k], np.float32)
        img += (curtain * 0.12)[..., None] * col
    return img


def procedural_background(name: str, width: int, height: int, seed: int, base=(0, 0, 0)) -> np.ndarray:
    rng = np.random.default_rng(seed)
    fn = {"stars": _stars, "forest": _forest, "ocean": _ocean, "aurora": _aurora}.get(name, _stars)
    return np.clip(fn(width, height, rng, base), 0.0, 1.0).astype(np.float32)
