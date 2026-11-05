"""Semantic validation of a parsed :class:`Program` and derived facts about it."""

from __future__ import annotations

from dataclasses import dataclass, field

from attractr.core.formula.ast import (
    DERIV_TARGETS,
    NEXT_TARGETS,
    SPECIAL_TARGETS,
    Call,
    Choose,
    Compare,
    Expr,
    Num,
    Program,
    Tuple,
    Var,
    all_assigns,
    walk,
)
from attractr.core.formula.functions import FUNCTIONS, RESERVED_VARS, START_VARS
from attractr.core.formula.lexer import FormulaError


@dataclass
class Analysis:
    kind: str  # map | flow | ifs
    dims: int  # 2 or 3 (plotted dimensions)
    params: tuple[str, ...]
    temps: tuple[str, ...]
    uses_rand: bool
    has_depth: bool
    has_color: bool
    uses_z: bool
    uses_w: bool = False  # 4th state variable in use (w' / dw / w)
    has_plot: bool = False  # plot = ex, ey, ez  (what is drawn instead of x, y, z)
    has_section: bool = False  # section = expr (Poincaré section: plot on sign change)
    has_event: bool = False  # on_section { … } block present
    warnings: list[str] = field(default_factory=list)


def validate(prog: Program) -> Analysis:
    """Raise :class:`FormulaError` on the first semantic error; return an :class:`Analysis`."""
    params = [p.name for p in prog.params]
    _check_param_names(prog)
    kind = _infer_kind(prog)
    temps: list[str] = []
    uses_rand = False
    has_depth = has_color = has_plot = has_section = False

    for stmt in prog.body:
        if isinstance(stmt, Choose):
            if kind != "ifs":
                raise FormulaError("choose blocks are only allowed in an ifs system", stmt.line)
            uses_rand = True
            total = sum(b.prob for b in stmt.branches)
            if total <= 0 or any(b.prob <= 0 for b in stmt.branches):
                raise FormulaError("choose probabilities must be positive", stmt.line)
            for br in stmt.branches:
                known = set(params) | set(temps)
                for a in br.body:
                    if a.target in DERIV_TARGETS:
                        raise FormulaError("flow derivatives are not allowed inside choose", a.line)
                    uses_rand |= _check_expr(a.expr, known, a.line)
                    known.add(a.target)
            continue
        a = stmt
        known = set(params) | set(temps) | (set(START_VARS) if kind == "escape" else set())
        uses_rand |= _check_expr(a.expr, known, a.line)
        if isinstance(a.expr, Tuple) and a.target != "plot":
            raise FormulaError("an expression list is only allowed after plot =", a.line)
        if a.target == "depth":
            has_depth = True
        elif a.target == "color":
            has_color = True
        elif a.target == "plot":
            has_plot = True
        elif a.target == "section":
            has_section = True
        elif a.is_temp:
            if a.target in params:
                raise FormulaError(f"cannot assign to parameter {a.target!r}", a.line)
            if a.target in RESERVED_VARS:
                raise FormulaError(f"{a.target!r} is reserved", a.line)
            if a.target.endswith("'") and a.target not in NEXT_TARGETS:
                raise FormulaError(f"unknown target {a.target!r} (only x', y', z' may be primed)", a.line)
            if a.target in FUNCTIONS:
                raise FormulaError(f"{a.target!r} is a function name", a.line)
            temps.append(a.target)

    _check_required_targets(prog, kind)
    if has_depth and has_plot:
        raise FormulaError("use either depth = … or plot = …, not both")
    if kind == "escape":
        for p in prog.params:
            if p.name in START_VARS:
                raise FormulaError(f"{p.name!r} is the orbit start in an escape system and cannot be a parameter", p.line)
        for a in (*all_assigns(prog.body), *prog.on_section):
            if a.target in START_VARS:
                raise FormulaError(f"{a.target!r} is the orbit start and cannot be assigned", a.line)
            if a.target in SPECIAL_TARGETS and any(isinstance(v, Var) and v.name in START_VARS for v in walk(a.expr)):
                raise FormulaError("x0 / y0 / z0 may only be used in the update statements", a.line)
    if kind == "escape" and has_section:
        raise FormulaError("kind: escape cannot combine with section =")
    for key, lo in (("max_iter", 1), ("min_iter", 0)):
        if key in prog.header:
            try:
                if int(float(prog.header[key])) < lo:
                    raise ValueError
            except ValueError:
                raise FormulaError(f"{key} must be an integer ≥ {lo}") from None
    has_event = bool(prog.on_section)
    if has_event:
        if not has_section:
            raise FormulaError("on_section needs a section = … statement", prog.on_section[0].line)
        known = set(params)
        for a in prog.on_section:
            if a.target in DERIV_TARGETS or a.target in SPECIAL_TARGETS:
                raise FormulaError(f"{a.target!r} is not allowed inside on_section (assign x', y', z', w' or temporaries)", a.line)
            if a.is_temp and (a.target in RESERVED_VARS or a.target in FUNCTIONS or a.target.endswith("'")):
                raise FormulaError(f"{a.target!r} cannot be assigned inside on_section", a.line)
            uses_rand |= _check_expr(a.expr, known, a.line)
            known.add(a.target)
    if prog.header.get("section_dir", "both").strip().lower() not in ("both", "up", "down"):
        raise FormulaError("section_dir must be both, up or down")
    dims = _infer_dims(prog, kind, has_depth or has_plot)
    targets = {a.target for a in all_assigns(prog.body)}
    uses_w = ("w'" in targets or "dw" in targets
              or any(isinstance(v, Var) and v.name == "w" for a in all_assigns(prog.body) for v in walk(a.expr)))
    uses_z = dims == 3
    uses_w = uses_w or any(a.target == "w'" or any(isinstance(v, Var) and v.name == "w" for v in walk(a.expr)) for a in prog.on_section)
    analysis = Analysis(kind, dims, tuple(params), tuple(dict.fromkeys(temps)), uses_rand, has_depth, has_color, uses_z,
                        uses_w, has_plot, has_section, has_event)
    used = {v.name for a in (*all_assigns(prog.body), *prog.on_section) for v in walk(a.expr) if isinstance(v, Var)}
    for p in params:
        if p not in used:
            analysis.warnings.append(f"parameter {p!r} is never used")
    return analysis


def _check_param_names(prog: Program) -> None:
    seen: set[str] = set()
    for p in prog.params:
        if (p.name in RESERVED_VARS and p.name != "e") or p.name in FUNCTIONS or p.name in ("dx", "dy", "dz", "depth", "color"):
            raise FormulaError(f"{p.name!r} cannot be used as a parameter name", p.line)
        if p.name in seen:
            raise FormulaError(f"parameter {p.name!r} declared twice", p.line)
        seen.add(p.name)


def _infer_kind(prog: Program) -> str:
    targets = {a.target for a in all_assigns(prog.body)}
    has_next = bool(targets & set(NEXT_TARGETS))
    has_deriv = bool(targets & set(DERIV_TARGETS))
    has_choose = any(isinstance(s, Choose) for s in prog.body)
    if has_next and has_deriv:
        line = next(a.line for a in all_assigns(prog.body) if a.is_deriv)
        raise FormulaError("a system is either a map (x' = …) or a flow (dx = …), not both", line)
    declared = prog.header.get("kind")
    inferred = "ifs" if has_choose else ("flow" if has_deriv else "map")
    if declared and declared not in ("map", "flow", "ifs", "escape"):
        raise FormulaError(f"unknown kind {declared!r} (map | flow | ifs | escape)")
    if declared == "flow" and not has_deriv:
        raise FormulaError("kind: flow but no dx/dy/dz statements")
    if declared in ("map", "ifs", "escape") and has_deriv:
        raise FormulaError(f"kind: {declared} but dx/dy/dz statements found")
    if declared == "escape":
        if has_choose:
            raise FormulaError("kind: escape cannot use choose blocks")
        if "w'" in targets:
            raise FormulaError("kind: escape: w is the escape count during replay and cannot be assigned")
    if declared == "ifs" and not has_choose:
        # an ifs without choose is just a map; allow it but treat as map
        return "map"
    return declared or inferred


def _check_required_targets(prog: Program, kind: str) -> None:
    targets = {a.target for a in all_assigns(prog.body)}
    if kind == "flow":
        if not targets & set(DERIV_TARGETS):
            raise FormulaError("a flow needs at least dx and dy")
        if "dx" not in targets or "dy" not in targets:
            raise FormulaError("a flow must define both dx and dy")
    else:
        if "x'" not in targets or "y'" not in targets:
            raise FormulaError("a map must define both x' and y'")
    for a in all_assigns(prog.body):
        if a.target in SPECIAL_TARGETS and isinstance(prog.body, tuple):
            continue


def _infer_dims(prog: Program, kind: str, has_depth: bool) -> int:
    if "dims" in prog.header:
        d = prog.header["dims"].strip()
        if d not in ("2", "3"):
            raise FormulaError("dims must be 2 or 3")
        return int(d)
    targets = {a.target for a in all_assigns(prog.body)}
    plot = next((a for a in all_assigns(prog.body) if a.target == "plot"), None)
    if plot is not None and isinstance(plot.expr, Tuple):
        third = plot.expr.items[2]
        return 2 if isinstance(third, Num) and third.value == 0.0 else 3
    zt = "dz" if kind == "flow" else "z'"
    if zt in targets or has_depth:
        return 3
    uses_z = any(isinstance(v, Var) and v.name == "z" for a in all_assigns(prog.body) for v in walk(a.expr))
    return 3 if uses_z else 2


def _check_expr(expr: Expr, known: set[str], line: int) -> bool:
    """Check identifiers and arities; return True if the expression calls rand()."""
    uses_rand = False
    for node in walk(expr):
        if isinstance(node, Var):
            n = node.name
            if n in RESERVED_VARS or n in known or n in NEXT_TARGETS:
                continue
            if n in FUNCTIONS:
                raise FormulaError(f"{n!r} is a function — call it with parentheses", line)
            raise FormulaError(f"unknown identifier {n!r}", line)
        elif isinstance(node, Call):
            spec = FUNCTIONS.get(node.fn)
            if spec is None:
                raise FormulaError(f"unknown function {node.fn!r}", line)
            if not spec.accepts(len(node.args)):
                raise FormulaError(
                    f"{node.fn}() takes {spec.arity} argument(s), got {len(node.args)}", line
                )
            if node.fn in ("rand", "randn"):
                uses_rand = True
            if node.fn == "select" and not _is_boolean(node.args[0]):
                raise FormulaError("the first argument of select() must be a comparison", line)
        elif isinstance(node, Compare):
            pass
    return uses_rand


def _is_boolean(e: Expr) -> bool:
    from attractr.core.formula.ast import BoolOp, Unary

    return isinstance(e, Compare | BoolOp) or (isinstance(e, Unary) and e.op == "not")
