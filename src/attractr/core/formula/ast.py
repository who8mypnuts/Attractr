"""AST node types for the Attractr formula DSL (see docs/formula_dsl.md)."""

from __future__ import annotations

from dataclasses import dataclass, field

# ── expressions ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Num:
    value: float


@dataclass(frozen=True)
class Var:
    name: str  # "x", "y", "z", param, temp, "x'" (new value), "t_step"


@dataclass(frozen=True)
class Call:
    fn: str
    args: tuple[Expr, ...]


@dataclass(frozen=True)
class BinOp:
    op: str  # + - * / % ^
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Unary:
    op: str  # "-" or "not"
    operand: Expr


@dataclass(frozen=True)
class Compare:
    op: str  # < <= > >= == !=
    left: Expr
    right: Expr


@dataclass(frozen=True)
class BoolOp:
    op: str  # and | or
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Tuple:
    """Expression list — only valid as the right-hand side of ``plot = …``."""

    items: tuple[Expr, ...]


Expr = Num | Var | Call | BinOp | Unary | Compare | BoolOp | Tuple

# ── statements ──────────────────────────────────────────────────────────────────

NEXT_TARGETS = ("x'", "y'", "z'", "w'")
DERIV_TARGETS = ("dx", "dy", "dz", "dw")
SPECIAL_TARGETS = ("depth", "color", "plot", "section")
STATE_VARS = ("x", "y", "z", "w")


@dataclass(frozen=True)
class Assign:
    target: str  # "x'", "dx", "depth", "color" or a temporary name
    expr: Expr
    line: int = field(default=0, compare=False)

    @property
    def is_next(self) -> bool:
        return self.target in NEXT_TARGETS

    @property
    def is_deriv(self) -> bool:
        return self.target in DERIV_TARGETS

    @property
    def is_temp(self) -> bool:
        return not (self.is_next or self.is_deriv or self.target in SPECIAL_TARGETS)


@dataclass(frozen=True)
class Branch:
    prob: float
    body: tuple[Assign, ...]
    line: int = field(default=0, compare=False)


@dataclass(frozen=True)
class Choose:
    branches: tuple[Branch, ...]
    line: int = field(default=0, compare=False)


Stmt = Assign | Choose


@dataclass(frozen=True)
class ParamDecl:
    name: str
    default: float
    lo: float
    hi: float
    hint: str = ""
    is_int: bool = False
    step: float | None = None
    line: int = field(default=0, compare=False)


@dataclass(frozen=True)
class Program:
    header: dict[str, str] = field(default_factory=dict)
    params: tuple[ParamDecl, ...] = ()
    body: tuple[Stmt, ...] = ()

    @property
    def kind(self) -> str:
        """map | flow | ifs — explicit header wins, else inferred from the statements."""
        k = self.header.get("kind")
        if k:
            return k
        if any(isinstance(s, Choose) for s in self.body):
            return "ifs"
        for s in self.body:
            if isinstance(s, Assign) and s.is_deriv:
                return "flow"
        return "map"

    @property
    def name(self) -> str:
        return self.header.get("name", "Untitled")


def walk(node: Expr):
    """Yield every sub-expression of ``node`` (pre-order)."""
    yield node
    if isinstance(node, Call):
        for a in node.args:
            yield from walk(a)
    elif isinstance(node, BinOp | Compare | BoolOp):
        yield from walk(node.left)
        yield from walk(node.right)
    elif isinstance(node, Unary):
        yield from walk(node.operand)
    elif isinstance(node, Tuple):
        for a in node.items:
            yield from walk(a)


def all_assigns(body: tuple[Stmt, ...]):
    for s in body:
        if isinstance(s, Assign):
            yield s
        else:
            for b in s.branches:
                yield from b.body
