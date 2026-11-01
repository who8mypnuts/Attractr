"""Timeline: tracks of keyframes on dotted property paths of RenderSettings.

Evaluating the timeline at time ``t`` yields a complete :class:`RenderSettings` — the
*base* settings with every animated property replaced by its interpolated value.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field, replace
from typing import Any

from attractr.core.animation.easing import get_easing, loop_time
from attractr.core.color.gradient import Gradient, Stop
from attractr.core.math import quaternion as Q
from attractr.core.render.settings import RenderSettings

ANIMATABLE = {
    # path: (label, kind)      kinds: float | quat | gradient | color | int
    "camera.rotation": ("Camera rotation", "quat"),
    "camera.zoom": ("Zoom", "float"),
    "camera.pan_u": ("Pan X", "float"),
    "camera.pan_v": ("Pan Y", "float"),
    "camera.perspective": ("Perspective", "float"),
    "look.phase": ("Palette phase", "float"),
    "look.cycles": ("Palette cycles", "float"),
    "look.gamma": ("Gamma", "float"),
    "look.brightness": ("Brightness", "float"),
    "look.contrast": ("Contrast", "float"),
    "look.percentile": ("Percentile", "float"),
    "look.depth_cue": ("Depth cue", "float"),
    "look.bands": ("Plasma bands", "float"),
    "look.glow": ("Glow", "float"),
    "look.solid_threshold": ("Solid threshold", "float"),
    "look.gradient": ("Gradient", "gradient"),
    "look.background.color": ("Background colour", "color"),
    "look.light.azimuth": ("Light azimuth", "float"),
    "look.light.elevation": ("Light elevation", "float"),
    "quality.dt": ("dt", "float"),
    "quality.points_per_pixel": ("Points per pixel", "float"),
}


@dataclass(frozen=True)
class Keyframe:
    time: float
    value: Any
    easing: str = "smooth"  # easing *into* the next key
    bezier: tuple[float, float, float, float] | None = None


@dataclass
class Track:
    path: str
    keys: list[Keyframe] = field(default_factory=list)

    @property
    def kind(self) -> str:
        if self.path.startswith("params."):
            return "float"
        return ANIMATABLE.get(self.path, ("", "float"))[1]

    @property
    def label(self) -> str:
        if self.path.startswith("params."):
            return self.path.split(".", 1)[1]
        return ANIMATABLE.get(self.path, (self.path, ""))[0]

    def sorted(self) -> None:
        self.keys.sort(key=lambda k: k.time)

    def set_key(self, time: float, value: Any, easing: str | None = None, tol: float = 1e-6) -> Keyframe:
        for i, k in enumerate(self.keys):
            if abs(k.time - time) <= tol:
                nk = replace(k, value=value, easing=easing or k.easing)
                self.keys[i] = nk
                return nk
        nk = Keyframe(time, value, easing or "smooth")
        self.keys.append(nk)
        self.sorted()
        return nk

    def remove_key_at(self, time: float, tol: float = 1e-6) -> bool:
        for i, k in enumerate(self.keys):
            if abs(k.time - time) <= tol:
                del self.keys[i]
                return True
        return False

    def value_at(self, t: float) -> Any:
        if not self.keys:
            return None
        times = [k.time for k in self.keys]
        if t <= times[0]:
            return self.keys[0].value
        if t >= times[-1]:
            return self.keys[-1].value
        i = bisect.bisect_right(times, t) - 1
        a, b = self.keys[i], self.keys[i + 1]
        span = b.time - a.time
        u = 0.0 if span <= 0 else (t - a.time) / span
        u = get_easing(a.easing, a.bezier)(u)
        return interpolate(self.kind, a.value, b.value, u)


def interpolate(kind: str, a: Any, b: Any, u: float) -> Any:
    if kind == "quat":
        return Q.slerp(tuple(a), tuple(b), u)
    if kind == "gradient":
        return blend_gradients(a if isinstance(a, Gradient) else Gradient.from_dict(a), b if isinstance(b, Gradient) else Gradient.from_dict(b), u)
    if kind == "color":
        return tuple(float(x + (y - x) * u) for x, y in zip(a, b, strict=True))
    if kind == "int":
        return int(round(a + (b - a) * u))
    return float(a + (b - a) * u)


def blend_gradients(a: Gradient, b: Gradient, u: float, n: int = 16) -> Gradient:
    """Stop-wise blend when the stop counts match, otherwise a resampled cross-fade."""
    if u <= 0:
        return a
    if u >= 1:
        return b
    if len(a.stops) == len(b.stops):
        stops = tuple(Stop(sa.pos + (sb.pos - sa.pos) * u, sa.r + (sb.r - sa.r) * u, sa.g + (sb.g - sa.g) * u,
                           sa.b + (sb.b - sa.b) * u, sa.a + (sb.a - sa.a) * u) for sa, sb in zip(a.stops, b.stops, strict=True))
        return Gradient(stops, a.space, a.cyclic, a.name)
    la, lb = a.lut(n), b.lut(n)
    lut = la * (1 - u) + lb * u
    stops = tuple(Stop(i / (n - 1), float(c[0]), float(c[1]), float(c[2]), float(c[3])) for i, c in enumerate(lut))
    return Gradient(stops, "rgb", a.cyclic, f"{a.name}→{b.name}")


# ── dotted-path access on the frozen settings tree ────────────────────────────


def get_path(settings: RenderSettings, path: str) -> Any:
    if path.startswith("params."):
        return settings.param_dict.get(path.split(".", 1)[1])
    obj: Any = settings
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def set_path(settings: RenderSettings, path: str, value: Any) -> RenderSettings:
    if path.startswith("params."):
        return settings.with_params(**{path.split(".", 1)[1]: float(value)})
    parts = path.split(".")
    return _set_rec(settings, parts, value)


def _set_rec(obj: Any, parts: list[str], value: Any) -> Any:
    if len(parts) == 1:
        if parts[0] == "gradient" and isinstance(value, dict):
            value = Gradient.from_dict(value)
        if parts[0] == "rotation":
            value = tuple(float(v) for v in value)
        return replace(obj, **{parts[0]: value})
    child = getattr(obj, parts[0])
    return replace(obj, **{parts[0]: _set_rec(child, parts[1:], value)})


@dataclass
class Timeline:
    duration: float = 8.0
    fps: int = 30
    loop: str = "none"  # none | loop | pingpong
    tracks: dict[str, Track] = field(default_factory=dict)
    motion_blur: int = 1  # sub-frame samples
    lock_framing: bool = True

    @property
    def frame_count(self) -> int:
        return max(1, int(round(self.duration * self.fps)))

    def frame_time(self, i: int) -> float:
        return i / self.fps

    def track(self, path: str) -> Track:
        if path not in self.tracks:
            self.tracks[path] = Track(path)
        return self.tracks[path]

    def set_key(self, path: str, time: float, value: Any, easing: str | None = None) -> Keyframe:
        return self.track(path).set_key(time, _storable(value), easing)

    def remove_empty(self) -> None:
        for p in [p for p, tr in self.tracks.items() if not tr.keys]:
            del self.tracks[p]

    def key_times(self) -> list[float]:
        return sorted({k.time for tr in self.tracks.values() for k in tr.keys})

    def evaluate(self, base: RenderSettings, t: float) -> RenderSettings:
        t = loop_time(t, self.duration, self.loop) if self.loop != "none" else t
        s = base
        for path, tr in self.tracks.items():
            if not tr.keys:
                continue
            v = tr.value_at(t)
            s = set_path(s, path, v)
        return s

    def key_all(self, settings: RenderSettings, time: float, paths: list[str] | None = None) -> None:
        paths = paths or [f"params.{k}" for k in settings.param_dict] + ["camera.rotation", "camera.zoom", "camera.pan_u", "camera.pan_v", "camera.perspective", "look.phase"]
        for p in paths:
            self.set_key(p, time, get_path(settings, p))

    # ── serialisation ──────────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return {
            "duration": self.duration, "fps": self.fps, "loop": self.loop, "motion_blur": self.motion_blur,
            "lock_framing": self.lock_framing,
            "tracks": {p: [{"time": k.time, "value": _storable(k.value), "easing": k.easing, "bezier": k.bezier} for k in tr.keys]
                       for p, tr in self.tracks.items()},
        }

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> Timeline:
        tl = Timeline()
        if not d:
            return tl
        tl.duration = float(d.get("duration", 8.0))
        tl.fps = int(d.get("fps", 30))
        tl.loop = d.get("loop", "none")
        tl.motion_blur = int(d.get("motion_blur", 1))
        tl.lock_framing = bool(d.get("lock_framing", True))
        for p, keys in d.get("tracks", {}).items():
            tr = Track(p, [Keyframe(float(k["time"]), _restore(p, k["value"]), k.get("easing", "smooth"),
                                    tuple(k["bezier"]) if k.get("bezier") else None) for k in keys])
            tr.sorted()
            tl.tracks[p] = tr
        return tl


def _storable(v: Any) -> Any:
    if isinstance(v, Gradient):
        return v.to_dict()
    if isinstance(v, tuple):
        return list(v)
    return v


def _restore(path: str, v: Any) -> Any:
    if path == "look.gradient" and isinstance(v, dict):
        return Gradient.from_dict(v)
    if isinstance(v, list):
        return tuple(v)
    return v
