# Ikeda

`ikeda` · map · 2-D · family: Maps

![Ikeda](images/ikeda.png)

Light in a ring cavity (Ikeda, 1979) — spiralling arms that fold back on themselves.

## Equations

```text
t = c − d / (1 + x² + y²)
x′ = a + b · (x · cos(t) − y · sin(t))
y′ = b · (x · sin(t) + y · cos(t))
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 1 | [0, 2] | Input amplitude. |
| b | 0.9 | [0, 1] | Cavity loss (contraction). |
| c | 0.4 | [0, 1] | Phase offset. |
| d | 6 | [1, 12] | Nonlinear phase strength. |

## References

- K. Ikeda, Opt. Commun. 30 (1979)

## Source (`.atr`)

```text
name: Ikeda
family: Maps
desc: Light in a ring cavity (Ikeda, 1979) — spiralling arms that fold back on themselves.
ref: K. Ikeda, Opt. Commun. 30 (1979)
tags: map, 2d, optics
dims: 2
ic: 0.1 0.1 0
warmup: 200

param a = 1.0 [0, 2] "Input amplitude."
param b = 0.9 [0, 1] "Cavity loss (contraction)."
param c = 0.4 [0, 1] "Phase offset."
param d = 6.0 [1, 12] "Nonlinear phase strength."

t  = c - d/(1 + x^2 + y^2)
x' = a + b*(x*cos(t) - y*sin(t))
y' = b*(x*sin(t) + y*cos(t))
```

Render it: `attractr render ikeda --size 2048x2048 --report md`
