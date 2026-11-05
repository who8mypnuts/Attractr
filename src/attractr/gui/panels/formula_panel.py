"""Formula editor panel: edit the DSL source, see errors inline, apply live."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from attractr.core.attractors.registry import registry
from attractr.core.attractors.spec import AttractorSpec, spec_from_source
from attractr.core.formula.lexer import FormulaError
from attractr.gui.state.document import Document
from attractr.gui.widgets.formula_editor.code_editor import CodeEditor
from attractr.gui.widgets.formula_editor.highlighter import FormulaHighlighter

TEMPLATES = {
    "Map (2-D)": "name: My Map\nkind: map\ndims: 2\n\nparam a = 1.4 [-3, 3]\nparam b = 0.3 [-1, 1]\n\nx' = 1 - a*x^2 + y\ny' = b*x\n",
    "Map (3-D)": "name: My 3-D Map\nkind: map\n\nparam a = 2.24 [-3, 3]\nparam b = 0.43 [-3, 3]\nparam c = -0.65 [-3, 3]\nparam d = -2.43 [-3, 3]\n\nx' = sin(a*y) - z*cos(b*x)\ny' = z*sin(c*x) - cos(d*y)\nz' = sin(x)\n",
    "Flow (ODE)": "name: My Flow\nkind: flow\ndt: 0.01\nic: 0.1 0.1 0.1\n\nparam a = 10 [0, 20]\nparam b = 28 [0, 50]\nparam c = 8/3 [0, 5]\n\ndx = a*(y - x)\ndy = x*(b - z) - y\ndz = x*y - c*z\n",
    "IFS (chaos game)": "name: My IFS\nkind: ifs\nic: 0 0 0\n\nparam s = 0.5 [0.3, 0.7]\n\nchoose {\n  1: x' = s*x;          y' = s*y\n  1: x' = s*x + (1-s);  y' = s*y\n  1: x' = s*x + (1-s)/2; y' = s*y + (1-s)\n}\n",
    "Driven oscillator (w = time)": "name: My Driven Oscillator\nkind: flow\ndt: 0.01\nic: 0.1 0 0 0\n\nparam delta = 0.3 [0, 1]\nparam gamma = 0.5 [0, 1]\nparam omega = 1.2 [0.5, 2]\n\ndx = y\ndy = x - x^3 - delta*y + gamma*cos(omega*w)\ndz = 0\ndw = 1\nplot = x, y, 0\n",
    "Poincare section": "name: My Section\nkind: flow\ndt: 0.01\nic: 0.1 0 0 0\n\nparam delta = 0.3 [0, 1]\nparam gamma = 0.5 [0, 1]\nparam omega = 1.2 [0.5, 2]\n\ndx = y\ndy = x - x^3 - delta*y + gamma*cos(omega*w)\ndz = 0\ndw = 1\nplot = x, y, 0\n# plot once per forcing period (sign change of the section function)\nsection = sin(omega*w/2)\n",
    "Symmetric icon": "name: My Icon\nkind: map\n\nparam lam = -2.5 [-4, -1]\nparam al = 5.0 [1, 8]\nparam be = -1.8 [-3, 0.5]\nparam ga = 1.0 [-2, 2]\nparam om = 0.0 [-1, 1]\nparam n = 3 [3, 12] int\n\nzz  = x*x + y*y\nren = re_pow(x, y, n)\nt   = lam + al*zz + be*ren\ncr  = re_pow(x, -y, n - 1)\nci  = im_pow(x, -y, n - 1)\nx'  = t*x - om*y + ga*cr\ny'  = t*y + om*x + ga*ci\ndepth = ren\n",
}


class _ProbeBridge(QObject):
    done = Signal(str, str)  # text, token


class _ProbeTask(QRunnable):
    def __init__(self, bridge: _ProbeBridge, spec: AttractorSpec, params: dict, dt: float | None, token: str) -> None:
        super().__init__()
        self.bridge, self.spec, self.params, self.dt, self.token = bridge, spec, params, dt, token

    def run(self) -> None:
        try:
            from attractr.core.analysis.probe import probe

            r = probe(self.spec, self.params, self.dt, steps=4000)
            text = f"λ₁ ≈ {r.lyapunov:.3f} · {r.classification} · dim ≈ {r.box_dimension:.2f}"
        except Exception as exc:  # noqa: BLE001
            text = f"probe failed: {exc}"
        try:
            self.bridge.done.emit(text, self.token)
        except RuntimeError:  # panel already destroyed
            pass


class FormulaPanel(QWidget):
    popOutRequested = Signal()

    def __init__(self, doc: Document, worker=None, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.worker = worker
        self._loading = False
        self._last_applied = ""
        self._status_base = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        bar = QHBoxLayout()
        self.btn_new = QToolButton()
        self.btn_new.setText("New ▾")
        self.btn_new.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.btn_new)
        for name, src in TEMPLATES.items():
            menu.addAction(name, lambda s=src: self._load_text(s, apply=True))
        self.btn_new.setMenu(menu)
        self.btn_fork = QPushButton("Fork current")
        self.btn_fork.setToolTip("Copy the current attractor's definition into the editor as a new user formula")
        self.auto = QCheckBox("Apply live")
        self.auto.setChecked(True)
        self.btn_apply = QPushButton("Apply")
        self.btn_save = QPushButton("Save to My Attractors")
        self.btn_revert = QPushButton("Revert")
        for w in (self.btn_new, self.btn_fork, self.auto, self.btn_apply, self.btn_save, self.btn_revert):
            bar.addWidget(w)
        bar.addStretch(1)
        self.btn_popout = QPushButton("⤢ Enlarge")
        self.btn_popout.setToolTip("Float the editor in a large window (click again to dock it back)")
        self.btn_popout.clicked.connect(self.popOutRequested)
        bar.addWidget(self.btn_popout)
        lay.addLayout(bar)

        self.editor = CodeEditor()
        self.highlighter = FormulaHighlighter(self.editor.document())
        lay.addWidget(self.editor, 1)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color:#9aa5b1;")
        lay.addWidget(self.status)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._validate_and_apply)
        self.editor.textChanged.connect(self._on_text_changed)
        self.btn_apply.clicked.connect(lambda: self._validate_and_apply(force=True))
        self.btn_fork.clicked.connect(self._fork)
        self.btn_save.clicked.connect(self._save)
        self.btn_revert.clicked.connect(lambda: self.load_spec(self.doc.spec))
        self._bridge = _ProbeBridge()
        self._bridge.done.connect(self._on_probe)
        if self.worker is not None:
            self.worker.probeReady.connect(self._on_worker_probe)
            self.worker.failed.connect(lambda tok, msg: self._on_probe(f"probe failed: {msg}", tok))
        self._probe_token = ""
        doc.attractorChanged.connect(self._on_attractor_changed)
        self.load_spec(doc.spec)

    # ── loading ────────────────────────────────────────────────────────────────
    def load_spec(self, spec: AttractorSpec) -> None:
        self._load_text(spec.source, apply=False)
        self.status.setText(f"{'built-in' if spec.builtin else 'user'} attractor · {spec.kind} · {len(spec.params)} params — edit to fork")

    def _load_text(self, text: str, apply: bool) -> None:
        self._loading = True
        self.editor.setPlainText(text)
        self._loading = False
        self._last_applied = text
        try:
            prog_spec = spec_from_source(text)
            self.highlighter.set_params(set(prog_spec.param_names))
            self.editor.set_completion_words(set(prog_spec.param_names))
            self.editor.set_error(None)
        except FormulaError:
            pass
        if apply:
            self._validate_and_apply(force=True)

    def _on_attractor_changed(self, spec: AttractorSpec) -> None:
        if self.editor.toPlainText() != spec.source:
            self.load_spec(spec)

    def _on_text_changed(self) -> None:
        if not self._loading:
            self._timer.start()

    # ── validate / apply ───────────────────────────────────────────────────────
    def _validate_and_apply(self, force: bool = False) -> None:
        text = self.editor.toPlainText()
        try:
            spec = spec_from_source(text, builtin=False)
        except FormulaError as exc:
            self.editor.set_error(exc.line or 1, exc.col, exc.length)
            self.status.setText(f"✗ line {exc.line}: {exc.message}" if exc.line else f"✗ {exc.message}")
            self.status.setStyleSheet("color:#ff7a7a;")
            return
        except Exception as exc:  # noqa: BLE001
            self.editor.set_error(None)
            self.status.setText(f"✗ {exc}")
            self.status.setStyleSheet("color:#ff7a7a;")
            return
        self.editor.set_error(None)
        self.highlighter.set_params(set(spec.param_names))
        self.editor.set_completion_words(set(spec.param_names))
        warn = ("  ⚠ " + "; ".join(spec.analysis.warnings)) if spec.analysis.warnings else ""
        self._status_base = f"✓ {spec.name}: {spec.kind}, {spec.dims}-D, {len(spec.params)} params{warn}"
        self.status.setText(self._status_base + " · probing…")
        self.status.setStyleSheet("color:#c3e88d;")
        if (self.auto.isChecked() or force) and text != self._last_applied:
            self._last_applied = text
            try:
                self.doc.set_source(text)
            except Exception as exc:  # noqa: BLE001
                self.status.setText(f"✗ {exc}")
                self.status.setStyleSheet("color:#ff7a7a;")
                return
        self._probe_token = spec.content_hash
        if self.worker is not None:
            from dataclasses import replace

            s = replace(self.doc.settings, source=text, attractor=spec.id)
            self.worker.probe(spec.content_hash, s)
        else:
            QThreadPool.globalInstance().start(_ProbeTask(self._bridge, spec, self.doc.settings.param_dict, self.doc.settings.quality.dt, spec.content_hash))

    def _on_worker_probe(self, token: str, r: dict) -> None:
        self._on_probe(f"λ₁ ≈ {r['lyapunov']:.3f} · {r['classification']} · dim ≈ {r['dimension']:.2f}", token)

    def _on_probe(self, text: str, token: str) -> None:
        if token != self._probe_token:
            return
        self.status.setText(f"{self._status_base} · {text}")

    # ── fork / save ────────────────────────────────────────────────────────────
    def _fork(self) -> None:
        spec = self.doc.spec
        src = spec.source
        if "name:" in src:
            src = src.replace(f"name: {spec.name}", f"name: {spec.name} (fork)", 1)
        self._load_text(src, apply=True)

    def _save(self) -> None:
        text = self.editor.toPlainText()
        try:
            spec = spec_from_source(text, builtin=False)
        except FormulaError as exc:
            QMessageBox.warning(self, "Save attractor", str(exc))
            return
        name, ok = QInputDialog.getText(self, "Save to My Attractors", "File name (id):", text=spec.id)
        if not ok or not name.strip():
            return
        saved = registry.save_user(text, name.strip())
        self.status.setText(f"saved {saved.path}")
        self.doc.set_attractor(saved)
