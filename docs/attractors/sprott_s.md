# Sprott S

`sprott_s` · flow · 3-D · family: Flows

![Sprott S](images/sprott_s.png)

One of J. C. Sprott's 19 simplest chaotic flows (case S) — five terms, one or two nonlinearities.

## Equations

```text
dx/dt = −x − a · y
dy/dt = x + z²
dz/dt = b + x
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 4 | [2, 6] |  |
| b | 1 | [0.5, 2] |  |

Integration: RK4, default dt = 0.02, initial condition (0.1, 0.1, 0.1, 0.0).

## References

- J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)

## Source (`.atr`)

```text
name: Sprott S
family: Flows
desc: One of J. C. Sprott's 19 simplest chaotic flows (case S) — five terms, one or two nonlinearities.
ref: J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)
tags: flow, sprott, 3d
dt: 0.02
ic: 0.1 0.1 0.1
camera: 25 20 0 1

param a = 4.0 [2, 6]
param b = 1.0 [0.5, 2]

dx = -x - a*y
dy = x + z^2
dz = b + x
```

Render it: `attractr render sprott_s --size 2048x2048 --report md`
