"""Persistent helper-process server used by the GUI through QProcess.

Heavy CPU work that would otherwise hold the GIL inside the GUI process (numba
compilation, thumbnail renders, Lyapunov probes, the daily attractor) runs here.

Protocol — one request per line on stdin, one reply per line on stdout (tab separated)::

    THUMB  <key>\\t<size>\\t<settings-json>      →  THUMB <key> <png-path>
    PROBE  <token>\\t<settings-json>             →  PROBE <token> <json: probe result>
    DAILY  <token>                                →  DAILY <token> <json: {preset, settings}>
    QUIT

Errors are reported as ``ERR <token> <message>``.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace

from attractr.core.io.paths import cache_dir
from attractr.core.render.develop.developer import develop
from attractr.core.render.engines import selector
from attractr.core.render.pipeline import resolve_spec
from attractr.core.render.settings import RenderSettings


def render_thumb(settings: RenderSettings, size: int, ppp: float = 6.0):
    q = replace(settings.quality, width=size, height=size, points_per_pixel=ppp, supersample=1, splat_radius=0)
    s = replace(settings, quality=q)
    spec = resolve_spec(s)
    try:
        result = selector.select("auto", "preview", spec).accumulate(s, spec)
    except Exception:  # noqa: BLE001
        result = selector.get_engine("cpu").accumulate(s, spec)
    return develop(result, s.look)


def handle(cmd: str, arg: str, out_dir) -> str:
    from attractr.core.io.image_export import to_pil

    if cmd == "THUMB":
        key, size, payload = arg.split("\t", 2)
        settings = RenderSettings.from_dict(json.loads(payload))
        dev = render_thumb(settings, int(size))
        path = out_dir / f"{key}_{size}.png"
        to_pil(dev, settings.look.background.mode == "transparent").save(path)
        return f"THUMB\t{key}\t{path}"
    if cmd == "PROBE":
        token, payload = arg.split("\t", 1)
        settings = RenderSettings.from_dict(json.loads(payload))
        from attractr.core.analysis.probe import probe

        spec = resolve_spec(settings)
        r = probe(spec, settings.param_dict, settings.quality.dt, steps=4000)
        return f"PROBE\t{token}\t" + json.dumps(
            {"lyapunov": r.lyapunov, "classification": r.classification, "dimension": r.box_dimension, "radius": r.radius}
        )
    if cmd == "DAILY":
        from attractr.core.analysis.daily import daily

        preset, settings = daily()
        return f"DAILY\t{arg}\t" + json.dumps({"preset": preset.to_dict(), "settings": settings.to_dict()})
    raise ValueError(f"unknown command {cmd!r}")


def main() -> int:
    import contextlib
    import os

    with contextlib.suppress(Exception):  # be a good neighbour to the GUI process
        os.nice(10)
    out_dir = cache_dir("thumbs")
    print("READY", flush=True)
    for line in sys.stdin:
        line = line.rstrip("\n")
        if not line:
            continue
        if line == "QUIT":
            break
        cmd, _, arg = line.partition("\t")
        token = arg.split("\t", 1)[0]
        try:
            print(handle(cmd, arg, out_dir), flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"ERR\t{token}\t{type(exc).__name__}: {exc}", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
