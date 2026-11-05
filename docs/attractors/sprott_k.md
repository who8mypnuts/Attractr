# Sprott K

`sprott_k` · flow · 3-D · family: Flows

![Sprott K](images/sprott_k.png)

One of J. C. Sprott's 19 simplest chaotic flows (case K) — five terms, one or two nonlinearities.

## Equations

```text
dx/dt = x · y − z
dy/dt = x − y
dz/dt = a · x + b · z
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 1 | [0.5, 2] |  |
| b | 0.3 | [0.1, 0.6] |  |

Integration: RK4, default dt = 0.02, initial condition (0.1, 0.1, 0.1, 0.0).

## References

- J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)

## Source (`.atr`)

```text
name: Sprott K
family: Flows
desc: One of J. C. Sprott's 19 simplest chaotic flows (case K) — five terms, one or two nonlinearities.
ref: J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)
tags: flow, sprott, 3d
dt: 0.02
ic: 0.1 0.1 0.1
camera: 25 20 0 1

param a = 1.0 [0.5, 2]
param b = 0.3 [0.1, 0.6]

dx = x*y - z
dy = x - y
dz = a*x + b*z
```

Render it: `attractr render sprott_k --size 2048x2048 --report md`
