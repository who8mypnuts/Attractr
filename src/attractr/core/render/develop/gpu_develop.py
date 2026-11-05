"""GPU development pass (OpenGL 4.3 compute) for large images.

The per-pixel styles (gas, dust, light, plasma) are evaluated by ``shaders/develop.comp``
and the lit styles (liquid, solid) by ``shaders/develop_light.comp`` (height field →
3×3 blur → screen-space normals → Phong, processed in row chunks with a 2-row halo), with
exactly the same formulas as the NumPy path; the handful of global scalars they need
(normaliser, colour-value / depth / surface-depth percentiles) are still computed on the
CPU from a strided subsample.  Anything the shaders do not implement (histogram
equalisation, bloom, image/procedural backgrounds) returns ``None`` so the caller falls
back to the CPU developer.

The pass is opt-in per call through :func:`wanted` (large images only — for preview-sized
results the NumPy path is faster than the round trip) and switches itself off for the
process after the first OpenGL failure.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager

import numpy as np

from attractr.core.render.result import RenderResult
from attractr.core.render.settings import Look

log = logging.getLogger(__name__)

MIN_PIXELS = 1_500_000  # below this the CPU path wins
CHUNK_PIXELS = 4_000_000  # rows are processed in chunks so buffers stay < ~100 MB
STYLE_CODES = {"gas": 0, "dust": 1, "light": 2, "plasma": 3}
LIT_STYLE_CODES = {"liquid": 4, "solid": 5}
HALO = 2  # rows of context the lit pass needs on each side of a chunk
SUBSAMPLE = 7  # stride for the percentile estimates (prime, to dodge structured aliasing)
RELIEF_SCALE = 0.12  # pixels per unit of depth, as a fraction of the short side (lighting.py)
NO_DEPTH = np.float32(3.0e38)  # stands in for +inf in the zmin buffer (GLSL has no isinf-safe max)
UNIT_RANGE = (0.0, 1.0)
# ``u_flags`` bits shared by both shaders
FLAG_CV, FLAG_DEPTH, FLAG_INVERT, FLAG_TRANSPARENT, FLAG_GRADIENT, FLAG_ZMIN = 1, 2, 4, 8, 16, 32
# storage-buffer bindings shared by both shaders
BIND_COUNT, BIND_CV, BIND_DEPTH, BIND_LUT, BIND_OUT, BIND_ZMIN, BIND_HRAW, BIND_HBLUR, BIND_FILL = range(9)

enabled = True  # preference toggle (GUI / CLI)
_lock = threading.Lock()
_failed = False
_developer: _GpuDeveloper | None = None


def applicable(result: RenderResult, look: Look) -> bool:
    """True when the shaders implement everything this look needs."""
    if look.style in LIT_STYLE_CODES:
        if result.zmin is None:
            return False
    elif look.style not in STYLE_CODES:
        return False
    if look.equalize:
        return False
    if look.glow > 0 and look.style in ("light", "plasma"):
        return False
    return look.background.mode in ("solid", "transparent", "gradient")


def wanted(result: RenderResult, look: Look) -> bool:
    """Whether :func:`develop_gpu` should be tried for this result (size, look, availability)."""
    return enabled and not _failed and result.width * result.height >= MIN_PIXELS and applicable(result, look)


def develop_gpu(result: RenderResult, look: Look, norm: float, lut: np.ndarray) -> np.ndarray | None:
    """Return float32 RGBA ``[H, W, 4]`` or ``None`` (not applicable / GPU unavailable).

    Serialised by a lock: the GL context is process-wide and re-created when another thread
    calls (standalone contexts cannot be shared between threads)."""
    global _developer, _failed
    if not applicable(result, look) or _failed:
        return None
    with _lock:
        try:
            if _developer is None or _developer.thread_id != threading.get_ident():
                if _developer is not None:
                    _developer.release()
                _developer = _GpuDeveloper()
            _developer.make_current()
            return _developer.develop(result, look, norm, lut)
        except Exception as exc:  # noqa: BLE001 — never lose a render over the fast path
            _failed = True
            log.warning("GPU develop unavailable (%s: %s); using the CPU developer", type(exc).__name__, exc)
            return None


def release() -> None:
    """Drop the process-wide GL context (tests / shutdown)."""
    global _developer
    with _lock:
        if _developer is not None:
            _developer.release()
            _developer = None


# ── scalar estimates (CPU, subsampled) ──────────────────────────────────────────


def _percentiles(values: np.ndarray, mask: np.ndarray) -> tuple[float, float]:
    """1–99 % range of ``values`` over ``mask`` from a strided subsample (never degenerate)."""
    v = values[::SUBSAMPLE, ::SUBSAMPLE][mask[::SUBSAMPLE, ::SUBSAMPLE]]
    if v.size == 0:
        return UNIT_RANGE
    lo, hi = np.percentile(v, [1.0, 99.0])
    if hi - lo < 1e-12:
        hi = lo + 1.0
    return float(lo), float(hi)


def _solid_zmin_range(result: RenderResult, look: Look, norm: float) -> tuple[float, float]:
    """1–99 % of the nearest depth over the Solid surface (density > threshold), from a
    subsample tone-mapped exactly like the shader does it."""
    from attractr.core.render.develop.tonemap import apply_curve, log_density

    cnt = result.count[::SUBSAMPLE, ::SUBSAMPLE]
    d = apply_curve(log_density(cnt, norm), look)
    d[cnt <= 0] = 1.0 if look.invert else 0.0
    z = result.zmin[::SUBSAMPLE, ::SUBSAMPLE][d > look.solid_threshold]
    z = z[np.isfinite(z)]
    if z.size == 0:
        return UNIT_RANGE
    lo, hi = np.percentile(z, [1.0, 99.0])
    return float(lo), float(hi)


def _decode_fill_key(key: int) -> float:
    """Inverse of the shader's monotonic float→uint key: the fill height (−max zmin)."""
    if key == 0:
        return 0.0
    raw = (~np.uint32(key)) if (key & 0x80000000) == 0 else np.uint32(key & 0x7FFFFFFF)
    return -float(np.frombuffer(np.uint32(raw).tobytes(), dtype=np.float32)[0])


def _set(prog, name: str, value) -> None:
    """Set a uniform the compiler kept (unused uniforms are optimised away)."""
    if name in prog:
        prog[name].value = value


# ── the developer ───────────────────────────────────────────────────────────────


class _GpuDeveloper:
    """Owns the GL context and both compute programs; one instance per process."""

    def __init__(self) -> None:
        from attractr.core.render.engines.gl_common import create_context, read_shader

        self.thread_id = threading.get_ident()
        self.ctx = create_context(430)
        self.flat = self.ctx.compute_shader(read_shader("develop.comp"))
        self.lit = self.ctx.compute_shader(read_shader("develop_light.comp"))

    def make_current(self) -> None:
        """Make this developer's GL context current on the calling thread."""
        from attractr.core.render.engines.gl_common import make_current

        make_current(self.ctx)

    def release(self) -> None:
        """Drop the process-wide GL context (tests / shutdown)."""
        try:
            self.ctx.release()
        except Exception:  # noqa: BLE001 — releasing a dead context must not raise
            pass

    def develop(self, result: RenderResult, look: Look, norm: float, lut: np.ndarray) -> np.ndarray:
        """Run the style's shader pass and return straight-alpha float32 RGBA ``[H, W, 4]``."""
        if look.style in LIT_STYLE_CODES:
            return self._develop_lit(result, look, norm, lut)
        return self._develop_flat(result, look, norm, lut)

    # ── shared plumbing ────────────────────────────────────────────────────────
    @staticmethod
    def _flags(result: RenderResult, look: Look, has_depth: bool) -> int:
        """The ``u_flags`` bit set describing which planes and background options apply."""
        bg = look.background
        return ((FLAG_CV if result.cv_sum is not None else 0) | (FLAG_DEPTH if has_depth else 0)
                | (FLAG_INVERT if look.invert else 0) | (FLAG_TRANSPARENT if bg.mode == "transparent" else 0)
                | (FLAG_GRADIENT if bg.mode == "gradient" else 0) | (FLAG_ZMIN if result.zmin is not None else 0))

    def _tone_uniforms(self, prog, result: RenderResult, look: Look, norm: float, lut: np.ndarray, style: int, flags: int,
                       depth_range: tuple[float, float]) -> None:
        """Tone-mapping, colour and background uniforms common to both shaders."""
        h, w = result.count.shape
        for name, value in (("u_width", w), ("u_height", h), ("u_lut_n", int(lut.shape[0])), ("u_style", style), ("u_flags", flags),
                            ("u_norm", float(norm)), ("u_gamma", float(look.gamma)), ("u_brightness", float(look.brightness)),
                            ("u_contrast", float(look.contrast)), ("u_bands", float(look.bands)), ("u_depth_cue", float(look.depth_cue)),
                            ("u_depth_range", depth_range), ("u_bg0", tuple(float(c) for c in look.background.color)),
                            ("u_bg1", tuple(float(c) for c in look.background.color2))):
            _set(prog, name, value)

    @contextmanager
    def _bound(self, data: np.ndarray | bytes | None, binding: int, reserve: int = 16):
        """A storage buffer bound for the duration of the block (a 16-byte placeholder when ``data`` is None)."""
        if data is None:
            buf = self.ctx.buffer(reserve=reserve)
        elif isinstance(data, bytes):
            buf = self.ctx.buffer(data)
        else:
            buf = self.ctx.buffer(np.ascontiguousarray(data, dtype=np.float32).tobytes())
        buf.bind_to_storage_buffer(binding)
        try:
            yield buf
        finally:
            buf.release()

    @staticmethod
    def _chunks(h: int, w: int):
        """Row ranges that keep each chunk below :data:`CHUNK_PIXELS`."""
        rows = max(1, CHUNK_PIXELS // w)
        return [(r0, min(h, r0 + rows)) for r0 in range(0, h, rows)]

    def _run(self, prog, n: int) -> None:
        """Dispatch one invocation per pixel of the bound chunk and make the writes visible."""
        prog.run(group_x=(n + 255) // 256)
        self.ctx.memory_barrier()

    # ── gas / dust / light / plasma ────────────────────────────────────────────
    def _develop_flat(self, result: RenderResult, look: Look, norm: float, lut: np.ndarray) -> np.ndarray:
        """Gas / Dust / Light / Plasma: one pass per chunk, no neighbourhood operations."""
        prog = self.flat
        h, w = result.count.shape
        mask = result.count > 0
        has_depth = result.depth_sum is not None and look.depth_cue > 0
        flags = self._flags(result, look, has_depth) & ~FLAG_ZMIN
        self._tone_uniforms(prog, result, look, norm, lut, STYLE_CODES[look.style], flags,
                            _percentiles(result.mean_depth(), mask) if has_depth else UNIT_RANGE)
        _set(prog, "u_cv_range", _percentiles(result.mean_cv(), mask) if result.cv_sum is not None else UNIT_RANGE)
        out = np.empty((h, w, 4), dtype=np.float32)
        with self._bound(lut, BIND_LUT):
            for r0, r1 in self._chunks(h, w):
                n = (r1 - r0) * w
                with (self._bound(result.count[r0:r1], BIND_COUNT),
                      self._bound(result.cv_sum[r0:r1] if result.cv_sum is not None else None, BIND_CV),
                      self._bound(result.depth_sum[r0:r1] if has_depth else None, BIND_DEPTH),
                      self._bound(None, BIND_OUT, reserve=n * 16) as ob):
                    _set(prog, "u_n", n)
                    _set(prog, "u_row0", r0)
                    self._run(prog, n)
                    self.ctx.finish()
                    out[r0:r1] = np.frombuffer(ob.read(), dtype=np.float32).reshape(r1 - r0, w, 4)
        return out

    # ── liquid / solid ─────────────────────────────────────────────────────────
    def _develop_lit(self, result: RenderResult, look: Look, norm: float, lut: np.ndarray) -> np.ndarray:
        """Liquid / Solid: a global fill-height scan, then height → blur → shade per chunk with halos."""
        prog = self.lit
        h, w = result.count.shape
        mask = result.count > 0
        has_depth = result.depth_sum is not None
        self._tone_uniforms(prog, result, look, norm, lut, LIT_STYLE_CODES[look.style], self._flags(result, look, has_depth),
                            _percentiles(result.mean_depth(), mask) if has_depth else UNIT_RANGE)
        _set(prog, "u_threshold", float(look.solid_threshold))
        _set(prog, "u_ppu", float(min(w, h) * RELIEF_SCALE))
        _set(prog, "u_cv_range", UNIT_RANGE)
        _set(prog, "u_zmin_range", _solid_zmin_range(result, look, norm) if look.style == "solid" else UNIT_RANGE)
        self._light_uniforms(prog, look)
        zmin = np.where(np.isfinite(result.zmin), result.zmin, NO_DEPTH).astype(np.float32)

        @contextmanager
        def rows(r0: int, r1: int):
            """Bind the input planes of rows ``[r0, r1)`` and set the chunk uniforms; yields the pixel count."""
            n = (r1 - r0) * w
            with (self._bound(result.count[r0:r1], BIND_COUNT), self._bound(None, BIND_CV),
                  self._bound(result.depth_sum[r0:r1] if has_depth else None, BIND_DEPTH), self._bound(zmin[r0:r1], BIND_ZMIN)):
                _set(prog, "u_n", n)
                _set(prog, "u_rows", r1 - r0)
                _set(prog, "u_row0", r0)
                yield n

        out = np.empty((h, w, 4), dtype=np.float32)
        with self._bound(lut, BIND_LUT), self._bound(np.zeros(1, dtype=np.uint32).tobytes(), BIND_FILL) as fill_buf:
            # pass 0: the global fill height (max zmin over the surface) via atomicMax
            _set(prog, "u_pass", 0)
            for r0, r1 in self._chunks(h, w):
                with rows(r0, r1) as n:
                    self._run(prog, n)
            self.ctx.finish()
            _set(prog, "u_fill", _decode_fill_key(int(np.frombuffer(fill_buf.read(), dtype=np.uint32)[0])))
            # passes 1–3 per chunk, with HALO rows of context on each side
            for c0, c1 in self._chunks(h, w):
                r0, r1 = max(0, c0 - HALO), min(h, c1 + HALO)
                with (rows(r0, r1) as n, self._bound(None, BIND_HRAW, reserve=n * 4), self._bound(None, BIND_HBLUR, reserve=n * 4),
                      self._bound(None, BIND_OUT, reserve=(c1 - c0) * w * 16) as ob):
                    _set(prog, "u_core0", c0 - r0)
                    _set(prog, "u_core_rows", c1 - c0)
                    for pass_id in (1, 2, 3):
                        _set(prog, "u_pass", pass_id)
                        self._run(prog, n)
                    self.ctx.finish()
                    out[c0:c1] = np.frombuffer(ob.read(), dtype=np.float32).reshape(c1 - c0, w, 4)
        return out

    @staticmethod
    def _light_uniforms(prog, look: Look) -> None:
        """Phong light direction, colour and coefficients of the look."""
        from attractr.core.render.develop.lighting import light_direction

        lt = look.light
        _set(prog, "u_light_dir", tuple(float(v) for v in light_direction(lt)))
        _set(prog, "u_light_color", tuple(float(c) for c in lt.color))
        _set(prog, "u_light", (float(lt.ambient), float(lt.diffuse), float(lt.specular), float(lt.shininess)))
