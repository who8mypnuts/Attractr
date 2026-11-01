import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from attractr.core.formula.lexer import FormulaError
from attractr.core.formula.parser import parse, parse_expression
from attractr.core.formula.pretty import expr_to_source, program_to_source
from attractr.core.formula.validate import validate

CLIFFORD = """
name: Clifford
param a = -1.4 [-3, 3]
param b = 1.6 [-3, 3]
param c = 1.0
param d = 0.7
x' = sin(a*y) + c*cos(a*x)
y' = sin(b*x) + d*cos(b*y)
"""


def test_parse_and_validate_map():
    prog = parse(CLIFFORD)
    an = validate(prog)
    assert an.kind == "map" and an.dims == 2 and an.params == ("a", "b", "c", "d")
    assert prog.params[2].lo < 1.0 < prog.params[2].hi  # default range around the value


def test_roundtrip_source():
    prog = parse(CLIFFORD)
    again = parse(program_to_source(prog))
    assert again.body == prog.body and again.params == prog.params


def test_flow_detection_and_dt_header():
    prog = parse("name: L\nkind: flow\ndt: 8/3\nparam s = 10\ndx = s*(y-x)\ndy = x - y\ndz = x*y - z\n")
    assert validate(prog).kind == "flow"
    assert prog.header["dt"] == "8/3"


def test_mixed_map_and_flow_is_error():
    with pytest.raises(FormulaError):
        validate(parse("x' = y\ndy = x\n"))


def test_unknown_identifier_and_function():
    with pytest.raises(FormulaError, match="unknown identifier"):
        validate(parse("x' = q\ny' = x\n"))
    with pytest.raises(FormulaError, match="unknown function"):
        validate(parse("x' = foo(x)\ny' = x\n"))
    with pytest.raises(FormulaError, match="argument"):
        validate(parse("x' = sin(x, y)\ny' = x\n"))


def test_param_may_shadow_e():
    prog = parse("param e = 2\nx' = e*x\ny' = exp(1)*y\n")
    validate(prog)
    assert any(getattr(v, "name", None) == "e" for v in _vars(prog))


def _vars(prog):
    from attractr.core.formula.ast import Var, all_assigns, walk

    return [n for a in all_assigns(prog.body) for n in walk(a.expr) if isinstance(n, Var)]


def test_choose_block():
    prog = parse("choose {\n 0.5: x' = x*0.5; y' = y*0.5\n 0.5: x' = x*0.5 + 0.5; y' = y*0.5 + 0.5\n}\n")
    an = validate(prog)
    assert an.kind == "ifs" and an.uses_rand


def test_precedence():
    e = parse_expression("-a^2 + b*c^d^2")
    assert expr_to_source(e) == "-a^2 + b * c^d^2"
    e2 = parse_expression("(a+b)*c")
    assert expr_to_source(e2) == "(a + b) * c"


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=60))
@settings(max_examples=200, deadline=None)
def test_parser_never_crashes(text):
    try:
        validate(parse(text))
    except FormulaError:
        pass


def test_codegen_numba_matches_python(tmp_path):
    from attractr.core.formula.compile import compile_source

    cf = compile_source(CLIFFORD)
    p = np.array([-1.4, 1.6, 1.0, 0.7])
    rs = np.array([1], dtype=np.uint32)
    x, y, z = 0.3, -0.2, 0.0
    for _ in range(50):
        nx = math.sin(p[0] * y) + p[2] * math.cos(p[0] * x)
        ny = math.sin(p[1] * x) + p[3] * math.cos(p[1] * y)
        gx, gy, gz = cf.step(x, y, z, p, rs, 0, 0.0, 0.0)
        assert abs(gx - nx) < 1e-12 and abs(gy - ny) < 1e-12 and gz == 0.0
        x, y = nx, ny
