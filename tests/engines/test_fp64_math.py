"""Accuracy of the software double-precision math library used by the fp64 GLSL build."""

import math

import numpy as np
import pytest

from attractr.core.render.engines import selector
from attractr.core.render.engines.gl_common import GLSL_PRECISION_FP64, read_shader

FUNCS = ["_sin", "_cos", "_tan", "_exp", "_logp", "_atan", "_asin", "_acos", "_sinh", "_cosh", "_tanh", "_atan2"]


def _reference(name, x, y):
    f = {"_sin": math.sin, "_cos": math.cos, "_tan": math.tan, "_exp": math.exp, "_logp": math.log, "_atan": math.atan,
         "_asin": math.asin, "_acos": math.acos, "_sinh": math.sinh, "_cosh": math.cosh, "_tanh": math.tanh}
    if name == "_atan2":
        return math.atan2(y, x)
    return f[name](x)


@pytest.mark.parametrize("fn", FUNCS)
def test_glsl_double_math_matches_libm(fn):
    caps = selector.probe("gl_compute")
    if not caps.available or not caps.fp64:
        pytest.skip("no fp64-capable GL context")
    ctx = selector.get_engine("gl_compute").pool.get()
    rng = np.random.default_rng(3)
    if fn in ("_asin", "_acos"):
        xs = rng.uniform(-0.999, 0.999, 2048)
    elif fn == "_logp":
        xs = np.exp(rng.uniform(-40, 40, 2048))
    elif fn in ("_exp", "_sinh", "_cosh"):
        xs = rng.uniform(-30, 30, 2048)
    elif fn == "_tan":
        xs = rng.uniform(-1.4, 1.4, 2048)
    else:
        xs = rng.uniform(-50, 50, 2048)
    ys = rng.uniform(-50, 50, 2048)
    src = ("#version 430\n" + GLSL_PRECISION_FP64 + read_shader("prelude_fp64.glsl") + read_shader("prelude.glsl")
           + "\nlayout(local_size_x = 64) in;\nlayout(std430, binding = 0) buffer X { double xs[]; };\n"
           "layout(std430, binding = 1) buffer Y { double ys[]; };\nlayout(std430, binding = 2) buffer O { double os[]; };\n"
           "void main() { uint i = gl_GlobalInvocationID.x; if (i >= xs.length()) return; "
           + (f"os[i] = {fn}(ys[i], xs[i]);" if fn == "_atan2" else f"os[i] = {fn}(xs[i]);") + " }\n")
    cs = ctx.compute_shader(src)
    bx = ctx.buffer(xs.astype(np.float64).tobytes())
    by = ctx.buffer(ys.astype(np.float64).tobytes())
    bo = ctx.buffer(reserve=xs.size * 8)
    bx.bind_to_storage_buffer(0)
    by.bind_to_storage_buffer(1)
    bo.bind_to_storage_buffer(2)
    cs.run(group_x=xs.size // 64)
    ctx.finish()
    got = np.frombuffer(bo.read(), dtype=np.float64)
    ref = np.array([_reference(fn, float(x), float(y)) for x, y in zip(xs, ys, strict=True)])
    rel = np.abs(got - ref) / np.maximum(np.abs(ref), 1e-300)
    absd = np.abs(got - ref)
    ok = (rel < 5e-14) | (absd < 1e-14)
    assert ok.all(), f"{fn}: worst rel err {rel.max():.3e}, abs {absd.max():.3e}"
    for b in (bx, by, bo):
        b.release()
    cs.release()
