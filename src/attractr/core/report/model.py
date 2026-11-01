"""Report data model: a renderer-agnostic document built from settings + result + stats."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.render.result import RenderResult
from attractr.core.render.settings import RenderSettings


@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]]


@dataclass
class Section:
    title: str
    paragraphs: list[str] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    code: str | None = None
    code_lang: str = ""
    image: str | None = None  # path relative to the report
    bullets: list[str] = field(default_factory=list)


@dataclass
class Report:
    title: str
    subtitle: str
    generated: datetime
    sections: list[Section]
    thumbnail: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def _f(v: float, nd: int = 4) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1e6 or (abs(v) < 1e-4 and v != 0):
        return f"{v:.3e}"
    s = f"{v:.{nd}f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _seconds(v: float) -> str:
    if v < 1:
        return f"{v * 1000:.0f} ms"
    if v < 60:
        return f"{v:.2f} s"
    m, s = divmod(v, 60)
    return f"{int(m)} min {s:.0f} s"


def _human(n: float) -> str:
    for unit, div in (("G", 1e9), ("M", 1e6), ("k", 1e3)):
        if n >= div:
            return f"{n / div:.2f} {unit}"
    return f"{n:.0f}"


def build_report(
    settings: RenderSettings,
    result: RenderResult,
    spec: AttractorSpec,
    *,
    image_path: Path | None = None,
    thumbnail_rel: str | None = None,
    histogram_rel: str | None = None,
    develop_seconds: float = 0.0,
    dynamics: dict[str, Any] | None = None,
    cli_command: str | None = None,
) -> Report:
    from attractr.core.project.codes import settings_to_code
    from attractr.version import __version__

    st = result.stats
    q = settings.quality
    look = settings.look
    cam = settings.camera
    yaw, pitch, roll = cam.euler
    now = datetime.now()
    sections: list[Section] = []

    # ── attractor ──────────────────────────────────────────────────────────────
    s = Section(f"Attractor — {spec.name}")
    if spec.description:
        s.paragraphs.append(spec.description)
    s.code = "\n".join(spec.formula_text())
    s.code_lang = "text"
    s.tables.append(Table(["Property", "Value"], [
        ["Id", spec.id], ["Kind", spec.kind], ["Dimensions", f"{spec.dims}-D"], ["Family", spec.family],
        ["Integrator", q.integrator if spec.is_flow else "map"],
        ["dt", _f(q.dt or spec.dt, 6) if spec.is_flow else "—"],
        ["Sub-steps", str(q.substeps) if spec.is_flow else "—"],
    ]))
    if spec.references:
        s.bullets = list(spec.references)
    sections.append(s)

    # ── parameters ─────────────────────────────────────────────────────────────
    pd = settings.param_dict
    rows = [[p.name, _f(pd.get(p.name, p.default), 6), _f(p.default, 6), f"[{_f(p.lo)}, {_f(p.hi)}]", p.hint]
            for p in spec.params]
    sections.append(Section("Parameters", tables=[Table(["Name", "Value", "Default", "Range", "Meaning"], rows)]))

    # ── camera & framing ───────────────────────────────────────────────────────
    fr = result.framing
    sections.append(Section("Camera & framing", tables=[Table(["Property", "Value"], [
        ["Yaw / pitch / roll", f"{_f(yaw, 2)}° / {_f(pitch, 2)}° / {_f(roll, 2)}°"],
        ["Zoom", _f(cam.zoom)], ["Pan (u, v)", f"{_f(cam.pan_u)}, {_f(cam.pan_v)}"],
        ["Perspective", _f(cam.perspective)], ["Fit mode", cam.fit],
        ["Bounding sphere centre", ", ".join(_f(c, 3) for c in fr.center)],
        ["Bounding sphere radius", _f(fr.radius, 4)],
        ["Bounding box", f"[{', '.join(_f(c, 2) for c in fr.bbox_min)}] → [{', '.join(_f(c, 2) for c in fr.bbox_max)}]"],
        ["2-D fit zoom / pan", f"{_f(fr.fit_zoom, 3)} / {_f(fr.fit_pan[0], 3)}, {_f(fr.fit_pan[1], 3)}"],
    ])]))

    # ── look ───────────────────────────────────────────────────────────────────
    g = look.gradient
    stops = ", ".join(f"{_f(s_.pos, 2)}:{s_.hex}" for s_ in g.stops)
    sections.append(Section("Look (development)", tables=[Table(["Property", "Value"], [
        ["Style", look.style], ["Colour source", look.color_source],
        ["Palette", f"{g.name} ({g.space}{', cyclic' if g.cyclic else ''})"], ["Stops", stops],
        ["Palette phase / cycles", f"{_f(look.phase)} / {_f(look.cycles)}"],
        ["Percentile → full brightness", f"{look.percentile * 100:.2f} %  (count = {_f(st.percentile_count, 1)})"],
        ["Gamma / brightness / contrast", f"{_f(look.gamma)} / {_f(look.brightness)} / {_f(look.contrast)}"],
        ["Equalise / invert", f"{look.equalize} / {look.invert}"],
        ["Depth cue", _f(look.depth_cue)],
        ["Background", f"{look.background.mode} {look.background.color if look.background.mode == 'solid' else ''}".strip()],
        ["Light (az / el)", f"{_f(look.light.azimuth, 1)}° / {_f(look.light.elevation, 1)}°"] if look.style in ("liquid", "solid") else ["Light", "—"],
    ])]))

    # ── quality & engine ───────────────────────────────────────────────────────
    sections.append(Section("Quality & engine", tables=[Table(["Property", "Value"], [
        ["Output size", f"{q.width} × {q.height} px"],
        ["Points per pixel", _f(q.points_per_pixel, 2)],
        ["Iterations requested / done", f"{_human(st.iterations_requested)} / {_human(st.iterations_done)}"],
        ["Trajectories", f"{st.trajectories:,}"], ["Warm-up steps (accumulation)", str(st.warmup_steps)],
        ["Supersampling", f"{q.supersample}×"], ["Splat radius", str(q.splat_radius)],
        ["Gap filling", str(q.gap_fill and spec.is_flow)], ["Seed", str(q.seed)],
        ["Engine", f"{st.engine} ({st.device})"], ["Precision", st.precision],
        ["Passes / tiles", f"{st.passes} / {st.tiles}"],
    ])]))

    # ── timing ─────────────────────────────────────────────────────────────────
    sections.append(Section("Timing", tables=[Table(["Stage", "Time"], [
        ["Formula compile", _seconds(st.compile_seconds)], ["Framing", _seconds(st.framing_seconds)],
        ["Accumulation", _seconds(st.accumulate_seconds)], ["Development", _seconds(develop_seconds)],
        ["Total", _seconds(st.elapsed + develop_seconds)],
        ["Throughput", f"{_human(st.points_per_second)} points/s"],
    ])]))

    # ── statistics ─────────────────────────────────────────────────────────────
    stat = Section("Statistics", tables=[Table(["Metric", "Value"], [
        ["Non-empty pixels", f"{st.nonzero_pixels:,} ({st.coverage * 100:.2f} % coverage)"],
        ["Points landed in frame", f"{_human(st.points_plotted)} ({(st.points_plotted / max(st.iterations_done, 1)) * 100:.1f} %)"],
        ["Trajectory restarts (divergence)", str(st.restarts)],
        ["Max / mean / median density", f"{_f(st.max_count, 1)} / {_f(st.mean_count, 2)} / {_f(st.median_count, 2)}"],
        ["Density entropy", f"{_f(st.entropy_bits, 2)} bits"],
    ])], image=histogram_rel)
    if st.density_histogram:
        stat.paragraphs.append("Density histogram (log-spaced bins): " + sparkline(st.density_histogram))
    if st.notes:
        stat.bullets = list(st.notes)
    sections.append(stat)

    # ── dynamics ───────────────────────────────────────────────────────────────
    if dynamics:
        rows = [[k, _f(v, 4) if isinstance(v, int | float) else str(v)] for k, v in dynamics.items()]
        sections.append(Section("Dynamics", tables=[Table(["Quantity", "Value"], rows)]))

    # ── reproducibility ────────────────────────────────────────────────────────
    rep = Section("Reproducibility")
    rep.code = settings_to_code(settings)
    rep.code_lang = "text"
    if cli_command:
        rep.paragraphs.append("Command line: `" + cli_command + "`")
    rep.tables.append(Table(["Software", "Version"], [
        ["Attractr", __version__], ["Python", sys.version.split()[0]],
        ["NumPy", _ver("numpy")], ["numba", _ver("numba")], ["Platform", platform.platform()],
    ]))
    sections.append(rep)

    return Report(
        title=f"Attractr render report — {spec.name}",
        subtitle=f"{q.width}×{q.height} · {look.style} · {now:%Y-%m-%d %H:%M}" + (f" · {image_path.name}" if image_path else ""),
        generated=now,
        sections=sections,
        thumbnail=thumbnail_rel,
        meta={"attractor": spec.id, "image": str(image_path) if image_path else None},
    )


def sparkline(values: list[int]) -> str:
    bars = "▁▂▃▄▅▆▇█"
    if not values:
        return ""
    import math

    m = max(values) or 1
    return "".join(bars[min(7, int(math.log1p(v) / math.log1p(m) * 7.999))] if v else " " for v in values)


def _ver(mod: str) -> str:
    try:
        return __import__(mod).__version__
    except Exception:  # noqa: BLE001
        return "—"
