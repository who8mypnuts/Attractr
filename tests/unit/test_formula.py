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
        gx, gy, gz, gw = cf.step(x, y, z, 0.0, p, rs, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
        assert abs(gx - nx) < 1e-12 and abs(gy - ny) < 1e-12 and gz == 0.0 and gw == 0.0
        x, y = nx, ny


FORCED = """name: Forced
dt: 0.01
param g = 0.5
dx = y
dy = x - x*x*x - 0.3*y + g*cos(1.2*w)
dz = 0
dw = 1
plot = x, y, 0
section = sin(0.6*w)
"""


def test_dsl_w_plot_section():
    from attractr.core.formula.compile import compile_source
    from attractr.core.formula.validate import validate

    an = validate(parse(FORCED))
    assert an.kind == "flow" and an.uses_w and an.has_plot and an.has_section and an.dims == 2
    cf = compile_source(FORCED)
    p = np.array([0.5])
    rs = np.array([1], dtype=np.uint32)
    x, y, z, w = cf.step(0.1, 0.0, 0.0, 0.0, p, rs, 0, 0.0, 0.01, 0.0, 0.0, 0.0)
    assert abs(w - 0.01) < 1e-15 and z == 0.0
    assert cf.plot_fn(1.0, 2.0, 3.0, 4.0, p) == (1.0, 2.0, 0.0)
    assert abs(cf.section_fn(0.0, 0.0, 0.0, math.pi / 0.6, p)) < 1e-12


def test_dsl_rejects_tuple_outside_plot_and_w_assignment():
    from attractr.core.formula.validate import validate

    for bad in ("x' = 1, 2\ny' = 1\n", "w = 1\nx' = w\ny' = x\n", "ic: 1 2\nx' = y\ny' = x\n"):
        try:
            validate(parse(bad))
        except FormulaError:
            continue
        if "ic:" in bad:
            from attractr.core.attractors.spec import spec_from_source
            try:
                spec_from_source(bad)
            except FormulaError:
                continue
        raise AssertionError(bad)


RETURN_MAP = """name: Lorenz return map
dt: 0.005
section_dir: down
param sigma = 10
param rho = 28
param beta = 8/3
dx = sigma*(y - x)
dy = x*(rho - z) - y
dz = x*y - beta*z
dw = 0
plot = w, z, 0
section = x*y - beta*z
on_section { w' = z }
"""


def test_on_section_event_and_direction():
    from attractr.core.formula.compile import compile_source
    from attractr.core.formula.pretty import program_to_source
    from attractr.core.formula.validate import validate

    prog = parse(RETURN_MAP)
    an = validate(prog)
    assert an.has_section and an.has_event and an.uses_w and prog.section_dir == 2
    assert "on_section {" in program_to_source(prog) and "w' = z" in program_to_source(prog)
    cf = compile_source(RETURN_MAP)
    p = np.array([10.0, 28.0, 8 / 3])
    rs = np.array([1], dtype=np.uint32)
    assert cf.module.event_fn(1.0, 2.0, 3.0, 4.0, p, rs, 0) == (1.0, 2.0, 3.0, 3.0)
    assert cf.module.HAS_EVENT and cf.module.SECTION_DIR == 2
    for bad in (RETURN_MAP.replace("section = x*y - beta*z\n", ""),  # event without a section
                RETURN_MAP.replace("on_section { w' = z }", "on_section { dw = 1 }"),
                RETURN_MAP.replace("section_dir: down", "section_dir: sideways")):
        try:
            validate(parse(bad))
        except FormulaError:
            continue
        raise AssertionError(bad)


BUDDHA = """name: B
kind: escape
dims: 2
region: -2 1 -1.5 1.5
bailout: 2
max_iter: 100
min_iter: 5
x' = x*x - y*y + x0
y' = 2*x*y + y0
color = w
"""


def test_escape_kind_validation_and_codegen():
    from attractr.core.attractors.spec import spec_from_source
    from attractr.core.formula.compile import compile_source
    from attractr.core.formula.validate import validate

    an = validate(parse(BUDDHA))
    assert an.kind == "escape" and an.dims == 2 and an.has_color
    spec = spec_from_source(BUDDHA)
    assert spec.is_escape and spec.region == (-2.0, 1.0, -1.5, 1.5, 0.0, 0.0) and spec.max_iter == 100 and spec.min_iter == 5
    cf = compile_source(BUDDHA)
    p = np.zeros(0)
    rs = np.array([1], dtype=np.uint32)
    assert cf.step(0.0, 0.0, 0.0, 0.0, p, rs, 0, 0.0, 1.0, 0.25, -0.5, 0.0) == (0.25, -0.5, 0.0, 0.0)
    assert cf.module.KIND_ESCAPE
    for bad in ("name: m\nx' = x + x0\ny' = y\n",  # x0 outside escape kind
                BUDDHA.replace("color = w", "w' = 1"),  # w is the escape count
                BUDDHA + "section = x\n",
                BUDDHA.replace("max_iter: 100", "max_iter: 0")):
        try:
            validate(parse(bad))
        except FormulaError:
            continue
        raise AssertionError(bad)
    # x0.. are ordinary names outside escape systems (the polynomial map uses them as coefficients)
    assert validate(parse("name: m\nparam x0 = 1\nx' = x0*y\ny' = x\n")).kind == "map"
