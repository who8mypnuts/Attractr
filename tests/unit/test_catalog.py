from attractr.core.attractors.registry import registry
from attractr.core.attractors.spec import spec_from_source


def test_all_builtin_attractors_parse():
    registry.load()
    assert not registry.errors, registry.errors
    assert len(registry.ids()) >= 52


def test_clifford_is_canonical():
    """Regression for the WebGL source's wrong y' = sin(c*x) form."""
    spec = registry.get("clifford")
    lines = spec.formula_text()
    assert any("sin(b · x)" in line for line in lines)


def test_inline_spec_from_source():
    spec = spec_from_source("name: Test Map\nparam a = 1\nx' = a*y\ny' = -x\n")
    assert spec.id == "test_map" and spec.kind == "map" and spec.dims == 2
