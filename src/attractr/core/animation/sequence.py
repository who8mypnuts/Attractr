"""Frame-sequence renderer: timeline × base settings → numbered PNGs (+ manifest, report,
optional ffmpeg encode).  Resumable: existing frames are skipped."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from attractr.core.animation.ffmpeg import PRESETS, encode
from attractr.core.animation.timeline import Timeline
from attractr.core.io.image_export import save_image
from attractr.core.io.metadata import settings_text_chunks
from attractr.core.jobs.cancel import NEVER, CancelToken
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.develop.developer import Developed, develop
from attractr.core.render.framing import compute_framing
from attractr.core.render.pipeline import accumulate, resolve_spec
from attractr.core.render.settings import RenderSettings


@dataclass
class SequenceOptions:
    out_dir: Path
    name: str = "anim"
    start: int = 0
    end: int | None = None  # exclusive; None → all frames
    engine: str = "auto"
    resume: bool = True
    encode_preset: str = "h264"  # key of PRESETS or "png_only"
    crf: int = 18
    ffmpeg: str | None = None
    movie_path: Path | None = None
    write_report: bool = True


@dataclass
class SequenceResult:
    frames: list[Path] = field(default_factory=list)
    movie: Path | None = None
    seconds: float = 0.0
    per_frame_seconds: list[float] = field(default_factory=list)
    report: Path | None = None


def locked_camera(base: RenderSettings, timeline: Timeline) -> RenderSettings:
    """Lock the framing to the union of the bounding spheres at every key time (plus the
    start/end), so the whole animation shares one frame of reference."""
    spec = resolve_spec(base)
    times = sorted(set(timeline.key_times()) | {0.0, timeline.duration})
    centers, radii = [], []
    for t in times[:12]:
        s = timeline.evaluate(base, t)
        q = s.quality
        fr, _ = compute_framing(spec, spec.params_array(s.param_dict), float(q.dt) if q.dt else spec.dt, max(1, q.substeps), spec.warmup, q.seed)
        centers.append(np.asarray(fr.center))
        radii.append(fr.radius)
    c = np.mean(centers, axis=0)
    r = max(float(np.linalg.norm(ci - c)) + ri for ci, ri in zip(centers, radii, strict=True))
    cam = replace(base.camera, fit="sphere", lock_center=tuple(float(v) for v in c), lock_radius=float(r))
    return replace(base, camera=cam)


def frame_settings(base: RenderSettings, timeline: Timeline, i: int) -> RenderSettings:
    return timeline.evaluate(base, timeline.frame_time(i))


def render_frame(base: RenderSettings, timeline: Timeline, i: int, engine: str, cancel: CancelToken) -> tuple[Developed, object]:
    """Render frame ``i`` with optional motion blur (sub-frame averaging)."""
    samples = max(1, timeline.motion_blur)
    acc = None
    last_result = None
    for k in range(samples):
        t = timeline.frame_time(i) + (k / samples) / timeline.fps if samples > 1 else timeline.frame_time(i)
        s = timeline.evaluate(base, t)
        result = accumulate(s, engine=engine, cancel=cancel)
        dev = develop(result, s.look)
        acc = dev.rgba / samples if acc is None else acc + dev.rgba / samples
        last_result = result
    return Developed(acc, 0.0), last_result


def render_sequence(base: RenderSettings, timeline: Timeline, opts: SequenceOptions, *, cancel: CancelToken = NEVER,
                    tracker: ProgressTracker | None = None, on_frame=None) -> SequenceResult:
    tracker = tracker or ProgressTracker(None)
    t_start = time.perf_counter()
    out_dir = Path(opts.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if timeline.lock_framing and not base.camera.locked:
        tracker.update(0.0, "locking framing", force=True)
        base = locked_camera(base, timeline)
    n = timeline.frame_count
    end = n if opts.end is None else min(opts.end, n)
    frames = list(range(opts.start, end))
    res = SequenceResult()
    manifest = {"name": opts.name, "fps": timeline.fps, "frames": n, "timeline": timeline.to_dict(), "base": base.to_dict(), "rendered": {}}
    for k, i in enumerate(frames):
        cancel.check()
        path = out_dir / f"{opts.name}_{i:04d}.png"
        if opts.resume and path.exists():
            res.frames.append(path)
            continue
        t0 = time.perf_counter()
        dev, result = render_frame(base, timeline, i, opts.engine, cancel)
        s = frame_settings(base, timeline, i)
        save_image(dev, path, texts=settings_text_chunks(s), dither=s.look.dither)
        dt = time.perf_counter() - t0
        res.frames.append(path)
        res.per_frame_seconds.append(dt)
        manifest["rendered"][str(i)] = {"seconds": dt, "coverage": getattr(result.stats, "coverage", 0.0), "iterations": getattr(result.stats, "iterations_done", 0)}
        tracker.update(0.02 + 0.9 * (k + 1) / max(len(frames), 1), f"frame {i + 1}/{n} · {dt:.1f}s")
        if on_frame:
            on_frame(i, path, dev)
    (out_dir / f"{opts.name}_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    if opts.encode_preset != "png_only" and frames:
        tracker.update(0.93, "encoding", force=True)
        ext = PRESETS[opts.encode_preset]["ext"]
        movie = opts.movie_path or (out_dir / f"{opts.name}{ext}")
        pattern = str(out_dir / f"{opts.name}_%04d.png")
        enc = encode(pattern, timeline.fps, movie, opts.encode_preset, opts.crf, opts.ffmpeg, frame_count=n,
                     on_progress=lambda f: tracker.update(0.93 + 0.06 * min(f / max(n, 1), 1.0), f"encoding frame {f}"))
        res.movie = enc.path
        (out_dir / f"{opts.name}_ffmpeg.log").write_text(" ".join(enc.command) + "\n\n" + enc.log, encoding="utf-8")
    res.seconds = time.perf_counter() - t_start
    if opts.write_report:
        res.report = write_animation_report(base, timeline, opts, res, out_dir)
    tracker.update(1.0, "done", force=True)
    return res


def write_animation_report(base: RenderSettings, timeline: Timeline, opts: SequenceOptions, res: SequenceResult, out_dir: Path) -> Path:
    spec = resolve_spec(base)
    lines = [f"# Attractr animation report — {spec.name}", "",
             f"_{timeline.frame_count} frames · {timeline.fps} fps · {timeline.duration:.2f} s · {base.quality.width}×{base.quality.height} · {len(res.frames)} rendered_", "",
             "## Timeline", "", "| Track | Keys | Times |", "|---|---|---|"]
    for tr in timeline.tracks.values():
        lines.append(f"| {tr.label} | {len(tr.keys)} | {', '.join(f'{k.time:.2f}' for k in tr.keys)} |")
    lines += ["", f"Loop: {timeline.loop} · motion blur: {timeline.motion_blur}× · framing locked: {timeline.lock_framing}", ""]
    if res.per_frame_seconds:
        arr = np.array(res.per_frame_seconds)
        lines += ["## Timing", "", f"- total {res.seconds:.1f} s", f"- per frame mean {arr.mean():.2f} s · min {arr.min():.2f} s · max {arr.max():.2f} s", ""]
    if res.movie:
        lines += ["## Output", "", f"- movie: `{res.movie}`", f"- encoder preset: {opts.encode_preset} (crf {opts.crf})", ""]
    lines += ["## Base settings", "", "```", json.dumps(base.to_dict(), indent=1)[:4000], "```", ""]
    path = out_dir / f"{opts.name}_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ── CLI glue ─────────────────────────────────────────────────────────────────


def cli_animate(a) -> int:
    from attractr.cli.common import ProgressBar
    from attractr.core.project.files import load_project

    proj = load_project(a.project)
    if not proj.animation:
        raise ValueError("this project has no timeline — add keyframes in the GUI first")
    tl = Timeline.from_dict(proj.animation)
    if a.fps:
        tl.fps = a.fps
    base = proj.settings
    if a.size:
        w, h = (int(v) for v in a.size.lower().split("x"))
        base = replace(base, quality=base.quality.with_size(w, h))
    if a.ppp:
        base = replace(base, quality=replace(base.quality, points_per_pixel=a.ppp))
    out = Path(a.output)
    opts = SequenceOptions(out_dir=out, name=a.name, start=a.start, end=a.end, engine=a.engine or "auto",
                           resume=not a.no_resume, encode_preset=a.encode, crf=a.crf,
                           movie_path=Path(a.movie) if a.movie else None)
    res = render_sequence(base, tl, opts, tracker=ProgressTracker(ProgressBar("animate")))
    print(f"{len(res.frames)} frames in {out} ({res.seconds:.1f} s)" + (f" → {res.movie}" if res.movie else ""))
    return 0
