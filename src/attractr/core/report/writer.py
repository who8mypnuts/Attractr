"""Write a report next to an image in one or more formats."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.io.image_export import to_pil
from attractr.core.render.develop.developer import Developed
from attractr.core.render.result import RenderResult
from attractr.core.render.settings import REPORT_FORMATS, RenderSettings
from attractr.core.report.model import build_report
from attractr.core.report.plots import histogram_plot
from attractr.core.report.render_html import render_html
from attractr.core.report.render_md import render_markdown
from attractr.core.report.render_txt import render_text


def write_report(
    settings: RenderSettings,
    result: RenderResult,
    spec: AttractorSpec,
    developed: Developed | None,
    image_path: Path,
    formats: list[str] | tuple[str, ...] = ("md",),
    *,
    develop_seconds: float = 0.0,
    dynamics: dict[str, Any] | None = None,
    cli_command: str | None = None,
) -> list[Path]:
    """Returns the written report paths.  Side files (thumbnail, histogram plot) go into
    ``<image>_report/``."""
    formats = [f for f in formats if f in REPORT_FORMATS]
    if not formats:
        return []
    side = image_path.with_name(image_path.stem + "_report")
    side.mkdir(exist_ok=True)
    thumb_rel = hist_rel = None
    if developed is not None:
        thumb = to_pil(developed)
        thumb.thumbnail((720, 720))
        thumb.save(side / "thumbnail.png")
        thumb_rel = f"{side.name}/thumbnail.png"
    if result.stats.density_histogram:
        histogram_plot(result.stats.density_histogram, result.stats.density_histogram_edges, side / "histogram.png")
        hist_rel = f"{side.name}/histogram.png"
    report = build_report(settings, result, spec, image_path=image_path, thumbnail_rel=thumb_rel,
                          histogram_rel=hist_rel, develop_seconds=develop_seconds, dynamics=dynamics,
                          cli_command=cli_command)
    out: list[Path] = []
    for fmt in formats:
        path = image_path.with_name(image_path.stem + f"_report.{fmt}")
        if fmt == "md":
            path.write_text(render_markdown(report), encoding="utf-8")
        elif fmt == "txt":
            path.write_text(render_text(report), encoding="utf-8")
        elif fmt == "html":
            path.write_text(render_html(report), encoding="utf-8")
        elif fmt == "pdf":
            from attractr.core.report.render_pdf import render_pdf

            render_pdf(report, path, base_dir=image_path.parent)
        out.append(path)
    return out
