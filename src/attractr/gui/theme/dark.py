"""Dark theme: Qt palette + stylesheet (accent cyan #4fc3f7 / violet #5b2fd1)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#4fc3f7"
ACCENT2 = "#5b2fd1"

QSS = """
QWidget { font-size: 12px; }
QMainWindow::separator { background: #1c1c26; width: 4px; height: 4px; }
QDockWidget { titlebar-close-icon: url(none); font-weight: 600; }
QDockWidget::title { background: #171722; padding: 5px 8px; border-bottom: 1px solid #262636; }
QToolBar { background: #141420; border: none; spacing: 4px; padding: 3px; }
QToolButton { padding: 4px 8px; border-radius: 4px; }
QToolButton:hover { background: #232336; }
QToolButton:checked { background: #2a2a44; }
QPushButton { background: #232336; border: 1px solid #33334a; border-radius: 5px; padding: 5px 10px; }
QPushButton:hover { background: #2d2d46; border-color: #4fc3f7; }
QPushButton:pressed { background: #1b1b2a; }
QPushButton:default { border-color: #4fc3f7; }
QPushButton:disabled { color: #666; border-color: #2a2a3a; }
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit { background: #12121a; border: 1px solid #2e2e40; border-radius: 4px; padding: 3px 6px; selection-background-color: #5b2fd1; }
QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover { border-color: #4fc3f7; }
QComboBox QAbstractItemView { background: #16161f; selection-background-color: #2a2a44; }
QSlider::groove:horizontal { height: 4px; background: #2a2a3a; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #4fc3f7; border-radius: 2px; }
QSlider::handle:horizontal { width: 12px; height: 12px; margin: -5px 0; border-radius: 6px; background: #e6e6f0; border: 1px solid #4fc3f7; }
QSlider::handle:horizontal:hover { background: #ffffff; }
QProgressBar { background: #12121a; border: 1px solid #2e2e40; border-radius: 4px; text-align: center; height: 16px; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5b2fd1, stop:1 #4fc3f7); border-radius: 3px; }
QTabWidget::pane { border: 1px solid #262636; }
QTabBar::tab { background: #171722; padding: 5px 12px; border: 1px solid #262636; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { background: #232336; color: #4fc3f7; }
QListWidget, QTreeWidget, QTableWidget, QTextBrowser { background: #0f0f16; border: 1px solid #262636; border-radius: 4px; }
QListWidget::item:selected { background: #2a2a44; border: 1px solid #4fc3f7; border-radius: 4px; }
QHeaderView::section { background: #171722; padding: 3px; border: none; }
QScrollBar:vertical { background: #12121a; width: 10px; } QScrollBar::handle:vertical { background: #33334a; border-radius: 5px; min-height: 24px; }
QScrollBar:horizontal { background: #12121a; height: 10px; } QScrollBar::handle:horizontal { background: #33334a; border-radius: 5px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QStatusBar { background: #141420; border-top: 1px solid #262636; }
QMenuBar { background: #141420; } QMenuBar::item:selected { background: #232336; }
QMenu { background: #16161f; border: 1px solid #2e2e40; } QMenu::item:selected { background: #2a2a44; }
QGroupBox { border: 1px solid #2a2a3a; border-radius: 6px; margin-top: 10px; padding-top: 6px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #9fd8ff; }
QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #44445a; background: #12121a; }
QCheckBox::indicator:checked { background: #4fc3f7; border-color: #4fc3f7; }
QToolTip { background: #1b1b2a; color: #e6e6f0; border: 1px solid #4fc3f7; padding: 4px; }
"""


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    bg = QColor("#0e0e14")
    base = QColor("#12121a")
    text = QColor("#e6e6f0")
    pal.setColor(QPalette.ColorRole.Window, bg)
    pal.setColor(QPalette.ColorRole.WindowText, text)
    pal.setColor(QPalette.ColorRole.Base, base)
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#16161f"))
    pal.setColor(QPalette.ColorRole.Text, text)
    pal.setColor(QPalette.ColorRole.Button, QColor("#232336"))
    pal.setColor(QPalette.ColorRole.ButtonText, text)
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT2))
    pal.setColor(QPalette.ColorRole.HighlightedText, text)
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1b1b2a"))
    pal.setColor(QPalette.ColorRole.ToolTipText, text)
    pal.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#666"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#666"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#666"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#666"))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
