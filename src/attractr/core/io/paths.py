"""Well-known directories (user data, cache, bundled resources)."""

from __future__ import annotations

import os
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2]  # .../attractr


def resources_dir() -> Path:
    return _PKG_ROOT / "resources"


def user_dir() -> Path:
    override = os.environ.get("ATTRACTR_HOME")
    base = Path(override) if override else Path.home() / ".attractr"
    base.mkdir(parents=True, exist_ok=True)
    return base


def subdir(name: str) -> Path:
    d = user_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir(kind: str = "") -> Path:
    return subdir("cache") if not kind else subdir(f"cache/{kind}")


def user_attractors_dir() -> Path:
    return subdir("attractors")


def user_palettes_dir() -> Path:
    return subdir("palettes")


def user_presets_dir() -> Path:
    return subdir("presets")


def logs_dir() -> Path:
    return subdir("logs")
