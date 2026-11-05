"""QApplication bootstrap for the GUI."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from attractr.version import APP_NAME, ORG_NAME


def run_gui(argv: list[str]) -> int:
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication

    from attractr.core.io.logging_setup import setup_logging

    setup_logging(logging.INFO)
    QCoreApplication.setOrganizationName(ORG_NAME)
    QCoreApplication.setApplicationName(APP_NAME)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    from attractr.i18n import install_translators

    install_translators(app)
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
