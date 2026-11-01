"""Gradient model: ordered colour stops → look-up table.

A :class:`Gradient` is immutable; editing creates a new instance (undo-friendly). The LUT
is the only thing engines and developers ever see.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache

import numpy as np

from attractr.core.color.interpolation import SPACES, lerp_in_space


@dataclass(frozen=True, order=True)
class Stop:
    pos: float
    r: float
    g: float
    b: float
    a: float = 1.0

    @property
    def rgb(self) -> tuple[float, float, float]:
        return (self.r, self.g, self.b)

    @property
    def hex(self) -> str:
        return "#" + "".join(f"{int(round(c * 255)):02x}" for c in self.rgb)

    @staticmethod
    def from_hex(pos: float, hex_color: str, a: float = 1.0) -> Stop:
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
        return Stop(pos, r, g, b, a)

    @staticmethod
    def from_255(pos: float, r: int, g: int, b: int, a: int = 255) -> Stop:
        return Stop(pos, r / 255.0, g / 255.0, b / 255.0, a / 255.0)


@dataclass(frozen=True)
class Gradient:
    stops: tuple[Stop, ...] = field(
        default_factory=lambda: (Stop(0.0, 0, 0, 0), Stop(1.0, 1, 1, 1))
    )
    space: str = "rgb"
    cyclic: bool = False
    name: str = "Custom"

    def __post_init__(self) -> None:
        if len(self.stops) < 2:
            raise ValueError("a gradient needs at least two stops")
        if self.space not in SPACES:
            raise ValueError(f"unknown interpolation space {self.space!r}")
        object.__setattr__(self, "stops", tuple(sorted(self.stops, key=lambda s: s.pos)))

    # ── editing helpers (return new gradients) ─────────────────────────────────
    def with_stop(self, index: int, stop: Stop) -> Gradient:
        stops = list(self.stops)
        stops[index] = stop
        return replace(self, stops=tuple(stops))

    def add_stop(self, stop: Stop) -> Gradient:
        return replace(self, stops=(*self.stops, stop))

    def remove_stop(self, index: int) -> Gradient:
        if len(self.stops) <= 2:
            return self
        stops = list(self.stops)
        del stops[index]
        return replace(self, stops=tuple(stops))

    def reversed(self) -> Gradient:
        return replace(self, stops=tuple(replace(s, pos=1.0 - s.pos) for s in self.stops))

    def distributed(self) -> Gradient:
        n = len(self.stops)
        return replace(
            self, stops=tuple(replace(s, pos=i / (n - 1)) for i, s in enumerate(self.stops))
        )

    def sample_at(self, t: float) -> Stop:
        """Colour at position ``t`` (0..1) — convenience for editors."""
        lut = self.lut(256)
        i = int(np.clip(round(t * 255), 0, 255))
        r, g, b, a = (float(v) for v in lut[i])
        return Stop(t, r, g, b, a)

    # ── LUT ────────────────────────────────────────────────────────────────────
    def lut(self, size: int = 1024, phase: float = 0.0, cycles: float = 1.0) -> np.ndarray:
        """RGBA float32 table of ``size`` entries.

        ``phase`` rotates the gradient (cyclic palettes wrap; others clamp) and ``cycles``
        repeats it — both are animatable look parameters, so they are applied here rather
        than baked into the stops.
        """
        return _lut_cached(self.stops, self.space, self.cyclic, size, float(phase), float(cycles))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "space": self.space,
            "cyclic": self.cyclic,
            "stops": [[s.pos, s.r, s.g, s.b, s.a] for s in self.stops],
        }

    @staticmethod
    def from_dict(d: dict) -> Gradient:
        stops = tuple(Stop(*[float(v) for v in s]) for s in d["stops"])
        return Gradient(stops, d.get("space", "rgb"), bool(d.get("cyclic", False)), d.get("name", "Custom"))


def _base_lut(stops: tuple[Stop, ...], space: str, size: int) -> np.ndarray:
    pos = np.array([s.pos for s in stops])
    cols = np.array([[s.r, s.g, s.b] for s in stops])
    alphas = np.array([s.a for s in stops])
    t = np.linspace(0.0, 1.0, size)
    out = np.empty((size, 4), dtype=np.float32)
    out[:, 3] = np.interp(t, pos, alphas)
    out[:, :3] = cols[0]
    for i in range(len(stops) - 1):
        p0, p1 = pos[i], pos[i + 1]
        if p1 <= p0:
            continue
        m = (t >= p0) & (t <= p1)
        if not m.any():
            continue
        f = (t[m] - p0) / (p1 - p0)
        out[m, :3] = lerp_in_space(cols[i], cols[i + 1], f, space)
    out[t > pos[-1], :3] = cols[-1]
    out[t < pos[0], :3] = cols[0]
    return out


@lru_cache(maxsize=256)
def _lut_cached(
    stops: tuple[Stop, ...], space: str, cyclic: bool, size: int, phase: float, cycles: float
) -> np.ndarray:
    base = _base_lut(stops, space, size)
    if phase == 0.0 and cycles == 1.0:
        return base
    t = np.linspace(0.0, 1.0, size) * cycles + phase
    if cyclic or cycles != 1.0:
        t = t % 1.0
    else:
        t = np.clip(t, 0.0, 1.0)
    idx = np.clip((t * (size - 1) + 0.5).astype(int), 0, size - 1)
    return base[idx]
