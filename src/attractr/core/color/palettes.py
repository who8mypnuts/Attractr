"""Palette library: built-in (``resources/palettes/*.json``) + user (``~/.attractr/palettes``)."""

from __future__ import annotations

import json
from pathlib import Path

from attractr.core.color.gradient import Gradient, Stop
from attractr.core.io.paths import resources_dir, user_palettes_dir


class PaletteLibrary:
    def __init__(self) -> None:
        self._items: dict[str, Gradient] = {}
        self._meta: dict[str, dict] = {}
        self._loaded = False

    def load(self) -> None:
        self._items.clear()
        self._meta.clear()
        for path in sorted((resources_dir() / "palettes").glob("*.json")):
            self._load_file(path, builtin=True)
        udir = user_palettes_dir()
        for path in sorted(udir.glob("*.json")):
            self._load_file(path, builtin=False)
        self._loaded = True

    def _load_file(self, path: Path, builtin: bool) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("palettes", [data]) if isinstance(data, dict) else data
        for e in entries:
            stops = tuple(Stop(*[float(v) for v in s]) for s in e["stops"])
            g = Gradient(stops, e.get("space", "rgb"), bool(e.get("cyclic", False)), e.get("name", path.stem))
            pid = e.get("id") or g.name.lower().replace(" ", "_")
            self._items[pid] = g
            self._meta[pid] = {"desc": e.get("desc", ""), "source": e.get("source", ""), "builtin": builtin, "path": str(path)}

    def _ensure(self) -> None:
        if not self._loaded:
            self.load()

    def get(self, pid: str) -> Gradient:
        self._ensure()
        if pid not in self._items:
            raise KeyError(f"unknown palette {pid!r}")
        return self._items[pid]

    def __contains__(self, pid: str) -> bool:
        self._ensure()
        return pid in self._items

    def ids(self) -> list[str]:
        self._ensure()
        return list(self._items)

    def items(self) -> list[tuple[str, Gradient]]:
        self._ensure()
        return list(self._items.items())

    def meta(self, pid: str) -> dict:
        self._ensure()
        return dict(self._meta.get(pid, {}))

    def save_user(self, pid: str, gradient: Gradient, desc: str = "") -> Path:
        path = user_palettes_dir() / f"{pid}.json"
        d = gradient.to_dict()
        d.update({"id": pid, "desc": desc, "source": "user"})
        path.write_text(json.dumps(d, indent=1), encoding="utf-8")
        self._items[pid] = gradient
        self._meta[pid] = {"desc": desc, "source": "user", "builtin": False, "path": str(path)}
        return path


palettes = PaletteLibrary()
