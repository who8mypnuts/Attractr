"""Background photo loader (centre-crop 'cover' fit)."""

from __future__ import annotations

import numpy as np
from PIL import Image


def load_cover(path: str, width: int, height: int) -> np.ndarray:
    img = Image.open(path).convert("RGB")
    sw, sh = img.size
    scale = max(width / sw, height / sh)
    nw, nh = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - width) // 2, (nh - height) // 2
    img = img.crop((left, top, left + width, top + height))
    return np.asarray(img, dtype=np.float32) / 255.0
