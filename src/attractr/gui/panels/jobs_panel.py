"""Jobs panel: render queue with progress bars, live thumbnails and per-job controls
(cancel, *finish now*, *checkpoint now*)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget

from attractr.core.jobs.job import Job
from attractr.core.jobs.progress import Progress
from attractr.core.jobs.queue import JobQueue
from attractr.core.render.result import RenderResult
from attractr.core.render.thumb import shrink_result
from attractr.gui.controllers.develop_controller import DevelopController
from attractr.i18n import tr

THUMB = 112


class JobRow(QWidget):
    def __init__(self, job: Job, queue: JobQueue, parent=None) -> None:
        super().__init__(parent)
        self.job = job
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        self.thumb = QLabel()
        self.thumb.setFixedSize(THUMB, THUMB)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setStyleSheet("background:#111; border:1px solid #333")
        self.thumb.setVisible(False)
        self.label = QLabel(job.name)
        self.label.setMinimumWidth(120)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(True)
        self.eta = QLabel("")
        self.eta.setMinimumWidth(70)
        self.btn_finish = QPushButton("⏹")
        self.btn_finish.setFixedWidth(28)
        self.btn_finish.setToolTip(tr("Finish now — stop accumulating and save what has been rendered so far"))
        self.btn_finish.setVisible(hasattr(job, "finish_now"))
        self.btn_ckpt = QPushButton("💾")
        self.btn_ckpt.setFixedWidth(28)
        self.btn_ckpt.setToolTip(tr("Write a checkpoint now (Render → Resume from checkpoint… continues it later)"))
        self.btn_ckpt.setVisible(hasattr(job, "checkpoint_now"))
        self.btn = QPushButton("✕")
        self.btn.setFixedWidth(28)
        self.btn.setToolTip(tr("Cancel"))
        lay.addWidget(self.thumb)
        lay.addWidget(self.label)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self.eta)
        lay.addWidget(self.btn_finish)
        lay.addWidget(self.btn_ckpt)
        lay.addWidget(self.btn)
        self.btn.clicked.connect(lambda: queue.cancel(job))
        self.btn_finish.clicked.connect(self._finish)
        self.btn_ckpt.clicked.connect(lambda: job.checkpoint_now())
        job.progress.connect(self.on_progress)
        job.partial.connect(self.on_partial)
        self.develop = DevelopController(self)
        self.develop.imageReady.connect(self._on_thumb)

    def _finish(self) -> None:
        self.job.finish_now()
        self.btn_finish.setEnabled(False)
        self.bar.setFormat(tr("finishing…"))

    def on_progress(self, p: Progress) -> None:
        self.bar.setValue(int(p.fraction * 1000))
        self.bar.setFormat(f"{p.fraction * 100:.1f} %  {p.message}")
        self.eta.setText(f"ETA {p.format_eta()}")

    def on_partial(self, result: object) -> None:
        if isinstance(result, RenderResult):
            self.develop.request(shrink_result(result, THUMB), result.settings.look)

    def _on_thumb(self, img, dev, result) -> None:
        self.thumb.setVisible(True)
        self.thumb.setPixmap(QPixmap.fromImage(img).scaled(THUMB, THUMB, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def finish(self) -> None:
        state = self.job.state
        self.bar.setValue(1000 if state == "done" else self.bar.value())
        self.bar.setFormat({"done": "done", "failed": "failed", "cancelled": "cancelled"}.get(state, state))
        self.eta.setText("")
        for b in (self.btn, self.btn_finish, self.btn_ckpt):
            b.setEnabled(False)
        if state == "failed":
            self.label.setToolTip(self.job.error or "")
        ck = getattr(self.job, "checkpoint_file", None)
        if state == "cancelled" and ck is not None and ck.exists():
            self.label.setToolTip(f"checkpoint kept: {ck}")
            self.bar.setFormat(tr("cancelled · checkpoint kept"))


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
        self.btn_clear = QPushButton(tr("Clear finished"))
        self.btn_cancel_all = QPushButton(tr("Cancel all"))
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
