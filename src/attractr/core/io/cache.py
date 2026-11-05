"""Bounded on-disk caches: delete the least recently used files once a folder exceeds
its budget (thumbnails of edited user formulas are keyed by content hash, so the
thumbnail cache would otherwise grow without limit)."""

from __future__ import annotations

import os
from pathlib import Path


def folder_size(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.glob("*") if p.is_file()) if folder.is_dir() else 0


def prune(folder: Path, max_bytes: int, keep_fraction: float = 0.8) -> int:
    """Remove the oldest files (by modification time) until the folder is below
    ``keep_fraction × max_bytes``. Returns the number of files removed; ``max_bytes <= 0``
    disables pruning."""
    if max_bytes <= 0 or not folder.is_dir():
        return 0
    files = [(p.stat().st_mtime, p.stat().st_size, p) for p in folder.glob("*") if p.is_file()]
    total = sum(sz for _, sz, _ in files)
    if total <= max_bytes:
        return 0
    target = max_bytes * keep_fraction
    removed = 0
    for _, sz, p in sorted(files):
        if total <= target:
            break
        try:
            os.remove(p)
            total -= sz
            removed += 1
        except OSError:
            continue
    return removed
