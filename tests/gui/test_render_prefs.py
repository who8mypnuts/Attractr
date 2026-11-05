"""Render-output preferences and the job factory built on them."""

from pathlib import Path

from PySide6.QtCore import QSettings

from attractr.core.render.settings import RenderSettings
from attractr.gui.controllers.render_actions import make_job
from attractr.gui.state.render_prefs import KEY_CHECKPOINT_MINUTES, KEY_FOLDER, KEY_REPORT, KEY_REPORT_FMT, RenderPrefs


def _settings(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)


def test_prefs_defaults_and_overrides(tmp_path, app):
    qs = _settings(tmp_path)
    prefs = RenderPrefs.load(qs)
    assert prefs.folder == Path.home() / "Attractr" and prefs.report_formats == ["md"] and prefs.checkpoint_every == 120.0
    qs.setValue(KEY_FOLDER, str(tmp_path))
    qs.setValue(KEY_REPORT, "false")
    qs.setValue(KEY_REPORT_FMT, "pdf")
    qs.setValue(KEY_CHECKPOINT_MINUTES, 0.5)
    prefs = RenderPrefs.load(qs)
    assert prefs.folder == tmp_path and prefs.report_formats == [] and prefs.checkpoint_every == 30.0


def test_make_job_follows_prefs_and_options(tmp_path, app):
    prefs = RenderPrefs(tmp_path, "{name}", ["html"], 45.0)
    job = make_job(prefs, RenderSettings())
    assert job.out_dir == tmp_path and job.name_template == "{name}" and job.report_formats == ["html"] and job.checkpoint_every == 45.0
    job = make_job(prefs, RenderSettings(), out_dir=tmp_path / "x", template="{w}", report_formats=[], fmt="jpg")
    assert job.out_dir == tmp_path / "x" and job.name_template == "{w}" and job.report_formats == [] and job.fmt == "jpg"


def test_resume_render_picks_output_folder_from_checkpoint_location(tmp_path, app, monkeypatch):
    """GUI checkpoints live in <out>/checkpoints → resume into <out>; any other file resumes into the preferred folder."""
    from types import SimpleNamespace

    import numpy as np

    from attractr.core.render.checkpoint import Checkpoint
    from attractr.core.render.result import Framing, RenderResult, RenderStats
    from attractr.gui.controllers import render_actions as ra

    res = RenderResult(RenderSettings(), np.zeros((4, 4), dtype=np.float32), Framing((0, 0, 0), 1.0), RenderStats())
    gui_ck = Checkpoint.from_result(res).save(tmp_path / "out" / "checkpoints" / "a.attractr-ckpt.npz")
    cli_ck = Checkpoint.from_result(res).save(tmp_path / "elsewhere" / "b.attractr-ckpt.npz")
    jobs = []
    window = SimpleNamespace(doc=None, submit_job=jobs.append, set_status=lambda t: None)
    actions = ra.RenderActions(window)
    monkeypatch.setattr(ra.RenderPrefs, "load", staticmethod(lambda qs=None: ra.RenderPrefs(tmp_path / "pref", "{name}", [], 0.0)))
    for path, expected in ((gui_ck, tmp_path / "out"), (cli_ck, tmp_path / "pref")):
        monkeypatch.setattr(ra.QFileDialog, "getOpenFileName", staticmethod(lambda *a, p=path, **k: (str(p), "")))
        actions.resume_render()
        assert jobs[-1].out_dir == expected and jobs[-1].resume is not None
    # an unreadable file is reported, not raised
    bad = tmp_path / "bad.npz"
    bad.write_bytes(b"junk")
    warned = []
    monkeypatch.setattr(ra.QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a)))
    monkeypatch.setattr(ra.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(bad), "")))
    actions.resume_render()
    assert warned and len(jobs) == 2
