"""Progress reporting with ETA, usable from any thread."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Progress:
    fraction: float  # 0..1
    message: str = ""
    elapsed: float = 0.0
    eta: float | None = None  # seconds remaining, None if unknown

    def format_eta(self) -> str:
        if self.eta is None:
            return "—"
        s = int(self.eta)
        if s < 60:
            return f"{s}s"
        if s < 3600:
            return f"{s // 60}m {s % 60:02d}s"
        return f"{s // 3600}h {(s % 3600) // 60:02d}m"


ProgressCallback = Callable[[Progress], None]


class ProgressTracker:
    """Turns ``(fraction, message)`` updates into :class:`Progress` objects with ETA and
    rate-limits callbacks to at most one every ``min_interval`` seconds."""

    def __init__(self, callback: ProgressCallback | None, min_interval: float = 0.1) -> None:
        self._cb = callback
        self._start = time.perf_counter()
        self._last = 0.0
        self._min = min_interval
        self.latest = Progress(0.0)

    def update(self, fraction: float, message: str = "", force: bool = False) -> None:
        now = time.perf_counter()
        elapsed = now - self._start
        fraction = min(max(fraction, 0.0), 1.0)
        eta = (elapsed / fraction - elapsed) if fraction > 0.01 else None
        self.latest = Progress(fraction, message, elapsed, eta)
        if self._cb is not None and (force or now - self._last >= self._min or fraction >= 1.0):
            self._last = now
            self._cb(self.latest)

    def done(self, message: str = "done") -> None:
        self.update(1.0, message, force=True)


def null_progress(_: Progress) -> None:
    """No-op callback for headless runs."""
