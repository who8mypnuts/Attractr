"""Screen-space lighting from the nearest-depth (zmin) buffer for Liquid / Solid styles."""

from __future__ import annotations

import math

import numpy as np

from attractr.core.render.settings import Light


def _blur3(a: np.ndarray) -> np.ndarray:
    p = np.pad(a, 1, mode="edge")
    return (
        p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:]
        + 2 * p[1:-1, :-2] + 4 * p[1:-1, 1:-1] + 2 * p[1:-1, 2:]
        + p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]
    ) / 16.0


def height_field(zmin: np.ndarray, mask: np.ndarray, pixels_per_unit: float) -> np.ndarray:
    """Nearest-surface height in *pixel units* (near = high), holes filled with the
    minimum so edges slope down to the background."""
    mask = mask & np.isfinite(zmin)  # an inverted look marks empty pixels as "surface"; they have no depth
    h = np.where(mask, -zmin, np.nan).astype(np.float32)
    fill = np.nanmin(h) if mask.any() else 0.0
    h = np.where(mask, h, fill)
    return _blur3(h * pixels_per_unit)


def normals(height: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(height)
    n = np.stack([-gx, -gy, np.ones_like(height)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n


def light_direction(light: Light) -> np.ndarray:
    az, el = math.radians(light.azimuth), math.radians(light.elevation)
    return np.array([math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)], dtype=np.float32)


def shade(normals_: np.ndarray, light: Light) -> tuple[np.ndarray, np.ndarray]:
    """Return (diffuse+ambient factor [H,W], specular term [H,W])."""
    L = light_direction(light)
    ndotl = np.clip(normals_ @ L, 0.0, 1.0)
    view = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    half = L + view
    half /= np.linalg.norm(half)
    spec = np.power(np.clip(normals_ @ half, 0.0, 1.0), light.shininess) * light.specular
    return light.ambient + light.diffuse * ndotl, spec
