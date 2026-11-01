"""QThread wrapper that executes one :class:`Job`."""

from __future__ import annotations

from PySide6.QtCore import QThread

from attractr.core.jobs.job import Job


class JobThread(QThread):
    def __init__(self, job: Job, parent=None) -> None:
        super().__init__(parent)
        self.job = job
        job.moveToThread(self)

    def run(self) -> None:  # executes in the new thread
        self.job.execute()

    def request_cancel(self) -> None:
        self.job.cancel()
