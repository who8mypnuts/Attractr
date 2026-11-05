"""Shared test configuration: offscreen Qt, an isolated Attractr home, the ``app`` fixture."""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# persistent cache between test runs keeps numba compile times out of the test loop
os.environ.setdefault("ATTRACTR_HOME", os.path.join(os.environ.get("TMPDIR", "/tmp"), "attractr_test_home"))


@pytest.fixture(scope="session")
def app():
    """The process-wide QApplication, flagged so the GUI skips warm-up processes and tray balloons."""
    from PySide6.QtWidgets import QApplication

    a = QApplication.instance() or QApplication([])
    a.setProperty("attractr_testing", True)
    return a


def pump(app, seconds: float, until=None) -> bool:
    """Process Qt events for up to ``seconds`` (or until ``until()`` is true); returns the predicate's result."""
    t0 = time.time()
    while time.time() - t0 < seconds:
        app.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.01)
    return until() if until else True
