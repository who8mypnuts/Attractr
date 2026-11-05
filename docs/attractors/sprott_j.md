# Sprott J

`sprott_j` · flow · 3-D · family: Flows

![Sprott J](images/sprott_j.png)

One of J. C. Sprott's 19 simplest chaotic flows (case J) — five terms, one or two nonlinearities.

## Equations

```text
dx/dt = a · z
dy/dt = −b · y + z
dz/dt = −x + y + y²
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 2 | [1, 3] |  |
| b | 2 | [1, 3] |  |

Integration: RK4, default dt = 0.02, initial condition (0.1, 0.1, 0.1, 0.0).

## References

- J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)

## Source (`.atr`)

```text
name: Sprott J
family: Flows
desc: One of J. C. Sprott's 19 simplest chaotic flows (case J) — five terms, one or two nonlinearities.
ref: J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)
tags: flow, sprott, 3d
dt: 0.02
ic: 0.1 0.1 0.1
camera: 25 20 0 1

param a = 2.0 [1, 3]
param b = 2.0 [1, 3]

dx = a*z
dy = -b*y + z
dz = -x + y + y^2
```

Render it: `attractr render sprott_j --size 2048x2048 --report md`
