# Sprott C

`sprott_c` · flow · 3-D · family: Flows

![Sprott C](images/sprott_c.png)

One of J. C. Sprott's 19 simplest chaotic flows (case C) — five terms, one or two nonlinearities.

## Equations

```text
dx/dt = y · z
dy/dt = x − y
dz/dt = 1 − x²
```

Integration: RK4, default dt = 0.02, initial condition (0.1, 0.1, 0.1).

## References

- J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)

## Source (`.atr`)

```text
name: Sprott C
family: Flows
desc: One of J. C. Sprott's 19 simplest chaotic flows (case C) — five terms, one or two nonlinearities.
ref: J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)
tags: flow, sprott, 3d
dt: 0.02
ic: 0.1 0.1 0.1
camera: 25 20 0 1



dx = y*z
dy = x - y
dz = 1 - x^2
```

Render it: `attractr render sprott_c --size 2048x2048 --report md`
