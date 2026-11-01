# Sprott E

`sprott_e` · flow · 3-D · family: Flows

![Sprott E](images/sprott_e.png)

One of J. C. Sprott's 19 simplest chaotic flows (case E) — five terms, one or two nonlinearities.

## Equations

```text
dx/dt = y · z
dy/dt = x² − y
dz/dt = 1 − 4 · x
```

Integration: RK4, default dt = 0.02, initial condition (0.1, 0.1, 0.1).

## References

- J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)

## Source (`.atr`)

```text
name: Sprott E
family: Flows
desc: One of J. C. Sprott's 19 simplest chaotic flows (case E) — five terms, one or two nonlinearities.
ref: J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)
tags: flow, sprott, 3d
dt: 0.02
ic: 0.1 0.1 0.1
camera: 25 20 0 1



dx = y*z
dy = x^2 - y
dz = 1 - 4*x
```

Render it: `attractr render sprott_e --size 2048x2048 --report md`
