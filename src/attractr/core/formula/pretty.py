"""Pretty printers: AST → DSL source (round-trippable) and → Unicode maths for the UI."""

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
    Tuple,
    Unary,
    Var,
)

_PREC = {"or": 1, "and": 2, "not": 3, "cmp": 4, "+": 5, "-": 5, "*": 6, "/": 6, "%": 6, "neg": 7, "^": 8}

_UNICODE_NAMES = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "eps": "ε", "epsilon": "ε",
    "theta": "θ", "kappa": "κ", "lam": "λ", "lambda": "λ", "mu": "μ", "nu": "ν", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "phi": "φ", "omega": "ω", "om": "ω", "al": "α", "be": "β", "ga": "γ",
}


def fmt_number(v: float) -> str:
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    s = f"{v:.10g}"
    return s


def expr_to_source(e: Expr, parent_prec: int = 0, unicode: bool = False) -> str:
    if isinstance(e, Num):
        return fmt_number(e.value)
    if isinstance(e, Var):
        n = e.name
        if unicode:
            base = n[:-1] if n.endswith("'") else n
            base = _UNICODE_NAMES.get(base, base)
            return base + ("′" if n.endswith("'") else "")
        return n
    if isinstance(e, Call):
        args = ", ".join(expr_to_source(a, 0, unicode) for a in e.args)
        return f"{e.fn}({args})"
    if isinstance(e, Unary):
        if e.op == "not":
            s = "not " + expr_to_source(e.operand, _PREC["not"], unicode)
            return _paren(s, _PREC["not"], parent_prec)
        s = ("−" if unicode else "-") + expr_to_source(e.operand, _PREC["neg"], unicode)
        return _paren(s, _PREC["neg"], parent_prec)
    if isinstance(e, BinOp):
        prec = _PREC[e.op]
        lp = prec if e.op != "^" else prec + 1
        rp = prec + 1 if e.op != "^" else prec
        op = e.op
        if unicode:
            op = {"*": "·", "-": "−", "^": "^"}.get(op, op)
        if e.op == "^" and isinstance(e.right, Num) and unicode and e.right.value in (2, 3):
            return _paren(expr_to_source(e.left, lp, True) + ("²" if e.right.value == 2 else "³"), prec, parent_prec)
        s = f"{expr_to_source(e.left, lp, unicode)}{'' if e.op == '^' else ' '}{op}{'' if e.op == '^' else ' '}{expr_to_source(e.right, rp, unicode)}"
        return _paren(s, prec, parent_prec)
    if isinstance(e, Compare):
        op = e.op
        if unicode:
            op = {"<=": "≤", ">=": "≥", "!=": "≠", "==": "="}.get(op, op)
        s = f"{expr_to_source(e.left, _PREC['cmp'] + 1, unicode)} {op} {expr_to_source(e.right, _PREC['cmp'] + 1, unicode)}"
        return _paren(s, _PREC["cmp"], parent_prec)
    if isinstance(e, BoolOp):
        prec = _PREC[e.op]
        s = f"{expr_to_source(e.left, prec, unicode)} {e.op} {expr_to_source(e.right, prec + 1, unicode)}"
        return _paren(s, prec, parent_prec)
    if isinstance(e, Tuple):
        return ", ".join(expr_to_source(a, 0, unicode) for a in e.items)
    raise TypeError(type(e))


def _paren(s: str, prec: int, parent: int) -> str:
    return f"({s})" if prec < parent else s


def statement_to_source(a: Assign, unicode: bool = False) -> str:
    target = a.target
    if unicode:
        if target.endswith("'"):
            target = target[0] + "′"
        elif target in ("dx", "dy", "dz"):
            target = f"d{target[1]}/dt"
    return f"{target} = {expr_to_source(a.expr, 0, unicode)}"


def program_to_source(prog: Program) -> str:
    """Regenerate DSL source (headers, params, body)."""
    lines: list[str] = []
    for k, v in prog.header.items():
        for part in (v.split("\n") if k in ("ref", "tags") else [v]):
            lines.append(f"{k}: {part}")
    if prog.header and prog.params:
        lines.append("")
    for p in prog.params:
        s = f"param {p.name} = {fmt_number(p.default)} [{fmt_number(p.lo)}, {fmt_number(p.hi)}]"
        if p.is_int:
            s += " int"
        if p.step is not None:
            s += f" step={fmt_number(p.step)}"
        if p.hint:
            s += f' "{p.hint}"'
        lines.append(s)
    if prog.params:
        lines.append("")
    for stmt in prog.body:
        if isinstance(stmt, Choose):
            lines.append("choose {")
            for br in stmt.branches:
                body = "; ".join(statement_to_source(a) for a in br.body)
                lines.append(f"  {fmt_number(br.prob)}: {body}")
            lines.append("}")
        else:
            lines.append(statement_to_source(stmt))
    return "\n".join(lines) + "\n"


def formula_lines(prog: Program) -> list[str]:
    """Unicode maths lines for the Info panel / reports (equations only)."""
    out: list[str] = []
    for stmt in prog.body:
        if isinstance(stmt, Choose):
            for br in stmt.branches:
                out.append(f"with p = {fmt_number(br.prob)}:")
                out.extend("    " + statement_to_source(a, True) for a in br.body)
        else:
            out.append(statement_to_source(stmt, True))
    return out
