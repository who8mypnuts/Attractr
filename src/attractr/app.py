"""QApplication bootstrap for the GUI."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from attractr.version import APP_NAME, ORG_NAME


def run_gui(argv: list[str]) -> int:
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    QCoreApplication.setOrganizationName(ORG_NAME)
    QCoreApplication.setApplicationName(APP_NAME)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    from attractr.gui.theme.dark import apply_dark_theme

    apply_dark_theme(app)
    from attractr.gui.main_window import MainWindow

    win = MainWindow()
    app.aboutToQuit.connect(win.shutdown)
    for a in argv:
        if a.endswith(".attractr") and Path(a).exists():
            win.load_path(a)
    win.show()
    return app.exec()
