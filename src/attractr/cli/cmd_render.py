"""``attractr render`` — render a still image (+ optional report)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from attractr.cli.common import ProgressBar, add_override_args, apply_overrides, command_line, resolve_target
from attractr.core.io.image_export import save_image
from attractr.core.io.metadata import settings_text_chunks
from attractr.core.io.naming import render_name, unique_path
from attractr.core.jobs.cancel import CancelToken
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.checkpoint import SUFFIX, Checkpoint
from attractr.core.render.develop.developer import develop
from attractr.core.render.pipeline import accumulate, resolve_spec


def add_parser(sub) -> None:
    ap = sub.add_parser("render", help="render a still image", description="Render an attractor to an image file.")
    ap.add_argument("target", nargs="?", default="lorenz", help="attractor id, .attractr project, .atr file or ATR1:/CHS1: code (ignored with --resume)")
    ap.add_argument("-o", "--output", help="output file (.png/.jpg/.webp/.tif); '-' writes PNG to stdout; default: auto-named PNG in the current directory")
    ap.add_argument("--bits", type=int, choices=(8, 16), default=8)
    ap.add_argument("--report", metavar="FMT[,FMT]", help="write a render report: md, txt, html, pdf")
    ap.add_argument("--dynamics", action="store_true", help="include Lyapunov exponent / dimension in the report")
    ap.add_argument("--quiet", "-q", action="store_true")
    ap.add_argument("--develop", choices=("auto", "cpu", "gpu"), default="auto", help="where to run the develop pass (gpu = OpenGL compute for large images)")
    ap.add_argument("--checkpoint-every", type=float, default=0.0, metavar="MIN", help="write a resumable checkpoint every MIN minutes (default: off); Ctrl-C keeps the last one")
    ap.add_argument("--resume", metavar="FILE", help="continue from a .attractr-ckpt.npz checkpoint (settings come from the file)")
    ap.add_argument("--finish-after", type=float, metavar="SEC", help="soft time limit: stop accumulating after SEC seconds and save what is there")
    add_override_args(ap)
    ap.set_defaults(func=run)


def run(a) -> int:
    resume = Checkpoint.load(a.resume) if a.resume else None
    settings = apply_overrides(resume.next_settings() if resume else resolve_target(a.target), a)
    spec = resolve_spec(settings)
    quiet = a.quiet or a.output == "-"
    tracker = ProgressTracker(ProgressBar("render", enabled=not quiet))
    t0 = time.perf_counter()
    cancel = CancelToken()
    if a.resume:
        ck_path = Path(a.resume)
    else:
        ck_path = Path(a.output).with_suffix("") if a.output and a.output != "-" else Path.cwd() / render_name(settings)
        ck_path = ck_path.with_name(ck_path.name + SUFFIX)
    segment = resume.segment + 1 if resume else 1
    last_ck = [time.perf_counter()]

    def sink(result, fraction):
        if a.finish_after and time.perf_counter() - t0 >= a.finish_after:
            cancel.finish()
        if a.checkpoint_every > 0 and not result.complete and time.perf_counter() - last_ck[0] >= 60 * a.checkpoint_every:
            last_ck[0] = time.perf_counter()
            Checkpoint.from_result(result, segment).save(ck_path)
            if not quiet:
                print(f"\rcheckpoint {ck_path} ({fraction * 100:.0f} %)", file=sys.stderr)

    try:
        result = accumulate(settings, tracker=tracker, cancel=cancel, sink=sink, resume=resume)
    except KeyboardInterrupt:
        if ck_path.exists():
            print(f"interrupted — resume with: attractr render --resume {ck_path}", file=sys.stderr)
        raise
    if ck_path.exists():
        ck_path.unlink()
    t1 = time.perf_counter()
    dev = develop(result, settings.look, gpu={"auto": "auto", "cpu": "off", "gpu": "force"}[a.develop])
    develop_seconds = time.perf_counter() - t1
    transparent = settings.look.background.mode == "transparent"
    if a.output == "-":
        from attractr.core.io.image_export import to_pil

        to_pil(dev, transparent).save(sys.stdout.buffer, format="PNG")
        return 0
    out = Path(a.output) if a.output else unique_path(Path.cwd() / (render_name(settings) + ".png"))
    out.parent.mkdir(parents=True, exist_ok=True)
    save_image(dev, out, bit_depth=a.bits, transparent=transparent, texts=settings_text_chunks(settings), dither=settings.look.dither)
    st = result.stats
    if not quiet:
        print(f"wrote {out}  ({st.iterations_done / 1e6:.1f} M points in {st.elapsed:.1f} s on {st.engine}, "
              f"{st.points_per_second / 1e6:.1f} Mpts/s, coverage {st.coverage * 100:.1f} %, total {time.perf_counter() - t0:.1f} s)")
    if a.report:
        from attractr.core.report.writer import write_report

        dynamics = None
        if a.dynamics:
            from attractr.core.analysis.probe import probe

            dynamics = probe(spec, settings.param_dict, settings.quality.dt).as_dict()
        paths = write_report(settings, result, spec, dev, out, a.report.split(","), develop_seconds=develop_seconds,
                             dynamics=dynamics, cli_command=command_line())
        if not quiet:
            for p in paths:
                print(f"report {p}")
    return 0
