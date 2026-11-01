"""Attractor of the Day: a date-seeded, validated variation of a curated preset
(same result on every machine for the same date — no backend)."""

from __future__ import annotations

import random
from datetime import date

from attractr.core.project.presets import Preset, presets
from attractr.core.render.settings import RenderSettings

PARAM_JITTER = 0.05


def daily_seed(day: date | None = None) -> int:
    d = day or date.today()
    return d.year * 10000 + d.month * 100 + d.day


def daily_candidate(day: date | None = None, attempt: int = 0) -> tuple[Preset, RenderSettings]:
    from dataclasses import replace

    from attractr.core.attractors.registry import registry
    from attractr.core.color.palettes import palettes
    from attractr.core.render.settings import STYLES

    rng = random.Random(daily_seed(day) + attempt)
    base = rng.choice(presets.curated())
    spec = registry.get(base.attractor)
    s = base.apply()
    vals = dict(s.param_dict)
    for p in spec.params:
        if p.is_int:
            continue
        vals[p.name] = p.clamp(vals.get(p.name, p.default) + (rng.random() * 2 - 1) * PARAM_JITTER * p.span)
    s = s.with_param_dict(vals)
    pid = rng.choice([i for i in palettes.ids() if i not in ("light",)])
    style = rng.choice([st for st in STYLES if st != "solid"])
    look = replace(s.look, gradient=palettes.get(pid), style=style)
    cam = s.camera
    if spec.is_3d:
        yaw, pitch, roll = cam.euler
        cam = cam.with_euler(yaw + rng.uniform(-20, 20), max(-90, min(90, pitch + rng.uniform(-10, 10))), roll)
    s = replace(s, look=look, camera=cam)
    name = f"{base.name} · {date.today():%d %b}" if day is None else f"{base.name} · {day:%d %b}"
    return Preset(name, base.attractor, vals, base.camera, pid, style, None, "daily"), s


def daily(day: date | None = None, validate: bool = True) -> tuple[Preset, RenderSettings]:
    """Return today's preset; when ``validate`` is set, skip candidates whose quick probe
    says they are divergent/periodic (up to 5 attempts)."""
    for attempt in range(5 if validate else 1):
        preset, s = daily_candidate(day, attempt)
        if not validate:
            return preset, s
        try:
            from attractr.core.analysis.probe import probe
            from attractr.core.attractors.registry import registry

            r = probe(registry.get(preset.attractor), s.param_dict, s.quality.dt, steps=3000)
            if r.classification == "chaotic":
                return preset, s
        except Exception:  # noqa: BLE001
            continue
    return daily_candidate(day, 0)
