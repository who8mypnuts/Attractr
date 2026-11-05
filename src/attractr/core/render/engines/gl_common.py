"""Shared OpenGL plumbing for the GPU engines: context creation, shader assembly, probing.

Contexts are created *per thread* (ModernGL standalone contexts cannot be shared across
threads); engines keep one context per owning thread in :class:`GLContextPool`.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from attractr.core.formula.codegen_glsl import generate_gpu_source
from attractr.core.formula.compile import CompiledFormula

log = logging.getLogger(__name__)
SHADER_DIR = Path(__file__).resolve().parents[1] / "shaders"
MAX_PARAMS = 32


class GLUnavailable(RuntimeError):
    pass


@dataclass
class GLInfo:
    version_code: int
    renderer: str
    vendor: str
    version: str
    compute: bool
    fp64: bool
    max_texture_size: int
    max_ssbo_mb: float


def create_context(require: int = 430):
    try:
        import moderngl
    except ImportError as exc:  # pragma: no cover
        raise GLUnavailable(f"moderngl not installed: {exc}") from exc
    try:
        return moderngl.create_standalone_context(require=require)
    except Exception as exc:  # noqa: BLE001
        raise GLUnavailable(f"could not create an OpenGL {require / 100:.1f} context: {exc}") from exc


def query_info(ctx) -> GLInfo:
    info = ctx.info
    exts = set(ctx.extensions) if hasattr(ctx, "extensions") else set()
    return GLInfo(
        version_code=ctx.version_code,
        renderer=str(info.get("GL_RENDERER", "?")),
        vendor=str(info.get("GL_VENDOR", "?")),
        version=str(info.get("GL_VERSION", "?")),
        compute=ctx.version_code >= 430,
        fp64="GL_ARB_gpu_shader_fp64" in exts or ctx.version_code >= 400,
        max_texture_size=int(info.get("GL_MAX_TEXTURE_SIZE", 8192)),
        max_ssbo_mb=float(info.get("GL_MAX_SHADER_STORAGE_BLOCK_SIZE", 128 * 1024 * 1024)) / (1024 * 1024),
    )


class GLContextPool:
    """One standalone context per thread, created lazily."""

    def __init__(self, require: int = 430) -> None:
        self.require = require
        self._local = threading.local()
        self._all: list = []
        self._lock = threading.Lock()

    def get(self):
        ctx = getattr(self._local, "ctx", None)
        if ctx is None:
            ctx = create_context(self.require)
            self._local.ctx = ctx
            with self._lock:
                self._all.append(ctx)
        return ctx

    def release_all(self) -> None:
        with self._lock:
            for c in self._all:
                try:
                    c.release()
                except Exception:  # noqa: BLE001
                    pass
            self._all.clear()


def read_shader(name: str) -> str:
    return (SHADER_DIR / name).read_text(encoding="utf-8")


GLSL_PRECISION_FP32 = """
#define real float
#define real3 vec3
#define real4 vec4
#define R(x) (x)
"""
GLSL_PRECISION_FP64 = """
#extension GL_ARB_gpu_shader_fp64 : enable
#define ATTRACTR_FP64 1
#define real double
#define real3 dvec3
#define real4 dvec4
#define R(x) double(x)
"""


def assemble_iterate_shader(cf: CompiledFormula, integrator: str, fp64: bool = False) -> str:
    """Fill the iterate.comp template with the precision header, the prelude(s) and the
    generated step()/color_fn()."""
    src = read_shader("iterate.comp")
    gen = generate_gpu_source(cf.program, cf.analysis, integrator if cf.kind == "flow" else "rk4", "glsl")
    nparams = max(1, len(cf.param_names))
    prelude = read_shader("prelude.glsl")
    if fp64:
        prelude = read_shader("prelude_fp64.glsl") + "\n" + prelude
    return (
        src.replace("__NPARAMS__", str(nparams))
        .replace("//__PRECISION__", GLSL_PRECISION_FP64 if fp64 else GLSL_PRECISION_FP32)
        .replace("//__PRELUDE__", prelude)
        .replace("//__STEP__", gen)
    )


def compile_compute(ctx, source: str, label: str):
    try:
        return ctx.compute_shader(source)
    except Exception as exc:  # noqa: BLE001
        raise GLUnavailable(f"{label} failed to compile: {exc}") from exc


def probe_compute(ctx) -> tuple[bool, str]:
    """Try a tiny atomic-add compute dispatch; returns (ok, message)."""
    src = """#version 430
layout(local_size_x = 64) in;
layout(r32ui, binding = 0) uniform uimage2D img;
layout(std430, binding = 0) buffer B { uint total; };
void main() { imageAtomicAdd(img, ivec2(gl_GlobalInvocationID.x % 8u, 0), 1u); atomicAdd(total, 1u); }
"""
    try:
        cs = ctx.compute_shader(src)
        tex = ctx.texture((8, 1), 1, dtype="u4")
        tex.write(np.zeros(8, dtype=np.uint32).tobytes())
        buf = ctx.buffer(np.zeros(1, dtype=np.uint32).tobytes())
        tex.bind_to_image(0, read=True, write=True)
        buf.bind_to_storage_buffer(0)
        cs.run(group_x=4)
        ctx.finish()
        total = int(np.frombuffer(buf.read(), dtype=np.uint32)[0])
        hist = np.frombuffer(tex.read(), dtype=np.uint32)
        ok = total == 256 and int(hist.sum()) == 256
        tex.release()
        buf.release()
        cs.release()
        return ok, "compute + image atomics OK" if ok else f"atomic test mismatch ({total}, {hist.sum()})"
    except Exception as exc:  # noqa: BLE001
        return False, f"compute test failed: {exc}"


def micro_benchmark(ctx, seconds: float = 0.25) -> float:
    """Rough Mpts/s of a Clifford-like iteration with atomics into a 256² image."""
    src = """#version 430
layout(local_size_x = 128) in;
layout(r32ui, binding = 0) uniform uimage2D img;
uniform int iters;
void main() {
    uint s = gl_GlobalInvocationID.x * 747796405u + 2891336453u; if (s == 0u) s = 1u;
    float x = float(s & 255u) / 255.0 - 0.5, y = float((s >> 8) & 255u) / 255.0 - 0.5;
    for (int i = 0; i < iters; i++) {
        float nx = sin(-1.4 * y) + cos(-1.4 * x); float ny = sin(1.6 * x) + 0.7 * cos(1.6 * y); x = nx; y = ny;
        ivec2 p = ivec2((x + 2.5) * 51.2, (y + 2.5) * 51.2);
        if (p.x >= 0 && p.x < 256 && p.y >= 0 && p.y < 256) imageAtomicAdd(img, p, 1u);
    }
}"""
    try:
        cs = ctx.compute_shader(src)
        tex = ctx.texture((256, 256), 1, dtype="u4")
        tex.bind_to_image(0, read=True, write=True)
        cs["iters"].value = 16
        cs.run(group_x=64)
        ctx.finish()
        iters = 64
        total = 0
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < seconds:
            cs["iters"].value = iters
            cs.run(group_x=128)
            ctx.finish()
            total += 128 * 128 * iters
        rate = total / max(time.perf_counter() - t0, 1e-9) / 1e6
        tex.release()
        cs.release()
        return rate
    except Exception:  # noqa: BLE001
        return 0.0
