"""Syntax highlighter for the Attractr formula DSL."""

from __future__ import annotations

import re

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from attractr.core.formula.functions import FUNCTIONS
from attractr.core.formula.lexer import HEADER_KEYS


def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    return f


class FormulaHighlighter(QSyntaxHighlighter):
    def __init__(self, doc) -> None:
        super().__init__(doc)
        self.params: set[str] = set()
        self.rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        self.f_comment = _fmt("#6a737d", italic=True)
        self.f_header_key = _fmt("#b39ddb", bold=True)
        self.f_header_val = _fmt("#9aa5b1")
        self.f_keyword = _fmt("#ff7ab6", bold=True)
        self.f_func = _fmt("#4fc3f7")
        self.f_state = _fmt("#ffd166", bold=True)
        self.f_target = _fmt("#c3e88d", bold=True)
        self.f_number = _fmt("#f78c6c")
        self.f_string = _fmt("#c8e6ff")
        self.f_param = _fmt("#82aaff")
        self.f_op = _fmt("#89ddff")
        self._build()

    def set_params(self, names: set[str]) -> None:
        if names != self.params:
            self.params = set(names)
            self._build()
            self.rehighlight()

    def _build(self) -> None:
        r = self.rules = []
        r.append((QRegularExpression(r"\b(param|choose|on_section|and|or|not|int|step)\b"), self.f_keyword))
        r.append((QRegularExpression(r"\b(" + "|".join(sorted(FUNCTIONS, key=len, reverse=True)) + r")(?=\s*\()"), self.f_func))
        r.append((QRegularExpression(r"\b(x|y|z|w)'"), self.f_target))
        r.append((QRegularExpression(r"^\s*(dx|dy|dz|dw|depth|color|plot|section)\b(?=\s*=)"), self.f_target))
        r.append((QRegularExpression(r"\b(x|y|z|w|x0|y0|z0|t_step|pi|tau)\b(?!')"), self.f_state))
        if self.params:
            r.append((QRegularExpression(r"\b(" + "|".join(map(re.escape, sorted(self.params, key=len, reverse=True))) + r")\b(?!')"), self.f_param))
        r.append((QRegularExpression(r"\b\d+(\.\d*)?([eE][+-]?\d+)?\b|\.\d+"), self.f_number))
        r.append((QRegularExpression(r"[-+*/%^=<>!]+"), self.f_op))
        r.append((QRegularExpression(r'"[^"]*"'), self.f_string))

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        m = re.match(r"^\s*([a-z_]+)\s*:(.*)$", text)
        if m and m.group(1) in HEADER_KEYS:
            self.setFormat(0, len(m.group(1)) + 1, self.f_header_key)
            self.setFormat(len(m.group(1)) + 1, len(text), self.f_header_val)
            return
        for rx, fmt in self.rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                mm = it.next()
                self.setFormat(mm.capturedStart(), mm.capturedLength(), fmt)
        i = text.find("#")
        if i >= 0:
            self.setFormat(i, len(text) - i, self.f_comment)
