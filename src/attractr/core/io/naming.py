"""Output file naming templates, e.g. ``{name}_{date}_{w}x{h}_{seed}``."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from attractr.core.render.settings import RenderSettings

DEFAULT_TEMPLATE = "{name}_{date}_{w}x{h}"


def render_name(settings: RenderSettings, template: str = DEFAULT_TEMPLATE, now: datetime | None = None) -> str:
    now = now or datetime.now()
    fields = {
        "name": re.sub(r"[^A-Za-z0-9_-]+", "_", settings.attractor).strip("_") or "attractor",
        "date": now.strftime("%Y%m%d"),
        "time": now.strftime("%H%M%S"),
        "datetime": now.strftime("%Y%m%d_%H%M%S"),
        "w": settings.quality.width,
        "h": settings.quality.height,
        "seed": settings.quality.seed,
        "style": settings.look.style,
        "ppp": int(settings.quality.points_per_pixel),
    }
    try:
        return template.format(**fields)
    except (KeyError, IndexError, ValueError):
        return DEFAULT_TEMPLATE.format(**fields)


def unique_path(path: Path) -> Path:
    """Append _2, _3 … if the file exists."""
    if not path.exists():
        return path
    for i in range(2, 10000):
        cand = path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not cand.exists():
            return cand
    return path
