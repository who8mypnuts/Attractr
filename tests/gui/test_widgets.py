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
