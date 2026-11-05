# Qi-Chen

`qi_chen` · flow · 3-D · family: Flows

![Qi-Chen](images/qi_chen.png)

A four-wing system by Qi, Chen et al.

## Equations

```text
dx/dt = a · (y − x) + y · z
dy/dt = c · x + y − x · z
dz/dt = x · y − b · z
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 38 | [30, 45] |  |
| b | 2.66667 | [1, 5] |  |
| c | 80 | [60, 100] |  |

Integration: RK4, default dt = 0.001, initial condition (0.1, 0.1, 0.1, 0.0).

## References

- G. Qi et al., Chaos Solitons Fractals (2005)

## Source (`.atr`)

```text
name: Qi-Chen
family: Flows
desc: A four-wing system by Qi, Chen et al.
ref: G. Qi et al., Chaos Solitons Fractals (2005)
tags: flow, 3d
dt: 0.001
ic: 0.1 0.1 0.1
camera: 25 20 0 1

param a = 38 [30, 45]
param b = 8/3 [1, 5]
param c = 80 [60, 100]

dx = a*(y - x) + y*z
dy = c*x + y - x*z
dz = x*y - b*z
```

Render it: `attractr render qi_chen --size 2048x2048 --report md`
