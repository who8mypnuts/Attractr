"""Collect every ``tr("…")`` literal of the GUI into a Qt Linguist ``.ts`` file
(context ``attractr``, the one :func:`attractr.i18n.tr` uses) — merging with an existing
file so finished translations are kept.

Usage: python tools/extract_ts.py LOCALE [--src src/attractr/gui]
       → src/attractr/resources/i18n/attractr_LOCALE.ts   (compile with pyside6-lrelease)
"""

from __future__ import annotations

import ast
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

OUT_DIR = Path("src/attractr/resources/i18n")
CONTEXT = "attractr"


def collect(src: Path) -> dict[str, list[tuple[str, int]]]:
    out: dict[str, list[tuple[str, int]]] = {}
    for f in sorted(src.rglob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr" and node.args
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                out.setdefault(node.args[0].value, []).append((str(f), node.lineno))
    return out


def existing_translations(path: Path) -> dict[str, tuple[str, str]]:
    """source → (translation, type attribute) from a previous .ts."""
    if not path.exists():
        return {}
    res: dict[str, tuple[str, str]] = {}
    for msg in ET.parse(path).getroot().iter("message"):
        s = msg.findtext("source") or ""
        t = msg.find("translation")
        if t is not None and (t.text or "").strip():
            res[s] = (t.text or "", t.get("type", ""))
    return res


def write_ts(path: Path, locale: str, strings: dict[str, list[tuple[str, int]]], old: dict[str, tuple[str, str]]) -> int:
    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<!DOCTYPE TS>", f'<TS version="2.1" language="{locale}">',
             f"<context>\n    <name>{CONTEXT}</name>"]
    done = 0
    for s in sorted(strings):
        locs = "".join(f'\n        <location filename="{escape(f)}" line="{ln}"/>' for f, ln in strings[s][:3])
        if s in old and old[s][1] != "unfinished":
            tr_el = f"        <translation>{escape(old[s][0])}</translation>"
            done += 1
        else:
            tr_el = '        <translation type="unfinished"></translation>'
        lines.append(f"    <message>{locs}\n        <source>{escape(s)}</source>\n{tr_el}\n    </message>")
    lines += ["</context>", "</TS>", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return done


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    locale = argv[0]
    src = Path(argv[argv.index("--src") + 1]) if "--src" in argv else Path("src/attractr/gui")
    strings = collect(src)
    path = OUT_DIR / f"attractr_{locale}.ts"
    old = existing_translations(path)
    done = write_ts(path, locale, strings, old)
    print(f"{path}: {len(strings)} strings, {done} translated")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
