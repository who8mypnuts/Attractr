# Sprott A (Nosé–Hoover)

`sprott_a` · flow · 3-D · family: Flows

![Sprott A (Nosé–Hoover)](images/sprott_a.png)

Conservative — no parameters; a chaotic sea rather than an attractor.

## Equations

```text
dx/dt = y
dy/dt = −x + y · z
dz/dt = 1 − y²
```

Integration: RK4, default dt = 0.02, initial condition (0.0, 5.0, 0.0, 0.0).

## References

- J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)

## Source (`.atr`)

```text
name: Sprott A (Nosé–Hoover)
family: Flows
desc: Conservative — no parameters; a chaotic sea rather than an attractor.
ref: J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)
tags: flow, sprott, 3d
dt: 0.02
ic: 0 5 0
camera: 25 20 0 1



dx = y
dy = -x + y*z
dz = 1 - y^2
```

Render it: `attractr render sprott_a --size 2048x2048 --report md`
