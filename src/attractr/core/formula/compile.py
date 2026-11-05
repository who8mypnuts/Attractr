"""Parse + validate + generate + import: the one entry point engines use.

Generated modules are written to ``~/.attractr/cache/numba/<hash>.py`` so numba's on-disk
cache (``cache=True``) works across runs; compilation of the *kernel* that uses them
happens lazily inside the CPU engine.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import threading
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from attractr.core.formula.ast import Program
from attractr.core.formula.codegen_numba import generate_module_source
from attractr.core.formula.parser import parse
from attractr.core.formula.validate import Analysis, validate
from attractr.core.io.paths import cache_dir


@dataclass(frozen=True)
class CompiledFormula:
    program: Program
    analysis: Analysis
    integrator: str
    source_hash: str
    module: ModuleType

    @property
    def step(self) -> Any:
        return self.module.step

    @property
    def color_fn(self) -> Any:
        return self.module.color_fn

    @property
    def plot_fn(self) -> Any:
        return self.module.plot_fn

    @property
    def section_fn(self) -> Any:
        return self.module.section_fn

    @property
    def param_names(self) -> tuple[str, ...]:
        return self.analysis.params

    @property
    def kind(self) -> str:
        return self.analysis.kind


_memo: dict[str, CompiledFormula] = {}
_lock = threading.RLock()  # generated-module import must not race between threads


def program_hash(prog: Program, integrator: str) -> str:
    from attractr.core.formula.pretty import program_to_source

    key = program_to_source(prog) + "\n#integrator=" + integrator
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def compile_program(prog: Program, integrator: str = "rk4") -> CompiledFormula:
    an = validate(prog)
    if an.kind != "flow":
        integrator = "map"
    h = program_hash(prog, integrator)
    with _lock:
        if h in _memo:
            return _memo[h]
        src = generate_module_source(prog, an, integrator if integrator != "map" else "rk4")
        mod = _import_generated(h, src)
        cf = CompiledFormula(prog, an, integrator, h, mod)
        _memo[h] = cf
        return cf


def compile_source(text: str, integrator: str = "rk4") -> CompiledFormula:
    return compile_program(parse(text), integrator)


def _import_generated(h: str, src: str) -> ModuleType:
    name = f"attractr_gen_{h}"
    if name in sys.modules:
        return sys.modules[name]
    path = cache_dir("numba") / f"{name}.py"
    if not path.exists() or path.read_text() != src:
        path.write_text(src)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
