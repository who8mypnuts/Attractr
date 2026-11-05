"""AttractorSpec: everything the program knows about one attractor, built from a ``.atr``
file (see docs/formula_dsl.md)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from attractr.core.formula.ast import ParamDecl, Program
from attractr.core.formula.compile import CompiledFormula, compile_program
from attractr.core.formula.lexer import FormulaError
from attractr.core.formula.parser import eval_const, parse
from attractr.core.formula.pretty import formula_lines
from attractr.core.formula.validate import Analysis, validate


@dataclass(frozen=True)
class ParamSpec:
    name: str
    default: float
    lo: float
    hi: float
    hint: str = ""
    is_int: bool = False
    step: float | None = None

    @staticmethod
    def from_decl(d: ParamDecl) -> ParamSpec:
        return ParamSpec(d.name, d.default, d.lo, d.hi, d.hint, d.is_int, d.step)

    @property
    def span(self) -> float:
        return self.hi - self.lo

    def clamp(self, v: float) -> float:
        return float(min(max(v, self.lo), self.hi))


@dataclass(frozen=True)
class AttractorSpec:
    id: str
    name: str
    kind: str  # map | flow | ifs
    dims: int
    params: tuple[ParamSpec, ...]
    program: Program
    analysis: Analysis
    source: str
    content_hash: str
    description: str = ""
    references: tuple[str, ...] = ()
    author: str = ""
    family: str = ""
    tags: tuple[str, ...] = ()
    dt: float = 0.01
    ic: tuple[float, float, float, float] = (0.1, 0.1, 0.1, 0.0)  # x, y, z, w
    jitter: float = 0.1
    warmup: int = 1000
    boost: float = 1.0  # iteration multiplier (Poincaré sections plot only a fraction of the steps)
    # escape-time systems (kind: escape): orbit start region, bailout radius, iteration limits
    region: tuple[float, ...] = (-2.0, 2.0, -2.0, 2.0, 0.0, 0.0)  # xmin xmax ymin ymax zmin zmax
    bailout: float = 2.0
    max_iter: int = 500
    min_iter: int = 0
    camera: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)  # yaw, pitch, roll, zoom
    palette: str = "nebula"
    style: str = "gas"
    lyapunov_hint: float | None = None
    path: Path | None = None
    builtin: bool = True

    # ── derived helpers ────────────────────────────────────────────────────────
    @property
    def param_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.params)

    @property
    def is_3d(self) -> bool:
        return self.dims == 3

    @property
    def is_flow(self) -> bool:
        return self.kind == "flow"

    @property
    def is_escape(self) -> bool:
        return self.kind == "escape"

    def iteration_budget(self, quality_iterations: int) -> int:
        """Steps the engines actually run for a requested ``Quality.iterations``."""
        return int(round(quality_iterations * self.boost))

    @property
    def plots_continuous(self) -> bool:
        """True when consecutive plotted points are neighbours on a curve (a flow without a
        Poincaré ``section``) — the only case where gap filling makes sense."""
        return self.kind == "flow" and not self.analysis.has_section

    def default_params(self) -> dict[str, float]:
        return {p.name: p.default for p in self.params}

    def params_array(self, values: dict[str, float] | None = None) -> np.ndarray:
        values = values or {}
        return np.array([float(values.get(p.name, p.default)) for p in self.params], dtype=np.float64)

    def formula_text(self) -> list[str]:
        return formula_lines(self.program)

    def compiled(self, integrator: str = "rk4") -> CompiledFormula:
        return compile_program(self.program, integrator)

    def with_source(self, source: str) -> AttractorSpec:
        """Re-parse from edited text, keeping id/path/builtin flags."""
        return spec_from_source(source, id=self.id, path=self.path, builtin=self.builtin)


def _parse_floats(text: str, n: int | None = None) -> tuple[float, ...]:
    vals = tuple(float(v) for v in re.findall(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?", text))
    if n is not None and len(vals) != n:
        raise FormulaError(f"expected {n} numbers, got {len(vals)}: {text!r}")
    return vals


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "untitled"


def spec_from_source(source: str, id: str | None = None, path: Path | None = None, builtin: bool = False) -> AttractorSpec:
    """Parse + validate DSL text into an :class:`AttractorSpec` (raises FormulaError)."""
    prog = parse(source)
    an = validate(prog)
    h = prog.header
    name = h.get("name", "Untitled")
    spec_id = id or h.get("id") or slugify(name)
    camera = (0.0, 0.0, 0.0, 1.0)
    if "camera" in h:
        vals = _parse_floats(h["camera"])
        camera = tuple((list(vals) + [0.0, 0.0, 0.0, 1.0])[:4])  # type: ignore[assignment]
    ic = (0.1, 0.1, 0.1, 0.0)
    if "ic" in h:
        vals = _parse_floats(h["ic"])
        if len(vals) not in (3, 4):
            raise FormulaError(f"ic: expected 3 or 4 numbers (x y z [w]), got {len(vals)}: {h['ic']!r}")
        ic = tuple((list(vals) + [0.0])[:4])  # type: ignore[assignment]
    dt = eval_const(h["dt"]) if "dt" in h else (0.01 if an.kind == "flow" else 1.0)
    tags = tuple(t.strip() for t in re.split(r"[,\n]", h.get("tags", "")) if t.strip())
    refs = tuple(r.strip() for r in h.get("ref", "").split("\n") if r.strip())
    boost = max(1.0, float(eval_const(h["boost"]))) if "boost" in h else 1.0
    region = (-2.0, 2.0, -2.0, 2.0, 0.0, 0.0)
    if "region" in h:
        vals = _parse_floats(h["region"])
        if len(vals) not in (4, 6):
            raise FormulaError(f"region: expected xmin xmax ymin ymax [zmin zmax], got {len(vals)} numbers")
        region = tuple((list(vals) + [0.0, 0.0])[:6])  # type: ignore[assignment]
    bailout = float(eval_const(h["bailout"])) if "bailout" in h else 2.0
    max_iter = int(float(h["max_iter"])) if "max_iter" in h else 500
    min_iter = int(float(h["min_iter"])) if "min_iter" in h else 0
    lyap = float(h["lyapunov"]) if "lyapunov" in h else None
    return AttractorSpec(
        id=spec_id,
        name=name,
        kind=an.kind,
        dims=an.dims,
        params=tuple(ParamSpec.from_decl(p) for p in prog.params),
        program=prog,
        analysis=an,
        source=source,
        content_hash=hashlib.sha1(source.encode()).hexdigest()[:16],
        description=h.get("desc", ""),
        references=refs,
        author=h.get("author", ""),
        family=h.get("family", {"map": "Maps", "flow": "Flows", "ifs": "IFS", "escape": "Escape"}[an.kind]),
        tags=tags,
        dt=dt,
        ic=ic,
        boost=boost,
        region=region,
        bailout=bailout,
        max_iter=max_iter,
        min_iter=min_iter,
        jitter=float(h.get("jitter", 0.1)) if "jitter" in h else 0.1,
        warmup=int(float(h["warmup"])) if "warmup" in h else default_warmup(an.kind, dt),
        camera=camera,
        palette=h.get("palette", "nebula"),
        style=h.get("style", "gas"),
        lyapunov_hint=lyap,
        path=path,
        builtin=builtin,
    )


def default_warmup(kind: str, dt: float) -> int:
    """Transient-discard steps for framing: flows need ≈ 20 time units, maps 200 steps."""
    if kind == "flow":
        return int(min(max(20.0 / max(dt, 1e-9), 1000), 60000))
    return 200


def spec_from_file(path: Path, builtin: bool = False) -> AttractorSpec:
    return spec_from_source(path.read_text(encoding="utf-8"), id=path.stem, path=path, builtin=builtin)
