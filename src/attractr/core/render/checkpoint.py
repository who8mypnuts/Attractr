"""Render checkpoints: the accumulation buffers of an unfinished render, saved as ``.npz``
so a long render can survive a crash, a reboot or an impatient user and be resumed later
(``attractr render --resume FILE`` / Render → Resume from checkpoint…).

A checkpoint is taken from a *partial* :class:`RenderResult` (output resolution — the
supersampled buffers are already box-filtered down) and records how much of the budget it
contains.  Two shapes exist:

* **uniform** (``tiles_done == 0``): every pixel has ``iterations_done`` points' worth of
  accumulation — resuming renders the *remaining* budget with a fresh trajectory seed and
  adds the buffers;
* **tiled** (``tiles_done > 0``, precision GPU renders): the first ``tiles_done`` tiles are
  complete and the rest empty — resuming skips those tiles.

``segment`` counts how many times the render has been resumed; it offsets the trajectory
seed so a resumed segment never replays the random streams already accumulated.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from attractr.core.render.result import Framing, RenderResult, RenderStats
from attractr.core.render.settings import RenderSettings

FORMAT = 1
SUFFIX = ".attractr-ckpt.npz"


@dataclass
class Checkpoint:
    settings: RenderSettings
    framing: Framing
    count: np.ndarray
    depth_sum: np.ndarray | None
    zmin: np.ndarray | None
    cv_sum: np.ndarray | None
    iterations_done: int
    tiles_done: int = 0
    tiles: int = 1
    elapsed: float = 0.0
    engine: str = ""
    segment: int = 1

    # ── construction ───────────────────────────────────────────────────────────
    @staticmethod
    def from_result(result: RenderResult, segment: int = 1) -> Checkpoint:
        st = result.stats
        return Checkpoint(
            result.settings, result.framing, result.count, result.depth_sum, result.zmin, result.cv_sum,
            int(st.iterations_done), int(getattr(st, "tiles_done", 0)), int(st.tiles), float(st.accumulate_seconds),
            st.engine, segment,
        )

    @property
    def uniform(self) -> bool:
        return self.tiles_done == 0

    @property
    def fraction(self) -> float:
        """Share of the requested budget already accumulated."""
        if not self.uniform:
            return self.tiles_done / max(self.tiles, 1)
        return min(1.0, self.iterations_done / max(self.settings.quality.iterations, 1))

    # ── persistence ────────────────────────────────────────────────────────────
    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "format": FORMAT,
            "settings": self.settings.to_dict(),
            "framing": _framing_to_dict(self.framing),
            "iterations_done": self.iterations_done,
            "tiles_done": self.tiles_done,
            "tiles": self.tiles,
            "elapsed": self.elapsed,
            "engine": self.engine,
            "segment": self.segment,
        }
        arrays = {"count": self.count}
        for name in ("depth_sum", "zmin", "cv_sum"):
            a = getattr(self, name)
            if a is not None:
                arrays[name] = a
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "wb") as fh:
            np.savez(fh, meta=np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8), **arrays)
        tmp.replace(path)
        return path

    @staticmethod
    def load(path: str | Path) -> Checkpoint:
        with np.load(path) as z:
            meta = json.loads(bytes(z["meta"]).decode())
            if meta.get("format") != FORMAT:
                raise ValueError(f"unsupported checkpoint format {meta.get('format')}")
            get = lambda k: z[k] if k in z.files else None  # noqa: E731
            return Checkpoint(
                RenderSettings.from_dict(meta["settings"]), _framing_from_dict(meta["framing"]),
                z["count"], get("depth_sum"), get("zmin"), get("cv_sum"),
                int(meta["iterations_done"]), int(meta["tiles_done"]), int(meta["tiles"]),
                float(meta["elapsed"]), str(meta["engine"]), int(meta["segment"]),
            )

    # ── merging into a fresh accumulation ──────────────────────────────────────
    def merge_into(self, result: RenderResult, final: bool = True) -> None:
        """Add this checkpoint's buffers (and bookkeeping) to ``result`` in place.  For
        partial results (``final=False``) the stats object is copied first, because engines
        reuse one stats instance across all the partials they emit."""
        if result.count.shape != self.count.shape:
            raise ValueError(f"checkpoint size {self.count.shape[::-1]} ≠ render size {result.count.shape[::-1]}")
        result.count += self.count
        if result.depth_sum is not None and self.depth_sum is not None:
            result.depth_sum += self.depth_sum
        if result.zmin is not None and self.zmin is not None:
            np.minimum(result.zmin, self.zmin, out=result.zmin)
        if result.cv_sum is not None and self.cv_sum is not None:
            result.cv_sum += self.cv_sum
        st: RenderStats = result.stats
        if not final:
            st = copy.copy(st)
            st.notes = list(st.notes)
            result.stats = st
        if self.uniform:
            st.iterations_done += self.iterations_done
        st.accumulate_seconds += self.elapsed
        st.elapsed += self.elapsed
        st.notes.append(
            f"Resumed from a checkpoint (segment {self.segment + 1}): {self.iterations_done / 1e6:.1f} M points "
            f"/ {self.tiles_done} of {self.tiles} tiles were already accumulated."
        )

    def next_settings(self) -> RenderSettings:
        """Settings for the resumed segment: identical quality, the same camera."""
        return replace(self.settings)


def _framing_to_dict(f: Framing) -> dict:
    return {
        "center": list(f.center), "radius": f.radius, "bbox_min": list(f.bbox_min), "bbox_max": list(f.bbox_max),
        "fit_zoom": f.fit_zoom, "fit_pan": list(f.fit_pan),
    }


def _framing_from_dict(d: dict) -> Framing:
    return Framing(tuple(d["center"]), float(d["radius"]), tuple(d["bbox_min"]), tuple(d["bbox_max"]),
                   float(d.get("fit_zoom", 1.0)), tuple(d.get("fit_pan", (0.0, 0.0))))


def checkpoint_path(out_dir: Path, stem: str) -> Path:
    return out_dir / "checkpoints" / f"{stem}{SUFFIX}"


def list_checkpoints(out_dir: Path) -> list[Path]:
    d = out_dir / "checkpoints"
    return sorted(d.glob(f"*{SUFFIX}"), key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []
