# Polynomial B

`polynomial_b` · map · 3-D · family: Maps

![Polynomial B](images/polynomial_b.png)

Chaoscope's "Polynomial B" — six coefficients of a quadratic 3-D map.

## Equations

```text
x′ = a0 + y − z · (a1 + y)
y′ = a2 + z − x · (a3 + z)
z′ = a4 + x − y · (a5 + x)
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a0 | 0.949 | [-1.5, 1.5] |  |
| a1 | 0.988 | [-1.5, 1.5] |  |
| a2 | -0.693 | [-1.5, 1.5] |  |
| a3 | -0.08 | [-1.5, 1.5] |  |
| a4 | 0.397 | [-1.5, 1.5] |  |
| a5 | 0.193 | [-1.5, 1.5] |  |

## Source (`.atr`)

```text
name: Polynomial B
family: Maps
desc: Chaoscope's "Polynomial B" — six coefficients of a quadratic 3-D map.
tags: map, 3d, polynomial, chaoscope
ic: 0.1 0.1 0.1
warmup: 200
camera: 25 20 0 1

param a0 = 0.949 [-1.5, 1.5]
param a1 = 0.988 [-1.5, 1.5]
param a2 = -0.693 [-1.5, 1.5]
param a3 = -0.08 [-1.5, 1.5]
param a4 = 0.397 [-1.5, 1.5]
param a5 = 0.193 [-1.5, 1.5]

x' = a0 + y - z*(a1 + y)
y' = a2 + z - x*(a3 + z)
z' = a4 + x - y*(a5 + x)
```

Render it: `attractr render polynomial_b --size 2048x2048 --report md`
