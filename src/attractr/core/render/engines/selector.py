"""Engine registry + selection policy (probing happens lazily, once per process)."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from attractr.core.render.engines.base import Engine, EngineCaps

log = logging.getLogger(__name__)

_factories: dict[str, Callable[[], Engine]] = {}
_instances: dict[str, Engine] = {}
_caps: dict[str, EngineCaps] = {}
_lock = threading.Lock()

PREVIEW_ORDER = ("gl_compute", "gl_points", "opencl", "cpu")
FINAL_ORDER = ("gl_precision", "opencl", "cpu")


def register(engine_id: str, factory: Callable[[], Engine]) -> None:
    _factories[engine_id] = factory


def engine_ids() -> list[str]:
    return list(_factories)


def get_engine(engine_id: str) -> Engine:
    with _lock:
        if engine_id not in _instances:
            if engine_id not in _factories:
                raise KeyError(f"unknown engine {engine_id!r}; available: {', '.join(_factories)}")
            _instances[engine_id] = _factories[engine_id]()
        return _instances[engine_id]


def probe(engine_id: str) -> EngineCaps:
    if engine_id in _caps:
        return _caps[engine_id]
    try:
        caps = get_engine(engine_id).probe()
    except Exception as exc:  # noqa: BLE001 — a broken driver must never crash the app
        log.warning("engine %s unavailable: %s", engine_id, exc)
        caps = EngineCaps(engine_id, engine_id, available=False, notes=[str(exc)])
    _caps[engine_id] = caps
    return caps


def probe_all() -> dict[str, EngineCaps]:
    return {eid: probe(eid) for eid in _factories}


def select(engine_id: str = "auto", purpose: str = "final") -> Engine:
    """Resolve ``auto`` to the best available engine for ``purpose`` (preview|final)."""
    if engine_id != "auto":
        caps = probe(engine_id)
        if caps.available:
            return get_engine(engine_id)
        log.warning("engine %s not available (%s); falling back", engine_id, "; ".join(caps.notes))
    order = PREVIEW_ORDER if purpose == "preview" else FINAL_ORDER
    for eid in order:
        if eid in _factories and probe(eid).available:
            return get_engine(eid)
    return get_engine("cpu")


def _register_builtin() -> None:
    from attractr.core.render.engines.cpu_numba import CpuEngine

    register("cpu", CpuEngine)
    try:
        from attractr.core.render.engines import gl_engines  # noqa: F401  (registers itself)
    except Exception as exc:  # noqa: BLE001
        log.info("GL engines not registered: %s", exc)
    try:
        from attractr.core.render.engines import opencl_engine  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        log.info("OpenCL engine not registered: %s", exc)


_register_builtin()
