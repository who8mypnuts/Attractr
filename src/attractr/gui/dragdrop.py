"""Drag-and-drop plumbing shared by the viewport and the main window.

Accepted payloads:

| payload | effect |
|---|---|
| palette swatch from the gradient library (``MIME_PALETTE``) | apply the palette to the look |
| gallery image (``MIME_GALLERY`` or a dropped ``.png`` with embedded settings) | re-open the render's settings |
| ``.atr`` file | import into *My attractors* and select it |
| ``.attractr`` project | open it |
| ``.ggr`` / ``.json`` gradient file | apply the gradient |
| plain text that is an ``ATR1:`` / ``CHS1:`` share code | paste the code |

Drag *sources* (gallery list, palette library) only have to put the right MIME type on
the :class:`QMimeData`; everything else lives here so the rules exist once.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl

log = logging.getLogger(__name__)

MIME_PALETTE = "application/x-attractr-palette"  # payload: palette id (utf-8)
MIME_GALLERY = "application/x-attractr-gallery"  # payload: image path (utf-8)
FILE_SUFFIXES = (".atr", ".attractr", ".png", ".ggr", ".json")


def palette_mime(pid: str) -> QMimeData:
    """Drag payload for a palette id."""
    m = QMimeData()
    m.setData(MIME_PALETTE, pid.encode())
    m.setText(pid)
    return m


def gallery_mime(path: str) -> QMimeData:
    """Drag payload for a gallery image (internal type + file URL for other apps)."""
    m = QMimeData()
    m.setData(MIME_GALLERY, str(path).encode())
    m.setUrls([QUrl.fromLocalFile(str(path))])
    return m


def _local_files(mime: QMimeData) -> list[Path]:
    return [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile()]


def can_accept(mime: QMimeData) -> bool:
    """Whether :func:`handle_drop` knows what to do with ``mime``."""
    if mime.hasFormat(MIME_PALETTE) or mime.hasFormat(MIME_GALLERY):
        return True
    if any(p.suffix.lower() in FILE_SUFFIXES for p in _local_files(mime)):
        return True
    return mime.hasText() and mime.text().strip().startswith(("ATR1:", "CHS1:"))


def handle_drop(window, mime: QMimeData) -> bool:
    """Apply a dropped payload to ``window`` (a MainWindow). Returns True when handled."""
    doc = window.doc
    if mime.hasFormat(MIME_PALETTE):
        from attractr.core.color.palettes import palettes

        pid = bytes(mime.data(MIME_PALETTE)).decode()
        if pid in palettes:
            doc.set_look(replace(doc.settings.look, gradient=palettes.get(pid)), f"Palette {palettes.get(pid).name}")
            window.set_status(f"palette: {palettes.get(pid).name}")
            return True
        return False
    if mime.hasFormat(MIME_GALLERY):
        return _apply_image_settings(window, Path(bytes(mime.data(MIME_GALLERY)).decode()))
    for path in _local_files(mime):
        if _handle_file(window, path):
            return True
    if mime.hasText():
        text = mime.text().strip()
        if text.startswith(("ATR1:", "CHS1:")):
            from attractr.core.project.codes import settings_from_code
            from attractr.gui.state.document import TAGS_ALL

            s = settings_from_code(text)
            if s is not None:
                doc.apply(s, "Paste share code", TAGS_ALL)
                return True
    return False


def _handle_file(window, path: Path) -> bool:
    """Dispatch a dropped local file by suffix; errors go to the status bar."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".attractr":
            if window.confirm_discard():
                window.load_path(str(path))
            return True
        if suffix == ".atr":
            return _import_attractor(window, path)
        if suffix == ".png":
            return _apply_image_settings(window, path)
        if suffix in (".ggr", ".json"):
            return _apply_gradient_file(window, path)
    except Exception as exc:  # noqa: BLE001 — report, never crash on a bad drop
        log.warning("drop of %s failed: %s", path, exc)
        window.set_status(f"could not use {path.name}: {exc}")
    return False


def _import_attractor(window, path: Path) -> bool:
    """Save an ``.atr`` file into *My attractors* and select it."""
    from attractr.core.attractors.registry import registry

    spec = registry.save_user(path.read_text(encoding="utf-8"), spec_id=path.stem)
    window.doc.set_attractor(spec)
    window.set_status(f"imported {spec.name} into My attractors")
    if hasattr(window, "browser"):
        window.browser.populate()
    return True


def _apply_image_settings(window, path: Path) -> bool:
    """Re-open the settings embedded in an Attractr PNG."""
    from attractr.core.io.metadata import read_settings
    from attractr.gui.state.document import TAGS_ALL

    s = read_settings(path)
    if s is None:
        window.set_status(f"{path.name} has no Attractr settings embedded")
        return False
    window.doc.apply(s, f"Settings from {path.name}", TAGS_ALL)
    window.set_status(f"settings re-opened from {path.name}")
    return True


def _apply_gradient_file(window, path: Path) -> bool:
    """Apply a ``.ggr`` / gradient ``.json`` file to the look."""
    from attractr.core.color.gradient import Gradient

    if path.suffix.lower() == ".ggr":
        from attractr.core.color.ggr_io import read_ggr

        g = read_ggr(str(path))
    else:
        d = json.loads(path.read_text(encoding="utf-8"))
        if "stops" not in d:
            return False  # some other JSON
        g = Gradient.from_dict(d)
    window.doc.set_look(replace(window.doc.settings.look, gradient=g), f"Gradient {g.name}")
    window.set_status(f"gradient: {g.name}")
    return True
