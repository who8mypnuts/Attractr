"""Render presets and batch planning."""

from pathlib import Path

from attractr.core.attractors.registry import registry
from attractr.core.project import batch
from attractr.core.project.render_presets import RenderPreset, RenderPresetLibrary, render_presets


def test_builtin_render_presets_and_apply():
    names = render_presets.names()
    assert "Instagram 1080²" in names and all(render_presets.get(n).builtin for n in names)
    p = render_presets.get("Instagram 1080²")
    from attractr.core.render.pipeline import default_settings

    s = p.apply(default_settings(registry.get("lorenz")))
    assert (s.quality.width, s.quality.height, s.quality.points_per_pixel) == (1080, 1080, 20.0)
    assert not render_presets.delete("Instagram 1080²")  # built-ins cannot be deleted


def test_user_render_preset_roundtrip(tmp_path, monkeypatch):
    lib = RenderPresetLibrary()
    monkeypatch.setattr(RenderPresetLibrary, "user_file", property(lambda self: tmp_path / "rp.json"))
    lib.save(RenderPreset("Mine", 640, 480, 3.0, 1, 0, "cpu", "auto", "png", 16, ("txt",), True))
    lib2 = RenderPresetLibrary()
    p = lib2.get("Mine")
    assert p.width == 640 and p.bit_depth == 16 and p.report_formats == ("txt",) and not p.builtin
    assert lib2.delete("Mine") and "Mine" not in lib2.names()


def test_batch_plan_collects_renderable_files(tmp_path):
    (tmp_path / "henon.atr").write_text(registry.get("henon").source, encoding="utf-8")
    (tmp_path / "bad.atr").write_text("x' = \n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("no", encoding="utf-8")
    from attractr.core.project.files import Project, save_project
    from attractr.core.render.pipeline import default_settings

    save_project(Project(default_settings(registry.get("lorenz"))), tmp_path / "proj.attractr")
    items, skipped = batch.plan(tmp_path, render_presets.get("Draft 1024²"))
    assert sorted(i.path.name for i in items) == ["henon.atr", "proj.attractr"]
    assert [Path(p).name for p, _ in skipped] == ["bad.atr"]
    assert all(i.settings.quality.width == 1024 for i in items)
