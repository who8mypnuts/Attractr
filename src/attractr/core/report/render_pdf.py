"""Report → PDF via Qt (QTextDocument → QPdfWriter); no extra dependency.

Needs a QGuiApplication; the CLI creates an offscreen one on demand."""

from __future__ import annotations

from pathlib import Path

from attractr.core.report.model import Report
from attractr.core.report.render_html import render_html

PRINT_CSS = """
body{font-family:Helvetica,Arial,sans-serif;color:#111;font-size:10pt} h1{color:#0a5d8a;font-size:18pt}
h2{color:#4a3a8a;font-size:13pt;margin-top:14pt} table{border-collapse:collapse;width:100%;font-size:9pt}
th,td{border:1px solid #bbb;padding:3px 6px;text-align:left} th{background:#e8eef5}
pre{background:#f2f2f2;padding:6px;font-size:8.5pt;white-space:pre-wrap;word-wrap:break-word} img{max-width:100%}
"""


def render_pdf(r: Report, path: str | Path, base_dir: Path | None = None) -> Path:
    from PySide6.QtCore import QMarginsF, QUrl
    from PySide6.QtGui import QGuiApplication, QPageLayout, QPageSize, QPdfWriter, QTextDocument

    app = QGuiApplication.instance()
    if app is None:  # headless CLI
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QGuiApplication([])
    path = Path(path)
    doc = QTextDocument()
    doc.setDefaultStyleSheet(PRINT_CSS)
    if base_dir is not None:
        doc.setBaseUrl(QUrl.fromLocalFile(str(base_dir) + "/"))
    doc.setHtml(render_html(r, inline_css=False))
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)
    writer.setResolution(150)
    doc.setPageSize(writer.pageLayout().paintRectPixels(writer.resolution()).size())
    doc.print_(writer)
    return path
