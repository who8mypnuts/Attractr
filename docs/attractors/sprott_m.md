# Sprott M

`sprott_m` · flow · 3-D · family: Flows

![Sprott M](images/sprott_m.png)

One of J. C. Sprott's 19 simplest chaotic flows (case M) — five terms, one or two nonlinearities.

## Equations

```text
dx/dt = −z
dy/dt = −x² − y
dz/dt = a + b · x + y
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 1.7 | [1, 2.5] |  |
| b | 1.7 | [1, 2.5] |  |

Integration: RK4, default dt = 0.02, initial condition (0.1, 0.1, 0.1).

## References

- J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)

## Source (`.atr`)

```text
name: Sprott M
family: Flows
desc: One of J. C. Sprott's 19 simplest chaotic flows (case M) — five terms, one or two nonlinearities.
ref: J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)
tags: flow, sprott, 3d
dt: 0.02
ic: 0.1 0.1 0.1
camera: 25 20 0 1

param a = 1.7 [1, 2.5]
param b = 1.7 [1, 2.5]

dx = -z
dy = -x^2 - y
dz = a + b*x + y
```

Render it: `attractr render sprott_m --size 2048x2048 --report md`
