"""A queued full-size render: accumulate → develop → save → report."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from attractr.core.io.image_export import save_image
from attractr.core.io.metadata import settings_text_chunks
from attractr.core.io.naming import render_name, unique_path
from attractr.core.jobs.cancel import CancelToken
from attractr.core.jobs.job import Job
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.develop.developer import develop
from attractr.core.render.pipeline import accumulate, resolve_spec
from attractr.core.render.settings import RenderSettings


@dataclass
class RenderOutput:
    image_path: Path
    report_paths: list[Path] = field(default_factory=list)
    result: object = None
    developed: object = None
    seconds: float = 0.0


class RenderJob(Job):
    def __init__(self, settings: RenderSettings, out_dir: Path, name_template: str, fmt: str = "png",
                 bit_depth: int = 8, report_formats: list[str] | None = None, dynamics: bool = False,
                 name: str | None = None) -> None:
        super().__init__(name or f"Render {settings.quality.width}×{settings.quality.height}")
        self.settings = settings
        self.out_dir = out_dir
        self.name_template = name_template
        self.fmt = fmt
        self.bit_depth = bit_depth
        self.report_formats = report_formats or []
        self.dynamics = dynamics
        self.output: RenderOutput | None = None

    def run(self, cancel: CancelToken, tracker: ProgressTracker) -> RenderOutput:
        t0 = time.perf_counter()
        s = self.settings
        spec = resolve_spec(s)

        def sink(result, fraction):
            self.partial.emit(result)

        result = accumulate(s, cancel=cancel, tracker=tracker, sink=sink)
        cancel.check()
        tracker.update(0.96, "developing", force=True)
        t1 = time.perf_counter()
        dev = develop(result, s.look)
        develop_seconds = time.perf_counter() - t1
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = unique_path(self.out_dir / f"{render_name(s, self.name_template)}.{self.fmt}")
        transparent = s.look.background.mode == "transparent"
        tracker.update(0.98, "saving", force=True)
        if s.look.caption:
            from attractr.core.io.caption import draw_caption
            from attractr.core.io.image_export import to_pil

            img = draw_caption(to_pil(dev, transparent), spec, s, light_text=not s.look.invert)
            from PIL import PngImagePlugin

            info = PngImagePlugin.PngInfo()
            for k, v in settings_text_chunks(s).items():
                info.add_text(k, v)
            img.save(path, pnginfo=info) if path.suffix.lower() == ".png" else img.convert("RGB").save(path)
        else:
            save_image(dev, path, bit_depth=self.bit_depth, transparent=transparent, texts=settings_text_chunks(s), dither=s.look.dither)
        reports: list[Path] = []
        if self.report_formats:
            from attractr.core.report.writer import write_report

            dynamics = None
            if self.dynamics:
                tracker.update(0.99, "dynamics", force=True)
                from attractr.core.analysis.probe import probe

                dynamics = probe(spec, s.param_dict, s.quality.dt).as_dict()
            reports = write_report(s, result, spec, dev, path, self.report_formats, develop_seconds=develop_seconds, dynamics=dynamics)
        from attractr.core.project.gallery import gallery

        gallery.add(path, spec.id, s.quality.width, s.quality.height, reports[0] if reports else None)
        self.output = RenderOutput(path, reports, result, dev, time.perf_counter() - t0)
        return self.output
