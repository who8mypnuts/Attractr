"""Unit quaternions for camera orientation.

Convention: ``q = (w, x, y, z)``; rotation matrices are row-major 3×3 applied as ``R @ p``.
Euler angles follow the documented Attractr camera model (see docs/camera.md):
yaw about **Y** (vertical axis), pitch about **X**, roll about **Z** (screen normal),
composed as ``R = Rz(roll) · Rx(pitch) · Ry(yaw)``.  Angles are in degrees.
"""

from __future__ import annotations

import math

import numpy as np

Quat = tuple[float, float, float, float]

IDENTITY: Quat = (1.0, 0.0, 0.0, 0.0)


def normalize(q: Quat) -> Quat:
    w, x, y, z = q
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if n == 0.0:
        return IDENTITY
    return (w / n, x / n, y / n, z / n)


def multiply(a: Quat, b: Quat) -> Quat:
    """Hamilton product ``a * b`` (apply ``b`` first, then ``a``)."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def conjugate(q: Quat) -> Quat:
    w, x, y, z = q
    return (w, -x, -y, -z)


def from_axis_angle(axis: tuple[float, float, float], angle_deg: float) -> Quat:
    ax, ay, az = axis
    n = math.sqrt(ax * ax + ay * ay + az * az)
    if n == 0.0:
        return IDENTITY
    half = math.radians(angle_deg) * 0.5
    s = math.sin(half) / n
    return normalize((math.cos(half), ax * s, ay * s, az * s))


def to_matrix(q: Quat) -> np.ndarray:
    w, x, y, z = normalize(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def from_euler(yaw: float, pitch: float, roll: float) -> Quat:
    """Build ``Rz(roll) · Rx(pitch) · Ry(yaw)`` as a quaternion (degrees)."""
    qy = from_axis_angle((0.0, 1.0, 0.0), yaw)
    qx = from_axis_angle((1.0, 0.0, 0.0), pitch)
    qz = from_axis_angle((0.0, 0.0, 1.0), roll)
    return normalize(multiply(qz, multiply(qx, qy)))


def to_euler(q: Quat) -> tuple[float, float, float]:
    """Inverse of :func:`from_euler`; returns (yaw, pitch, roll) in degrees."""
    m = to_matrix(q)
    # R = Rz(c)·Rx(b)·Ry(a) ⇒ m[2,1] = sin b ; m[2,0] = -cos b·sin a ; m[2,2] = cos b·cos a ;
    # m[0,1] = -sin c·cos b ; m[1,1] = cos c·cos b
    sb = max(-1.0, min(1.0, m[2, 1]))
    pitch = math.asin(sb)
    if abs(sb) < 0.999999:
        yaw = math.atan2(-m[2, 0], m[2, 2])
        roll = math.atan2(-m[0, 1], m[1, 1])
    else:  # gimbal lock: fold roll into yaw
        yaw = math.atan2(m[0, 2], m[0, 0])
        roll = 0.0
    return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)


def slerp(a: Quat, b: Quat, t: float) -> Quat:
    """Spherical linear interpolation along the shortest arc."""
    a = normalize(a)
    b = normalize(b)
    dot = sum(i * j for i, j in zip(a, b, strict=True))
    if dot < 0.0:
        b = tuple(-c for c in b)  # type: ignore[assignment]
        dot = -dot
    if dot > 0.9995:
        out = tuple(ai + (bi - ai) * t for ai, bi in zip(a, b, strict=True))
        return normalize(out)  # type: ignore[arg-type]
    theta0 = math.acos(dot)
    theta = theta0 * t
    s0 = math.cos(theta) - dot * math.sin(theta) / math.sin(theta0)
    s1 = math.sin(theta) / math.sin(theta0)
    return normalize(tuple(s0 * ai + s1 * bi for ai, bi in zip(a, b, strict=True)))  # type: ignore[arg-type]


def rotate_vector(q: Quat, v: tuple[float, float, float]) -> tuple[float, float, float]:
    m = to_matrix(q)
    r = m @ np.asarray(v, dtype=np.float64)
    return float(r[0]), float(r[1]), float(r[2])
