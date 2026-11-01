"""Jobs panel: render queue with progress bars and cancel buttons."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget

from attractr.core.jobs.job import Job
from attractr.core.jobs.progress import Progress
from attractr.core.jobs.queue import JobQueue


class JobRow(QWidget):
    def __init__(self, job: Job, queue: JobQueue, parent=None) -> None:
        super().__init__(parent)
        self.job = job
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        self.label = QLabel(job.name)
        self.label.setMinimumWidth(120)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(True)
        self.eta = QLabel("")
        self.eta.setMinimumWidth(70)
        self.btn = QPushButton("✕")
        self.btn.setFixedWidth(28)
        self.btn.setToolTip("Cancel")
        lay.addWidget(self.label)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self.eta)
        lay.addWidget(self.btn)
        self.btn.clicked.connect(lambda: queue.cancel(job))
        job.progress.connect(self.on_progress)

    def on_progress(self, p: Progress) -> None:
        self.bar.setValue(int(p.fraction * 1000))
        self.bar.setFormat(f"{p.fraction * 100:.1f} %  {p.message}")
        self.eta.setText(f"ETA {p.format_eta()}")

    def finish(self) -> None:
        state = self.job.state
        self.bar.setValue(1000 if state == "done" else self.bar.value())
        self.bar.setFormat({"done": "done", "failed": "failed", "cancelled": "cancelled"}.get(state, state))
        self.eta.setText("")
        self.btn.setEnabled(False)
        if state == "failed":
            self.label.setToolTip(self.job.error or "")


class JobsPanel(QWidget):
    def __init__(self, queue: JobQueue, parent=None) -> None:
        super().__init__(parent)
        self.queue = queue
        self.rows: dict[int, JobRow] = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        btns = QHBoxLayout()
        self.btn_clear = QPushButton("Clear finished")
        self.btn_cancel_all = QPushButton("Cancel all")
        btns.addWidget(self.btn_clear)
        btns.addWidget(self.btn_cancel_all)
        outer.addLayout(btns)
        self.btn_clear.clicked.connect(self.clear_finished)
        self.btn_cancel_all.clicked.connect(queue.cancel_all)
        queue.job_added.connect(self.add_job)
        queue.job_ended.connect(self.job_ended)

    def add_job(self, job: Job) -> None:
        row = JobRow(job, self.queue)
        self.rows[job.id] = row
        self.lay.insertWidget(self.lay.count() - 1, row)

    def job_ended(self, job: Job) -> None:
        row = self.rows.get(job.id)
        if row:
            row.finish()

    def clear_finished(self) -> None:
        for jid, row in list(self.rows.items()):
            if row.job.state in ("done", "failed", "cancelled"):
                row.setParent(None)
                row.deleteLater()
                del self.rows[jid]
