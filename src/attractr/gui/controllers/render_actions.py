"""The main window's render commands (quick render, resume, batch, re-render) and the
"queue finished" notification — kept out of :class:`MainWindow` so the window only wires
actions to them."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox, QSystemTrayIcon

from attractr.core.project import batch
from attractr.core.project.render_presets import RenderPreset, render_presets
from attractr.core.render.checkpoint import SUFFIX, Checkpoint, list_checkpoints
from attractr.core.render.settings import RenderSettings
from attractr.gui.controllers.render_job import RenderJob
from attractr.gui.state.render_prefs import RenderPrefs
from attractr.i18n import tr
from attractr.version import APP_NAME

log = logging.getLogger(__name__)
QUICK_RENDER_SIDE = 2048
QUICK_RENDER_PPP = 12.0
BATCH_TEMPLATE = "{name}_{w}x{h}"


def make_job(prefs: RenderPrefs, settings: RenderSettings, out_dir: Path | None = None, template: str | None = None,
             **options) -> RenderJob:
    """A :class:`RenderJob` that follows the output preferences (``options`` override single fields)."""
    kwargs = {"report_formats": list(prefs.report_formats), "checkpoint_every": prefs.checkpoint_every}
    kwargs.update(options)
    return RenderJob(settings, out_dir or prefs.folder, template or prefs.template, **kwargs)


class RenderActions(QObject):
    """Render menu commands for a main window.

    The window provides ``doc`` (the document), ``submit_job(job)`` and ``set_status(text)``;
    everything else (preferences, dialogs, job construction) happens here.
    """

    def __init__(self, window) -> None:
        super().__init__(window if isinstance(window, QObject) else None)
        self.window = window
        self._jobs_since_idle: list = []
        self._tray: QSystemTrayIcon | None = None

    # ── commands ───────────────────────────────────────────────────────────────
    def quick_render(self) -> None:
        """Render the current settings at 2048² / standard quality with the saved output preferences."""
        from dataclasses import replace

        s = self.window.doc.settings
        q = replace(s.quality, width=QUICK_RENDER_SIDE, height=QUICK_RENDER_SIDE, points_per_pixel=QUICK_RENDER_PPP, supersample=2)
        self.window.submit_job(make_job(RenderPrefs.load(), replace(s, quality=q)))

    def resume_render(self) -> None:
        """Continue an interrupted render from a ``*.attractr-ckpt.npz`` checkpoint chosen by the user."""
        prefs = RenderPrefs.load()
        existing = list_checkpoints(prefs.folder)
        start = str(existing[0]) if existing else str(prefs.folder / "checkpoints")
        path, _ = QFileDialog.getOpenFileName(self.window, tr("Resume render from checkpoint"), start,
                                              f"Attractr checkpoints (*{SUFFIX});;All files (*)")
        if not path:
            return
        try:
            ck = Checkpoint.load(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self.window, tr("Resume render"), tr("Could not read the checkpoint:") + f"\n{exc}")
            return
        # checkpoints written by the GUI live in <output folder>/checkpoints; others resume into the preferred folder
        parent = Path(path).parent
        out_dir = parent.parent if parent.name == "checkpoints" else prefs.folder
        job = make_job(prefs, ck.next_settings(), out_dir=out_dir, resume=ck)
        self.window.set_status(f"resuming at {ck.fraction * 100:.0f} % ({Path(path).name})")
        self.window.submit_job(job)

    def batch_render(self) -> None:
        """Render every project / ``.atr`` / tagged PNG of a folder with one render preset into ``<folder>/renders``."""
        folder = QFileDialog.getExistingDirectory(self.window, tr("Folder with .attractr / .atr / tagged .png files"), str(Path.home()))
        if not folder:
            return
        name, ok = QInputDialog.getItem(self.window, tr("Batch render"), tr("Render preset:"), render_presets.names(), 0, False)
        if not ok:
            return
        preset = render_presets.get(name)
        items, skipped = batch.plan(Path(folder), preset)
        if not items:
            QMessageBox.information(self.window, tr("Batch render"), tr("No renderable files found in that folder."))
            return
        out = Path(folder) / "renders"
        for it in items:
            self.window.submit_job(self._preset_job(it.settings, preset, out, BATCH_TEMPLATE, name=f"Batch {it.path.name}"))
        msg = f"queued {len(items)} render(s) → {out}"
        if skipped:
            msg += f" · skipped {len(skipped)} file(s)"
        self.window.set_status(msg)

    def rerender(self, settings_list: list[RenderSettings], preset: RenderPreset) -> None:
        """Queue one job per settings object with a render preset (Gallery → Re-render…)."""
        for s in settings_list:
            self.window.submit_job(self._preset_job(s, preset))
        self.window.set_status(f"queued {len(settings_list)} re-render(s) [{preset.name}]")

    @staticmethod
    def _preset_job(settings: RenderSettings, preset: RenderPreset, out_dir: Path | None = None,
                    template: str | None = None, **kwargs) -> RenderJob:
        """A job whose size / quality / format / report come from ``preset``."""
        return make_job(RenderPrefs.load(), preset.apply(settings), out_dir, template, fmt=preset.fmt, bit_depth=preset.bit_depth,
                        report_formats=list(preset.report_formats), dynamics=preset.dynamics, **kwargs)

    # ── queue notifications ────────────────────────────────────────────────────
    def job_ended(self, job) -> None:
        self._jobs_since_idle.append(job)

    def queue_idle(self) -> None:
        """Desktop notification when a batch of jobs has finished while the window is not in front."""
        done = [j for j in self._jobs_since_idle if j.state == "done"]
        failed = [j for j in self._jobs_since_idle if j.state == "failed"]
        self._jobs_since_idle = []
        if not done and not failed:
            return
        if self.window.isActiveWindow() and len(done) + len(failed) == 1:
            return  # the status bar already says it
        self._notify(tr("Attractr — queue finished"), f"{len(done)} render(s) finished" + (f", {len(failed)} failed" if failed else ""))

    def _notify(self, title: str, text: str) -> None:
        """Show a tray balloon (no-op without a system tray or under tests)."""
        if not QSystemTrayIcon.isSystemTrayAvailable() or QApplication.instance().property("attractr_testing"):
            return
        if self._tray is None:
            self._tray = QSystemTrayIcon(self.window.windowIcon(), self)
            self._tray.setToolTip(APP_NAME)
            self._tray.show()
        self._tray.showMessage(title, text, QSystemTrayIcon.MessageIcon.Information, 6000)
