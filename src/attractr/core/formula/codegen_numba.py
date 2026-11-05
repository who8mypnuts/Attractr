"""AST → Python/numba source.

The output defines, in a generated module::

    PARAM_NAMES = (...)                      # order of the ``p`` array
    @njit def step(x, y, z, p, rs, i, t_step, dt) -> (nx, ny, nz)
    @njit def color_fn(x, y, z, p) -> float  # DSL ``color = …`` or 0.0
    HAS_COLOR = bool

For flows a ``deriv`` function is emitted and ``step`` applies the requested integrator.
"""

from __future__ import annotations

from attractr.core.formula.ast import (
    SPECIAL_TARGETS,
    Assign,
    BinOp,
    BoolOp,
    Call,
    Choose,
    Compare,
    Expr,
    Num,
    Program,
    Tuple,
    Unary,
    Var,
)
from attractr.core.formula.functions import FUNCTIONS
from attractr.core.formula.validate import Analysis

NJIT = '@njit(cache=True, nogil=True, error_model="numpy")'


class PyEmitter:
    """Expression emitter with a name-mapping context."""

    def __init__(self, params: tuple[str, ...], state: dict[str, str] | None = None) -> None:
        self.params = {n: i for i, n in enumerate(params)}
        self.state = dict(state or {"x": "x", "y": "y", "z": "z", "w": "w"})

    def name(self, n: str) -> str:
        if n in self.state:
            return self.state[n]
        if n in ("x'", "y'", "z'", "w'"):
            return "_n" + n[0]
        if n in self.params:
            return f"p[{self.params[n]}]"
        if n == "t_step":
            return "t_step"
        return "_t_" + n

    def expr(self, e: Expr) -> str:
        if isinstance(e, Num):
            return repr(float(e.value))
        if isinstance(e, Var):
            return self.name(e.name)
        if isinstance(e, Unary):
            if e.op == "not":
                return f"(not {self.expr(e.operand)})"
            return f"(-{self.expr(e.operand)})"
        if isinstance(e, BinOp):
            a, b = self.expr(e.left), self.expr(e.right)
            if e.op == "^":
                if isinstance(e.right, Num) and e.right.value == int(e.right.value) and 0 <= e.right.value <= 8:
                    n = int(e.right.value)
                    if isinstance(e.left, Var | Num) and n <= 4:
                        return "(" + "*".join([a] * n) + ")" if n else "1.0"
                    return f"({a})**{n}"
                return f"({a})**({b})"
            if e.op == "%":
                return f"_mod({a}, {b})"
            if e.op == "/":
                return f"({a} / {b})"
            return f"({a} {e.op} {b})"
        if isinstance(e, Compare):
            return f"({self.expr(e.left)} {e.op} {self.expr(e.right)})"
        if isinstance(e, BoolOp):
            return f"({self.expr(e.left)} {e.op} {self.expr(e.right)})"
        if isinstance(e, Call):
            return self.call(e)
        if isinstance(e, Tuple):
            return ", ".join(self.expr(a) for a in e.items)
        raise TypeError(type(e))

    def call(self, c: Call) -> str:
        spec = FUNCTIONS[c.fn]
        args = [self.expr(a) for a in c.args]
        if c.fn == "select":
            return f"({args[1]} if {args[0]} else {args[2]})"
        if c.fn in ("rand", "randn"):
            return f"_{c.fn}(rs, i)"
        if c.fn == "pow":
            return f"(({args[0]})**({args[1]}))"
        if c.fn in ("min", "max"):
            return f"{c.fn}({args[0]}, {args[1]})"
        if spec.py is not None:
            return f"{spec.py}({', '.join(args)})"
        return f"_{c.fn}({', '.join(args)})"


def _emit_assign_block(stmts: tuple[Assign, ...], em: PyEmitter, indent: str) -> list[str]:
    out = []
    for a in stmts:
        if a.target in SPECIAL_TARGETS:
            continue
        out.append(f"{indent}{em.name(a.target)} = {em.expr(a.expr)}")
    return out


def _find_special(prog: Program, target: str) -> Assign | None:
    for s in prog.body:
        if isinstance(s, Assign) and s.target == target:
            return s
    return None


def generate_map_step(prog: Program, an: Analysis) -> str:
    em = PyEmitter(an.params, _state_names(an))
    lines = [NJIT, "def step(x, y, z, w, p, rs, i, t_step, dt, x0, y0, z0):", "    _nx = x; _ny = y; _nz = z; _nw = w"]
    for stmt in prog.body:
        if isinstance(stmt, Choose):
            total = sum(b.prob for b in stmt.branches)
            lines.append("    _r = _rand(rs, i)")
            acc = 0.0
            for k, br in enumerate(stmt.branches):
                acc += br.prob / total
                if k < len(stmt.branches) - 1:
                    kw = "if" if k == 0 else "elif"
                    lines.append(f"    {kw} _r < {acc!r}:")
                else:
                    lines.append("    else:")
                lines.extend(_emit_assign_block(br.body, em, "        "))
        else:
            lines.extend(_emit_assign_block((stmt,), em, "    "))
    depth = _find_special(prog, "depth")
    if depth is not None:
        em_new = PyEmitter(an.params, {"x": "_nx", "y": "_ny", "z": "_nz", "w": "_nw"})
        lines.append(f"    _nz = {em_new.expr(depth.expr)}")
    lines.append("    return _nx, _ny, _nz, _nw")
    return "\n".join(lines)


def generate_flow_step(prog: Program, an: Analysis, integrator: str) -> str:
    em = PyEmitter(an.params)
    lines = [NJIT, "def deriv(x, y, z, w, p, rs, i, t_step):", "    _dx = 0.0; _dy = 0.0; _dz = 0.0; _dw = 0.0"]
    for stmt in prog.body:
        assert isinstance(stmt, Assign)
        if stmt.target in SPECIAL_TARGETS:
            continue
        tgt = "_" + stmt.target if stmt.is_deriv else em.name(stmt.target)
        lines.append(f"    {tgt} = {em.expr(stmt.expr)}")
    lines.append("    return _dx, _dy, _dz, _dw")
    lines += ["", NJIT, "def step(x, y, z, w, p, rs, i, t_step, dt, x0, y0, z0):"]
    if integrator == "euler":
        lines += [
            "    k1x, k1y, k1z, k1w = deriv(x, y, z, w, p, rs, i, t_step)",
            "    return x + dt * k1x, y + dt * k1y, z + dt * k1z, w + dt * k1w",
        ]
    elif integrator == "rk2":
        lines += [
            "    k1x, k1y, k1z, k1w = deriv(x, y, z, w, p, rs, i, t_step)",
            "    h = 0.5 * dt",
            "    k2x, k2y, k2z, k2w = deriv(x + h * k1x, y + h * k1y, z + h * k1z, w + h * k1w, p, rs, i, t_step)",
            "    return x + dt * k2x, y + dt * k2y, z + dt * k2z, w + dt * k2w",
        ]
    else:  # rk4
        lines += [
            "    h = 0.5 * dt",
            "    k1x, k1y, k1z, k1w = deriv(x, y, z, w, p, rs, i, t_step)",
            "    k2x, k2y, k2z, k2w = deriv(x + h * k1x, y + h * k1y, z + h * k1z, w + h * k1w, p, rs, i, t_step)",
            "    k3x, k3y, k3z, k3w = deriv(x + h * k2x, y + h * k2y, z + h * k2z, w + h * k2w, p, rs, i, t_step)",
            "    k4x, k4y, k4z, k4w = deriv(x + dt * k3x, y + dt * k3y, z + dt * k3z, w + dt * k3w, p, rs, i, t_step)",
            "    s = dt / 6.0",
            "    return (x + s * (k1x + 2.0 * k2x + 2.0 * k3x + k4x),",
            "            y + s * (k1y + 2.0 * k2y + 2.0 * k3y + k4y),",
            "            z + s * (k1z + 2.0 * k2z + 2.0 * k3z + k4z),",
            "            w + s * (k1w + 2.0 * k2w + 2.0 * k3w + k4w))",
        ]
    return "\n".join(lines)


def _state_names(an: Analysis) -> dict[str, str]:
    """State-variable spelling for update statements; escape systems also see the orbit start."""
    names = {"x": "x", "y": "y", "z": "z", "w": "w"}
    if an.kind == "escape":
        names.update({"x0": "x0", "y0": "y0", "z0": "z0"})
    return names


def _temps_prelude(prog: Program, em: PyEmitter) -> list[str]:
    """Temporaries recomputed from the *current* state (for colour / plot / section)."""
    out = []
    for s in prog.body:
        if isinstance(s, Assign) and s.is_temp:
            out.append(f"    {em.name(s.target)} = {em.expr(s.expr)}")
    return out


def generate_color_fn(prog: Program, an: Analysis) -> str:
    color = _find_special(prog, "color")
    lines = [NJIT, "def color_fn(x, y, z, w, p):"]
    if color is None:
        lines.append("    return 0.0")
    else:
        em = PyEmitter(an.params)
        lines += _temps_prelude(prog, em)
        lines.append(f"    return float({em.expr(color.expr)})")
    return "\n".join(lines)


def generate_plot_fn(prog: Program, an: Analysis) -> str:
    """``plot_fn(x, y, z, w, p) -> (px, py, pz)``: what gets drawn (default: the state)."""
    plot = _find_special(prog, "plot")
    lines = [NJIT, "def plot_fn(x, y, z, w, p):"]
    if plot is None:
        lines.append("    return x, y, z")
    else:
        em = PyEmitter(an.params)
        lines += _temps_prelude(prog, em)
        assert isinstance(plot.expr, Tuple)
        lines.append("    return " + ", ".join(f"float({em.expr(e)})" for e in plot.expr.items))
    return "\n".join(lines)


def generate_section_fn(prog: Program, an: Analysis) -> str:
    """``section_fn(x, y, z, w, p) -> float``: a point is plotted only when this changes sign."""
    sec = _find_special(prog, "section")
    lines = [NJIT, "def section_fn(x, y, z, w, p):"]
    if sec is None:
        lines.append("    return 1.0")
    else:
        em = PyEmitter(an.params)
        lines += _temps_prelude(prog, em)
        lines.append(f"    return float({em.expr(sec.expr)})")
    return "\n".join(lines)


def generate_event_fn(prog: Program, an: Analysis) -> str:
    """``event_fn(x, y, z, w, p, rs, i) -> (x, y, z, w)``: the ``on_section`` assignments, applied to
    the state right after a point was plotted at a section crossing (identity when absent)."""
    lines = [NJIT, "def event_fn(x, y, z, w, p, rs, i):"]
    if not prog.on_section:
        lines.append("    return x, y, z, w")
        return "\n".join(lines)
    em = PyEmitter(an.params)
    lines.append("    _nx = x; _ny = y; _nz = z; _nw = w")
    for a in prog.on_section:
        lines.append(f"    {em.name(a.target)} = {em.expr(a.expr)}")
    lines.append("    return _nx, _ny, _nz, _nw")
    return "\n".join(lines)


def generate_module_source(prog: Program, an: Analysis, integrator: str = "rk4") -> str:
    """Complete Python module text for the attractor's step/colour functions."""
    head = [
        '"""Generated by attractr.core.formula.codegen_numba — do not edit."""',
        "import math",
        "import numpy as np",
        "from numba import njit",
        "from attractr.core.formula.runtime_numba import *  # noqa: F401,F403",
        "",
        f"KIND = {an.kind!r}",
        f"DIMS = {an.dims}",
        f"PARAM_NAMES = {tuple(an.params)!r}",
        f"HAS_COLOR = {an.has_color!r}",
        f"HAS_PLOT = {an.has_plot!r}",
        f"HAS_SECTION = {an.has_section!r}",
        f"HAS_EVENT = {an.has_event!r}",
        f"SECTION_DIR = {prog.section_dir}",
        f"USES_W = {an.uses_w!r}",
        f"KIND_ESCAPE = {an.kind == 'escape'!r}",
        f"INTEGRATOR = {integrator!r}",
        "",
    ]
    if an.kind == "flow":
        body = generate_flow_step(prog, an, integrator)
    else:
        body = generate_map_step(prog, an)
    return ("\n".join(head) + body + "\n\n" + generate_color_fn(prog, an) + "\n\n"
            + generate_plot_fn(prog, an) + "\n\n" + generate_section_fn(prog, an) + "\n\n"
            + generate_event_fn(prog, an) + "\n")
