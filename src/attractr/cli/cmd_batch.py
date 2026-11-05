"""``attractr batch`` — render every project / formula / tagged PNG in a folder with a render preset."""

from __future__ import annotations

import time
from pathlib import Path

from attractr.cli.common import ProgressBar
from attractr.core.io.image_export import save_image
from attractr.core.io.metadata import settings_text_chunks
from attractr.core.io.naming import render_name, unique_path
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.project import batch
from attractr.core.project.render_presets import render_presets
from attractr.core.render.develop.developer import develop
from attractr.core.render.pipeline import accumulate, resolve_spec


def add_parser(sub) -> None:
    ap = sub.add_parser("batch", help="render every file in a folder with a render preset",
                        description="Render all .attractr projects, .atr formulas and settings-tagged PNGs in FOLDER.")
    ap.add_argument("folder", nargs="?", default=".", help="folder to scan")
    ap.add_argument("--preset", default="Wallpaper 1920×1080", help="render preset name (see --list-presets)")
    ap.add_argument("--out", help="output folder (default: FOLDER/renders)")
    ap.add_argument("--template", default="{name}_{w}x{h}", help="file name template")
    ap.add_argument("--recursive", "-r", action="store_true")
    ap.add_argument("--report", metavar="FMT[,FMT]", help="override the preset's report formats (md, txt, html, pdf; '' = none)")
    ap.add_argument("--dry-run", action="store_true", help="list what would be rendered")
    ap.add_argument("--list-presets", action="store_true")
    ap.add_argument("--quiet", "-q", action="store_true")
    ap.set_defaults(func=run)


def run(a) -> int:
    if a.list_presets:
        for p in render_presets.all():
            print(f"  {p.name:34s} {p.summary}{'' if p.builtin else '  (user)'}")
        return 0
    preset = render_presets.get(a.preset)
    folder = Path(a.folder).expanduser()
    if not folder.is_dir():
        raise FileNotFoundError(f"not a folder: {folder}")
    out_dir = Path(a.out).expanduser() if a.out else folder / "renders"
    items, skipped = batch.plan(folder, preset, a.recursive)
    reports = list(preset.report_formats) if a.report is None else [f for f in a.report.split(",") if f]
    for p, why in skipped:
        print(f"skip {p.name}: {why}")
    if not items:
        print("nothing to render")
        return 0
    print(f"{len(items)} file(s) → {out_dir}  [{preset.name}: {preset.summary}]")
    if a.dry_run:
        for it in items:
            print(f"  {it.path.name}  →  {render_name(it.settings, a.template)}.{preset.fmt}")
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    t_all = time.perf_counter()
    for n, it in enumerate(items, 1):
        s = it.settings
        tracker = ProgressTracker(ProgressBar(f"[{n}/{len(items)}] {it.path.name[:24]:24s}", enabled=not a.quiet))
        t0 = time.perf_counter()
        result = accumulate(s, tracker=tracker)
        t1 = time.perf_counter()
        dev = develop(result, s.look)
        develop_seconds = time.perf_counter() - t1
        path = unique_path(out_dir / f"{render_name(s, a.template)}.{preset.fmt}")
        save_image(dev, path, bit_depth=preset.bit_depth, transparent=s.look.background.mode == "transparent",
                   texts=settings_text_chunks(s), dither=s.look.dither)
        if reports:
            from attractr.core.report.writer import write_report

            spec = resolve_spec(s)
            dynamics = None
            if preset.dynamics:
                from attractr.core.analysis.probe import probe

                dynamics = probe(spec, s.param_dict, s.quality.dt).as_dict()
            write_report(s, result, spec, dev, path, reports, develop_seconds=develop_seconds, dynamics=dynamics)
        if not a.quiet:
            print(f"wrote {path.name}  ({result.stats.iterations_done / 1e6:.0f} M points, {time.perf_counter() - t0:.1f} s)")
    if not a.quiet:
        print(f"batch done: {len(items)} image(s) in {time.perf_counter() - t_all:.1f} s")
    return 0
