"""Write / update ``resources/i18n/attractors_LOCALE.json`` — the translatable texts of
every built-in attractor (description + parameter hints).  Existing translations are kept;
new attractors get their English text as a placeholder marked with ``"_todo": true``.

Usage: python tools/extract_attractor_strings.py LOCALE
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from attractr.core.attractors.registry import registry

OUT = Path("src/attractr/resources/i18n")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    locale = argv[0]
    path = OUT / f"attractors_{locale}.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    out: dict[str, dict] = {}
    todo = 0
    for spec in registry.all():
        if not spec.builtin:
            continue
        entry = old.get(spec.id)
        if entry and not entry.get("_todo"):
            out[spec.id] = entry
            continue
        out[spec.id] = {"_todo": True, "desc": spec.description, "hints": {p.name: p.hint for p in spec.params if p.hint}}
        todo += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{path}: {len(out)} attractors, {todo} to translate")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
