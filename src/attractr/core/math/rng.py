"""Deterministic seeding helpers shared by every engine.

Each trajectory owns a 32-bit xorshift state derived from ``(seed, trajectory_id)``
through SplitMix-style mixing, so CPU, GLSL and OpenCL engines seed identically.
"""

from __future__ import annotations

import numpy as np

MASK32 = 0xFFFFFFFF


def mix32(a: int, b: int) -> int:
    """Integer hash of two 32-bit values (murmur3 finaliser on ``a ^ rot(b)``)."""
    h = (a ^ ((b * 0x9E3779B9) & MASK32)) & MASK32
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & MASK32
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & MASK32
    h ^= h >> 16
    return h or 1  # xorshift must never be seeded with 0


def trajectory_seeds(seed: int, n: int) -> np.ndarray:
    """Vectorised :func:`mix32` for trajectory ids ``0..n-1`` → uint32 array."""
    ids = np.arange(n, dtype=np.uint64)
    h = (np.uint64(seed & MASK32) ^ ((ids * np.uint64(0x9E3779B9)) & np.uint64(MASK32))) & np.uint64(MASK32)
    h ^= h >> np.uint64(16)
    h = (h * np.uint64(0x85EBCA6B)) & np.uint64(MASK32)
    h ^= h >> np.uint64(13)
    h = (h * np.uint64(0xC2B2AE35)) & np.uint64(MASK32)
    h ^= h >> np.uint64(16)
    h[h == 0] = 1
    return h.astype(np.uint32)


def xorshift32_floats(state: np.ndarray, count: int) -> np.ndarray:
    """Advance an array of xorshift32 states ``count`` times; return floats in [0,1)
    of shape ``(count, len(state))``.  Used for seeding initial conditions on the host."""
    s = state.astype(np.uint32).copy()
    out = np.empty((count, s.size), dtype=np.float64)
    for i in range(count):
        s ^= s << np.uint32(13)
        s ^= s >> np.uint32(17)
        s ^= s << np.uint32(5)
        out[i] = (s >> np.uint32(8)).astype(np.float64) * (1.0 / 16777216.0)
    state[:] = s
    return out
