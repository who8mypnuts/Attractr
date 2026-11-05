# Finance

`finance` · flow · 3-D · family: Flows

![Finance](images/finance.png)

A chaotic finance model (interest rate, investment demand, price index), with y shifted by 1/b.

## Equations

```text
dx/dt = (1 / b − a) · x + z + x · y
dy/dt = −b · y − x²
dz/dt = −x − c · z
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 3 | [1, 5] | Savings amount. |
| b | 0.1 | [0.05, 0.3] | Cost per investment. |
| c | 1 | [0.5, 2] | Elasticity of demand. |

Integration: RK4, default dt = 0.01, initial condition (1.0, -8.0, 0.5, 0.0).

## References

- J.-H. Ma & Y.-S. Chen, Appl. Math. Mech. 22 (2001)

## Source (`.atr`)

```text
name: Finance
family: Flows
desc: A chaotic finance model (interest rate, investment demand, price index), with y shifted by 1/b.
ref: J.-H. Ma & Y.-S. Chen, Appl. Math. Mech. 22 (2001)
tags: flow, 3d
dt: 0.01
ic: 1 -8 0.5
camera: 25 20 0 1

param a = 3.0 [1, 5] "Savings amount."
param b = 0.1 [0.05, 0.3] "Cost per investment."
param c = 1.0 [0.5, 2] "Elasticity of demand."

dx = (1/b - a)*x + z + x*y
dy = -b*y - x^2
dz = -x - c*z
```

Render it: `attractr render finance --size 2048x2048 --report md`
