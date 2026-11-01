from attractr.core.animation import helpers
from attractr.core.animation.easing import get_easing, loop_time
from attractr.core.animation.timeline import Timeline, get_path
from attractr.core.attractors.registry import registry
from attractr.core.render.pipeline import default_settings


def test_easing_endpoints():
    for name in ("linear", "ease_in", "ease_out", "ease_in_out", "smooth", "hold"):
        f = get_easing(name)
        assert abs(f(0.0)) < 1e-9 and abs(f(1.0) - 1.0) < 1e-9
    bz = get_easing("bezier", (0.42, 0.0, 0.58, 1.0))
    assert abs(bz(0.5) - 0.5) < 0.02
    assert loop_time(2.5, 2.0, "loop") == 0.5 and loop_time(2.5, 2.0, "pingpong") == 1.5


def test_timeline_interpolates_params_and_camera():
    base = default_settings(registry.get("lorenz"))
    tl = Timeline(duration=2.0, fps=10)
    tl.set_key("params.rho", 0.0, 20.0, "linear")
    tl.set_key("params.rho", 2.0, 40.0, "linear")
    tl.set_key("camera.zoom", 0.0, 1.0, "linear")
    tl.set_key("camera.zoom", 2.0, 3.0, "linear")
    s = tl.evaluate(base, 1.0)
    assert abs(s.param_dict["rho"] - 30.0) < 1e-9 and abs(s.camera.zoom - 2.0) < 1e-9
    # round trip
    tl2 = Timeline.from_dict(tl.to_dict())
    assert tl2.evaluate(base, 0.5).param_dict["rho"] == tl.evaluate(base, 0.5).param_dict["rho"]


def test_turntable_is_seamless_and_morph_blends_gradient():
    base = default_settings(registry.get("aizawa"))
    tl = helpers.turntable(base, duration=4.0, fps=10)
    q0 = get_path(tl.evaluate(base, 0.0), "camera.rotation")
    q1 = get_path(tl.evaluate(base, 4.0), "camera.rotation")
    dot = abs(sum(a * b for a, b in zip(q0, q1, strict=True)))
    assert dot > 0.999  # same orientation after a full turn
    from dataclasses import replace

    from attractr.core.color.palettes import palettes

    b = replace(base, look=replace(base.look, gradient=palettes.get("fire"))).with_params(a=1.1)
    m = helpers.morph(base, b, duration=2.0, fps=10)
    mid = m.evaluate(base, 1.0)
    assert mid.look.gradient != base.look.gradient and mid.look.gradient != b.look.gradient
    assert abs(mid.param_dict["a"] - (0.95 + 1.1) / 2) < 1e-9
