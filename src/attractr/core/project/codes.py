"""Shareable text codes.

* ``ATR1:<base64url(zlib(json))>`` — full Attractr settings (our own format).
* ``CHS1:<base64url(pipe-string)>`` — Chaoscope (Android) preset codes, imported for
  compatibility (attractor/palette/style names mapped to Attractr equivalents).
"""

from __future__ import annotations

import base64
import json
import re
import zlib

from attractr.core.render.camera import Camera
from attractr.core.render.settings import Look, Quality, RenderSettings

PREFIX = "ATR1:"
CHS_PREFIX = "CHS1:"


def settings_to_code(settings: RenderSettings) -> str:
    payload = json.dumps(settings.to_dict(), separators=(",", ":")).encode()
    return PREFIX + base64.urlsafe_b64encode(zlib.compress(payload, 9)).decode().rstrip("=")


def settings_from_code(text: str) -> RenderSettings | None:
    """Decode the first code found anywhere in ``text`` (ATR1 or CHS1); None if absent."""
    m = re.search(r"ATR1:([A-Za-z0-9_-]+)", text)
    if m:
        token = m.group(1)
        token += "=" * (-len(token) % 4)
        try:
            payload = zlib.decompress(base64.urlsafe_b64decode(token))
            return RenderSettings.from_dict(json.loads(payload))
        except Exception:  # noqa: BLE001
            return None
    m = re.search(r"CHS1:([A-Za-z0-9_-]+)", text)
    if m:
        return chs1_to_settings(m.group(1))
    return None


# ── Chaoscope (Android) compatibility ───────────────────────────────────────────

_CHS_ATTRACTORS = {
    "CLIFFORD": "clifford", "PETER_DE_JONG": "de_jong", "GUMOWSKI_MIRA": "gumowski_mira",
    "LORENZ": "lorenz", "ROSSLER": "rossler", "AIZAWA": "aizawa", "THOMAS": "thomas",
    "CHAOTIC_FLOW": "dadras", "ICON": "symmetric_icon", "IFS": "barnsley_fern", "JULIA": "julia_quaternion",
    "PICKOVER": "pickover", "HALVORSEN": "halvorsen", "BURKE_SHAW": "burke_shaw", "SPROTT_B": "sprott_b",
    "LORENZ_84": "lorenz84", "HENON": "henon",
}
_CHS_PALETTES = {
    "NEBULA": "nebula", "FIRE": "fire", "ELECTRIC": "electric", "AURORA": "aurora", "MATRIX": "matrix",
    "GREYSCALE": "greyscale", "SPECTRUM": "spectrum", "SUNSET": "sunset", "ICE": "ice", "NEON": "neon",
    "CUSTOM": "nebula",
}
_CHS_STYLES = {"STANDARD": "gas", "GAS": "dust", "LIQUID": "liquid", "PLASMA": "plasma", "SOLID": "solid", "LIGHT": "light"}
# Android param order per attractor → Attractr names (dt entries become integrator dt)
_CHS_PARAMS = {
    "CLIFFORD": ["a", "b", "c", "d", "e", "f"], "PETER_DE_JONG": ["a", "b", "c", "d", "e", "f"],
    "GUMOWSKI_MIRA": ["a", "mu"], "LORENZ": ["sigma", "rho", "beta", "dt"], "ROSSLER": ["a", "b", "c", "dt"],
    "AIZAWA": ["a", "b", "c", "d", "e", "f", "dt"], "THOMAS": ["b", "dt"], "CHAOTIC_FLOW": ["a", "b", "c", "d", "e", "dt"],
    "ICON": ["lam", "al", "be", "ga"], "IFS": ["width", "lean", "twist"], "JULIA": ["c_re", "c_im", "c_j"],
    "PICKOVER": ["a", "b", "c", "d"], "HALVORSEN": ["a", "dt"], "BURKE_SHAW": ["s", "v", "dt"],
    "SPROTT_B": ["a", "b", "dt"], "LORENZ_84": ["a", "b", "F", "G", "dt"], "HENON": ["a", "b"],
}


def chs1_to_settings(token: str) -> RenderSettings | None:
    """``name|TYPE|p0,p1,..|yaw|pitch|roll|zoom|PALETTE|STYLE|BG``"""
    try:
        token += "=" * (-len(token) % 4)
        text = base64.urlsafe_b64decode(token).decode("utf-8")
        f = text.split("|")
        if len(f) < 10:
            return None
        atype = f[1]
        aid = _CHS_ATTRACTORS.get(atype)
        if aid is None:
            return None
        values = [float(v) for v in f[2].split(",") if v.strip()]
        names = _CHS_PARAMS.get(atype, [])
        params: dict[str, float] = {}
        dt = None
        for n, v in zip(names, values, strict=False):
            if n == "dt":
                dt = v
            else:
                params[n] = v
        yaw, pitch, roll, zoom = (float(v) for v in f[3:7])
        from attractr.core.color.palettes import palettes

        grad = palettes.get(_CHS_PALETTES.get(f[7], "nebula"))
        bg_white = f[9] == "WHITE"
        look = Look(style=_CHS_STYLES.get(f[8], "gas"), gradient=grad)
        if bg_white:
            from dataclasses import replace

            look = replace(look, background=replace(look.background, color=(1.0, 1.0, 1.0)))
        return RenderSettings(
            attractor=aid,
            params=tuple(params.items()),
            camera=Camera.from_euler(yaw, pitch, roll, zoom=zoom),
            quality=Quality(dt=dt, integrator="euler" if dt else "rk4"),
            look=look,
        )
    except Exception:  # noqa: BLE001
        return None
