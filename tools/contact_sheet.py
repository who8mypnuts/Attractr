"""Render every registered attractor at low resolution into one contact sheet.

Usage: python tools/contact_sheet.py [--size 256] [--ppp 6] [--engine cpu] [-o docs/images/contact_sheet.png]
"""

from __future__ import annotations

import argparse
import math
import time

from PIL import Image, ImageDraw

from attractr.core.attractors.registry import registry
from attractr.core.io.image_export import to_pil
from attractr.core.render.pipeline import default_settings, render
from attractr.core.render.settings import Quality


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--ppp", type=float, default=6.0)
    ap.add_argument("--engine", default="cpu")
    ap.add_argument("--only", default="")
    ap.add_argument("-o", "--output", default="docs/images/contact_sheet.png")
    a = ap.parse_args()
    registry.load()
    specs = [s for s in registry.all() if not a.only or a.only in s.id]
    cols = math.ceil(math.sqrt(len(specs)))
    rows = math.ceil(len(specs) / cols)
    S = a.size
    sheet = Image.new("RGB", (cols * S, rows * S), (10, 10, 14))
    draw = ImageDraw.Draw(sheet)
    for i, spec in enumerate(specs):
        t = time.perf_counter()
        settings = default_settings(spec, Quality(width=S, height=S, points_per_pixel=a.ppp))
        try:
            result, dev = render(settings, engine=a.engine)
            img = to_pil(dev)
            note = f"{result.stats.coverage*100:.0f}% {result.stats.accumulate_seconds:.1f}s"
        except Exception as exc:  # noqa: BLE001
            img = Image.new("RGB", (S, S), (60, 0, 0))
            note = f"ERR {type(exc).__name__}"
        x, y = (i % cols) * S, (i // cols) * S
        sheet.paste(img, (x, y))
        draw.text((x + 4, y + 4), f"{spec.name}", fill=(230, 230, 230))
        draw.text((x + 4, y + S - 14), note, fill=(160, 160, 160))
        print(f"{spec.id:24s} {note}  ({time.perf_counter() - t:.1f}s)")
    sheet.save(a.output)
    print("wrote", a.output)


if __name__ == "__main__":
    main()
