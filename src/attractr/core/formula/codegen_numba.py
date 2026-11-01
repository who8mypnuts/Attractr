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
    Assign,
    BinOp,
    BoolOp,
    Call,
    Choose,
    Compare,
    Expr,
    Num,
    Program,
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
        self.state = state or {"x": "x", "y": "y", "z": "z"}

    def name(self, n: str) -> str:
        if n in self.state:
            return self.state[n]
        if n in ("x'", "y'", "z'"):
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
        if a.target in ("depth", "color"):
            continue
        out.append(f"{indent}{em.name(a.target)} = {em.expr(a.expr)}")
    return out


def _find_special(prog: Program, target: str) -> Assign | None:
    for s in prog.body:
        if isinstance(s, Assign) and s.target == target:
            return s
    return None


def generate_map_step(prog: Program, an: Analysis) -> str:
    em = PyEmitter(an.params)
    lines = [NJIT, "def step(x, y, z, p, rs, i, t_step, dt):", "    _nx = x; _ny = y; _nz = z"]
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
        em_new = PyEmitter(an.params, {"x": "_nx", "y": "_ny", "z": "_nz"})
        lines.append(f"    _nz = {em_new.expr(depth.expr)}")
    lines.append("    return _nx, _ny, _nz")
    return "\n".join(lines)


def generate_flow_step(prog: Program, an: Analysis, integrator: str) -> str:
    em = PyEmitter(an.params)
    lines = [NJIT, "def deriv(x, y, z, p, rs, i, t_step):", "    _dx = 0.0; _dy = 0.0; _dz = 0.0"]
    for stmt in prog.body:
        assert isinstance(stmt, Assign)
        if stmt.target in ("depth", "color"):
            continue
        tgt = "_" + stmt.target if stmt.is_deriv else em.name(stmt.target)
        lines.append(f"    {tgt} = {em.expr(stmt.expr)}")
    lines.append("    return _dx, _dy, _dz")
    lines += ["", NJIT, "def step(x, y, z, p, rs, i, t_step, dt):"]
    if integrator == "euler":
        lines += [
            "    k1x, k1y, k1z = deriv(x, y, z, p, rs, i, t_step)",
            "    return x + dt * k1x, y + dt * k1y, z + dt * k1z",
        ]
    elif integrator == "rk2":
        lines += [
            "    k1x, k1y, k1z = deriv(x, y, z, p, rs, i, t_step)",
            "    h = 0.5 * dt",
            "    k2x, k2y, k2z = deriv(x + h * k1x, y + h * k1y, z + h * k1z, p, rs, i, t_step)",
            "    return x + dt * k2x, y + dt * k2y, z + dt * k2z",
        ]
    else:  # rk4
        lines += [
            "    h = 0.5 * dt",
            "    k1x, k1y, k1z = deriv(x, y, z, p, rs, i, t_step)",
            "    k2x, k2y, k2z = deriv(x + h * k1x, y + h * k1y, z + h * k1z, p, rs, i, t_step)",
            "    k3x, k3y, k3z = deriv(x + h * k2x, y + h * k2y, z + h * k2z, p, rs, i, t_step)",
            "    k4x, k4y, k4z = deriv(x + dt * k3x, y + dt * k3y, z + dt * k3z, p, rs, i, t_step)",
            "    s = dt / 6.0",
            "    return (x + s * (k1x + 2.0 * k2x + 2.0 * k3x + k4x),",
            "            y + s * (k1y + 2.0 * k2y + 2.0 * k3y + k4y),",
            "            z + s * (k1z + 2.0 * k2z + 2.0 * k3z + k4z))",
        ]
    return "\n".join(lines)


def generate_color_fn(prog: Program, an: Analysis) -> str:
    color = _find_special(prog, "color")
    lines = [NJIT, "def color_fn(x, y, z, p):"]
    if color is None:
        lines.append("    return 0.0")
    else:
        em = PyEmitter(an.params)
        # temporaries used by the colour expression must be recomputed from the *new* state
        for s in prog.body:
            if isinstance(s, Assign) and s.is_temp:
                lines.append(f"    {em.name(s.target)} = {em.expr(s.expr)}")
        lines.append(f"    return float({em.expr(color.expr)})")
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
        f"INTEGRATOR = {integrator!r}",
        "",
    ]
    if an.kind == "flow":
        body = generate_flow_step(prog, an, integrator)
    else:
        body = generate_map_step(prog, an)
    return "\n".join(head) + body + "\n\n" + generate_color_fn(prog, an) + "\n"
