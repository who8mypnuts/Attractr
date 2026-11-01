"""``attractr animate`` — frame sequence + ffmpeg encode from a project's timeline."""

from __future__ import annotations

from attractr.core.animation.ffmpeg import PRESETS


def add_parser(sub) -> None:
    ap = sub.add_parser("animate", help="render an animation (frames + ffmpeg)")
    ap.add_argument("project", help=".attractr project with a timeline")
    ap.add_argument("-o", "--output", default="frames", help="frame directory")
    ap.add_argument("--name", default="anim", help="frame file prefix")
    ap.add_argument("--fps", type=int)
    ap.add_argument("--size", metavar="WxH")
    ap.add_argument("--ppp", type=float)
    ap.add_argument("--engine")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int)
    ap.add_argument("--no-resume", action="store_true", help="re-render existing frames")
    ap.add_argument("--encode", default="h264", choices=list(PRESETS), help="ffmpeg preset (png_only to skip)")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--movie", help="movie output path (default: <output>/<name>.<ext>)")
    ap.set_defaults(func=run)


def run(a) -> int:
    from attractr.core.animation import sequence

    return sequence.cli_animate(a)
