"""Per-locale overlays for the texts that live inside ``.atr`` files (descriptions and
parameter hints).  ``resources/i18n/attractors_<locale>.json``::

    {"lorenz": {"desc": "…", "hints": {"sigma": "…", "rho": "…"}}, …}

The overlay for the current locale (``ATTRACTR_LANG`` or the system locale) is applied
by the registry after loading; equations, names and ids stay as written.  Run
``python tools/extract_attractor_strings.py LOCALE`` to produce a template with every
built-in attractor's texts (existing translations are kept)."""

from __future__ import annotations

import json
import locale as _locale
import logging
import os
from dataclasses import replace
from pathlib import Path

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.io.paths import resources_dir

log = logging.getLogger(__name__)


def current_locale() -> str:
    name = os.environ.get("ATTRACTR_LANG")
    if not name:
        try:
            name = _locale.getlocale()[0] or ""
        except ValueError:
            name = ""
    return (name or "en").replace("-", "_")


def overlay_path(locale: str) -> Path | None:
    d = resources_dir() / "i18n"
    for cand in (locale, locale.split("_")[0]):
        p = d / f"attractors_{cand}.json"
        if p.exists():
            return p
    return None


def load_overlay(locale: str | None = None) -> dict[str, dict]:
    p = overlay_path(locale or current_locale())
    if p is None:
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("ignoring attractor overlay %s: %s", p, exc)
        return {}


def apply_overlay(spec: AttractorSpec, entry: dict) -> AttractorSpec:
    """A copy of ``spec`` with the overlay's description / hints (missing keys keep the original)."""
    desc = entry.get("desc") or spec.description
    hints = entry.get("hints") or {}
    params = tuple(replace(p, hint=hints.get(p.name, p.hint)) for p in spec.params)
    return replace(spec, description=desc, params=params)
