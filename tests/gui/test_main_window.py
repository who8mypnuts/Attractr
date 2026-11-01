"""Offscreen GUI smoke test: window builds, preview renders, changes propagate, undo works."""

import time

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    a.setProperty("attractr_testing", True)
    return a


def pump(app, seconds: float, until=None):
    t0 = time.time()
    while time.time() - t0 < seconds:
        app.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.01)
    return until() if until else True


def test_main_window_preview_and_undo(app):
    from attractr.gui.main_window import MainWindow

    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    assert pump(app, 60, lambda: w.viewport._image is not None), "preview never arrived"
    rho0 = w.doc.settings.param_dict["rho"]
    w.doc.set_param("rho", rho0 + 5)
    assert w.doc.settings.param_dict["rho"] == rho0 + 5
    w.doc.undo_stack.undo()
    assert w.doc.settings.param_dict["rho"] == rho0
    # look change must not restart the preview (develop only)
    pump(app, 0.3)
    gen = w.preview._generation
    from dataclasses import replace

    w.doc.set_look(replace(w.doc.settings.look, gamma=0.7))
    pump(app, 0.3)
    assert w.preview._generation == gen
    # switching attractor rebuilds the parameter panel
    from attractr.core.attractors.registry import registry

    w.doc.set_attractor(registry.get("clifford"))
    pump(app, 0.2)
    assert set(w.params_panel.sliders) == {"a", "b", "c", "d", "e", "f"}
    w.doc.undo_stack.setClean()
    w.close()
    pump(app, 0.5)
