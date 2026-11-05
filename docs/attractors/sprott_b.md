# Sprott B

`sprott_b` · flow · 3-D · family: Flows

![Sprott B](images/sprott_b.png)

One of Sprott's minimal chaotic systems — just two quadratic terms, yet it traces a broad swirling disc.

## Equations

```text
dx/dt = a · y · z
dy/dt = x − y
dz/dt = 1 − b · x · y
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 1 | [0.5, 2] | Coupling — scales the y·z drive that feeds the swirl. |
| b | 1 | [0.5, 2] | Damping of the z growth. |

Integration: RK4, default dt = 0.02, initial condition (0.1, 0.1, 0.1, 0.0).

## References

- J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)

## Source (`.atr`)

```text
name: Sprott B
family: Flows
desc: One of Sprott's minimal chaotic systems — just two quadratic terms, yet it traces a broad swirling disc.
ref: J. C. Sprott, "Some simple chaotic flows", Phys. Rev. E 50 (1994)
tags: flow, sprott, 3d
dt: 0.02
ic: 0.1 0.1 0.1
camera: 25 20 0 1

param a = 1.0 [0.5, 2] "Coupling — scales the y·z drive that feeds the swirl."
param b = 1.0 [0.5, 2] "Damping of the z growth."

dx = a*y*z
dy = x - y
dz = 1 - b*x*y
```

Render it: `attractr render sprott_b --size 2048x2048 --report md`
