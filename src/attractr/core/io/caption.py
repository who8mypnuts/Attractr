"""Caption overlay: attractor name, formula and parameters drawn onto an exported image
(the WebGL experiment's 'infos' block)."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.render.settings import RenderSettings

FONT_CANDIDATES = ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "DejaVuSansMono.ttf", "Menlo.ttc", "consola.ttf")


def caption_lines(spec: AttractorSpec, settings: RenderSettings) -> list[str]:
    vals = settings.param_dict
    lines = [spec.name]
    lines += spec.formula_text()
    if spec.params:
        lines.append("  ".join(f"{p.name} = {vals.get(p.name, p.default):.4g}" for p in spec.params))
    return lines


def _font(size: int):
    for c in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_caption(img: Image.Image, spec: AttractorSpec, settings: RenderSettings, light_text: bool = True) -> Image.Image:
    lines = caption_lines(spec, settings)
    size = max(11, int(img.height * 0.016))
    font = _font(size)
    title_font = _font(int(size * 1.4))
    d = ImageDraw.Draw(img, "RGBA")
    pad = int(size * 0.8)
    lh = int(size * 1.35)
    h = lh * (len(lines) - 1) + int(size * 1.9) + 2 * pad
    w = max(d.textlength(t, font=font) for t in lines[1:]) if len(lines) > 1 else 0
    w = int(max(w, d.textlength(lines[0], font=title_font)) + 2 * pad)
    x0, y0 = pad, img.height - h - pad
    bg = (0, 0, 0, 120) if light_text else (255, 255, 255, 140)
    fg = (235, 238, 245, 255) if light_text else (20, 20, 28, 255)
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=int(size * 0.6), fill=bg)
    d.text((x0 + pad, y0 + pad), lines[0], font=title_font, fill=(79, 195, 247, 255) if light_text else (20, 60, 120, 255))
    y = y0 + pad + int(size * 1.9)
    for t in lines[1:]:
        d.text((x0 + pad, y), t, font=font, fill=fg)
        y += lh
    return img
