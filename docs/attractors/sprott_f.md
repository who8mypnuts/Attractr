# Sprott F

`sprott_f` · flow · 3-D · family: Flows

![Sprott F](images/sprott_f.png)

One of J. C. Sprott's 19 simplest chaotic flows (case F) — five terms, one or two nonlinearities.

## Equations

```text
dx/dt = y + z
dy/dt = −x + a · y
dz/dt = x² − b · z
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 0.5 | [0.1, 1] |  |
| b | 1 | [0.5, 2] |  |

Integration: RK4, default dt = 0.02, initial condition (0.1, 0.1, 0.1, 0.0).

## References

- J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)

## Source (`.atr`)

```text
name: Sprott F
family: Flows
desc: One of J. C. Sprott's 19 simplest chaotic flows (case F) — five terms, one or two nonlinearities.
ref: J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)
tags: flow, sprott, 3d
dt: 0.02
ic: 0.1 0.1 0.1
camera: 25 20 0 1

param a = 0.5 [0.1, 1]
param b = 1.0 [0.5, 2]

dx = y + z
dy = -x + a*y
dz = x^2 - b*z
```

Render it: `attractr render sprott_f --size 2048x2048 --report md`
