"""Colour-space conversions used when interpolating gradient stops.

All functions are vectorised: inputs/outputs are float arrays ``[..., 3]`` in 0..1 sRGB
unless stated otherwise.
"""

from __future__ import annotations

import numpy as np

SPACES = ("rgb", "linear", "hsv", "hsv_long", "oklab")


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def rgb_to_hsv(c: np.ndarray) -> np.ndarray:
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    mx = np.max(c, axis=-1)
    mn = np.min(c, axis=-1)
    d = mx - mn
    h = np.zeros_like(mx)
    nz = d > 1e-12
    rm = nz & (mx == r)
    gm = nz & (mx == g) & ~rm
    bm = nz & ~rm & ~gm
    h[rm] = ((g[rm] - b[rm]) / d[rm]) % 6.0
    h[gm] = (b[gm] - r[gm]) / d[gm] + 2.0
    h[bm] = (r[bm] - g[bm]) / d[bm] + 4.0
    h = h / 6.0
    s = np.where(mx > 1e-12, d / np.maximum(mx, 1e-12), 0.0)
    return np.stack([h, s, mx], axis=-1)


def hsv_to_rgb(c: np.ndarray) -> np.ndarray:
    h, s, v = c[..., 0] % 1.0, c[..., 1], c[..., 2]
    i = np.floor(h * 6.0)
    f = h * 6.0 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    i = i.astype(int) % 6
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)


_M1 = np.array(
    [[0.4122214708, 0.5363325363, 0.0514459929],
     [0.2119034982, 0.6806995451, 0.1073969566],
     [0.0883024619, 0.2817188376, 0.6299787005]]
)
_M2 = np.array(
    [[0.2104542553, 0.7936177850, -0.0040720468],
     [1.9779984951, -2.4285922050, 0.4505937099],
     [0.0259040371, 0.7827717662, -0.8086757660]]
)


def rgb_to_oklab(c: np.ndarray) -> np.ndarray:
    lin = srgb_to_linear(c)
    lms = lin @ _M1.T
    lms = np.cbrt(lms)
    return lms @ _M2.T


def oklab_to_rgb(lab: np.ndarray) -> np.ndarray:
    lms = lab @ np.linalg.inv(_M2).T
    lms = lms ** 3
    lin = lms @ np.linalg.inv(_M1).T
    return linear_to_srgb(lin)


def to_space(rgb: np.ndarray, space: str) -> np.ndarray:
    if space == "rgb":
        return rgb
    if space == "linear":
        return srgb_to_linear(rgb)
    if space in ("hsv", "hsv_long"):
        return rgb_to_hsv(rgb)
    if space == "oklab":
        return rgb_to_oklab(rgb)
    raise ValueError(f"unknown colour space {space!r}")


def from_space(c: np.ndarray, space: str) -> np.ndarray:
    if space == "rgb":
        return c
    if space == "linear":
        return linear_to_srgb(c)
    if space in ("hsv", "hsv_long"):
        return hsv_to_rgb(c)
    if space == "oklab":
        return oklab_to_rgb(c)
    raise ValueError(f"unknown colour space {space!r}")


def lerp_in_space(c0: np.ndarray, c1: np.ndarray, t: np.ndarray, space: str) -> np.ndarray:
    """Interpolate two sRGB colours (shape [3]) at fractions ``t`` (shape [n]) in ``space``."""
    a = to_space(c0[None, :], space)[0]
    b = to_space(c1[None, :], space)[0]
    tt = t[:, None]
    if space in ("hsv", "hsv_long"):
        dh = b[0] - a[0]
        if space == "hsv":  # shortest hue arc
            if dh > 0.5:
                dh -= 1.0
            elif dh < -0.5:
                dh += 1.0
        else:  # longest arc
            if 0.0 < dh < 0.5:
                dh -= 1.0
            elif -0.5 < dh <= 0.0:
                dh += 1.0
        # grey endpoints have undefined hue: borrow the other end's hue
        if a[1] < 1e-6:
            a = a.copy()
            a[0] = b[0]
            dh = 0.0
        if b[1] < 1e-6:
            dh = 0.0
        h = a[0] + dh * t
        sv = a[1:] + (b[1:] - a[1:]) * tt
        out = np.concatenate([h[:, None], sv], axis=1)
    else:
        out = a + (b - a) * tt
    return np.clip(from_space(out, space), 0.0, 1.0)
