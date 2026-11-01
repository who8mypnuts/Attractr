"""Settings embedded in exported images so any Attractr image can be re-opened."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from attractr.core.render.settings import RenderSettings

KEY_SETTINGS = "attractr:settings"
KEY_CODE = "attractr:code"
KEY_VERSION = "attractr:version"


def settings_text_chunks(settings: RenderSettings) -> dict[str, str]:
    from attractr.core.project.codes import settings_to_code
    from attractr.version import __version__

    return {
        KEY_SETTINGS: json.dumps(settings.to_dict(), separators=(",", ":")),
        KEY_CODE: settings_to_code(settings),
        KEY_VERSION: __version__,
    }


def read_settings(path: str | Path) -> RenderSettings | None:
    """Recover settings from a PNG written by Attractr (None if absent)."""
    try:
        img = Image.open(path)
        info = getattr(img, "text", None) or img.info
        raw = info.get(KEY_SETTINGS)
        if raw:
            return RenderSettings.from_dict(json.loads(raw))
        code = info.get(KEY_CODE)
        if code:
            from attractr.core.project.codes import settings_from_code

            return settings_from_code(code)
    except Exception:  # noqa: BLE001
        return None
    return None
