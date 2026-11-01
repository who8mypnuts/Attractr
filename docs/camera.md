# Camera & framing model

## World → unit space

The attractor is sampled once per (attractor, parameters, dt, seed) to find its **bounding
sphere** (centre `c`, radius `R`, using the 0.1–99.9 % percentiles so stray excursions are
ignored). Points are normalised: `p_u = (p − c) / R`. Because the sphere is
rotation-invariant, orbiting the camera never changes the apparent size — animations do
not “breathe”.

## Camera

| Field | Meaning |
|---|---|
| `rotation` | unit quaternion; edited as yaw/pitch/roll (degrees) — `R = Rz(roll)·Rx(pitch)·Ry(yaw)` |
| `zoom` | scale about the image centre |
| `pan_u`, `pan_v` | offset as a fraction of width/height |
| `perspective` | 0 = orthographic … 1 = strong foreshortening |
| `fit` | `bbox` (default for stills): extra zoom/pan so the projected cloud fills the frame with a 3 % margin · `sphere`: rotation-invariant framing for animations |

## Projection (identical in numba, GLSL and OpenCL)

```
q     = R · p_u
d     = max(1 + perspective · q.z, 0.05)
u     = cx + focal · zoom · q.x / d + pan_u · W
v     = cy − focal · zoom · q.y / d + pan_v · H         (v grows downward)
focal = 0.82 · min(W, H) / 2
depth = q.z                                             (negative = near the camera)
```

Image row 0 is the top; +y in world space points up on screen at the identity rotation.
