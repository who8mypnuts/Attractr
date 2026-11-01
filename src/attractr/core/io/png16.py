"""Minimal 16-bit RGB/RGBA PNG writer with tEXt chunks (Pillow cannot write 16-bit colour)."""

from __future__ import annotations

import struct
import zlib

import numpy as np


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png16(path: str, img: np.ndarray, texts: dict[str, str] | None = None) -> None:
    """``img`` is uint16 [H, W, 3|4]."""
    assert img.dtype == np.uint16 and img.ndim == 3 and img.shape[2] in (3, 4)
    h, w, c = img.shape
    color_type = 6 if c == 4 else 2
    raw = img.astype(">u2").tobytes()
    stride = w * c * 2
    rows = bytearray()
    for y in range(h):
        rows.append(0)  # filter: none
        rows += raw[y * stride : (y + 1) * stride]
    out = bytearray(b"\x89PNG\r\n\x1a\n")
    out += _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 16, color_type, 0, 0, 0))
    for k, v in (texts or {}).items():
        out += _chunk(b"tEXt", k.encode("latin-1", "replace") + b"\x00" + v.encode("latin-1", "replace"))
    out += _chunk(b"IDAT", zlib.compress(bytes(rows), 6))
    out += _chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(out)
