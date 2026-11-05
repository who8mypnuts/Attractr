"""Assemble ``generated formula module + CPU kernel template`` into numba modules.

Two kinds of generated module live in ``~/.attractr/cache/numba``:

* ``attractr_kern_<hash>.py`` — the *base* kernel for a formula: ``sample_points`` and
  ``lyapunov_kernel`` (framing, analysis) plus a default ``accumulate``.
* ``attractr_kern_<hash>_d<D>z<Z>c<C>r<R>.py`` — *variants* of ``accumulate`` with the
  buffer set (depth / zmin / colour) and the splat radius baked in as constants.  Baking
  them removes the runtime flags that forced the compiler to assume aliasing between the
  accumulation buffers (measured ≈ 3× speed-up).
"""

from __future__ import annotations

import importlib.util
import sys
import threading
import time
from pathlib import Path
from types import ModuleType

from attractr.core.formula.codegen_numba import generate_module_source
from attractr.core.formula.compile import CompiledFormula, compile_program
from attractr.core.formula.parser import parse
from attractr.core.io.paths import cache_dir

_TEMPLATE = Path(__file__).with_name("cpu_kernel_template.py")
_SPLIT_MARK = "from numba import prange  # noqa: E402,F401"
_memo: dict[str, ModuleType] = {}
_lock = threading.RLock()

Variant = tuple[int, int, int, int]  # want_depth, want_zmin, want_color, splat_r
DEFAULT_VARIANT: Variant = (0, 0, 0, 0)


def _template_body() -> str:
    return _TEMPLATE.read_text().split(_SPLIT_MARK, 1)[1]


def _bake(text: str, variant: Variant) -> str:
    d, z, c, r = variant
    return (text.replace("__WANT_DEPTH__", str(int(d))).replace("__WANT_ZMIN__", str(int(z)))
            .replace("__WANT_COLOR__", str(int(c))).replace("__SPLAT_R__", str(int(r))))


def _import(name: str, src: str) -> ModuleType:
    path = cache_dir("numba") / f"{name}.py"
    if not path.exists() or path.read_text() != src:
        path.write_text(src)
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def kernel_module(cf: CompiledFormula, variant: Variant = DEFAULT_VARIANT) -> ModuleType:
    """Module with ``accumulate`` specialised for ``variant`` (plus ``sample_points`` and
    ``lyapunov_kernel`` in the default variant)."""
    key = cf.source_hash if variant == DEFAULT_VARIANT else f"{cf.source_hash}_d{variant[0]}z{variant[1]}c{variant[2]}r{variant[3]}"
    with _lock:
        if key in _memo:
            return _memo[key]
        if variant == DEFAULT_VARIANT:
            src = generate_module_source(cf.program, cf.analysis, cf.integrator if cf.integrator != "map" else "rk4")
            src += "\nfrom numba import prange  # noqa: F401\n" + _bake(_template_body(), variant)
        else:
            base = kernel_module(cf, DEFAULT_VARIANT)  # ensures the formula module is importable
            body = _template_body()
            # variants only need the accumulation kernel; drop sample_points / lyapunov_kernel
            body = body.split("@njit(nogil=True, cache=True)\ndef sample_points", 1)[0]
            src = (
                '"""Generated kernel variant — do not edit."""\n'
                "import math\nimport numpy as np\nfrom numba import njit\n"
                "from attractr.core.formula.runtime_numba import *  # noqa: F401,F403\n"
                f"from {base.__name__} import step, color_fn, plot_fn, section_fn, event_fn, HAS_PLOT, HAS_SECTION, HAS_EVENT, SECTION_DIR, KIND_ESCAPE  # noqa: F401\n"
                + _bake(body, variant)
            )
        mod = _import(f"attractr_kern_{key}", src)
        _memo[key] = mod
        return mod


def kernel_for_source(text: str, integrator: str = "rk4") -> tuple[CompiledFormula, ModuleType, float]:
    """Convenience: parse + compile + default kernel module.  Returns ``(cf, module, seconds)``."""
    t0 = time.perf_counter()
    cf = compile_program(parse(text), integrator)
    mod = kernel_module(cf)
    return cf, mod, time.perf_counter() - t0

