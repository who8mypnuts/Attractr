"""Trajectory state containers shared by the CPU engine and the framing pass."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from attractr.core.math.rng import trajectory_seeds, xorshift32_floats


@dataclass
class TrajectoryState:
    X: np.ndarray
    Y: np.ndarray
    Z: np.ndarray
    RS: np.ndarray  # uint32 rng states
    PU: np.ndarray  # previous projected u
    PV: np.ndarray
    PC: np.ndarray  # previous colour value
    HAVE: np.ndarray  # uint8 — previous point valid
    DXp: np.ndarray  # previous step deltas (curvature)
    DYp: np.ndarray
    DZp: np.ndarray

    @property
    def n(self) -> int:
        return int(self.X.shape[0])

    def reset_history(self) -> None:
        self.HAVE[:] = 0


def seed_trajectories(n: int, seed: int, ic: tuple[float, float, float], jitter: float) -> TrajectoryState:
    """Deterministic initial conditions: ``ic + (rand − 0.5)·jitter`` per trajectory."""
    rs = trajectory_seeds(seed, n)
    r = xorshift32_floats(rs, 3)  # advances rs in place — same as the kernels' _reseed
    X = ic[0] + (r[0] - 0.5) * jitter
    Y = ic[1] + (r[1] - 0.5) * jitter
    Z = ic[2] + (r[2] - 0.5) * jitter
    zeros = np.zeros(n, dtype=np.float64)
    return TrajectoryState(
        X.astype(np.float64), Y.astype(np.float64), Z.astype(np.float64), rs,
        zeros.copy(), zeros.copy(), zeros.copy(), np.zeros(n, dtype=np.uint8),
        zeros.copy(), zeros.copy(), zeros.copy(),
    )


def seed_from_points(n: int, seed: int, pts: np.ndarray, jitter: float) -> TrajectoryState:
    """Initial conditions drawn (deterministically) from points already on the attractor,
    so accumulation needs only a short decorrelation warm-up."""
    good = pts[np.all(np.isfinite(pts), axis=1)]
    if good.shape[0] == 0:
        return seed_trajectories(n, seed, (0.0, 0.0, 0.0), jitter)
    rs = trajectory_seeds(seed, n)
    r = xorshift32_floats(rs, 4)
    idx = np.minimum((r[0] * good.shape[0]).astype(np.int64), good.shape[0] - 1)
    base = good[idx]
    X = base[:, 0] + (r[1] - 0.5) * jitter
    Y = base[:, 1] + (r[2] - 0.5) * jitter
    Z = base[:, 2] + (r[3] - 0.5) * jitter
    zeros = np.zeros(n, dtype=np.float64)
    return TrajectoryState(
        X.astype(np.float64), Y.astype(np.float64), Z.astype(np.float64), rs,
        zeros.copy(), zeros.copy(), zeros.copy(), np.zeros(n, dtype=np.uint8),
        zeros.copy(), zeros.copy(), zeros.copy(),
    )
