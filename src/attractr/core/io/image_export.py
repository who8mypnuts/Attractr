"""Write developed images to disk (PNG 8/16-bit, JPEG, WebP, TIFF) with metadata."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, PngImagePlugin

from attractr.core.io.png16 import write_png16
from attractr.core.render.develop.developer import Developed

FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP", ".tif": "TIFF", ".tiff": "TIFF"}


def save_image(dev: Developed, path: str | Path, bit_depth: int = 8, transparent: bool = False,
               texts: dict[str, str] | None = None, dither: bool = True, quality: int = 95) -> Path:
    path = Path(path)
    fmt = FORMATS.get(path.suffix.lower())
    if fmt is None:
        raise ValueError(f"unsupported image format {path.suffix!r}")
    channels = 4 if transparent else 3
    if fmt == "PNG" and bit_depth == 16:
        arr = dev.to_uint16(dither)[..., :channels]
        write_png16(str(path), np.ascontiguousarray(arr), texts)
        return path
    arr = dev.to_uint8(dither)[..., :channels]
    img = Image.fromarray(np.ascontiguousarray(arr), "RGBA" if channels == 4 else "RGB")
    if fmt == "PNG":
        info = PngImagePlugin.PngInfo()
        for k, v in (texts or {}).items():
            info.add_text(k, v)
        img.save(path, format="PNG", pnginfo=info, compress_level=6)
    elif fmt == "JPEG":
        img.convert("RGB").save(path, format="JPEG", quality=quality, subsampling=0)
    elif fmt == "WEBP":
        img.save(path, format="WEBP", quality=quality)
    else:
        img.save(path, format="TIFF")
    return path


def to_pil(dev: Developed, transparent: bool = False) -> Image.Image:
    arr = dev.to_uint8(False)[..., : (4 if transparent else 3)]
    return Image.fromarray(np.ascontiguousarray(arr), "RGBA" if transparent else "RGB")
