import json
from pathlib import Path

from attractr.cli.main import run


def test_cli_render_and_report(tmp_path: Path, capsys):
    out = tmp_path / "img.png"
    rc = run(["render", "henon", "--size", "96x64", "--ppp", "2", "--engine", "cpu", "-o", str(out), "--report", "md,txt", "-q"])
    assert rc == 0 and out.exists()
    assert (tmp_path / "img_report.md").exists() and (tmp_path / "img_report.txt").exists()
    from attractr.core.io.metadata import read_settings

    s = read_settings(out)
    assert s is not None and s.attractor == "henon" and s.quality.width == 96


def test_cli_list_json(capsys):
    assert run(["list", "attractors", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    ids = {d["id"] for d in data}
    assert {"lorenz", "clifford", "barnsley_fern", "tinkerbell"} <= ids


def test_cli_code_roundtrip(tmp_path: Path, capsys):
    from attractr.core.attractors.registry import registry
    from attractr.core.project.codes import settings_from_code, settings_to_code
    from attractr.core.render.pipeline import default_settings

    s = default_settings(registry.get("pickover")).with_params(a=2.0)
    code = settings_to_code(s)
    assert settings_from_code("look at this: " + code + " !") == s
    out = tmp_path / "c.png"
    assert run(["render", code, "--size", "48x48", "--ppp", "1", "--engine", "cpu", "-o", str(out), "-q"]) == 0
    assert out.exists()


def test_svg_export(tmp_path):
    from attractr.core.attractors.registry import registry
    from attractr.core.io.svg_export import write_svg
    from attractr.core.render.pipeline import default_settings
    from attractr.core.render.settings import Quality

    for aid, tag in (("lorenz", "<polyline"), ("henon", "<circle")):
        s = default_settings(registry.get(aid), Quality(width=200, height=150))
        out = write_svg(s, tmp_path / f"{aid}.svg", points=2000)
        text = out.read_text(encoding="utf-8")
        assert text.startswith("<svg") and 'width="200" height="150"' in text and tag in text
