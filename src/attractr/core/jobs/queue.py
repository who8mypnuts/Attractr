"""Sequential/limited-concurrency job queue with Qt signals for the Jobs panel."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QObject, Signal

from attractr.core.jobs.job import Job
from attractr.core.jobs.worker import JobThread


class JobQueue(QObject):
    job_added = Signal(object)
    job_started = Signal(object)
    job_ended = Signal(object)  # finished, failed or cancelled — check job.state
    idle = Signal()

    def __init__(self, max_concurrent: int = 1, parent=None) -> None:
        super().__init__(parent)
        self.max_concurrent = max_concurrent
        self._pending: deque[Job] = deque()
        self._running: dict[int, JobThread] = {}

    # ── API ─────────────────────────────────────────────────────────────────────
    def submit(self, job: Job) -> Job:
        self._pending.append(job)
        self.job_added.emit(job)
        self._pump()
        return job

    def cancel(self, job: Job) -> None:
        if job in self._pending:
            self._pending.remove(job)
            job.state = "cancelled"
            job.cancelled.emit()
            self.job_ended.emit(job)
            return
        job.cancel()

    def cancel_all(self) -> None:
        for job in list(self._pending):
            self.cancel(job)
        for th in list(self._running.values()):
            th.request_cancel()

    @property
    def pending(self) -> list[Job]:
        return list(self._pending)

    @property
    def running(self) -> list[Job]:
        return [t.job for t in self._running.values()]

    @property
    def is_idle(self) -> bool:
        return not self._pending and not self._running

    def wait_all(self, timeout_ms: int = -1) -> None:
        for th in list(self._running.values()):
            th.wait(timeout_ms) if timeout_ms >= 0 else th.wait()

    # ── internals ───────────────────────────────────────────────────────────────
    def _pump(self) -> None:
        while self._pending and len(self._running) < self.max_concurrent:
            job = self._pending.popleft()
            th = JobThread(job, self)
            self._running[job.id] = th
            th.finished.connect(lambda j=job: self._on_thread_done(j))
            job.state = "running"
            self.job_started.emit(job)
            th.start()

    def _on_thread_done(self, job: Job) -> None:
        th = self._running.pop(job.id, None)
        if th is not None:
            th.deleteLater()
        self.job_ended.emit(job)
        self._pump()
        if self.is_idle:
            self.idle.emit()
