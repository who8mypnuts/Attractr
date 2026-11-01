"""Immutable settings objects that flow through the whole program.

* :class:`Quality`  — *accumulation* settings (changing any of them re-iterates)
* :class:`Look`     — *development* settings (changing them only re-develops)
* :class:`RenderSettings` — attractor + params + camera + quality + look

Every field has a default so a settings object can always be built incrementally; the GUI,
the CLI flags, the JSON schema, the undo stack and the render report all derive from these
definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from attractr.core.color.gradient import Gradient, Stop
from attractr.core.project.serialize import fields_from_dict, fields_to_dict
from attractr.core.render.camera import Camera

STYLES = ("gas", "dust", "light", "liquid", "solid", "plasma")
COLOR_SOURCES = ("density", "x", "y", "z", "depth", "speed", "radius", "index", "curvature", "formula")
INTEGRATORS = ("rk4", "rk2", "euler")
BACKGROUND_MODES = ("solid", "transparent", "gradient", "image", "procedural")
PROCEDURAL_BACKGROUNDS = ("stars", "forest", "ocean", "aurora")
REPORT_FORMATS = ("md", "txt", "html", "pdf")


@dataclass(frozen=True)
class Quality:
    width: int = 1024
    height: int = 1024
    points_per_pixel: float = 12.0  # iterations = ppp · width · height
    supersample: int = 1  # 1..4 — accumulation at (ss·W) × (ss·H), box-filtered down
    splat_radius: int = 0  # 0 = bilinear anti-aliased sub-pixel splat; 1..4 = soft disk
    gap_fill: bool = True  # interpolate between consecutive points (flows only)
    integrator: str = "rk4"  # rk4 | rk2 | euler   (ignored for maps)
    dt: float | None = None  # None → attractor default
    substeps: int = 1  # integrator steps per plotted point
    warmup: int | None = None  # None → attractor default
    trajectories: int = 0  # 0 → engine default
    seed: int = 1
    engine: str = "auto"  # auto | cpu | gl_compute | gl_points | gl_precision | opencl
    precision: str = "auto"  # auto | fp32 | fp64  (GPU engines)

    @property
    def iterations(self) -> int:
        return int(round(self.points_per_pixel * self.width * self.height))

    def with_size(self, width: int, height: int) -> Quality:
        return replace(self, width=int(width), height=int(height))


@dataclass(frozen=True)
class Light:
    azimuth: float = 135.0  # degrees, 0 = right, 90 = top
    elevation: float = 45.0  # degrees above the image plane
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    ambient: float = 0.25
    diffuse: float = 0.75
    specular: float = 0.35
    shininess: float = 24.0


@dataclass(frozen=True)
class Background:
    mode: str = "solid"  # solid | transparent | gradient | image | procedural
    color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    color2: tuple[float, float, float] = (0.05, 0.02, 0.12)  # gradient end
    image_path: str | None = None
    procedural: str = "stars"
    seed: int = 7


@dataclass(frozen=True)
class Look:
    style: str = "gas"
    color_source: str = "density"
    gradient: Gradient = field(default_factory=lambda: default_gradient())
    percentile: float = 0.998  # density percentile mapped to full brightness
    gamma: float = 1.0
    brightness: float = 1.0
    contrast: float = 0.0  # -1..1 S-curve strength
    equalize: bool = False  # histogram equalisation ("Full range")
    invert: bool = False  # light-on-dark ⇄ dark-on-light
    phase: float = 0.0  # palette rotation 0..1
    cycles: float = 1.0  # palette repeats
    bands: float = 4.0  # plasma density bands
    glow: float = 0.0  # plasma/light bloom amount 0..1
    depth_cue: float = 0.5  # 0 flat … 1 strong far-attenuation (liquid / depth shading)
    solid_threshold: float = 0.15  # solid: density below → background
    light: Light = field(default_factory=Light)
    background: Background = field(default_factory=Background)
    dither: bool = True
    caption: bool = False  # draw attractor name/formula/params onto the image


@dataclass(frozen=True)
class RenderSettings:
    attractor: str = "lorenz"  # attractor id (built-in or user)
    source: str | None = None  # inline .atr text for ad-hoc formulas
    params: tuple[tuple[str, float], ...] = ()
    camera: Camera = field(default_factory=Camera)
    quality: Quality = field(default_factory=Quality)
    look: Look = field(default_factory=Look)
    notes: str = ""

    # ── params helpers ─────────────────────────────────────────────────────────
    @property
    def param_dict(self) -> dict[str, float]:
        return dict(self.params)

    def with_params(self, **values: float) -> RenderSettings:
        d = self.param_dict
        d.update({k: float(v) for k, v in values.items()})
        return replace(self, params=tuple(d.items()))

    def with_param_dict(self, values: dict[str, float]) -> RenderSettings:
        return replace(self, params=tuple((k, float(v)) for k, v in values.items()))

    # ── (de)serialisation ──────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        d = fields_to_dict(self)
        d["params"] = self.param_dict
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> RenderSettings:
        d = dict(d)
        params = d.pop("params", {})
        if isinstance(params, dict):
            params = list(params.items())
        d["params"] = [[k, float(v)] for k, v in params]
        return fields_from_dict(RenderSettings, d)


def default_gradient() -> Gradient:
    """The 'Nebula' palette (Chaoscope default look)."""
    return Gradient(
        stops=(
            Stop.from_255(0.00, 0, 0, 0),
            Stop.from_255(0.25, 0, 20, 80),
            Stop.from_255(0.50, 20, 80, 200),
            Stop.from_255(0.75, 120, 180, 255),
            Stop.from_255(1.00, 255, 255, 255),
        ),
        name="Nebula",
    )
