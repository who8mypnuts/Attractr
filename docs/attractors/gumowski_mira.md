# Gumowski-Mira

`gumowski_mira` · map · 2-D · family: Maps

![Gumowski-Mira](images/gumowski_mira.png)

A 2-D map from plasma physics (CERN, 1980). Tends toward delicate, organic curves that look like seashells or jellyfish.

## Equations

```text
fx = μ · x + 2 · (1 − μ) · x² / (1 + x²)
x′ = y + a · (1 − 0.05 · y²) · y + fx
fxn = μ · x′ + 2 · (1 − μ) · x′² / (1 + x′²)
y′ = −x + fxn
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 0.008 | [-1, 1] | Damping — close to 0 keeps orbits open; further from 0 tightens loops. |
| mu | -0.496 | [-1, 1] | μ — shape of the nonlinear function f(x); sweeps between bulbs and spikes. |

## References

- I. Gumowski & C. Mira, "Recurrences and Discrete Dynamic Systems" (1980)

## Source (`.atr`)

```text
name: Gumowski-Mira
family: Maps
desc: A 2-D map from plasma physics (CERN, 1980). Tends toward delicate, organic curves that look like seashells or jellyfish.
ref: I. Gumowski & C. Mira, "Recurrences and Discrete Dynamic Systems" (1980)
tags: map, 2d
warmup: 200
dims: 2

param a = 0.008 [-1, 1] "Damping — close to 0 keeps orbits open; further from 0 tightens loops."
param mu = -0.496 [-1, 1] "μ — shape of the nonlinear function f(x); sweeps between bulbs and spikes."

fx  = mu*x + 2*(1 - mu)*x^2/(1 + x^2)
x'  = y + a*(1 - 0.05*y^2)*y + fx
fxn = mu*x' + 2*(1 - mu)*x'^2/(1 + x'^2)
y'  = -x + fxn
```

Render it: `attractr render gumowski_mira --size 2048x2048 --report md`
