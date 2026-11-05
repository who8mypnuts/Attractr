"""Wrap user-visible string literals of the GUI in ``tr("…")`` (idempotent).

Usage: python tools/wrap_tr.py [--check] [paths…]      (default: src/attractr/gui)

Only plain string literals (no f-strings) that contain a letter and sit in a position Qt
shows to the user are wrapped: the first positional argument of widget constructors /
``setText``-like setters, both text arguments of ``QMessageBox`` / ``QInputDialog`` calls,
the label of ``addRow``, the title of ``_dock``.  Literals already inside ``tr(...)`` are
left alone.  ``--check`` only reports what would change.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

FIRST_ARG = {
    "QLabel", "QPushButton", "QToolButton", "QCheckBox", "QGroupBox", "QRadioButton", "QAction", "QMenu",
    "setText", "setToolTip", "setWindowTitle", "setPlaceholderText", "setStatusTip", "setTitle", "setFormat",
    "setSpecialValueText", "addMenu", "addItem", "addRow", "addTab", "setWhatsThis", "addSection", "setLabelText",
    "setPrefix", "setSuffix",
}
DIALOG_CALLS = {"information", "warning", "critical", "question", "getText", "getItem", "getInt", "getDouble",
                "getOpenFileName", "getSaveFileName", "getExistingDirectory"}  # parent, title, text, ...
DOCK = {"_dock": 1}  # name → index of the title argument
LETTER = re.compile(r"[A-Za-zÀ-ÿ]")


def _callee(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _wrappable(arg: ast.expr) -> bool:
    return isinstance(arg, ast.Constant) and isinstance(arg.value, str) and bool(LETTER.search(arg.value))


def targets(tree: ast.AST) -> list[ast.Constant]:
    out: list[ast.Constant] = []
    seen: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _callee(node)
        if name == "tr":
            continue
        cands: list[ast.expr] = []
        if name in FIRST_ARG and node.args:
            cands.append(node.args[0])
        elif name in DIALOG_CALLS:
            cands.extend(node.args[1:3])
        elif name in DOCK and len(node.args) > DOCK[name]:
            cands.append(node.args[DOCK[name]])
        for c in cands:
            if _wrappable(c) and id(c) not in seen:
                seen.add(id(c))
                out.append(c)  # type: ignore[arg-type]
    return out


def wrap_file(path: Path, check: bool = False) -> int:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lits = sorted(targets(tree), key=lambda n: (n.lineno, n.col_offset), reverse=True)
    if not lits:
        return 0
    lines = src.split("\n")
    # replace from the end so earlier offsets stay valid; literals never span lines here.
    # ast column offsets are UTF-8 *byte* offsets → convert to character offsets.
    for lit in lits:
        if lit.end_lineno != lit.lineno:
            continue
        line = lines[lit.lineno - 1]
        raw = line.encode("utf-8")
        a = len(raw[: lit.col_offset].decode("utf-8"))
        b = len(raw[: lit.end_col_offset].decode("utf-8"))
        lines[lit.lineno - 1] = line[:a] + "tr(" + line[a:b] + ")" + line[b:]
    new = "\n".join(lines)
    if "from attractr.i18n import tr" not in new:
        # insert after the last top-level import
        idx = 0
        for i, line in enumerate(new.split("\n")):
            if line.startswith(("import ", "from ")) and not line.startswith("from __future__"):
                idx = i
        parts = new.split("\n")
        # skip continuation lines of a multi-line import
        while idx + 1 < len(parts) and (parts[idx].rstrip().endswith(("(", ",")) or parts[idx + 1].startswith((" ", ")"))):
            idx += 1
        parts.insert(idx + 1, "from attractr.i18n import tr")
        new = "\n".join(parts)
    if check:
        print(f"{path}: {len(lits)} literal(s)")
        return len(lits)
    path.write_text(new, encoding="utf-8")
    print(f"{path}: wrapped {len(lits)}")
    return len(lits)


def main(argv: list[str]) -> int:
    check = "--check" in argv
    paths = [Path(a) for a in argv if not a.startswith("--")] or [Path("src/attractr/gui")]
    total = 0
    for p in paths:
        for f in sorted(p.rglob("*.py") if p.is_dir() else [p]):
            total += wrap_file(f, check)
    print(f"total {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
