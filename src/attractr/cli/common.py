"""Shared CLI helpers: resolving a render target, applying overrides, progress bars."""

from __future__ import annotations

import shlex
import sys
from dataclasses import replace
from pathlib import Path

from attractr.core.attractors.registry import registry
from attractr.core.attractors.spec import spec_from_source
from attractr.core.color.palettes import palettes
from attractr.core.jobs.progress import Progress
from attractr.core.project.codes import settings_from_code
from attractr.core.project.files import SUFFIX, load_project
from attractr.core.render.pipeline import default_settings, resolve_spec
from attractr.core.render.settings import RenderSettings


def resolve_target(target: str) -> RenderSettings:
    """attractor id | .attractr project | .atr formula file | ATR1:/CHS1: code."""
    if target.startswith(("ATR1:", "CHS1:")):
        s = settings_from_code(target)
        if s is None:
            raise ValueError("could not decode the preset code")
        return s
    p = Path(target)
    if p.suffix == SUFFIX and p.exists():
        return load_project(p).settings
    if p.suffix == ".atr" and p.exists():
        spec = spec_from_source(p.read_text(encoding="utf-8"), id=p.stem)
        return default_settings(spec)
    return default_settings(registry.get(target))


def add_override_args(ap) -> None:
    ap.add_argument("--param", "-p", action="append", default=[], metavar="NAME=VALUE", help="override a parameter (repeatable)")
    ap.add_argument("--size", metavar="WxH", help="output size, e.g. 2048x2048")
    ap.add_argument("--ppp", type=float, help="points per pixel (iteration budget)")
    ap.add_argument("--iterations", type=float, help="absolute iteration count (overrides --ppp)")
    ap.add_argument("--engine", help="cpu | gl_compute | gl_points | gl_precision | opencl | auto")
    ap.add_argument("--precision", choices=("auto", "fp32", "fp64"), help="GPU trajectory precision (fp64 needs driver support)")
    ap.add_argument("--ss", type=int, help="supersampling factor 1..4")
    ap.add_argument("--splat", type=int, help="splat radius 0..4")
    ap.add_argument("--no-gap-fill", action="store_true")
    ap.add_argument("--integrator", choices=("rk4", "rk2", "euler"))
    ap.add_argument("--dt", type=float)
    ap.add_argument("--substeps", type=int)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--style", help="gas | dust | light | liquid | solid | plasma")
    ap.add_argument("--color-by", dest="color_by", help="density | x | y | z | depth | speed | radius | index | curvature | formula")
    ap.add_argument("--palette", help="palette id (see `attractr list palettes`)")
    ap.add_argument("--percentile", type=float)
    ap.add_argument("--gamma", type=float)
    ap.add_argument("--invert", action="store_true")
    ap.add_argument("--equalize", action="store_true")
    ap.add_argument("--bg", help="background colour hex (e.g. #000000) or 'transparent'")
    ap.add_argument("--camera", metavar="YAW,PITCH,ROLL", help="camera Euler angles in degrees")
    ap.add_argument("--zoom", type=float)
    ap.add_argument("--perspective", type=float)
    ap.add_argument("--fit", choices=("bbox", "sphere"))


def apply_overrides(s: RenderSettings, a) -> RenderSettings:
    q, look, cam = s.quality, s.look, s.camera
    spec = resolve_spec(s)
    if a.param:
        vals = {}
        for item in a.param:
            if "=" not in item:
                raise ValueError(f"--param expects NAME=VALUE, got {item!r}")
            k, v = item.split("=", 1)
            if k not in spec.param_names:
                raise ValueError(f"unknown parameter {k!r}; this attractor has: {', '.join(spec.param_names)}")
            vals[k] = float(v)
        s = s.with_params(**vals)
    if a.size:
        w, h = (int(v) for v in a.size.lower().split("x"))
        q = q.with_size(w, h)
    if a.iterations:
        q = replace(q, points_per_pixel=a.iterations / (q.width * q.height))
    elif a.ppp:
        q = replace(q, points_per_pixel=a.ppp)
    for name in ("engine", "integrator", "dt", "substeps", "seed", "precision"):
        v = getattr(a, name, None)
        if v is not None:
            q = replace(q, **{name: v})
    if a.ss:
        q = replace(q, supersample=a.ss)
    if a.splat is not None:
        q = replace(q, splat_radius=a.splat)
    if a.no_gap_fill:
        q = replace(q, gap_fill=False)
    if a.style:
        look = replace(look, style=a.style)
    if a.color_by:
        look = replace(look, color_source=a.color_by)
    if a.palette:
        look = replace(look, gradient=palettes.get(a.palette))
    for name in ("percentile", "gamma"):
        v = getattr(a, name, None)
        if v is not None:
            look = replace(look, **{name: v})
    if a.invert:
        look = replace(look, invert=True)
    if a.equalize:
        look = replace(look, equalize=True)
    if a.bg:
        if a.bg == "transparent":
            look = replace(look, background=replace(look.background, mode="transparent"))
        else:
            h = a.bg.lstrip("#")
            rgb = tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
            look = replace(look, background=replace(look.background, mode="solid", color=rgb))
    if a.camera:
        yaw, pitch, roll = (float(v) for v in a.camera.split(","))
        cam = cam.with_euler(yaw, pitch, roll)
    if a.zoom is not None:
        cam = replace(cam, zoom=a.zoom)
    if a.perspective is not None:
        cam = replace(cam, perspective=a.perspective)
    if a.fit:
        cam = replace(cam, fit=a.fit)
    return replace(s, quality=q, look=look, camera=cam)


class ProgressBar:
    def __init__(self, label: str, stream=sys.stderr, enabled: bool = True) -> None:
        self.label = label
        self.stream = stream
        self.enabled = enabled and stream.isatty()

    def __call__(self, p: Progress) -> None:
        if not self.enabled:
            return
        n = int(p.fraction * 30)
        bar = "█" * n + "░" * (30 - n)
        self.stream.write(f"\r{self.label} {bar} {p.fraction * 100:5.1f} %  {p.message[:40]:40s} ETA {p.format_eta():>7s}")
        self.stream.flush()
        if p.fraction >= 1.0:
            self.stream.write("\n")


def command_line() -> str:
    return "attractr " + " ".join(shlex.quote(a) for a in sys.argv[1:])
