# Sprott L

`sprott_l` · flow · 3-D · family: Flows

![Sprott L](images/sprott_l.png)

One of J. C. Sprott's 19 simplest chaotic flows (case L) — five terms, one or two nonlinearities.

## Equations

```text
dx/dt = y + a · z
dy/dt = 0.9 · x² − y
dz/dt = b − x
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 3.9 | [2, 5] |  |
| b | 1 | [0.5, 2] |  |

Integration: RK4, default dt = 0.02, initial condition (0.1, 0.1, 0.1).

## References

- J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)

## Source (`.atr`)

```text
name: Sprott L
family: Flows
desc: One of J. C. Sprott's 19 simplest chaotic flows (case L) — five terms, one or two nonlinearities.
ref: J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)
tags: flow, sprott, 3d
dt: 0.02
ic: 0.1 0.1 0.1
camera: 25 20 0 1

param a = 3.9 [2, 5]
param b = 1.0 [0.5, 2]

dx = y + a*z
dy = 0.9*x^2 - y
dz = b - x
```

Render it: `attractr render sprott_l --size 2048x2048 --report md`
