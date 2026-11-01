import json

from attractr.core.color.gradient import Gradient, Stop
from attractr.core.math import quaternion as Q
from attractr.core.render.camera import Camera
from attractr.core.render.settings import Quality, RenderSettings


def test_settings_json_roundtrip():
    s = RenderSettings(
        attractor="clifford",
        params=(("a", -1.4), ("b", 1.6)),
        camera=Camera.from_euler(30, 20, 5, zoom=1.3, perspective=0.4),
        quality=Quality(width=512, height=256, dt=0.01),
    )
    s2 = RenderSettings.from_dict(json.loads(json.dumps(s.to_dict())))
    assert s2 == s


def test_euler_roundtrip():
    for y, p, r in [(0, 0, 0), (30, 20, 5), (-120, 80, 170), (45, -45, -90)]:
        q = Q.from_euler(y, p, r)
        y2, p2, r2 = Q.to_euler(q)
        assert abs(y - y2) < 1e-6 and abs(p - p2) < 1e-6 and abs(r - r2) < 1e-6


def test_gradient_lut_endpoints_and_cycle():
    g = Gradient((Stop(0, 1, 0, 0), Stop(1, 0, 0, 1)), cyclic=True)
    lut = g.lut(256)
    assert lut.shape == (256, 4)
    assert tuple(lut[0, :3]) == (1, 0, 0) and tuple(lut[-1, :3]) == (0, 0, 1)
    rot = g.lut(256, phase=0.5)
    assert abs(rot[0, 2] - 0.5) < 0.02  # half way through after rotating
    assert Gradient.from_dict(g.to_dict()) == g


def test_quality_iterations():
    assert Quality(width=100, height=10, points_per_pixel=3).iterations == 3000
