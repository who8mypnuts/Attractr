# Chen

`chen` · flow · 3-D · family: Flows

![Chen](images/chen.png)

Chen's system — a Lorenz-family double scroll with a bridge between the lobes.

## Equations

```text
dx/dt = a · (y − x)
dy/dt = (c − a) · x − x · z + c · y
dz/dt = x · y − b · z
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 35 | [20, 45] | Coupling a(y − x). |
| b | 3 | [1, 6] | Damping of z. |
| c | 28 | [15, 35] | Growth of y. |

Integration: RK4, default dt = 0.005, initial condition (0.1, 0.0, 0.0).

## References

- G. Chen & T. Ueta, Int. J. Bifurcation Chaos 9 (1999)

## Source (`.atr`)

```text
name: Chen
family: Flows
desc: Chen's system — a Lorenz-family double scroll with a bridge between the lobes.
ref: G. Chen & T. Ueta, Int. J. Bifurcation Chaos 9 (1999)
tags: flow, 3d
dt: 0.005
ic: 0.1 0 0
camera: 25 20 0 1

param a = 35 [20, 45] "Coupling a(y − x)."
param b = 3 [1, 6] "Damping of z."
param c = 28 [15, 35] "Growth of y."

dx = a*(y - x)
dy = (c - a)*x - x*z + c*y
dz = x*y - b*z
```

Render it: `attractr render chen --size 2048x2048 --report md`
