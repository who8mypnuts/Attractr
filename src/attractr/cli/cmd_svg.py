"""``attractr svg`` — export one trajectory of the current view as SVG polylines / dots."""

from __future__ import annotations

from pathlib import Path

from attractr.cli.common import add_override_args, apply_overrides, resolve_target
from attractr.core.io.naming import render_name
from attractr.core.io.svg_export import write_svg


def add_parser(sub) -> None:
    ap = sub.add_parser("svg", help="export the orbit trace as SVG (vector art for plotters)",
                        description="Write one trajectory, projected exactly like the render, as SVG polylines (flows) or dots (maps).")
    ap.add_argument("target", nargs="?", default="lorenz", help="attractor id, .attractr project, .atr file or ATR1:/CHS1: code")
    ap.add_argument("-o", "--output", help="output .svg (default: auto-named in the current directory)")
    ap.add_argument("--points", type=int, default=20000, help="trajectory length in steps")
    ap.add_argument("--stroke-width", type=float, default=0.6)
    ap.add_argument("--stroke", help="stroke colour, e.g. #ffffff (default: white, black when the look is inverted)")
    ap.add_argument("--no-background", action="store_true", help="omit the background rectangle")
    add_override_args(ap)
    ap.set_defaults(func=run)


def run(a) -> int:
    settings = apply_overrides(resolve_target(a.target), a)
    out = Path(a.output) if a.output else Path.cwd() / (render_name(settings) + ".svg")
    style = {"stroke_width": a.stroke_width}
    if a.stroke:
        style["stroke"] = a.stroke
    if a.no_background:
        style["background"] = None
    write_svg(settings, out, a.points, **style)
    print(f"wrote {out}")
    return 0
