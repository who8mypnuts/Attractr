"""``attractr list`` — catalogue queries (human or JSON)."""

from __future__ import annotations

import json

from attractr.core.attractors.registry import registry
from attractr.core.color.palettes import palettes
from attractr.core.render.engines import selector
from attractr.core.render.settings import COLOR_SOURCES, INTEGRATORS, STYLES


def add_parser(sub) -> None:
    ap = sub.add_parser("list", help="list attractors, palettes, engines, styles")
    ap.add_argument("what", choices=("attractors", "palettes", "engines", "styles", "colors", "integrators"), nargs="?", default="attractors")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--family", help="filter attractors by family")
    ap.set_defaults(func=run)


def run(a) -> int:
    if a.what == "attractors":
        specs = [s for s in registry.all() if not a.family or s.family.lower() == a.family.lower()]
        if a.json:
            print(json.dumps([{
                "id": s.id, "name": s.name, "kind": s.kind, "dims": s.dims, "family": s.family,
                "params": [{"name": p.name, "default": p.default, "lo": p.lo, "hi": p.hi, "hint": p.hint} for p in s.params],
                "dt": s.dt, "description": s.description, "references": list(s.references), "builtin": s.builtin,
            } for s in specs], indent=1))
        else:
            fam = None
            for s in specs:
                if s.family != fam:
                    fam = s.family
                    print(f"\n{fam}")
                params = ", ".join(f"{p.name}={p.default:g}" for p in s.params) or "—"
                print(f"  {s.id:24s} {s.name:26s} {s.kind:4s} {s.dims}-D  {params}")
        if registry.errors:
            print("\nfiles with errors:")
            for path, err in registry.errors.items():
                print(f"  {path}: {err}")
    elif a.what == "palettes":
        if a.json:
            print(json.dumps([{"id": pid, **g.to_dict(), **palettes.meta(pid)} for pid, g in palettes.items()], indent=1))
        else:
            for pid, g in palettes.items():
                m = palettes.meta(pid)
                print(f"  {pid:16s} {len(g.stops)} stops {g.space:8s} {'cyclic ' if g.cyclic else '       '} {m.get('desc', '')}")
    elif a.what == "engines":
        caps = selector.probe_all()
        if a.json:
            print(json.dumps({k: v.__dict__ for k, v in caps.items()}, indent=1, default=str))
        else:
            for k, c in caps.items():
                flag = "available" if c.available else "unavailable"
                print(f"  {k:14s} {c.name:28s} {flag:12s} {c.device}  {'; '.join(c.notes)}")
    elif a.what == "styles":
        print("\n".join(STYLES) if not a.json else json.dumps(list(STYLES)))
    elif a.what == "colors":
        print("\n".join(COLOR_SOURCES) if not a.json else json.dumps(list(COLOR_SOURCES)))
    else:
        print("\n".join(INTEGRATORS) if not a.json else json.dumps(list(INTEGRATORS)))
    return 0
