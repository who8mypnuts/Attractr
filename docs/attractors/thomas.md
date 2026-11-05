# Thomas

`thomas` · flow · 3-D · family: Flows

![Thomas](images/thomas.png)

Cyclically symmetric — the same equation in x, y, and z. Looks like a tangled ball of yarn; below b ≈ 0.21 it becomes hyper-chaotic.

## Equations

```text
dx/dt = sin(y) − b · x
dy/dt = sin(z) − b · y
dz/dt = sin(x) − b · z
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| b | 0.208186 | [0.05, 0.5] | Damping — lower values make the orbit more chaotic. Below ≈ 0.21 it becomes hyperchaotic. |

Integration: RK4, default dt = 0.05, initial condition (0.1, 0.0, 0.0, 0.0).

## References

- R. Thomas, "Deterministic chaos seen in terms of feedback circuits", Int. J. Bifurcation Chaos 9 (1999)

## Source (`.atr`)

```text
name: Thomas
family: Flows
desc: Cyclically symmetric — the same equation in x, y, and z. Looks like a tangled ball of yarn; below b ≈ 0.21 it becomes hyper-chaotic.
ref: R. Thomas, "Deterministic chaos seen in terms of feedback circuits", Int. J. Bifurcation Chaos 9 (1999)
tags: flow, 3d
dt: 0.05
ic: 0.1 0 0
camera: 30 30 0 1
palette: electric
param b = 0.208186 [0.05, 0.5] "Damping — lower values make the orbit more chaotic. Below ≈ 0.21 it becomes hyperchaotic."

dx = sin(y) - b*x
dy = sin(z) - b*y
dz = sin(x) - b*z
```

Render it: `attractr render thomas --size 2048x2048 --report md`
