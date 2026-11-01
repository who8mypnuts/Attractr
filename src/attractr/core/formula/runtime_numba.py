"""numba helper functions referenced by generated CPU code (``_name`` for DSL ``name``).

These mirror the GLSL/OpenCL semantics exactly (see docs/formula_dsl.md §3).
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

_OPTS = {"cache": True, "nogil": True, "inline": "always", "error_model": "numpy"}


@njit(**_OPTS)
def _rand(rs, i):
    """xorshift32 on state array ``rs`` at index ``i`` → float in [0, 1)."""
    s = rs[i]
    s ^= (s << np.uint32(13)) & np.uint32(0xFFFFFFFF)
    s ^= s >> np.uint32(17)
    s ^= (s << np.uint32(5)) & np.uint32(0xFFFFFFFF)
    rs[i] = s
    return float(s >> np.uint32(8)) * (1.0 / 16777216.0)


@njit(**_OPTS)
def _randn(rs, i):
    u1 = _rand(rs, i)
    u2 = _rand(rs, i)
    if u1 < 1e-12:
        u1 = 1e-12
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


@njit(**_OPTS)
def _log(x):
    ax = abs(x)
    if ax < 1e-300:
        return -690.0
    return math.log(ax)


@njit(**_OPTS)
def _log2(x):
    return _log(x) * 1.4426950408889634


@njit(**_OPTS)
def _log10(x):
    return _log(x) * 0.4342944819032518


@njit(**_OPTS)
def _sqrt(x):
    return math.sqrt(abs(x))


@njit(**_OPTS)
def _cbrt(x):
    return math.copysign(abs(x) ** (1.0 / 3.0), x)


@njit(**_OPTS)
def _sign(x):
    if x > 0.0:
        return 1.0
    if x < 0.0:
        return -1.0
    return 0.0


@njit(**_OPTS)
def _floor(x):
    return float(math.floor(x))


@njit(**_OPTS)
def _ceil(x):
    return float(math.ceil(x))


@njit(**_OPTS)
def _round(x):
    return float(math.floor(x + 0.5))


@njit(**_OPTS)
def _fract(x):
    return x - math.floor(x)


@njit(**_OPTS)
def _mod(a, b):
    if b == 0.0:
        return 0.0
    return a - b * math.floor(a / b)


@njit(**_OPTS)
def _pow(a, b):
    return a**b


@njit(**_OPTS)
def _clamp(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


@njit(**_OPTS)
def _mix(a, b, t):
    return a + (b - a) * t


@njit(**_OPTS)
def _smoothstep(e0, e1, x):
    if e1 == e0:
        return 0.0 if x < e0 else 1.0
    t = _clamp((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


@njit(**_OPTS)
def _step(edge, x):
    return 0.0 if x < edge else 1.0


@njit(**_OPTS)
def _hypot(a, b):
    return math.sqrt(a * a + b * b)


@njit(**_OPTS)
def _re_pow(x, y, n):
    """Real part of (x + iy)^n for integer n ≥ 0 (binary exponentiation)."""
    k = int(n)
    rr, ri = 1.0, 0.0
    bx, by = x, y
    while k > 0:
        if k & 1:
            rr, ri = rr * bx - ri * by, rr * by + ri * bx
        bx, by = bx * bx - by * by, 2.0 * bx * by
        k >>= 1
    return rr


@njit(**_OPTS)
def _im_pow(x, y, n):
    k = int(n)
    rr, ri = 1.0, 0.0
    bx, by = x, y
    while k > 0:
        if k & 1:
            rr, ri = rr * bx - ri * by, rr * by + ri * bx
        bx, by = bx * bx - by * by, 2.0 * bx * by
        k >>= 1
    return ri


__all__ = [n for n in dir() if n.startswith("_") and not n.startswith("__") and n != "_OPTS"]
