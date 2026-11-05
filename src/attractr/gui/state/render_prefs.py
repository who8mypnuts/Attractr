"""The persisted render-output preferences (QSettings ``render/*``) in one place.

Every code path that queues a render job — the render dialog, quick render, resume,
batch, gallery re-render — needs the output folder, the naming template, the report
formats and the checkpoint interval.  Reading them through :class:`RenderPrefs` keeps the
keys and their defaults in a single module (the job factory lives with the render
actions, so this state module has no controller dependency).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings

from attractr.core.io.naming import DEFAULT_TEMPLATE

KEY_FOLDER = "render/folder"
KEY_TEMPLATE = "render/template"
KEY_REPORT = "render/report"
KEY_REPORT_FMT = "render/report_fmt"
KEY_CHECKPOINT_MINUTES = "render/checkpoint_minutes"
DEFAULT_CHECKPOINT_MINUTES = 2.0


@dataclass(frozen=True)
class RenderPrefs:
    """Snapshot of the render-output preferences.

    Attributes:
        folder: where finished images (and their reports / checkpoints) go.
        template: file-name template (see :mod:`attractr.core.io.naming`).
        report_formats: formats of the render report written next to the image (empty = none).
        checkpoint_every: seconds between resumable checkpoints (0 = off).
    """

    folder: Path
    template: str
    report_formats: list[str]
    checkpoint_every: float

    @staticmethod
    def load(qs: QSettings | None = None) -> RenderPrefs:
        """Read the preferences from ``qs`` (the application settings by default)."""
        qs = qs or QSettings()
        report_on = qs.value(KEY_REPORT, "true") in ("true", True)
        return RenderPrefs(
            Path(str(qs.value(KEY_FOLDER, str(Path.home() / "Attractr")))).expanduser(),
            str(qs.value(KEY_TEMPLATE, DEFAULT_TEMPLATE)) or DEFAULT_TEMPLATE,
            [str(qs.value(KEY_REPORT_FMT, "md"))] if report_on else [],
            60.0 * float(qs.value(KEY_CHECKPOINT_MINUTES, DEFAULT_CHECKPOINT_MINUTES)),
        )

