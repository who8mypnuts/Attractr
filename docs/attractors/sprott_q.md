# Sprott Q

`sprott_q` · flow · 3-D · family: Flows

![Sprott Q](images/sprott_q.png)

One of J. C. Sprott's 19 simplest chaotic flows (case Q) — five terms, one or two nonlinearities.

## Equations

```text
dx/dt = −z
dy/dt = x − y
dz/dt = a · x + y² + b · z
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 3.1 | [2, 4] |  |
| b | 0.5 | [0.2, 1] |  |

Integration: RK4, default dt = 0.02, initial condition (0.1, 0.1, 0.1, 0.0).

## References

- J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)

## Source (`.atr`)

```text
name: Sprott Q
family: Flows
desc: One of J. C. Sprott's 19 simplest chaotic flows (case Q) — five terms, one or two nonlinearities.
ref: J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)
tags: flow, sprott, 3d
dt: 0.02
ic: 0.1 0.1 0.1
camera: 25 20 0 1

param a = 3.1 [2, 4]
param b = 0.5 [0.2, 1]

dx = -z
dy = x - y
dz = a*x + y^2 + b*z
```

Render it: `attractr render sprott_q --size 2048x2048 --report md`
