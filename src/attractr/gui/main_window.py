"""Main window: viewport in the centre, every panel as a dock, menus, toolbar, status bar."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from attractr.core.io.paths import resources_dir, user_dir
from attractr.core.jobs.queue import JobQueue
from attractr.core.project.files import SUFFIX
from attractr.gui.controllers.animation_controller import AnimationController
from attractr.gui.controllers.preview_controller import PreviewController
from attractr.gui.controllers.render_job import RenderJob
from attractr.gui.controllers.worker_client import WorkerClient as ThumbnailWorker
from attractr.gui.dialogs.about_dialog import AboutDialog
from attractr.gui.dialogs.preferences_dialog import PreferencesDialog
from attractr.gui.dialogs.render_dialog import RenderDialog
from attractr.gui.panels.attractor_browser import AttractorBrowser
from attractr.gui.panels.camera_panel import CameraPanel
from attractr.gui.panels.formula_panel import FormulaPanel
from attractr.gui.panels.gallery_panel import GalleryPanel
from attractr.gui.panels.info_panel import InfoPanel
from attractr.gui.panels.jobs_panel import JobsPanel
from attractr.gui.panels.look_panel import LookPanel
from attractr.gui.panels.parameters_panel import ParametersPanel
from attractr.gui.panels.presets_panel import PresetsPanel
from attractr.gui.panels.search_panel import SearchPanel
from attractr.gui.panels.stats_panel import StatsPanel
from attractr.gui.panels.timeline_panel import TimelinePanel
from attractr.gui.state.document import Document
from attractr.gui.viewport.viewport import Viewport
from attractr.version import APP_NAME, __version__

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, document: Document | None = None) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        icon = resources_dir() / "logo" / "attractr_256.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1500, 920)
        self.qs = QSettings()
        self.doc = document or Document()
        self.queue = JobQueue(max_concurrent=1, parent=self)
        self.thumbs = ThumbnailWorker(parent=self)
        self.thumbs.start()

        # ── centre ──────────────────────────────────────────────────────────────
        self.viewport = Viewport(self.doc)
        self.setCentralWidget(self.viewport)
        self.preview = PreviewController(self.doc, self)
        self.preview.max_side = int(self.qs.value("preview/max_side", 1024))
        self.preview.ppp = float(self.qs.value("preview/ppp", 2.0))
        self.preview.interactive_ppp = float(self.qs.value("preview/interactive_ppp", 0.4))
        self.preview.set_engine(self.qs.value("preview/engine", "auto"))
        self.viewport.viewResized.connect(self.preview.set_view_size)
        self.preview.imageReady.connect(self._on_image)
        self.preview.statusChanged.connect(self._set_status)
        self.preview.engineChanged.connect(self._on_engine)
        self.viewport.hoverInfo.connect(self._set_hover)

        # ── docks ───────────────────────────────────────────────────────────────
        self.docks: dict[str, QDockWidget] = {}
        self.browser = AttractorBrowser(self.doc, self.thumbs)
        self.params_panel = ParametersPanel(self.doc)
        self.presets_panel = PresetsPanel(self.doc, self.thumbs)
        self.look_panel = LookPanel(self.doc)
        self.camera_panel = CameraPanel(self.doc)
        self.info_panel = InfoPanel(self.doc)
        self.stats_panel = StatsPanel(self.doc)
        self.jobs_panel = JobsPanel(self.queue)
        self.formula_panel = FormulaPanel(self.doc, self.thumbs)
        self.search_panel = SearchPanel(self.doc)
        self.search_panel.locked_provider = lambda: self.params_panel.locked
        self.gallery_panel = GalleryPanel(self.doc)
        self.anim = AnimationController(self.doc, self)
        self.timeline_panel = TimelinePanel(self.doc, self.anim)
        self.timeline_panel.renderRequested.connect(self.show_animate_dialog)
        self._dock("attractors", "Attractors", self.browser, Qt.DockWidgetArea.LeftDockWidgetArea)
        self._dock("parameters", "Parameters", self.params_panel, Qt.DockWidgetArea.LeftDockWidgetArea)
        self._dock("presets", "Presets", self.presets_panel, Qt.DockWidgetArea.LeftDockWidgetArea)
        self._dock("look", "Look", self.look_panel, Qt.DockWidgetArea.RightDockWidgetArea)
        self._dock("camera", "Camera", self.camera_panel, Qt.DockWidgetArea.RightDockWidgetArea)
        self._dock("info", "Info", self.info_panel, Qt.DockWidgetArea.RightDockWidgetArea)
        self._dock("stats", "Statistics", self.stats_panel, Qt.DockWidgetArea.RightDockWidgetArea)
        self._dock("jobs", "Jobs", self.jobs_panel, Qt.DockWidgetArea.BottomDockWidgetArea)
        self._dock("formula", "Formula", self.formula_panel, Qt.DockWidgetArea.BottomDockWidgetArea)
        self._dock("search", "Search", self.search_panel, Qt.DockWidgetArea.BottomDockWidgetArea)
        self._dock("gallery", "Gallery", self.gallery_panel, Qt.DockWidgetArea.BottomDockWidgetArea)
        self._dock("timeline", "Timeline", self.timeline_panel, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.tabifyDockWidget(self.docks["formula"], self.docks["timeline"])
        self.tabifyDockWidget(self.docks["formula"], self.docks["search"])
        self.tabifyDockWidget(self.docks["formula"], self.docks["gallery"])
        self.tabifyDockWidget(self.docks["formula"], self.docks["jobs"])
        self.docks["formula"].raise_()
        self.resizeDocks([self.docks["formula"]], [300], Qt.Orientation.Vertical)
        self.tabifyDockWidget(self.docks["attractors"], self.docks["presets"])
        self.tabifyDockWidget(self.docks["look"], self.docks["camera"])
        self.tabifyDockWidget(self.docks["info"], self.docks["stats"])
        self.docks["attractors"].raise_()
        self.docks["look"].raise_()
        self.docks["info"].raise_()
        for key in ("formula", "search", "gallery", "jobs", "timeline"):
            self.docks[key].hide()
        self.resizeDocks([self.docks["attractors"], self.docks["parameters"]], [420, 360], Qt.Orientation.Vertical)

        # ── menus / toolbar / status ─────────────────────────────────────────────
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self.status_label = QLabel("ready")
        self.hover_label = QLabel("")
        self.engine_label = QLabel("engine: …")
        self.engine_label.setStyleSheet("color:#4fc3f7; padding: 0 8px;")
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.hover_label)
        self.statusBar().addPermanentWidget(self.engine_label)

        self.render_dialog: RenderDialog | None = None
        self.doc.pathChanged.connect(self._update_title)
        self.doc.dirtyChanged.connect(lambda _: self._update_title())
        self.doc.attractorChanged.connect(lambda _: self._update_title())
        self.queue.job_ended.connect(self._on_job_ended)
        self._update_title()
        self._restore_layout()
        QTimer.singleShot(800, self.stats_panel.refresh_system_async)
        QTimer.singleShot(2500, self._maybe_warmup)
        QTimer.singleShot(100, self.preview.restart)
        self._autosave = QTimer(self)
        self._autosave.setInterval(30_000)
        self._autosave.timeout.connect(self._autosave_now)
        self._autosave.start()
        self._offer_recovery()
        QTimer.singleShot(1500, lambda: __import__("attractr.gui.dialogs.tips_dialog", fromlist=["TipsDialog"]).TipsDialog.maybe_show(self))

    # ── construction helpers ───────────────────────────────────────────────────
    def _dock(self, key: str, title: str, widget, area) -> QDockWidget:
        d = QDockWidget(title, self)
        d.setObjectName(f"dock_{key}")
        d.setWidget(widget)
        d.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.addDockWidget(area, d)
        self.docks[key] = d
        return d

    def _build_actions(self) -> None:
        a = self.actions_ = {}
        a["new"] = QAction("&New", self, shortcut=QKeySequence.StandardKey.New, triggered=self.new_project)
        a["open"] = QAction("&Open…", self, shortcut=QKeySequence.StandardKey.Open, triggered=self.open_project)
        a["save"] = QAction("&Save", self, shortcut=QKeySequence.StandardKey.Save, triggered=self.save_project)
        a["save_as"] = QAction("Save &As…", self, shortcut=QKeySequence.StandardKey.SaveAs, triggered=lambda: self.save_project(True))
        a["import_image"] = QAction("Import settings from image…", self, triggered=self.import_image)
        a["quit"] = QAction("&Quit", self, shortcut=QKeySequence.StandardKey.Quit, triggered=self.close)
        a["undo"] = self.doc.undo_stack.createUndoAction(self, "&Undo")
        a["undo"].setShortcut(QKeySequence.StandardKey.Undo)
        a["redo"] = self.doc.undo_stack.createRedoAction(self, "&Redo")
        a["redo"].setShortcut(QKeySequence.StandardKey.Redo)
        a["random"] = QAction("🎲 Randomize parameters", self, shortcut="R", triggered=lambda: self.doc.randomize_params(self.params_panel.locked))
        a["surprise"] = QAction("✨ Surprise me", self, shortcut="Shift+R", triggered=self.doc.randomize_all)
        a["mutate"] = QAction("Mutate grid…", self, shortcut="M", triggered=self.show_mutate)
        a["search"] = QAction("Search…", self, shortcut="Ctrl+F", triggered=lambda: (self.docks["search"].show(), self.docks["search"].raise_()))
        a["formula"] = QAction("Formula editor", self, shortcut="F4", triggered=lambda: (self.docks["formula"].show(), self.docks["formula"].raise_()))
        a["gradient"] = QAction("Gradient editor…", self, shortcut="G", triggered=self.look_panel.open_gradient_editor)
        a["reset_cam"] = QAction("Reset camera", self, shortcut="Home", triggered=self.doc.reset_camera)
        a["spin"] = QAction("Spin", self, shortcut="Space", checkable=True, triggered=self.viewport.toggle_spin)
        a["hud"] = QAction("Show HUD", self, shortcut="H", checkable=True, checked=True, triggered=self._toggle_hud)
        a["render"] = QAction("⬛ Render…", self, shortcut="Ctrl+R", triggered=self.show_render_dialog)
        a["quick_render"] = QAction("Quick render (2048²)", self, shortcut="Ctrl+Shift+R", triggered=self.quick_render)
        a["timeline"] = QAction("Timeline", self, shortcut="T", triggered=lambda: (self.docks["timeline"].show(), self.docks["timeline"].raise_()))
        a["animate"] = QAction("🎞 Render animation…", self, shortcut="Ctrl+Shift+A", triggered=self.show_animate_dialog)
        a["copy_code"] = QAction("Copy share code", self, shortcut="Ctrl+Shift+C", triggered=self.presets_panel._copy_code)
        a["copy_cli"] = QAction("Copy CLI command", self, triggered=self.copy_cli_command)
        a["paste_code"] = QAction("Paste share code", self, shortcut="Ctrl+Shift+V", triggered=self.presets_panel._paste_code)
        a["prefs"] = QAction("Preferences…", self, triggered=lambda: PreferencesDialog(self).exec() and self._apply_prefs())
        a["open_folder"] = QAction("Open user folder", self, triggered=lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(user_dir()))))
        a["about"] = QAction("About Attractr", self, triggered=lambda: AboutDialog(self).exec())
        a["tips"] = QAction("Tips", self, triggered=self._show_tips)
        a["docs"] = QAction("Documentation", self, triggered=lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[3] / "docs" / "README.md"))))

    def _build_menus(self) -> None:
        a = self.actions_
        mb = self.menuBar()
        m = mb.addMenu("&File")
        m.addActions([a["new"], a["open"], a["save"], a["save_as"]])
        m.addSeparator()
        m.addAction(a["import_image"])
        m.addSeparator()
        m.addAction(a["quit"])
        m = mb.addMenu("&Edit")
        m.addActions([a["undo"], a["redo"]])
        m.addSeparator()
        m.addActions([a["copy_code"], a["paste_code"], a["copy_cli"]])
        m.addSeparator()
        m.addAction(a["prefs"])
        m = mb.addMenu("&View")
        for d in self.docks.values():
            m.addAction(d.toggleViewAction())
        m.addSeparator()
        m.addActions([a["hud"], a["spin"], a["reset_cam"]])
        m = mb.addMenu("&Attractor")
        m.addActions([a["random"], a["surprise"], a["mutate"], a["search"], a["formula"]])
        m = mb.addMenu("&Look")
        m.addAction(a["gradient"])
        m = mb.addMenu("&Render")
        m.addActions([a["render"], a["quick_render"]])
        m = mb.addMenu("&Animate")
        m.addActions([a["timeline"], a["animate"]])
        m = mb.addMenu("&Help")
        m.addActions([a["docs"], a["tips"], a["open_folder"], a["about"]])

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setObjectName("toolbar_main")
        tb.setMovable(False)
        a = self.actions_
        for key in ("new", "open", "save", None, "undo", "redo", None, "random", "surprise", "mutate", "search", "formula", "gradient", None, "reset_cam", "spin", None, "render", "quick_render", "timeline", "animate"):
            if key is None:
                tb.addSeparator()
            else:
                tb.addAction(a[key])
        self.addToolBar(tb)

    # ── slots ──────────────────────────────────────────────────────────────────
    def _on_image(self, img, dev, result) -> None:
        self.viewport.set_image(img, result)
        st = result.stats
        self.viewport.set_hud([
            f"{self.doc.spec.name}  {result.width}×{result.height}",
            f"{st.iterations_done / 1e6:.2f} M pts · {st.points_per_second / 1e6:.0f} Mpts/s · {st.engine}",
            f"coverage {st.coverage * 100:.1f} % · max {st.max_count:.0f} · P {st.percentile_count:.0f}",
            "partial" if not result.complete else "complete",
        ])
        self.stats_panel.update_result(result, self.preview.develop.last_develop_seconds)
        if self.doc.settings.look.caption:
            from attractr.core.io.caption import caption_lines

            self.viewport.caption_lines = caption_lines(self.doc.spec, self.doc.settings)
        else:
            self.viewport.caption_lines = []

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _set_hover(self, text: str) -> None:
        self.hover_label.setText(text)

    def _on_engine(self, eid: str) -> None:
        self.engine_label.setText(f"preview engine: {eid}")

    def _toggle_hud(self, on: bool) -> None:
        self.viewport.show_hud = on
        self.viewport.update()

    def _apply_prefs(self) -> None:
        self.preview.max_side = int(self.qs.value("preview/max_side", 1024))
        self.preview.ppp = float(self.qs.value("preview/ppp", 2.0))
        self.preview.interactive_ppp = float(self.qs.value("preview/interactive_ppp", 0.4))
        self.preview.set_engine(self.qs.value("preview/engine", "auto"))

    def _update_title(self, *_: object) -> None:
        name = self.doc.path.name if self.doc.path else "untitled"
        star = " •" if self.doc.dirty else ""
        self.setWindowTitle(f"{name}{star} — {self.doc.spec.name} — {APP_NAME} {__version__}")

    # ── file actions ───────────────────────────────────────────────────────────
    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self.doc.new()

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open project", str(Path.home()), f"Attractr project (*{SUFFIX})")
        if path:
            self.load_path(path)

    def load_path(self, path: str) -> None:
        try:
            self.doc.load(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Open project", f"Could not open {path}:\n{exc}")

    def save_project(self, save_as: bool = False) -> bool:
        path = self.doc.path
        if save_as or path is None:
            p, _ = QFileDialog.getSaveFileName(self, "Save project", str(Path.home() / f"{self.doc.spec.id}{SUFFIX}"), f"Attractr project (*{SUFFIX})")
            if not p:
                return False
            path = Path(p)
        try:
            self.doc.save(path)
            self._set_status(f"saved {path}")
            return True
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save project", str(exc))
            return False

    def import_image(self) -> None:
        from attractr.core.io.metadata import read_settings
        from attractr.gui.state.document import TAGS_ALL

        path, _ = QFileDialog.getOpenFileName(self, "Import settings from image", "", "Images (*.png)")
        if not path:
            return
        s = read_settings(path)
        if s is None:
            QMessageBox.information(self, "Import", "That image has no Attractr settings embedded.")
            return
        self.doc.apply(s, "Import image settings", TAGS_ALL)

    def _confirm_discard(self) -> bool:
        if not self.doc.dirty:
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save the current project first?",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save_project()
        return r == QMessageBox.StandardButton.Discard

    def show_mutate(self) -> None:
        from attractr.gui.dialogs.mutate_dialog import MutateDialog

        dlg = MutateDialog(self.doc, lambda: self.params_panel.locked, self)
        dlg.show()

    # ── rendering ──────────────────────────────────────────────────────────────
    def show_render_dialog(self) -> None:
        if self.render_dialog is None:
            self.render_dialog = RenderDialog(lambda: self.doc.settings, self)
            self.render_dialog.jobCreated.connect(self.submit_job)
        self.render_dialog.show()
        self.render_dialog.raise_()

    def quick_render(self) -> None:
        from dataclasses import replace

        s = self.doc.settings
        q = replace(s.quality, width=2048, height=2048, points_per_pixel=12.0, supersample=2)
        fmt = self.qs.value("render/report_fmt", "md")
        reports = [fmt] if self.qs.value("render/report", "true") == "true" else []
        out = Path(self.qs.value("render/folder", str(Path.home() / "Attractr"))).expanduser()
        self.submit_job(RenderJob(replace(s, quality=q), out, self.qs.value("render/template", "{name}_{date}_{w}x{h}"), report_formats=reports))

    def show_animate_dialog(self) -> None:
        from attractr.gui.dialogs.animate_dialog import AnimateDialog

        if not self.anim.timeline.tracks:
            QMessageBox.information(self, "Render animation", "The timeline is empty — add keyframes or use Helpers ▾ in the Timeline panel first.")
            self.docks["timeline"].show()
            self.docks["timeline"].raise_()
            return
        dlg = AnimateDialog(self.anim.base_for_render, lambda: self.anim.timeline, self)
        dlg.jobCreated.connect(self.submit_job)
        dlg.show()

    def submit_job(self, job) -> None:
        self.docks["jobs"].show()
        self.queue.submit(job)
        self._set_status(f"queued {job.name}")

    def _on_job_ended(self, job) -> None:
        if isinstance(job, RenderJob) and job.state == "done" and job.output:
            out = job.output
            self.gallery_panel.refresh()
            self._set_status(f"rendered {out.image_path.name} in {out.seconds:.1f} s" + (f" · report {out.report_paths[0].name}" if out.report_paths else ""))
        elif job.state == "failed":
            self._set_status(f"{job.name} failed — see Jobs panel")

    def _maybe_warmup(self) -> None:
        """Pre-compile numba kernels for all built-ins in a separate process (first run)."""
        from attractr.core.warmup import is_warm

        if is_warm() or QApplication.instance().property("attractr_testing"):
            return
        import sys as _sys

        from PySide6.QtCore import QProcess

        self._warm_proc = QProcess(self)
        self._warm_proc.setProgram(_sys.executable)
        self._warm_proc.setArguments(["-m", "attractr.core.warmup", "--quiet"])
        self._warm_proc.finished.connect(lambda *_: self._set_status("attractor kernels prepared — CPU rendering is now fast for every built-in"))
        self._warm_proc.start()
        self._set_status("preparing attractor kernels in the background (first run only)…")

    def _show_tips(self) -> None:
        from attractr.gui.dialogs.tips_dialog import TipsDialog

        TipsDialog(self).show()

    def copy_cli_command(self) -> None:
        from PySide6.QtGui import QGuiApplication

        from attractr.core.project.codes import settings_to_code

        q = self.doc.settings.quality
        cmd = f"attractr render '{settings_to_code(self.doc.settings)}' --size {q.width}x{q.height} --ppp {q.points_per_pixel:g} --report md"
        QGuiApplication.clipboard().setText(cmd)
        self._set_status("CLI command copied to the clipboard")

    # ── autosave / recovery ────────────────────────────────────────────────────
    def _autosave_path(self) -> Path:
        return user_dir() / "autosave.attractr"

    def _autosave_now(self) -> None:
        if not self.doc.dirty:
            return
        try:
            from attractr.core.project.files import Project, save_project

            save_project(Project(self.doc.settings, self.doc.animation, self.doc.notes), self._autosave_path())
        except Exception:  # noqa: BLE001
            log.debug("autosave failed", exc_info=True)

    def _offer_recovery(self) -> None:
        p = self._autosave_path()
        if not p.exists() or QApplication.instance().property("attractr_testing"):
            return
        r = QMessageBox.question(self, "Recover session", "An autosaved session from a previous run was found. Restore it?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            try:
                from attractr.core.project.files import load_project
                from attractr.gui.state.document import TAGS_ALL

                self.doc.apply(load_project(p).settings, "Recover autosave", TAGS_ALL)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Recover session", str(exc))
        p.unlink(missing_ok=True)

    # ── layout persistence ─────────────────────────────────────────────────────
    def _restore_layout(self) -> None:
        g = self.qs.value("window/geometry")
        s = self.qs.value("window/state")
        if g is not None:
            self.restoreGeometry(g)
        if s is not None:
            self.restoreState(s)

    def closeEvent(self, e: QCloseEvent) -> None:  # noqa: N802
        if not self._confirm_discard():
            e.ignore()
            return
        self.qs.setValue("window/geometry", self.saveGeometry())
        self.qs.setValue("window/state", self.saveState())
        self._autosave_path().unlink(missing_ok=True)
        self.shutdown()
        super().closeEvent(e)

    def shutdown(self) -> None:
        """Stop every worker thread (idempotent; also called on QApplication.aboutToQuit)."""
        if getattr(self, "_shut", False):
            return
        self._shut = True
        self.queue.cancel_all()
        self.search_panel.shutdown()
        self.anim.pause()
        self.preview.shutdown()
        self.thumbs.stop()
        self.queue.wait_all(3000)
        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().waitForDone(3000)
