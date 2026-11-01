"""``attractr report`` — regenerate a report from an image's embedded settings, and
``attractr thumb`` — small PNG to a file or stdout."""

from __future__ import annotations

import sys
from pathlib import Path

from attractr.cli.common import add_override_args, apply_overrides, resolve_target
from attractr.core.io.metadata import read_settings
from attractr.core.render.pipeline import render, resolve_spec


def add_parser(sub) -> None:
    ap = sub.add_parser("report", help="regenerate a render report from an Attractr PNG")
    ap.add_argument("image")
    ap.add_argument("--format", default="md", help="md, txt, html, pdf (comma separated)")
    ap.add_argument("--rerender", action="store_true", help="re-render at the embedded settings for fresh statistics (default: quick 512² statistics render)")
    ap.set_defaults(func=run_report)

    tp = sub.add_parser("thumb", help="render a small thumbnail (PNG)")
    tp.add_argument("target", nargs="?", default="lorenz")
    tp.add_argument("-o", "--output", default="-", help="file or '-' for stdout")
    tp.add_argument("--thumb-size", type=int, default=256)
    add_override_args(tp)
    tp.set_defaults(func=run_thumb)


def run_report(a) -> int:
    from dataclasses import replace

    from attractr.core.report.writer import write_report

    settings = read_settings(a.image)
    if settings is None:
        raise ValueError("no Attractr settings found in that image")
    if not a.rerender:
        settings = replace(settings, quality=settings.quality.with_size(512, 512))
    result, dev = render(settings)
    paths = write_report(settings, result, resolve_spec(settings), dev, Path(a.image), a.format.split(","))
    for p in paths:
        print(p)
    return 0


def run_thumb(a) -> int:
    from dataclasses import replace

    from attractr.core.io.image_export import to_pil

    settings = apply_overrides(resolve_target(a.target), a)
    q = settings.quality.with_size(a.thumb_size, a.thumb_size)
    settings = replace(settings, quality=replace(q, points_per_pixel=min(q.points_per_pixel, 6.0)))
    _, dev = render(settings)
    img = to_pil(dev, settings.look.background.mode == "transparent")
    if a.output == "-":
        img.save(sys.stdout.buffer, format="PNG")
    else:
        img.save(a.output)
    return 0
