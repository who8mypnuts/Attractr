"""Offscreen GUI smoke test: window builds, preview renders, changes propagate, undo works."""

from conftest import pump


def test_main_window_preview_and_undo(app):
    from attractr.gui.main_window import MainWindow

    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    assert pump(app, 60, lambda: w.viewport._image is not None), "preview never arrived"
    rho0 = w.doc.settings.param_dict["rho"]
    w.doc.set_param("rho", rho0 + 5)
    assert w.doc.settings.param_dict["rho"] == rho0 + 5
    w.doc.undo_stack.undo()
    assert w.doc.settings.param_dict["rho"] == rho0
    # look change must not restart the preview (develop only)
    pump(app, 0.3)
    gen = w.preview._generation
    from dataclasses import replace

    w.doc.set_look(replace(w.doc.settings.look, gamma=0.7))
    pump(app, 0.3)
    assert w.preview._generation == gen
    # switching attractor rebuilds the parameter panel
    from attractr.core.attractors.registry import registry

    w.doc.set_attractor(registry.get("clifford"))
    pump(app, 0.2)
    assert set(w.params_panel.sliders) == {"a", "b", "c", "d", "e", "f"}
    w.doc.undo_stack.setClean()
    w.close()
    pump(app, 0.5)


def test_render_job_progressive_controls(app, tmp_path):
    """A queued render shows a live thumbnail, can be finished early and resumed."""
    from dataclasses import replace

    from attractr.core.render.checkpoint import Checkpoint, list_checkpoints
    from attractr.core.render.settings import Quality
    from attractr.gui.controllers.render_job import RenderJob
    from attractr.gui.main_window import MainWindow

    w = MainWindow()
    w.show()
    s = replace(w.doc.settings, quality=Quality(width=160, height=120, points_per_pixel=400, engine="cpu"))
    job = RenderJob(s, tmp_path, "{name}", checkpoint_every=0.5)
    w.submit_job(job)
    row = w.jobs_panel.rows[job.id]
    assert row.btn_finish.isVisibleTo(row) and row.btn_ckpt.isVisibleTo(row)
    pump(app, 3.0, lambda: row.thumb.pixmap() is not None and not row.thumb.pixmap().isNull())
    job.checkpoint_now()
    pump(app, 1.0, lambda: job.state != "running")
    if job.state == "running":
        job.finish_now()
    pump(app, 60, lambda: job.state != "running")
    assert job.state == "done", job.error
    assert job.output.image_path.exists()
    assert not job.checkpoint_file.exists()  # cleaned up after a successful save
    # a checkpoint file (simulated crash) can be resumed through a RenderJob
    res = job.output.result
    ck = Checkpoint.from_result(res)
    ck.iterations_done = res.stats.iterations_done // 2
    ck.count = ck.count * 0.5
    path = ck.save(tmp_path / "checkpoints" / "sim.attractr-ckpt.npz")
    assert list_checkpoints(tmp_path) == [path]
    job2 = RenderJob(ck.next_settings(), tmp_path, "{name}_resumed", resume=Checkpoint.load(path))
    w.submit_job(job2)
    pump(app, 60, lambda: job2.state != "running" and job2.state != "pending")
    assert job2.state == "done", job2.error
    assert any("Resumed" in n for n in job2.output.result.stats.notes)
    w.doc.undo_stack.setClean()
    w.close()
    pump(app, 0.5)


def test_drag_and_drop_payloads(app, tmp_path, monkeypatch):
    from PySide6.QtCore import QMimeData, QUrl

    import attractr.core.attractors.registry as registry_mod
    from attractr.core.attractors.registry import registry
    from attractr.gui import dragdrop
    from attractr.gui.main_window import MainWindow

    monkeypatch.setattr(registry_mod, "user_attractors_dir", lambda: tmp_path / "user_attractors")  # keep the real user folder clean
    (tmp_path / "user_attractors").mkdir()

    w = MainWindow()
    w.show()
    # palette swatch
    assert dragdrop.handle_drop(w, dragdrop.palette_mime("fire"))
    assert w.doc.settings.look.gradient.name.lower() == "fire"
    # share code as text
    from attractr.core.project.codes import settings_to_code

    m = QMimeData()
    m.setText(settings_to_code(w.doc.settings.with_params(rho=31.5)))
    assert dragdrop.can_accept(m) and dragdrop.handle_drop(w, m)
    assert abs(w.doc.settings.param_dict["rho"] - 31.5) < 1e-9
    # .atr file → imported as a user attractor and selected
    src = registry.get("clifford").source.replace("name: Clifford", "name: Dropped Clifford")
    f = tmp_path / "dropped_clifford.atr"
    f.write_text(src, encoding="utf-8")
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(str(f))])
    assert dragdrop.can_accept(m) and dragdrop.handle_drop(w, m)
    assert w.doc.spec.name == "Dropped Clifford" and not w.doc.spec.builtin
    # unrelated payloads are refused
    m = QMimeData()
    m.setText("hello")
    assert not dragdrop.can_accept(m)
    registry._specs.pop("dropped_clifford", None)
    w.doc.undo_stack.setClean()
    w.close()
    pump(app, 0.3)


def test_gallery_rerender_queues_jobs(app, tmp_path):
    from attractr.core.project.render_presets import render_presets
    from attractr.gui.main_window import MainWindow

    w = MainWindow()
    w.show()
    n = len(w.queue.pending) + len(w.queue.running)
    w.render_actions.rerender([w.doc.settings, w.doc.settings], render_presets.get("Draft 1024²"))
    jobs = w.queue.pending + w.queue.running
    assert len(jobs) == n + 2 and all(j.settings.quality.width == 1024 for j in jobs[-2:])
    w.queue.cancel_all()
    pump(app, 2.0, lambda: w.queue.is_idle)
    w.doc.undo_stack.setClean()
    w.close()
    pump(app, 0.3)
