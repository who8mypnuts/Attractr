"""Widget-level smoke tests (offscreen)."""

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    a.setProperty("attractr_testing", True)
    return a


def test_gradient_editor_edits(app):
    from attractr.core.color.palettes import palettes
    from attractr.gui.widgets.gradient_editor import GradientEditor

    ed = GradientEditor(palettes.get("fire"))
    got = []
    ed.gradientChanged.connect(got.append)
    n = len(ed.bar.gradient.stops)
    ed._add_stop()
    assert len(ed.bar.gradient.stops) == n + 1
    ed._remove_stop()
    assert len(ed.bar.gradient.stops) == n
    ed.btn_reverse.click()
    assert got and got[-1].stops[0].rgb == palettes.get("fire").stops[-1].rgb


def test_formula_highlighter_and_editor_errors(app):
    from attractr.gui.panels.formula_panel import FormulaPanel
    from attractr.gui.state.document import Document

    doc = Document()
    panel = FormulaPanel(doc)
    panel.editor.setPlainText("name: Bad\nx' = foo(x)\ny' = x\n")
    panel._validate_and_apply(force=True)
    assert panel.editor.error_line == 2
    panel.editor.setPlainText("name: Good\nparam a = 1.4\nx' = 1 - a*x^2 + y\ny' = 0.3*x\n")
    panel._validate_and_apply(force=True)
    assert panel.editor.error_line is None
    assert doc.spec.name == "Good" and doc.settings.param_dict == {"a": 1.4}


def test_slider_spin_range_growth(app):
    from attractr.gui.widgets.slider_spin import SliderSpin

    s = SliderSpin("a", -1.0, 1.0, 0.5)
    vals = []
    s.valueChanged.connect(vals.append)
    s.spin.setValue(3.0)  # outside the soft range → range grows, value kept
    assert s.value() == 3.0 and s.hi >= 3.0 and vals[-1] == 3.0


def test_slider_spin_nudge_wheel_and_history(app):
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    from attractr.gui.widgets.slider_spin import SliderSpin

    s = SliderSpin("a", 0.0, 10.0, 5.0)
    vals = []
    s.valueChanged.connect(vals.append)
    s.nudge_up.click()  # +1 % of the range
    assert abs(s.value() - 5.1) < 1e-9
    s.nudge(-0.1)  # −10 %
    assert abs(s.value() - 4.1) < 1e-9
    ev = QWheelEvent(QPointF(1, 1), QPointF(1, 1), QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.ControlModifier, Qt.ScrollPhase.NoScrollPhase, False)
    assert s.eventFilter(s.slider, ev)  # Ctrl-wheel: 0.1 % fine step
    assert abs(s.value() - 4.11) < 1e-9
    assert [round(v, 6) for v in list(s.history)[-3:]] == [5.1, 4.1, 4.11]
    s.spin.setValue(7.0)
    assert s.history[-1] == 7.0 and len(s.history) == 4
    assert ev.type() == QEvent.Type.Wheel


def test_search_panel_polynomial_mode(app):
    from attractr.core.attractors.registry import registry
    from attractr.gui.panels.search_panel import POLY_ID, SearchPanel, polynomial_space
    from attractr.gui.state.document import Document

    doc = Document()
    doc.set_attractor(registry.get("lorenz"))
    panel = SearchPanel(doc)
    assert not panel.polynomial_mode and not panel.magnitude.isVisibleTo(panel)
    panel.space.setCurrentIndex(1)
    assert panel.polynomial_mode and panel.magnitude.isVisibleTo(panel) and not panel.use_locks.isVisibleTo(panel)
    settings, spec = panel._search_space()
    assert spec.id == POLY_ID and settings.attractor == POLY_ID and len(spec.params) == 30
    assert spec.params[0].lo == -1.2 and polynomial_space(0.5).params[3].hi == 0.5
    assert settings.look == doc.settings.look  # the current look carries over
