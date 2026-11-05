"""The function table shared by the validator and every code generator.

``arity`` is an int or a tuple of accepted arities.  The back-end columns tell each code
generator how to spell the call; ``None`` means the back-end needs a helper (looked up in
its runtime prelude under the name ``_<fn>``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FunctionSpec:
    name: str
    arity: int | tuple[int, ...]
    py: str | None  # Python/numba spelling, e.g. "math.sin"; None → helper "_name"
    glsl: str | None  # GLSL spelling; None → helper
    doc: str = ""

    def accepts(self, n: int) -> bool:
        return n == self.arity if isinstance(self.arity, int) else n in self.arity


_F = FunctionSpec
FUNCTIONS: dict[str, FunctionSpec] = {
    f.name: f
    for f in (
        _F("sin", 1, "math.sin", "sin", "sine"),
        _F("cos", 1, "math.cos", "cos", "cosine"),
        _F("tan", 1, "math.tan", "tan", "tangent"),
        _F("asin", 1, "math.asin", "asin", "arc sine"),
        _F("acos", 1, "math.acos", "acos", "arc cosine"),
        _F("atan", 1, "math.atan", "atan", "arc tangent"),
        _F("atan2", 2, "math.atan2", "atan", "atan2(y, x) — angle of (x, y)"),
        _F("sinh", 1, "math.sinh", "sinh", "hyperbolic sine"),
        _F("cosh", 1, "math.cosh", "cosh", "hyperbolic cosine"),
        _F("tanh", 1, "math.tanh", "tanh", "hyperbolic tangent"),
        _F("asinh", 1, "math.asinh", "asinh", "inverse hyperbolic sine"),
        _F("acosh", 1, "math.acosh", "acosh", "inverse hyperbolic cosine"),
        _F("atanh", 1, "math.atanh", "atanh", "inverse hyperbolic tangent"),
        _F("exp", 1, "math.exp", "exp", "e^x"),
        _F("log", 1, None, "log", "natural logarithm (safe: log(|x|), −inf clamped)"),
        _F("log2", 1, None, "log2", "base-2 logarithm"),
        _F("log10", 1, None, None, "base-10 logarithm"),
        _F("sqrt", 1, None, "sqrt", "square root of |x|"),
        _F("cbrt", 1, None, None, "cube root (sign-preserving)"),
        _F("abs", 1, "abs", "abs", "absolute value"),
        _F("sign", 1, None, "sign", "−1, 0 or +1"),
        _F("floor", 1, None, "floor", "round down"),
        _F("ceil", 1, None, "ceil", "round up"),
        _F("round", 1, None, "round", "round to nearest"),
        _F("fract", 1, None, "fract", "fractional part x − floor(x)"),
        _F("mod", 2, None, "mod", "GLSL-style modulo (sign of divisor)"),
        _F("pow", 2, None, "pow", "x^y"),
        _F("min", 2, "min", "min", "minimum"),
        _F("max", 2, "max", "max", "maximum"),
        _F("clamp", 3, None, "clamp", "clamp(x, lo, hi)"),
        _F("mix", 3, None, "mix", "linear blend mix(a, b, t)"),
        _F("smoothstep", 3, None, "smoothstep", "smoothstep(e0, e1, x)"),
        _F("step", 2, None, "step", "step(edge, x): 0 if x < edge else 1"),
        _F("select", 3, None, None, "select(cond, a, b): a if cond else b"),
        _F("hypot", 2, None, "length2", "sqrt(x² + y²)"),
        _F("re_pow", 3, None, None, "real part of (x + iy)^n"),
        _F("im_pow", 3, None, None, "imaginary part of (x + iy)^n"),
        _F("rand", 0, None, None, "uniform random number in [0, 1)"),
        _F("randn", 0, None, None, "standard normal random number"),
    )
}

RESERVED_VARS = frozenset({"x", "y", "z", "w", "t_step", "pi", "e", "tau"})  # a parameter may shadow "e"
START_VARS = frozenset({"x0", "y0", "z0"})  # orbit start point — reserved in escape-time systems only
