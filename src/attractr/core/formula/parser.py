"""Pratt parser: token stream → :class:`Program`.

Grammar (informal)::

    program   := (param_decl | statement | choose | on_section | NEWLINE)*
    param     := 'param' IDENT '=' const ['[' const ',' const ']'] ['int'] ['step' '=' const] [STRING]
    statement := target '=' expr (';' | NEWLINE)
    choose    := 'choose' '{' (const ':' statement*)* '}'
    on_section:= 'on_section' '{' statement* '}'          (assignments to x'/y'/z'/w' at a section crossing)
    expr      := or_expr
    or_expr   := and_expr ('or' and_expr)*
    and_expr  := not_expr ('and' not_expr)*
    not_expr  := 'not' not_expr | cmp_expr
    cmp_expr  := sum (('<'|'<='|'>'|'>='|'=='|'!=') sum)?
    sum       := term (('+'|'-') term)*
    term      := unary (('*'|'/'|'%') unary)*
    unary     := '-' unary | power
    power     := atom ('^' unary)?              (right associative)
    atom      := NUMBER | IDENT | IDENT '(' args ')' | '(' expr ')'
"""

from __future__ import annotations

import math

from attractr.core.formula.ast import (
    Assign,
    BinOp,
    BoolOp,
    Branch,
    Call,
    Choose,
    Compare,
    Expr,
    Num,
    ParamDecl,
    Program,
    Stmt,
    Tuple,
    Unary,
    Var,
)
from attractr.core.formula.lexer import FormulaError, Token, split_headers, tokenize

CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.toks = tokens
        self.i = 0
        self.declared: set[str] = set()  # parameter names seen so far (may shadow ``e``)

    # ── token helpers ───────────────────────────────────────────────────────────
    @property
    def cur(self) -> Token:
        return self.toks[self.i]

    def advance(self) -> Token:
        t = self.toks[self.i]
        if t.kind != "eof":
            self.i += 1
        return t

    def at(self, kind: str, text: str | None = None) -> bool:
        t = self.cur
        return t.kind == kind and (text is None or t.text == text)

    def at_op(self, text: str) -> bool:
        return self.at("op", text)

    def expect(self, kind: str, text: str | None = None) -> Token:
        if not self.at(kind, text):
            want = text if text is not None else kind
            got = self.cur.text if self.cur.kind != "eof" else "end of input"
            raise FormulaError(f"expected {want!r}, got {got!r}", self.cur.line, self.cur.col)
        return self.advance()

    def skip_newlines(self) -> None:
        while self.at("newline") or self.at_op(";"):
            self.advance()

    # ── program ─────────────────────────────────────────────────────────────────
    def parse_program(self, header: dict[str, str]) -> Program:
        params: list[ParamDecl] = []
        body: list[Stmt] = []
        on_section: list[Assign] = []
        self.skip_newlines()
        while not self.at("eof"):
            if self.at("ident", "param"):
                params.append(self.parse_param())
            elif self.at("ident", "choose"):
                body.append(self.parse_choose())
            elif self.at("ident", "on_section"):
                if on_section:
                    raise FormulaError("only one on_section block is allowed", self.cur.line, self.cur.col)
                on_section = self.parse_on_section()
            else:
                body.append(self.parse_statement())
            self.skip_newlines()
        return Program(header, tuple(params), tuple(body), tuple(on_section))

    def parse_on_section(self) -> list[Assign]:
        start = self.expect("ident", "on_section")
        self.expect("op", "{")
        body: list[Assign] = []
        self.skip_newlines()
        while not self.at_op("}"):
            if self.at("eof"):
                raise FormulaError("unterminated on_section block", start.line, start.col)
            body.append(self.parse_statement())
            self.skip_newlines()
        self.expect("op", "}")
        if not body:
            raise FormulaError("empty on_section block", start.line, start.col)
        return body

    def parse_param(self) -> ParamDecl:
        start = self.expect("ident", "param")
        name = self.expect("ident").text
        if name.endswith("'") or name in ("x", "y", "z", "w"):
            raise FormulaError(f"{name!r} cannot be a parameter name", start.line, start.col)
        self.expect("op", "=")
        default = self.parse_const()
        lo, hi = -abs(default) * 2 - 1.0, abs(default) * 2 + 1.0
        is_int, step, hint = False, None, ""
        if self.at_op("["):
            self.advance()
            lo = self.parse_const()
            self.expect("op", ",")
            hi = self.parse_const()
            self.expect("op", "]")
        while not (self.at("newline") or self.at("eof") or self.at_op(";")):
            if self.at("ident", "int"):
                self.advance()
                is_int = True
            elif self.at("ident", "step"):
                self.advance()
                self.expect("op", "=")
                step = self.parse_const()
            elif self.at("string"):
                hint = self.advance().text[1:-1]
            else:
                raise FormulaError(f"unexpected {self.cur.text!r} in param declaration", self.cur.line, self.cur.col)
        if lo > hi:
            lo, hi = hi, lo
        self.declared.add(name)
        return ParamDecl(name, default, lo, hi, hint, is_int, step, start.line)

    def parse_const(self) -> float:
        expr = self.parse_expr()
        try:
            return float(_fold(expr))
        except ValueError as exc:
            raise FormulaError(str(exc), self.cur.line, self.cur.col) from None

    def parse_statement(self) -> Assign:
        t = self.cur
        if t.kind != "ident":
            raise FormulaError(f"expected a statement, got {t.text!r}", t.line, t.col)
        target = self.advance().text
        if target in ("x", "y", "z", "w"):
            raise FormulaError(
                f"cannot assign to state variable {target!r}; use {target}' (map) or d{target} (flow)",
                t.line, t.col, len(target),
            )
        if target in CONSTANTS or target in ("t_step",):
            raise FormulaError(f"{target!r} is reserved", t.line, t.col, len(target))
        self.expect("op", "=")
        expr = self.parse_expr()
        if target == "plot":  # plot = ex, ey[, ez]
            items = [expr]
            while self.at_op(","):
                self.advance()
                items.append(self.parse_expr())
            if len(items) == 2:
                items.append(Num(0.0))
            if len(items) != 3:
                raise FormulaError("plot needs two or three expressions: plot = ex, ey, ez", t.line, t.col)
            expr = Tuple(tuple(items))
        if not (self.at("newline") or self.at("eof") or self.at_op(";") or self.at_op("}")):
            raise FormulaError(f"unexpected {self.cur.text!r} after expression", self.cur.line, self.cur.col)
        return Assign(target, expr, t.line)

    def parse_choose(self) -> Choose:
        start = self.expect("ident", "choose")
        self.expect("op", "{")
        branches: list[Branch] = []
        self.skip_newlines()
        while not self.at_op("}"):
            if self.at("eof"):
                raise FormulaError("unterminated choose block", start.line, start.col)
            ptok = self.cur
            prob = self.parse_const()
            self.expect("op", ":")
            body: list[Assign] = []
            self.skip_newlines()
            # a branch runs until the next "const :" or the closing brace
            while not self.at_op("}") and not self._at_branch_start():
                body.append(self.parse_statement())
                self.skip_newlines()
            if not body:
                raise FormulaError("empty choose branch", ptok.line, ptok.col)
            branches.append(Branch(prob, tuple(body), ptok.line))
        self.expect("op", "}")
        if len(branches) < 2:
            raise FormulaError("choose needs at least two branches", start.line, start.col)
        return Choose(tuple(branches), start.line)

    def _at_branch_start(self) -> bool:
        # lookahead: NUMBER [ops…] ':'   — a probability followed by a colon
        j = self.i
        depth = 0
        if self.toks[j].kind not in ("number", "ident") or self.toks[j].text in ("param", "choose"):
            return False
        if self.toks[j].kind == "ident" and self.toks[j + 1].kind == "op" and self.toks[j + 1].text == "=":
            return False
        while j < len(self.toks):
            t = self.toks[j]
            if t.kind in ("newline", "eof"):
                return False
            if t.kind == "op":
                if t.text == "(":
                    depth += 1
                elif t.text == ")":
                    depth -= 1
                elif t.text == ":" and depth == 0:
                    return True
                elif t.text in ("=", ";", "{", "}"):
                    return False
            j += 1
        return False

    # ── expressions ─────────────────────────────────────────────────────────────
    def parse_expr(self) -> Expr:
        return self.parse_or()

    def parse_or(self) -> Expr:
        left = self.parse_and()
        while self.at("ident", "or"):
            self.advance()
            left = BoolOp("or", left, self.parse_and())
        return left

    def parse_and(self) -> Expr:
        left = self.parse_not()
        while self.at("ident", "and"):
            self.advance()
            left = BoolOp("and", left, self.parse_not())
        return left

    def parse_not(self) -> Expr:
        if self.at("ident", "not"):
            self.advance()
            return Unary("not", self.parse_not())
        return self.parse_cmp()

    def parse_cmp(self) -> Expr:
        left = self.parse_sum()
        if self.cur.kind == "op" and self.cur.text in ("<", "<=", ">", ">=", "==", "!="):
            op = self.advance().text
            right = self.parse_sum()
            return Compare(op, left, right)
        return left

    def parse_sum(self) -> Expr:
        left = self.parse_term()
        while self.cur.kind == "op" and self.cur.text in ("+", "-"):
            op = self.advance().text
            left = BinOp(op, left, self.parse_term())
        return left

    def parse_term(self) -> Expr:
        left = self.parse_unary()
        while self.cur.kind == "op" and self.cur.text in ("*", "/", "%"):
            op = self.advance().text
            left = BinOp(op, left, self.parse_unary())
        return left

    def parse_unary(self) -> Expr:
        if self.at_op("-"):
            self.advance()
            return Unary("-", self.parse_unary())
        if self.at_op("+"):
            self.advance()
            return self.parse_unary()
        return self.parse_power()

    def parse_power(self) -> Expr:
        base = self.parse_atom()
        if self.at_op("^"):
            self.advance()
            return BinOp("^", base, self.parse_unary())  # right-assoc, binds tighter than unary minus on the left
        return base

    def parse_atom(self) -> Expr:
        t = self.cur
        if t.kind == "number":
            self.advance()
            return Num(t.value)
        if t.kind == "ident":
            self.advance()
            if t.text in ("and", "or", "not", "param", "choose", "on_section"):
                raise FormulaError(f"unexpected keyword {t.text!r}", t.line, t.col, len(t.text))
            if self.at_op("("):
                self.advance()
                args: list[Expr] = []
                if not self.at_op(")"):
                    args.append(self.parse_expr())
                    while self.at_op(","):
                        self.advance()
                        args.append(self.parse_expr())
                self.expect("op", ")")
                return Call(t.text, tuple(args))
            if t.text in CONSTANTS and t.text not in self.declared:
                return Num(CONSTANTS[t.text])
            return Var(t.text)
        if t.kind == "op" and t.text == "(":
            self.advance()
            e = self.parse_expr()
            self.expect("op", ")")
            return e
        got = t.text if t.kind != "eof" else "end of input"
        raise FormulaError(f"expected an expression, got {got!r}", t.line, t.col, max(1, len(t.text)))


def _fold(e: Expr) -> float:
    """Evaluate a constant expression (numbers and arithmetic only)."""
    if isinstance(e, Num):
        return e.value
    if isinstance(e, Unary) and e.op == "-":
        return -_fold(e.operand)
    if isinstance(e, BinOp):
        a, b = _fold(e.left), _fold(e.right)
        return {"+": a + b, "-": a - b, "*": a * b, "/": a / b, "^": a**b, "%": a % b}[e.op]
    if isinstance(e, Call) and e.fn == "sqrt" and len(e.args) == 1:
        return math.sqrt(_fold(e.args[0]))
    raise ValueError("expected a constant expression")


def parse(source: str) -> Program:
    """Parse complete DSL source text into a :class:`Program` (syntax only; run
    :func:`attractr.core.formula.validate.validate` for semantic checks)."""
    header, code_lines = split_headers(source)
    tokens = tokenize(code_lines)
    return Parser(tokens).parse_program(header)


def parse_expression(text: str) -> Expr:
    """Parse a single expression (used by tests and the parameter editor)."""
    tokens = tokenize([(1, text)])
    p = Parser(tokens)
    e = p.parse_expr()
    if not (p.at("newline") or p.at("eof")):
        raise FormulaError(f"unexpected {p.cur.text!r}", p.cur.line, p.cur.col)
    return e


def eval_const(text: str) -> float:
    """Evaluate a constant arithmetic expression such as ``8/3``."""
    return float(_fold(parse_expression(text)))
