"""Trajectory state containers shared by the CPU engine and the framing pass."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from attractr.core.math.rng import trajectory_seeds, xorshift32_floats


@dataclass
class TrajectoryState:
    """Per-trajectory arrays the CPU kernel reads and writes between passes (see the fields)."""
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
    W: np.ndarray | None = None  # 4th state variable (starts at 0)
    SEC: np.ndarray | None = None  # previous Poincaré-section value
    # escape-time orbit bookkeeping (kind: escape): start point, mode, counters
    SX: np.ndarray | None = None
    SY: np.ndarray | None = None
    SZ: np.ndarray | None = None
    EMODE: np.ndarray | None = None
    ECNT: np.ndarray | None = None
    ENREP: np.ndarray | None = None

    def __post_init__(self) -> None:
        n = self.X.shape[0]
        if self.W is None:
            self.W = np.zeros(n, dtype=np.float64)
        if self.SEC is None:
            self.SEC = np.zeros(n, dtype=np.float64)
        if self.SX is None:
            self.SX, self.SY, self.SZ = self.X.copy(), self.Y.copy(), self.Z.copy()
        if self.EMODE is None:
            self.EMODE = np.zeros(n, dtype=np.uint8)
            self.ECNT = np.zeros(n, dtype=np.int64)
            self.ENREP = np.zeros(n, dtype=np.int64)

    def escape_state(self) -> np.ndarray:
        """``[n, 8]`` float32 rows (x0, y0, z0, 0, mode, cnt, nrep, 0) for the GPU kernels."""
        out = np.zeros((self.n, 8), dtype=np.float32)
        out[:, 0], out[:, 1], out[:, 2] = self.SX, self.SY, self.SZ
        out[:, 4], out[:, 5], out[:, 6] = self.EMODE, self.ECNT, self.ENREP
        return out

    @property
    def n(self) -> int:
        return int(self.X.shape[0])

    def reset_history(self) -> None:
        """Forget the previous points (no gap-fill segment across the warm-up boundary)."""
        self.HAVE[:] = 0


def seed_trajectories(n: int, seed: int, ic: tuple[float, ...], jitter: float) -> TrajectoryState:
    """Deterministic initial conditions: ``ic + (rand − 0.5)·jitter`` per trajectory."""
    rs = trajectory_seeds(seed, n)
    r = xorshift32_floats(rs, 3)  # advances rs in place — same as the kernels' _reseed
    X = ic[0] + (r[0] - 0.5) * jitter
    Y = ic[1] + (r[1] - 0.5) * jitter
    Z = ic[2] + (r[2] - 0.5) * jitter
    zeros = np.zeros(n, dtype=np.float64)
    w0 = float(ic[3]) if len(ic) > 3 else 0.0
    return TrajectoryState(
        X.astype(np.float64), Y.astype(np.float64), Z.astype(np.float64), rs,
        zeros.copy(), zeros.copy(), zeros.copy(), np.zeros(n, dtype=np.uint8),
        zeros.copy(), zeros.copy(), zeros.copy(),
        W=np.full(n, w0, dtype=np.float64),
    )


def seed_from_points(n: int, seed: int, pts: np.ndarray, jitter: float) -> TrajectoryState:
    """Initial conditions drawn (deterministically) from *states* already on the attractor
    (``pts`` is the framing sample: columns 0..3 = x, y, z, w), so accumulation needs only a
    short decorrelation warm-up."""
    st = pts[:, :4] if pts.shape[1] >= 4 else np.concatenate([pts[:, :3], np.zeros((pts.shape[0], 1))], axis=1)
    good = st[np.all(np.isfinite(st), axis=1)]
    if good.shape[0] == 0:
        return seed_trajectories(n, seed, (0.0, 0.0, 0.0, 0.0), jitter)
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
        zeros.copy(), zeros.copy(), zeros.copy(), W=base[:, 3].astype(np.float64).copy(),
    )
