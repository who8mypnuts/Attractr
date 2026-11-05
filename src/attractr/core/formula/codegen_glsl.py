"""AST → GLSL (and, with ``dialect="opencl"``, OpenCL C) source for the GPU engines.

Generated functions (GLSL)::

    void step(inout float x, inout float y, inout float z, inout uint rng, float t_step, float dt)
    float color_fn(float x, float y, float z)

Parameters are read from ``u_p[i]`` (a uniform array in GLSL, a ``__constant float*``
argument named ``p`` in OpenCL).  The runtime helpers (``_rand``, ``_mod`` …) live in
``core/render/shaders/prelude.glsl`` / ``prelude.cl`` and mirror ``runtime_numba.py``.
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
from attractr.core.formula.validate import Analysis

# Functions that GLSL implements natively for both float and double (GL 4.0+).  Everything
# else goes through the ``_name`` wrappers of the preludes (so the fp64 build can provide
# software implementations of the transcendental functions).
_GLSL_NATIVE = {"abs", "sign", "floor", "ceil", "fract", "min", "max", "clamp", "mix", "smoothstep", "step"}
_CL_NATIVE = {"floor", "ceil"}


def fmt_float(v: float) -> str:
    s = repr(float(v))
    if "e" not in s and "E" not in s and "." not in s:
        s += ".0"
    return f"R({s})"


class GlslEmitter:
    def __init__(self, params: tuple[str, ...], dialect: str = "glsl", state: dict[str, str] | None = None) -> None:
        self.params = {n: i for i, n in enumerate(params)}
        self.dialect = dialect
        self.state = dict(state or {"x": "x", "y": "y", "z": "z", "w": "w"})
        self.pname = "u_p" if dialect == "glsl" else "p"
        self.declared: set[str] = set()

    def declare(self, target: str) -> str:
        """``float name`` on first assignment of a temporary, plain ``name`` afterwards."""
        n = self.name(target)
        if target in self.declared:
            return n
        self.declared.add(target)
        return "real " + n

    def name(self, n: str) -> str:
        if n in self.state:
            return self.state[n]
        if n in ("x'", "y'", "z'", "w'"):
            return "_n" + n[0]
        if n in self.params:
            return f"R({self.pname}[{self.params[n]}])"
        if n == "t_step":
            return "t_step"
        return "_t_" + n

    def expr(self, e: Expr) -> str:
        if isinstance(e, Num):
            return fmt_float(e.value)
        if isinstance(e, Var):
            return self.name(e.name)
        if isinstance(e, Unary):
            if e.op == "not":
                return f"(!{self.expr(e.operand)})"
            return f"(-{self.expr(e.operand)})"
        if isinstance(e, BinOp):
            a, b = self.expr(e.left), self.expr(e.right)
            if e.op == "^":
                if isinstance(e.right, Num) and e.right.value == int(e.right.value) and 1 <= e.right.value <= 4:
                    n = int(e.right.value)
                    if isinstance(e.left, Var | Num):
                        return "(" + "*".join([a] * n) + ")"
                    return f"_ipow{n}({a})"
                return f"_pow({a}, {b})"
            if e.op == "%":
                return f"_mod({a}, {b})"
            return f"({a} {e.op} {b})"
        if isinstance(e, Compare):
            return f"({self.expr(e.left)} {e.op} {self.expr(e.right)})"
        if isinstance(e, BoolOp):
            op = "&&" if e.op == "and" else "||"
            return f"({self.expr(e.left)} {op} {self.expr(e.right)})"
        if isinstance(e, Call):
            return self.call(e)
        if isinstance(e, Tuple):
            return ", ".join(self.expr(a) for a in e.items)
        raise TypeError(type(e))

    def call(self, c: Call) -> str:
        args = [self.expr(a) for a in c.args]
        fn = c.fn
        if fn == "select":
            return f"({args[0]} ? {args[1]} : {args[2]})"
        if fn in ("rand", "randn"):
            return f"_{fn}(rng)"
        native = _GLSL_NATIVE if self.dialect == "glsl" else _CL_NATIVE
        if fn in native:
            return f"{fn}({', '.join(args)})"
        if fn == "abs" and self.dialect == "opencl":
            return f"fabs({args[0]})"
        return f"_{fn}({', '.join(args)})"


def _block(stmts: tuple[Assign, ...], em: GlslEmitter, indent: str) -> list[str]:
    out = []
    for a in stmts:
        if a.target in SPECIAL_TARGETS:
            continue
        if a.is_temp:
            out.append(f"{indent}{em.declare(a.target)} = {em.expr(a.expr)};")
        else:
            out.append(f"{indent}{em.name(a.target)} = {em.expr(a.expr)};")
    return out


def _special(prog: Program, target: str) -> Assign | None:
    return next((s for s in prog.body if isinstance(s, Assign) and s.target == target), None)


def _declared_temps(prog: Program) -> list[str]:
    names: list[str] = []
    for s in prog.body:
        if isinstance(s, Assign) and s.is_temp and s.target not in names:
            names.append(s.target)
        elif isinstance(s, Choose):
            for b in s.branches:
                for a in b.body:
                    if a.is_temp and a.target not in names:
                        names.append(a.target)
    return names


def generate_step(prog: Program, an: Analysis, integrator: str, dialect: str = "glsl") -> str:
    state = {"x": "x", "y": "y", "z": "z", "w": "w"}
    if an.kind == "escape":  # the orbit start is visible to the update statements
        state.update({"x0": "x0", "y0": "y0", "z0": "z0"})
    em = GlslEmitter(an.params, dialect, state)
    inout = "inout " if dialect == "glsl" else ""
    ptr = "" if dialect == "glsl" else "__constant float* p, "
    lines: list[str] = []
    if an.kind == "flow":
        o = "out " if dialect == "glsl" else ""
        ptrs = "" if dialect == "glsl" else "*"
        sig = (f"void deriv({ptr}real x, real y, real z, real w, {inout}uint{ptrs} rng, real t_step, "
               f"{o}real{ptrs} _dx, {o}real{ptrs} _dy, {o}real{ptrs} _dz, {o}real{ptrs} _dw)")
        lines.append(sig + " {")
        if dialect == "glsl":
            lines.append("    _dx = R(0.0); _dy = R(0.0); _dz = R(0.0); _dw = R(0.0);")
            for s in prog.body:
                assert isinstance(s, Assign)
                if s.target in SPECIAL_TARGETS:
                    continue
                if s.is_deriv:
                    lines.append(f"    _{s.target} = {em.expr(s.expr)};")
                else:
                    lines.append(f"    {em.declare(s.target)} = {em.expr(s.expr)};")
        else:
            lines.append("    real dx_ = R(0.0), dy_ = R(0.0), dz_ = R(0.0), dw_ = R(0.0);")
            for s in prog.body:
                assert isinstance(s, Assign)
                if s.target in SPECIAL_TARGETS:
                    continue
                if s.is_deriv:
                    lines.append(f"    {s.target}_ = {em.expr(s.expr)};")
                else:
                    lines.append(f"    {em.declare(s.target)} = {em.expr(s.expr)};")
            lines.append("    *_dx = dx_; *_dy = dy_; *_dz = dz_; *_dw = dw_;")
        lines.append("}")
        lines.append("")
        lines.append(_flow_step(integrator, dialect))
        return "\n".join(lines)

    # map / ifs
    if dialect == "glsl":
        lines.append("void step(inout real x, inout real y, inout real z, inout real w, inout uint rng, real t_step, real dt, real x0, real y0, real z0) {")
    else:
        lines.append("void step(__constant float* p, real* xp, real* yp, real* zp, real* wp, uint* rng, real t_step, real dt, real x0, real y0, real z0) {")
        lines.append("    real x = *xp, y = *yp, z = *zp, w = *wp;")
    lines.append("    real _nx = x, _ny = y, _nz = z, _nw = w;")
    for stmt in prog.body:
        if isinstance(stmt, Choose):
            total = sum(b.prob for b in stmt.branches)
            lines.append("    real _r = _rand(rng);")
            acc = 0.0
            for k, br in enumerate(stmt.branches):
                acc += br.prob / total
                if k == 0:
                    lines.append(f"    if (_r < {fmt_float(acc)}) {{")
                elif k < len(stmt.branches) - 1:
                    lines.append(f"    }} else if (_r < {fmt_float(acc)}) {{")
                else:
                    lines.append("    } else {")
                saved = set(em.declared)
                lines.extend(_block(br.body, em, "        "))
                em.declared = saved
            lines.append("    }")
        else:
            lines.extend(_block((stmt,), em, "    "))
    depth = _special(prog, "depth")
    if depth is not None:
        em_new = GlslEmitter(an.params, dialect, {"x": "_nx", "y": "_ny", "z": "_nz", "w": "_nw"})
        lines.append(f"    _nz = {em_new.expr(depth.expr)};")
    if dialect == "glsl":
        lines.append("    x = _nx; y = _ny; z = _nz; w = _nw;")
    else:
        lines.append("    *xp = _nx; *yp = _ny; *zp = _nz; *wp = _nw;")
    lines.append("}")
    return "\n".join(lines)


def _flow_step(integrator: str, dialect: str) -> str:
    if dialect == "glsl":
        head = "void step(inout real x, inout real y, inout real z, inout real w, inout uint rng, real t_step, real dt, real x0, real y0, real z0) {"
        call = lambda args: f"deriv({args}, rng, t_step, kx, ky, kz, kw);"  # noqa: E731
        decl = "    real kx, ky, kz, kw;"
        tail = ""
    else:
        head = ("void step(__constant float* p, real* xp, real* yp, real* zp, real* wp, uint* rng, real t_step, real dt, real x0, real y0, real z0) {\n"
                "    real x = *xp, y = *yp, z = *zp, w = *wp;")
        call = lambda args: f"deriv(p, {args}, rng, t_step, &kx, &ky, &kz, &kw);"  # noqa: E731
        decl = "    real kx, ky, kz, kw;"
        tail = "    *xp = x; *yp = y; *zp = z; *wp = w;\n"
    body = [head, decl]
    if integrator == "euler":
        body += [f"    {call('x, y, z, w')}", "    x += dt * kx; y += dt * ky; z += dt * kz; w += dt * kw;"]
    elif integrator == "rk2":
        body += [
            f"    {call('x, y, z, w')}",
            "    real h = R(0.5) * dt; real mx = x + h * kx, my = y + h * ky, mz = z + h * kz, mw = w + h * kw;",
            f"    {call('mx, my, mz, mw')}",
            "    x += dt * kx; y += dt * ky; z += dt * kz; w += dt * kw;",
        ]
    else:
        body += [
            "    real h = R(0.5) * dt;",
            f"    {call('x, y, z, w')}",
            "    real k1x = kx, k1y = ky, k1z = kz, k1w = kw;",
            f"    {call('x + h * k1x, y + h * k1y, z + h * k1z, w + h * k1w')}",
            "    real k2x = kx, k2y = ky, k2z = kz, k2w = kw;",
            f"    {call('x + h * k2x, y + h * k2y, z + h * k2z, w + h * k2w')}",
            "    real k3x = kx, k3y = ky, k3z = kz, k3w = kw;",
            f"    {call('x + dt * k3x, y + dt * k3y, z + dt * k3z, w + dt * k3w')}",
            "    real s = dt / R(6.0);",
            "    x += s * (k1x + R(2.0) * k2x + R(2.0) * k3x + kx);",
            "    y += s * (k1y + R(2.0) * k2y + R(2.0) * k3y + ky);",
            "    z += s * (k1z + R(2.0) * k2z + R(2.0) * k3z + kz);",
            "    w += s * (k1w + R(2.0) * k2w + R(2.0) * k3w + kw);",
        ]
    body.append(tail + "}")
    return "\n".join(body)


def _temps(prog: Program, em: GlslEmitter) -> list[str]:
    return [f"    {em.declare(s.target)} = {em.expr(s.expr)};" for s in prog.body if isinstance(s, Assign) and s.is_temp]


def generate_color_fn(prog: Program, an: Analysis, dialect: str = "glsl") -> str:
    color = _special(prog, "color")
    pfx = "" if dialect == "glsl" else "__constant float* p, "
    head = f"real color_fn({pfx}real x, real y, real z, real w) {{"
    if color is None:
        return head + "\n    return R(0.0);\n}"
    em = GlslEmitter(an.params, dialect)
    lines = [head, *_temps(prog, em), f"    return {em.expr(color.expr)};", "}"]
    return "\n".join(lines)


def generate_plot_fn(prog: Program, an: Analysis, dialect: str = "glsl") -> str:
    """``plot_fn``: the drawn point for a state (default: the state itself)."""
    plot = _special(prog, "plot")
    if dialect == "glsl":
        head = "void plot_fn(real x, real y, real z, real w, out real px, out real py, out real pz) {"
        assign = "    px = {0}; py = {1}; pz = {2};"
    else:
        head = "void plot_fn(__constant float* p, real x, real y, real z, real w, real* px, real* py, real* pz) {"
        assign = "    *px = {0}; *py = {1}; *pz = {2};"
    if plot is None:
        return head + "\n" + assign.format("x", "y", "z") + "\n}"
    em = GlslEmitter(an.params, dialect)
    assert isinstance(plot.expr, Tuple)
    ex = [em.expr(e) for e in plot.expr.items]
    return "\n".join([head, *_temps(prog, em), assign.format(*ex), "}"])


def generate_section_fn(prog: Program, an: Analysis, dialect: str = "glsl") -> str:
    sec = _special(prog, "section")
    pfx = "" if dialect == "glsl" else "__constant float* p, "
    head = f"real section_fn({pfx}real x, real y, real z, real w) {{"
    if sec is None:
        return head + "\n    return R(1.0);\n}"
    em = GlslEmitter(an.params, dialect)
    return "\n".join([head, *_temps(prog, em), f"    return {em.expr(sec.expr)};", "}"])


def generate_event_fn(prog: Program, an: Analysis, dialect: str = "glsl") -> str:
    """``event_fn``: the ``on_section`` assignments applied to the state after a plotted crossing."""
    if dialect == "glsl":
        head = "void event_fn(inout real x, inout real y, inout real z, inout real w, inout uint rng) {"
        tail = "    x = _nx; y = _ny; z = _nz; w = _nw;"
    else:
        head = ("void event_fn(__constant float* p, real* xp, real* yp, real* zp, real* wp, uint* rng) {\n"
                "    real x = *xp, y = *yp, z = *zp, w = *wp;")
        tail = "    *xp = _nx; *yp = _ny; *zp = _nz; *wp = _nw;"
    if not prog.on_section:
        return head + "\n}"
    em = GlslEmitter(an.params, dialect)
    lines = [head, "    real _nx = x, _ny = y, _nz = z, _nw = w;"]
    lines.extend(_block(prog.on_section, em, "    "))
    lines += [tail, "}"]
    return "\n".join(lines)


def generate_gpu_source(prog: Program, an: Analysis, integrator: str = "rk4", dialect: str = "glsl") -> str:
    """step() + color_fn() + plot_fn() + section_fn() + event_fn() for the given dialect (prelude
    not included).  ``#define HAS_PLOT / HAS_SECTION / HAS_EVENT / SECTION_DIR`` let the kernels
    skip the extra calls."""
    defines = (f"#define HAS_PLOT {int(an.has_plot)}\n#define HAS_SECTION {int(an.has_section)}\n"
               f"#define HAS_EVENT {int(an.has_event)}\n#define SECTION_DIR {prog.section_dir}\n"
               f"#define KIND_ESCAPE {int(an.kind == 'escape')}\n")
    return (defines + generate_step(prog, an, integrator, dialect) + "\n\n" + generate_color_fn(prog, an, dialect) + "\n\n"
            + generate_plot_fn(prog, an, dialect) + "\n\n" + generate_section_fn(prog, an, dialect) + "\n\n"
            + generate_event_fn(prog, an, dialect) + "\n")
