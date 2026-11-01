"""Camera model: orientation quaternion, zoom, pan, perspective and framing mode.

See docs/camera.md.  World points are first normalised into the attractor's bounding
sphere (centre ``c``, radius ``R`` from :mod:`framing`) so the camera never needs to know
the attractor's scale: ``p_u = (p - c) / R``.  Then

    q      = rotate(p_u)                       (quaternion → 3×3 matrix)
    d      = max(1 + perspective · q.z, 0.05)  (perspective foreshortening, 0 = orthographic)
    u      = cx + focal · zoom · q.x / d + pan_u · W
    v      = cy - focal · zoom · q.y / d + pan_v · H
    focal  = FIT · min(W, H) / 2
    depth  = q.z   (in roughly [-1, 1]; used by Liquid/Solid/colour-by-depth)
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from attractr.core.math import quaternion as Q

FIT = 0.82  # fraction of the short side the unit sphere occupies (from the C rewrite)
FIT_MODES = ("sphere", "bbox")


@dataclass(frozen=True)
class Camera:
    rotation: tuple[float, float, float, float] = Q.IDENTITY
    zoom: float = 1.0
    pan_u: float = 0.0  # fraction of image width
    pan_v: float = 0.0  # fraction of image height
    perspective: float = 0.0  # 0 = orthographic … 1 = strong
    fit: str = "bbox"  # bbox (tight 2-D fit — default for stills) | sphere (rotation-invariant, animations)
    # locked framing (animations): when set, engines use this bounding sphere instead of
    # re-fitting per frame, so morphing parameters never make the image "breathe"
    lock_center: tuple[float, float, float] | None = None
    lock_radius: float | None = None

    @property
    def locked(self) -> bool:
        return self.lock_center is not None and self.lock_radius is not None

    # ── Euler convenience ───────────────────────────────────────────────────────
    @property
    def euler(self) -> tuple[float, float, float]:
        return Q.to_euler(self.rotation)

    @property
    def yaw(self) -> float:
        return self.euler[0]

    @property
    def pitch(self) -> float:
        return self.euler[1]

    @property
    def roll(self) -> float:
        return self.euler[2]

    def with_euler(self, yaw: float, pitch: float, roll: float) -> Camera:
        return replace(self, rotation=Q.from_euler(yaw, pitch, roll))

    def rotated_by(self, delta: tuple[float, float, float, float]) -> Camera:
        """Apply an incremental rotation (screen-space trackball delta)."""
        return replace(self, rotation=Q.normalize(Q.multiply(delta, self.rotation)))

    @staticmethod
    def from_euler(yaw: float = 0.0, pitch: float = 0.0, roll: float = 0.0, **kw) -> Camera:
        return Camera(rotation=Q.from_euler(yaw, pitch, roll), **kw)

    # ── matrices ────────────────────────────────────────────────────────────────
    def matrix(self) -> np.ndarray:
        return Q.to_matrix(self.rotation)

    def projection_constants(self, width: int, height: int) -> tuple[float, float, float]:
        """``(cx, cy, focal·zoom)`` in pixels for an output of ``width × height``."""
        focal = FIT * min(width, height) * 0.5 * self.zoom
        cx = width * 0.5 + self.pan_u * width
        cy = height * 0.5 + self.pan_v * height
        return cx, cy, focal

    def project(self, pts_unit: np.ndarray, width: int, height: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Vectorised reference projection of unit-space points ``[n, 3]`` → (u, v, depth).
        The engines re-implement exactly this in numba / GLSL / OpenCL."""
        R = self.matrix()
        q = pts_unit @ R.T
        d = np.maximum(1.0 + self.perspective * q[:, 2], 0.05)
        cx, cy, focal = self.projection_constants(width, height)
        u = cx + focal * q[:, 0] / d
        v = cy - focal * q[:, 1] / d
        return u, v, q[:, 2]
