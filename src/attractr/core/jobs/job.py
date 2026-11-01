"""Job abstraction: a unit of work that runs off the GUI thread and reports via signals.

A :class:`Job` can also be executed synchronously (CLI, tests) with :meth:`Job.execute`.
"""

from __future__ import annotations

import itertools
import traceback
from typing import Any

from PySide6.QtCore import QObject, Signal

from attractr.core.jobs.cancel import Cancelled, CancelToken
from attractr.core.jobs.progress import Progress, ProgressTracker

_ids = itertools.count(1)


class Job(QObject):
    """Subclass and implement :meth:`run`.  Emit intermediate results via
    :attr:`partial` if the work is progressive."""

    progress = Signal(object)  # Progress
    partial = Signal(object)  # any intermediate result (e.g. a preview image)
    finished = Signal(object)  # final result
    failed = Signal(str)  # traceback text
    cancelled = Signal()

    def __init__(self, name: str = "job") -> None:
        super().__init__()
        self.id = next(_ids)
        self.name = name
        self.cancel_token = CancelToken()
        self.result: Any = None
        self.error: str | None = None
        self.state = "pending"  # pending | running | done | failed | cancelled

    # ── to implement ────────────────────────────────────────────────────────────
    def run(self, cancel: CancelToken, tracker: ProgressTracker) -> Any:  # pragma: no cover
        raise NotImplementedError

    # ── API ─────────────────────────────────────────────────────────────────────
    def cancel(self) -> None:
        self.cancel_token.cancel()

    def execute(self) -> Any:
        """Run synchronously on the calling thread, emitting the same signals."""
        self.state = "running"
        tracker = ProgressTracker(self.progress.emit)
        try:
            self.result = self.run(self.cancel_token, tracker)
        except Cancelled:
            self.state = "cancelled"
            self.cancelled.emit()
            return None
        except Exception:  # noqa: BLE001 — report anything to the UI
            self.state = "failed"
            self.error = traceback.format_exc()
            self.failed.emit(self.error)
            return None
        self.state = "done"
        tracker.done()
        self.finished.emit(self.result)
        return self.result

    def __repr__(self) -> str:
        return f"<Job #{self.id} {self.name} {self.state}>"


class FunctionJob(Job):
    """Wrap a plain callable ``fn(cancel, tracker) -> result``."""

    def __init__(self, fn, name: str = "function") -> None:
        super().__init__(name)
        self._fn = fn

    def run(self, cancel: CancelToken, tracker: ProgressTracker) -> Any:
        return self._fn(cancel, tracker)


__all__ = ["Job", "FunctionJob", "Progress", "ProgressTracker", "CancelToken", "Cancelled"]
