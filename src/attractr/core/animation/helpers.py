"""Timeline generators for the common animation recipes (the Android app's four video
modes and a few more)."""

from __future__ import annotations

import random
from dataclasses import replace

from attractr.core.animation.timeline import Timeline, get_path
from attractr.core.attractors.spec import AttractorSpec
from attractr.core.math import quaternion as Q
from attractr.core.render.settings import RenderSettings

CAMERA_PATHS = ["camera.rotation", "camera.zoom", "camera.pan_u", "camera.pan_v", "camera.perspective"]


def turntable(settings: RenderSettings, duration: float = 8.0, fps: int = 30, axis: str = "yaw", revolutions: float = 1.0) -> Timeline:
    """One (or more) full revolutions about the chosen axis; loops seamlessly."""
    tl = Timeline(duration=duration, fps=fps, loop="loop", lock_framing=True)
    q0 = settings.camera.rotation
    ax = {"yaw": (0.0, 1.0, 0.0), "pitch": (1.0, 0.0, 0.0), "roll": (0.0, 0.0, 1.0)}[axis]
    n = max(4, int(8 * revolutions))  # ≥ 4 keys per revolution so slerp takes the long way round
    for i in range(n + 1):
        angle = 360.0 * revolutions * i / n
        q = Q.normalize(Q.multiply(Q.from_axis_angle(ax, angle), q0))
        tl.set_key("camera.rotation", duration * i / n, q, easing="linear")
    return tl


def morph(a: RenderSettings, b: RenderSettings, duration: float = 6.0, fps: int = 30, pingpong: bool = True, easing: str = "smooth") -> Timeline:
    """Interpolate every parameter and the camera between two states."""
    tl = Timeline(duration=duration, fps=fps, loop="pingpong" if pingpong else "none", lock_framing=True)
    for name in a.param_dict:
        if name in b.param_dict:
            tl.set_key(f"params.{name}", 0.0, a.param_dict[name], easing)
            tl.set_key(f"params.{name}", duration, b.param_dict[name], easing)
    for p in CAMERA_PATHS:
        tl.set_key(p, 0.0, get_path(a, p), easing)
        tl.set_key(p, duration, get_path(b, p), easing)
    if a.look.gradient != b.look.gradient:
        tl.set_key("look.gradient", 0.0, a.look.gradient, easing)
        tl.set_key("look.gradient", duration, b.look.gradient, easing)
    return tl


def sweep_target(settings: RenderSettings, spec: AttractorSpec, fraction: float = 0.4, rng: random.Random | None = None) -> RenderSettings:
    """Random destination: every parameter moved by up to ±fraction of its range, plus a
    camera nudge (the Android 'Param Sweep' mode)."""
    rng = rng or random.Random()
    vals = dict(settings.param_dict)
    for p in spec.params:
        if p.is_int:
            continue
        vals[p.name] = p.clamp(vals.get(p.name, p.default) + rng.uniform(-1, 1) * fraction * p.span)
    cam = settings.camera
    if spec.is_3d:
        yaw, pitch, roll = cam.euler
        cam = cam.with_euler(yaw + rng.uniform(-30, 30), max(-90, min(90, pitch + rng.uniform(-15, 15))), roll)
    return replace(settings.with_param_dict(vals), camera=cam)


def param_sweep(settings: RenderSettings, spec: AttractorSpec, duration: float = 6.0, fps: int = 30, seed: int | None = None) -> Timeline:
    return morph(settings, sweep_target(settings, spec, rng=random.Random(seed)), duration, fps, pingpong=True)


def palette_cycle(settings: RenderSettings, duration: float = 6.0, fps: int = 30) -> Timeline:
    tl = Timeline(duration=duration, fps=fps, loop="loop")
    tl.set_key("look.phase", 0.0, settings.look.phase, "linear")
    tl.set_key("look.phase", duration, settings.look.phase + 1.0, "linear")
    return tl


def zoom_in(settings: RenderSettings, factor: float = 4.0, duration: float = 6.0, fps: int = 30) -> Timeline:
    tl = Timeline(duration=duration, fps=fps, loop="pingpong", lock_framing=True)
    tl.set_key("camera.zoom", 0.0, settings.camera.zoom, "smooth")
    tl.set_key("camera.zoom", duration, settings.camera.zoom * factor, "smooth")
    return tl


def orbit_trace(settings: RenderSettings, duration: float = 6.0, fps: int = 30) -> tuple[Timeline, RenderSettings]:
    """A single trajectory drawn progressively: frame i shows the first (i/N)·budget points.
    Returns the timeline and the base settings (one trajectory, locked framing)."""
    tl = Timeline(duration=duration, fps=fps, loop="none", lock_framing=True)
    q = replace(settings.quality, trajectories=1, warmup=0)
    base = replace(settings, quality=q)
    ppp = settings.quality.points_per_pixel
    tl.set_key("quality.points_per_pixel", 0.0, max(ppp * 0.002, 0.0005), "linear")
    tl.set_key("quality.points_per_pixel", duration, ppp, "linear")
    return tl, base
