"""Internationalisation scaffolding.

Attractr's user-visible strings are plain Python literals today. This module is the seam
through which they become translatable without touching every call site at once:

* :func:`tr` — ``QCoreApplication.translate`` with the ``"attractr"`` context, safe to call
  before a QApplication exists (returns the source text);
* :func:`install_translators` — loads ``resources/i18n/attractr_<locale>.qm`` (plus Qt's
  own ``qtbase_<locale>.qm``) for the current locale or the ``ATTRACTR_LANG`` override.

Workflow (see docs/development.md): wrap strings with ``tr("…")``, run
``pyside6-lupdate`` over ``src`` to produce ``resources/i18n/attractr_<locale>.ts``,
translate with Qt Linguist, ``pyside6-lrelease`` → ``.qm``.
"""

from __future__ import annotations

import logging
import os

from attractr.core.io.paths import resources_dir

log = logging.getLogger(__name__)
CONTEXT = "attractr"
_translators: list = []  # keep references alive


def tr(text: str, disambiguation: str | None = None, n: int = -1) -> str:
    try:
        from PySide6.QtCore import QCoreApplication
    except ImportError:  # pragma: no cover — core-only environments
        return text
    if QCoreApplication.instance() is None:
        return text
    return QCoreApplication.translate(CONTEXT, text, disambiguation, n)


def available_locales() -> list[str]:
    d = resources_dir() / "i18n"
    return sorted(p.stem.removeprefix("attractr_") for p in d.glob("attractr_*.qm")) if d.is_dir() else []


def install_translators(app, locale: str | None = None) -> list[str]:
    """Install the application and Qt translations for ``locale`` (default: system locale,
    overridable with ``ATTRACTR_LANG``). Returns the names of the files loaded."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    remove_translators(app)
    name = locale or os.environ.get("ATTRACTR_LANG") or QLocale.system().name()  # e.g. "de_DE"
    loaded: list[str] = []
    candidates = [name, name.split("_")[0]]
    i18n_dir = resources_dir() / "i18n"
    for cand in candidates:
        t = QTranslator(app)
        if t.load(f"attractr_{cand}", str(i18n_dir)):
            app.installTranslator(t)
            _translators.append(t)
            loaded.append(f"attractr_{cand}.qm")
            break
    qt_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for cand in candidates:
        t = QTranslator(app)
        if t.load(f"qtbase_{cand}", qt_dir):
            app.installTranslator(t)
            _translators.append(t)
            loaded.append(f"qtbase_{cand}.qm")
            break
    if loaded:
        log.info("translations: %s", ", ".join(loaded))
    return loaded


def remove_translators(app) -> None:
    """Uninstall every translator added by :func:`install_translators` (back to English)."""
    for t in _translators:
        app.removeTranslator(t)
    _translators.clear()
