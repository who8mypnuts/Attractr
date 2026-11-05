# Sprott P

`sprott_p` · flow · 3-D · family: Flows

![Sprott P](images/sprott_p.png)

One of J. C. Sprott's 19 simplest chaotic flows (case P) — five terms, one or two nonlinearities.

## Equations

```text
dx/dt = a · y + z
dy/dt = −x + y²
dz/dt = x + b · y
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 2.7 | [1.5, 4] |  |
| b | 1 | [0.5, 2] |  |

Integration: RK4, default dt = 0.02, initial condition (0.1, 0.1, 0.1, 0.0).

## References

- J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)

## Source (`.atr`)

```text
name: Sprott P
family: Flows
desc: One of J. C. Sprott's 19 simplest chaotic flows (case P) — five terms, one or two nonlinearities.
ref: J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)
tags: flow, sprott, 3d
dt: 0.02
ic: 0.1 0.1 0.1
camera: 25 20 0 1

param a = 2.7 [1.5, 4]
param b = 1.0 [0.5, 2]

dx = a*y + z
dy = -x + y^2
dz = x + b*y
```

Render it: `attractr render sprott_p --size 2048x2048 --report md`
