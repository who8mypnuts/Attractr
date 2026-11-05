"""GPU development pass (OpenGL 4.3 compute) for large images.

The per-pixel styles (gas, dust, light, plasma) are evaluated by ``shaders/develop.comp``
with exactly the same formulas as the NumPy path; the handful of global scalars they need
(normaliser, colour-value and depth percentiles) are still computed on the CPU from a
strided subsample.  Anything the shader does not implement (liquid/solid lighting,
histogram equalisation, bloom, image/procedural backgrounds) returns ``None`` so the
caller falls back to the CPU developer.

The pass is opt-in per call through :func:`wanted` (large images only — for preview-sized
results the NumPy path is faster than the round trip) and switches itself off for the
process after the first OpenGL failure.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

from attractr.core.render.result import RenderResult
from attractr.core.render.settings import Look

log = logging.getLogger(__name__)

MIN_PIXELS = 1_500_000  # below this the CPU path wins
CHUNK_PIXELS = 4_000_000  # rows are processed in chunks so buffers stay < ~100 MB
STYLE_CODES = {"gas": 0, "dust": 1, "light": 2, "plasma": 3}
SUBSAMPLE = 7  # stride for the percentile estimates (prime, to dodge structured aliasing)

enabled = True  # preference toggle (GUI / CLI)
_lock = threading.Lock()
_failed = False
_ctx = None
_prog = None
_thread_id: int | None = None


def applicable(result: RenderResult, look: Look) -> bool:
    """True when the shader implements everything this look needs."""
    if look.style not in STYLE_CODES:
        return False
    if look.equalize:
        return False
    if look.glow > 0 and look.style in ("light", "plasma"):
        return False
    return look.background.mode in ("solid", "transparent", "gradient")


def wanted(result: RenderResult, look: Look) -> bool:
    return enabled and not _failed and result.width * result.height >= MIN_PIXELS and applicable(result, look)


def _percentiles(values: np.ndarray, mask: np.ndarray) -> tuple[float, float]:
    v = values[::SUBSAMPLE, ::SUBSAMPLE][mask[::SUBSAMPLE, ::SUBSAMPLE]]
    if v.size == 0:
        return 0.0, 1.0
    lo, hi = np.percentile(v, [1.0, 99.0])
    if hi - lo < 1e-12:
        hi = lo + 1.0
    return float(lo), float(hi)


def _ensure_program():
    """Lazily create the (single, process-wide) context + program; contexts are not
    shareable across threads, so the pass is serialised by ``_lock`` and the context is
    re-created if a different thread asks for it."""
    global _ctx, _prog, _thread_id
    from attractr.core.render.engines.gl_common import create_context, read_shader

    tid = threading.get_ident()
    if _ctx is not None and _thread_id == tid:
        return _ctx, _prog
    if _ctx is not None:
        try:
            _ctx.release()
        except Exception:  # noqa: BLE001
            pass
        _ctx = _prog = None
    ctx = create_context(430)
    prog = ctx.compute_shader(read_shader("develop.comp"))
    _ctx, _prog, _thread_id = ctx, prog, tid
    return ctx, prog


def _set(prog, name: str, value) -> None:
    if name in prog:
        prog[name].value = value


def develop_gpu(result: RenderResult, look: Look, norm: float, lut: np.ndarray) -> np.ndarray | None:
    """Return float32 RGBA [H, W, 4] or ``None`` (not applicable / GPU unavailable)."""
    global _failed
    if not applicable(result, look) or _failed:
        return None
    with _lock:
        try:
            return _run(result, look, norm, lut)
        except Exception as exc:  # noqa: BLE001 — never lose a render over the fast path
            _failed = True
            log.warning("GPU develop unavailable (%s: %s); using the CPU developer", type(exc).__name__, exc)
            return None


def _run(result: RenderResult, look: Look, norm: float, lut: np.ndarray) -> np.ndarray:
    ctx, prog = _ensure_program()
    h, w = result.count.shape
    mask = result.count > 0
    has_cv = result.cv_sum is not None
    has_depth = result.depth_sum is not None and look.depth_cue > 0
    cv_range = _percentiles(result.mean_cv(), mask) if has_cv else (0.0, 1.0)
    depth_range = _percentiles(result.mean_depth(), mask) if has_depth else (0.0, 1.0)
    bg = look.background
    flags = (1 if has_cv else 0) | (2 if has_depth else 0) | (4 if look.invert else 0)
    flags |= (8 if bg.mode == "transparent" else 0) | (16 if bg.mode == "gradient" else 0)

    lut_buf = ctx.buffer(np.ascontiguousarray(lut, dtype=np.float32).tobytes())
    lut_buf.bind_to_storage_buffer(3)
    _set(prog, "u_width", w)
    _set(prog, "u_height", h)
    _set(prog, "u_lut_n", int(lut.shape[0]))
    _set(prog, "u_style", STYLE_CODES[look.style])
    _set(prog, "u_flags", flags)
    _set(prog, "u_norm", float(norm))
    _set(prog, "u_gamma", float(look.gamma))
    _set(prog, "u_brightness", float(look.brightness))
    _set(prog, "u_contrast", float(look.contrast))
    _set(prog, "u_bands", float(look.bands))
    _set(prog, "u_depth_cue", float(look.depth_cue))
    _set(prog, "u_cv_range", cv_range)
    _set(prog, "u_depth_range", depth_range)
    _set(prog, "u_bg0", tuple(float(c) for c in bg.color))
    _set(prog, "u_bg1", tuple(float(c) for c in bg.color2))

    rows_per_chunk = max(1, CHUNK_PIXELS // w)
    out = np.empty((h, w, 4), dtype=np.float32)
    dummy = ctx.buffer(reserve=16)
    bufs = []
    try:
        for r0 in range(0, h, rows_per_chunk):
            r1 = min(h, r0 + rows_per_chunk)
            n = (r1 - r0) * w
            cnt = ctx.buffer(np.ascontiguousarray(result.count[r0:r1], dtype=np.float32).tobytes())
            cnt.bind_to_storage_buffer(0)
            cvb = ctx.buffer(np.ascontiguousarray(result.cv_sum[r0:r1], dtype=np.float32).tobytes()) if has_cv else dummy
            cvb.bind_to_storage_buffer(1)
            dpb = ctx.buffer(np.ascontiguousarray(result.depth_sum[r0:r1], dtype=np.float32).tobytes()) if has_depth else dummy
            dpb.bind_to_storage_buffer(2)
            ob = ctx.buffer(reserve=n * 16)
            ob.bind_to_storage_buffer(4)
            _set(prog, "u_n", n)
            _set(prog, "u_row0", r0)
            prog.run(group_x=(n + 255) // 256)
            ctx.finish()
            out[r0:r1] = np.frombuffer(ob.read(), dtype=np.float32).reshape(r1 - r0, w, 4)
            bufs = [cnt, ob] + ([cvb] if has_cv else []) + ([dpb] if has_depth else [])
            for b in bufs:
                b.release()
            bufs = []
    finally:
        for b in bufs:
            b.release()
        dummy.release()
        lut_buf.release()
    return out


def release() -> None:
    global _ctx, _prog
    with _lock:
        if _ctx is not None:
            try:
                _ctx.release()
            except Exception:  # noqa: BLE001
                pass
        _ctx = _prog = None
