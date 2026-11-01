"""QPlainTextEdit with line numbers, current-line highlight, error marks and completion."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import QCompleter, QPlainTextEdit, QTextEdit, QWidget

from attractr.core.formula.functions import FUNCTIONS


class _Gutter(QWidget):
    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, e) -> None:  # noqa: N802
        self.editor.paint_gutter(e)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        font.setPointSize(10)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 2)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.gutter = _Gutter(self)
        self.error_line: int | None = None
        self.error_cols: tuple[int, int] | None = None
        self.blockCountChanged.connect(lambda _: self.setViewportMargins(self.gutter_width(), 0, 0, 0))
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self._refresh_extras)
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)
        words = sorted(set(FUNCTIONS) | {"param", "choose", "select", "depth", "color", "x'", "y'", "z'", "dx", "dy", "dz"})
        self.completer = QCompleter(words, self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseSensitive)
        self.completer.activated.connect(self._insert_completion)
        self._refresh_extras()

    # ── completion ─────────────────────────────────────────────────────────────
    def set_completion_words(self, extra: set[str]) -> None:
        from PySide6.QtCore import QStringListModel

        words = sorted(set(FUNCTIONS) | extra | {"param", "choose", "select", "depth", "color", "dx", "dy", "dz"})
        self.completer.setModel(QStringListModel(words, self.completer))

    def _word_under_cursor(self) -> str:
        tc = self.textCursor()
        tc.select(QTextCursor.SelectionType.WordUnderCursor)
        return tc.selectedText()

    def _insert_completion(self, text: str) -> None:
        tc = self.textCursor()
        prefix = self.completer.completionPrefix()
        tc.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(prefix))
        tc.insertText(text + ("(" if text in FUNCTIONS and FUNCTIONS[text].arity != 0 else "()" if text in FUNCTIONS else ""))
        self.setTextCursor(tc)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if self.completer.popup().isVisible() and e.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab, Qt.Key.Key_Escape):
            e.ignore()
            return
        if e.key() == Qt.Key.Key_Tab:
            self.insertPlainText("  ")
            return
        super().keyPressEvent(e)
        prefix = self._word_under_cursor()
        if len(prefix) >= 2 and e.text().isalnum():
            self.completer.setCompletionPrefix(prefix)
            cr = self.cursorRect()
            cr.setWidth(self.completer.popup().sizeHintForColumn(0) + 24)
            self.completer.complete(cr)
        else:
            self.completer.popup().hide()

    # ── gutter ─────────────────────────────────────────────────────────────────
    def gutter_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_gutter(self, rect, dy) -> None:
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def paint_gutter(self, e) -> None:
        p = QPainter(self.gutter)
        p.fillRect(e.rect(), QColor(18, 18, 26))
        block = self.firstVisibleBlock()
        n = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        while block.isValid() and top <= e.rect().bottom():
            if block.isVisible() and bottom >= e.rect().top():
                color = QColor(255, 90, 90) if self.error_line == n + 1 else QColor(110, 110, 130)
                p.setPen(color)
                p.drawText(0, top, self.gutter.width() - 5, self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, str(n + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            n += 1
        p.end()

    # ── error marks ────────────────────────────────────────────────────────────
    def set_error(self, line: int | None, col: int = 0, length: int = 1) -> None:
        self.error_line = line
        self.error_cols = (col, length) if line else None
        self._refresh_extras()
        self.gutter.update()

    def _refresh_extras(self) -> None:
        extras = []
        cur = QTextEdit.ExtraSelection()
        cur.format.setBackground(QColor(26, 26, 40))
        cur.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        cur.cursor = self.textCursor()
        cur.cursor.clearSelection()
        extras.append(cur)
        if self.error_line:
            block = self.document().findBlockByNumber(self.error_line - 1)
            if block.isValid():
                sel = QTextEdit.ExtraSelection()
                fmt = QTextCharFormat()
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                fmt.setUnderlineColor(QColor(255, 80, 80))
                fmt.setBackground(QColor(60, 20, 24))
                sel.format = fmt
                c = QTextCursor(block)
                col, length = self.error_cols or (0, 1)
                text = block.text()
                if col >= len(text):
                    col, length = 0, len(text)
                c.setPosition(block.position() + col)
                c.setPosition(block.position() + min(len(text), col + max(length, 1)), QTextCursor.MoveMode.KeepAnchor)
                sel.cursor = c
                extras.append(sel)
        self.setExtraSelections(extras)
