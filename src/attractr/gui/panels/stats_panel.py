"""Statistics panel: live render stats, density histogram, dynamics, system info."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget

from attractr.core.render.result import RenderResult
from attractr.gui.state.document import Document
from attractr.gui.widgets.histogram_widget import HistogramWidget
from attractr.i18n import tr


def _table(rows: list[tuple[str, str]]) -> QTableWidget:
    t = QTableWidget(0, 2)
    t.horizontalHeader().setVisible(False)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setShowGrid(False)
    fill_table(t, rows)
    return t


def fill_table(t: QTableWidget, rows: list[tuple[str, str]]) -> None:
    t.setRowCount(len(rows))
    for i, (k, v) in enumerate(rows):
        t.setItem(i, 0, QTableWidgetItem(k))
        t.setItem(i, 1, QTableWidgetItem(v))
    t.resizeColumnsToContents()
    t.horizontalHeader().setStretchLastSection(True)


def _human(n: float) -> str:
    for unit, div in (("G", 1e9), ("M", 1e6), ("k", 1e3)):
        if abs(n) >= div:
            return f"{n / div:.2f} {unit}"
    return f"{n:.0f}"


class _DynamicsTask(QRunnable):
    def __init__(self, sig, doc: Document) -> None:
        super().__init__()
        self.sig, self.doc = sig, doc

    def run(self) -> None:
        try:
            from attractr.core.analysis.probe import probe

            s = self.doc.settings
            r = probe(self.doc.spec, s.param_dict, s.quality.dt)
            self.sig.emit([(k, f"{v:.4f}" if isinstance(v, float) else str(v)) for k, v in r.as_dict().items()])
        except Exception as exc:  # noqa: BLE001
            self.sig.emit([("error", str(exc))])


class _Bridge(QObject):
    done = Signal(object)


class _SystemTask(QRunnable):
    def __init__(self, bridge: _Bridge) -> None:
        super().__init__()
        self.bridge = bridge

    def run(self) -> None:
        try:
            self.bridge.done.emit(StatsPanel.system_rows())
        except Exception as exc:  # noqa: BLE001
            self.bridge.done.emit([("error", str(exc))])


class StatsPanel(QWidget):
    def __init__(self, doc: Document, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)

        # render stats
        w = QWidget()
        v = QVBoxLayout(w)
        self.render_table = _table([])
        self.hist = HistogramWidget()
        v.addWidget(self.render_table, 1)
        v.addWidget(QLabel(tr("Density histogram (log-spaced bins) · tone curve")))
        v.addWidget(self.hist)
        self.tabs.addTab(w, "Render")

        # dynamics
        w = QWidget()
        v = QVBoxLayout(w)
        self.dyn_table = _table([("λ₁", "press Compute")])
        self.btn_dyn = QPushButton(tr("Compute Lyapunov exponent & dimension"))
        v.addWidget(self.dyn_table, 1)
        v.addWidget(self.btn_dyn)
        self.tabs.addTab(w, "Dynamics")
        self._bridge = _Bridge()
        self._bridge.done.connect(lambda rows: fill_table(self.dyn_table, rows))
        self.btn_dyn.clicked.connect(self._compute_dynamics)

        # system
        w = QWidget()
        v = QVBoxLayout(w)
        self.sys_table = _table([("probing…", "")])
        self.btn_probe = QPushButton(tr("Re-probe engines"))
        v.addWidget(self.sys_table, 1)
        v.addWidget(self.btn_probe)
        self.tabs.addTab(w, "System")
        self.btn_probe.clicked.connect(self.refresh_system)

    def update_result(self, result: RenderResult, develop_seconds: float = 0.0) -> None:
        st = result.stats
        rows = [
            ("Engine", f"{st.engine} · {st.device}"),
            ("Size", f"{result.width} × {result.height}"),
            ("Points", f"{_human(st.iterations_done)} / {_human(st.iterations_requested)}"),
            ("Throughput", f"{_human(st.points_per_second)} pts/s"),
            ("Accumulate / develop", f"{st.accumulate_seconds:.2f} s / {develop_seconds * 1000:.0f} ms"),
            ("Trajectories · restarts", f"{st.trajectories:,} · {st.restarts}"),
            ("Coverage", f"{st.coverage * 100:.2f} % ({st.nonzero_pixels:,} px)"),
            ("Density max / mean / median", f"{st.max_count:.1f} / {st.mean_count:.2f} / {st.median_count:.2f}"),
            ("Percentile count", f"{st.percentile_count:.1f}"),
            ("Entropy", f"{st.entropy_bits:.2f} bits"),
            ("Framing radius", f"{result.framing.radius:.4g}"),
            ("Passes · tiles", f"{st.passes} · {st.tiles}"),
        ]
        if st.notes:
            rows.append(("Notes", " ".join(st.notes)))
        fill_table(self.render_table, rows)
        self.hist.set_data(st.density_histogram, st.density_histogram_edges, st.percentile_count or 1.0, self.doc.settings.look.gamma)

    def _compute_dynamics(self) -> None:
        fill_table(self.dyn_table, [("computing…", "")])
        QThreadPool.globalInstance().start(_DynamicsTask(self._bridge.done, self.doc))

    def refresh_system_async(self) -> None:
        fill_table(self.sys_table, [("probing engines…", "")])
        bridge = _Bridge()
        bridge.done.connect(lambda rows: fill_table(self.sys_table, rows))
        self._sys_bridge = bridge
        QThreadPool.globalInstance().start(_SystemTask(bridge))

    def refresh_system(self) -> None:
        self.refresh_system_async()

    @staticmethod
    def system_rows() -> list[tuple[str, str]]:
        from attractr.cli.cmd_info import system_info

        info = system_info()
        rows = [("Attractr", info["attractr"]), ("Python", info["python"]), ("Platform", info["platform"]),
                ("CPU threads", f"{info['cpu_threads']} (numba {info['numba_threads']})"),
                ("numba / numpy", f"{info['numba']} / {info['numpy']}")]
        for k, c in info["engines"].items():
            flag = "✓" if c["available"] else "✗"
            bench = f" · {c['mpts_per_second']:.0f} Mpts/s" if c.get("mpts_per_second") else ""
            rows.append((f"{flag} {k}", f"{c['device']}{bench} {'; '.join(c['notes'])}"))
        return rows
