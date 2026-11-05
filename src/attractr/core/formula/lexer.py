"""Tokeniser for the formula DSL.

Header lines (``key: value``) are recognised here by a line pre-pass and returned
separately as raw strings because their values are free text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HEADER_KEYS = frozenset(
    {
        "name", "id", "kind", "dims", "desc", "ref", "author", "dt", "ic", "warmup",
        "camera", "palette", "style", "tags", "version", "family", "lyapunov", "jitter", "boost", "section_dir",
        "region", "bailout", "max_iter", "min_iter",
    }
)

_HEADER_RE = re.compile(r"^\s*([a-z_]+)\s*:\s*(.*?)\s*$")
_TOKEN_RE = re.compile(
    r"""
    (?P<ws>[ \t]+)
  | (?P<comment>\#[^\n]*)
  | (?P<newline>\n)
  | (?P<number>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)
  | (?P<string>"(?:[^"\\]|\\.)*")
  | (?P<ident>[A-Za-z_][A-Za-z_0-9]*'?)
  | (?P<op><=|>=|==|!=|[-+*/%^(),=<>{}:;\[\]])
""",
    re.VERBOSE,
)


class FormulaError(Exception):
    """Syntax or semantic error with a source position (1-based line, 0-based column)."""

    def __init__(self, message: str, line: int = 0, col: int = 0, length: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col
        self.length = length

    def __str__(self) -> str:
        return f"line {self.line}: {self.message}" if self.line else self.message


@dataclass(frozen=True)
class Token:
    kind: str  # number | string | ident | op | newline | eof
    text: str
    line: int
    col: int

    @property
    def value(self) -> float:
        return float(self.text)


def split_headers(source: str) -> tuple[dict[str, str], list[tuple[int, str]]]:
    """Return ``(headers, code_lines)`` where ``code_lines`` keep their original line
    numbers. Repeated ``desc``/``ref`` headers are joined with a space / newline."""
    headers: dict[str, str] = {}
    code: list[tuple[int, str]] = []
    for i, raw in enumerate(source.splitlines(), start=1):
        m = _HEADER_RE.match(raw)
        if m and m.group(1) in HEADER_KEYS and not raw.lstrip().startswith("#"):
            key, val = m.group(1), m.group(2)
            if key in headers and key in ("desc", "ref", "tags"):
                sep = " " if key == "desc" else "\n"
                headers[key] = headers[key] + sep + val
            else:
                headers[key] = val
            continue
        code.append((i, raw))
    return headers, code


def tokenize(code_lines: list[tuple[int, str]]) -> list[Token]:
    tokens: list[Token] = []
    for line_no, text in code_lines:
        pos = 0
        while pos < len(text):
            m = _TOKEN_RE.match(text, pos)
            if not m:
                raise FormulaError(f"unexpected character {text[pos]!r}", line_no, pos)
            kind = m.lastgroup or ""
            if kind not in ("ws", "comment", "newline"):
                tokens.append(Token(kind, m.group(0), line_no, pos))
            pos = m.end()
        tokens.append(Token("newline", "\n", line_no, len(text)))
    last_line = code_lines[-1][0] if code_lines else 1
    tokens.append(Token("eof", "", last_line + 1, 0))
    return tokens
