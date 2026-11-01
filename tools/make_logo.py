"""Generate the Attractr logo: a real attractor orbit drawn with depth-banded glowing
strokes on a dark rounded tile, plus the geometric wordmark.

    python tools/make_logo.py [--concept lorenz|thomas|aizawa|all] [--out src/attractr/resources/logo]

Outputs: attractr_<size>.png (16…1024), attractr.ico, attractr.svg, wordmark.png,
concepts/<name>.png (concept sheets).  Pure Python + NumPy + Pillow — no Attractr engine
dependency, so branding can be regenerated anywhere.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BG_INNER = (24, 16, 64)
BG_OUTER = (8, 8, 16)
BANDS = [  # far → near (violet → cyan), matches the app accent colours
    (59, 30, 143), (91, 47, 209), (61, 90, 254), (33, 150, 243), (0, 184, 212), (79, 195, 247)
]
SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)

CONCEPTS = {
    # name: (deriv, params, dt, steps, warmup, yaw, pitch, roll, line width factor)
    "lorenz": ("lorenz", (10.0, 28.0, 8 / 3), 0.005, 3600, 3000, 12.0, 86.0, 0.0, 1.25),
    "thomas": ("thomas", (0.19,), 0.05, 9000, 2000, 35.0, 28.0, 0.0, 0.9),
    "aizawa": ("aizawa", (0.95, 0.7, 0.6, 3.5, 0.25, 0.1), 0.01, 7000, 3000, 40.0, 25.0, 0.0, 0.9),
}


def deriv(name: str, p: tuple, s: np.ndarray) -> np.ndarray:
    x, y, z = s
    if name == "lorenz":
        a, r, b = p
        return np.array([a * (y - x), x * (r - z) - y, x * y - b * z])
    if name == "thomas":
        (b,) = p
        return np.array([math.sin(y) - b * x, math.sin(z) - b * y, math.sin(x) - b * z])
    a, b, c, d, e, f = p
    return np.array([(z - b) * x - d * y, d * x + (z - b) * y,
                     c + a * z - z**3 / 3 - (x * x + y * y) * (1 + e * z) + f * z * x**3])


def orbit(name: str, p: tuple, dt: float, steps: int, warmup: int) -> np.ndarray:
    s = np.array([0.1, 0.0, 0.0]) if name != "thomas" else np.array([1.1, 1.1, -0.01])
    out = np.empty((steps, 3))
    for i in range(warmup + steps):
        k1 = deriv(name, p, s)
        k2 = deriv(name, p, s + 0.5 * dt * k1)
        k3 = deriv(name, p, s + 0.5 * dt * k2)
        k4 = deriv(name, p, s + dt * k3)
        s = s + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        if i >= warmup:
            out[i - warmup] = s
    return out


def rotation(yaw: float, pitch: float, roll: float) -> np.ndarray:
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    cr, sr = math.cos(math.radians(roll)), math.sin(math.radians(roll))
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    Rz = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]])
    return Rz @ Rx @ Ry


def project(pts: np.ndarray, yaw: float, pitch: float, roll: float, size: int, fit: float = 0.36):
    c = (pts.min(0) + pts.max(0)) / 2
    q = (pts - c) @ rotation(yaw, pitch, roll).T
    r = np.abs(q[:, :2]).max()
    xy = q[:, :2] / r * size * fit + size / 2
    xy[:, 1] = size - xy[:, 1]
    depth = (q[:, 2] - q[:, 2].min()) / max(np.ptp(q[:, 2]), 1e-9)
    return xy, depth


def radial_tile(size: int, radius_frac: float = 0.22) -> Image.Image:
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    d = np.sqrt((x - size / 2) ** 2 + (y - size * 0.45) ** 2) / (size * 0.7)
    t = np.clip(d, 0, 1)[..., None]
    rgb = np.array(BG_INNER) * (1 - t) + np.array(BG_OUTER) * t
    img = Image.fromarray(rgb.astype(np.uint8), "RGB").convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * radius_frac), fill=255)
    img.putalpha(mask)
    return img


def draw_orbit(img: Image.Image, xy: np.ndarray, depth: np.ndarray, width_factor: float) -> Image.Image:
    size = img.size[0]
    ss = 2
    big = Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))
    glow = Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))
    d, g = ImageDraw.Draw(big), ImageDraw.Draw(glow)
    order = np.argsort(depth)  # far first so near strokes paint on top
    nb = len(BANDS)
    base_w = size * ss * 0.0065 * width_factor
    segs = [(i, i + 1) for i in range(len(xy) - 1)]
    band_of = np.minimum((depth * nb).astype(int), nb - 1)
    for band in range(nb):
        col = BANDS[band]
        w = base_w * (0.6 + 0.8 * band / (nb - 1))
        for i, j in segs:
            if band_of[i] != band:
                continue
            p0, p1 = xy[i] * ss, xy[j] * ss
            g.line([tuple(p0), tuple(p1)], fill=(*col, 110), width=int(w * 3.2))
            d.line([tuple(p0), tuple(p1)], fill=(*col, 255), width=max(1, int(w)))
    _ = order
    glow = glow.filter(ImageFilter.GaussianBlur(size * ss * 0.012))
    out = Image.alpha_composite(img.resize((size * ss, size * ss), Image.LANCZOS), glow)
    out = Image.alpha_composite(out, big)
    return out.resize((size, size), Image.LANCZOS)


def make_mark(concept: str, size: int = 1024) -> Image.Image:
    name, p, dt, steps, warmup, yaw, pitch, roll, wf = CONCEPTS[concept]
    pts = orbit(name, p, dt, steps, warmup)
    xy, depth = project(pts, yaw, pitch, roll, size)
    return draw_orbit(radial_tile(size), xy, depth, wf)


def make_wordmark(mark: Image.Image, out: Path) -> None:
    h = 256
    m = mark.resize((h, h), Image.LANCZOS)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 150)
    except OSError:
        font = ImageFont.load_default()
    text = "Attractr"
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    tw = tmp.textlength(text, font=font)
    img = Image.new("RGBA", (int(h + 48 + tw + 40), h), (0, 0, 0, 0))
    img.alpha_composite(m, (0, 0))
    d = ImageDraw.Draw(img)
    # two-tone wordmark: "Attract" light, "r" accent
    x = h + 40
    d.text((x, h / 2), "Attract", font=font, fill=(236, 238, 245, 255), anchor="lm")
    x2 = x + tmp.textlength("Attract", font=font)
    d.text((x2, h / 2), "r", font=font, fill=(79, 195, 247, 255), anchor="lm")
    img.save(out / "wordmark.png")
    dark = Image.new("RGBA", img.size, (14, 14, 20, 255))
    dark.alpha_composite(img)
    dark.save(out / "wordmark_dark.png")


def make_svg(concept: str, out: Path, size: int = 512) -> None:
    name, p, dt, steps, warmup, yaw, pitch, roll, wf = CONCEPTS[concept]
    pts = orbit(name, p, dt, steps, warmup)
    xy, depth = project(pts, yaw, pitch, roll, size)
    nb = len(BANDS)
    band_of = np.minimum((depth * nb).astype(int), nb - 1)
    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {size} {size}' width='{size}' height='{size}'>",
             "<defs><radialGradient id='bg' cx='50%' cy='45%' r='70%'>"
             f"<stop offset='0' stop-color='rgb{BG_INNER}'/><stop offset='1' stop-color='rgb{BG_OUTER}'/></radialGradient></defs>",
             f"<rect width='{size}' height='{size}' rx='{size * 0.22:.0f}' fill='url(#bg)'/>"]
    for band in range(nb):
        col = BANDS[band]
        w = size * 0.0065 * wf * (0.6 + 0.8 * band / (nb - 1))
        runs: list[list[str]] = []
        cur: list[str] = []
        for i in range(len(xy) - 1):
            if band_of[i] == band:
                if not cur:
                    cur.append(f"M{xy[i][0]:.1f} {xy[i][1]:.1f}")
                cur.append(f"L{xy[i + 1][0]:.1f} {xy[i + 1][1]:.1f}")
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        dpath = " ".join("".join(r) for r in runs)
        if dpath:
            parts.append(f"<path d='{dpath}' fill='none' stroke='rgb{col}' stroke-width='{w * 3:.2f}' stroke-opacity='0.35' stroke-linecap='round'/>")
            parts.append(f"<path d='{dpath}' fill='none' stroke='rgb{col}' stroke-width='{w:.2f}' stroke-linecap='round'/>")
    parts.append("</svg>")
    (out / "attractr.svg").write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concept", default="lorenz", choices=[*CONCEPTS, "all"])
    ap.add_argument("--out", default="src/attractr/resources/logo")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "concepts").mkdir(exist_ok=True)
    names = list(CONCEPTS) if a.concept == "all" else [a.concept]
    marks = {}
    for n in names:
        marks[n] = make_mark(n, 512)
        marks[n].save(out / "concepts" / f"{n}.png")
        print("concept", n)
    chosen = names[0] if a.concept != "all" else "lorenz"
    mark = make_mark(chosen, 1024)
    for s in SIZES:
        mark.resize((s, s), Image.LANCZOS).save(out / f"attractr_{s}.png")
    mark.resize((256, 256), Image.LANCZOS).save(out / "attractr.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    make_svg(chosen, out)
    make_wordmark(mark, out)
    # contact sheet of the concepts
    if len(marks) > 1:
        sheet = Image.new("RGBA", (len(marks) * 532 + 20, 560), (14, 14, 20, 255))
        d = ImageDraw.Draw(sheet)
        for i, (n, m) in enumerate(marks.items()):
            sheet.alpha_composite(m, (20 + i * 532, 20))
            d.text((20 + i * 532 + 8, 540), n, fill=(200, 200, 220, 255))
        sheet.save(out / "concepts" / "sheet.png")
    print("wrote logo to", out)


if __name__ == "__main__":
    main()
