# Spiral IFS

`spiral_ifs` · ifs · 2-D · family: IFS

![Spiral IFS](images/spiral_ifs.png)

A two-map IFS whose dominant map is a slow rotation-and-shrink — fern-like spirals of spirals.

## Equations

```text
with p = 0.9:
    x′ = sc · (x · cos(rot) − y · sin(rot))
    y′ = sc · (x · sin(rot) + y · cos(rot))
with p = 0.1:
    x′ = leaf · x + 1
    y′ = leaf · y
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| rot | 0.25 | [0.05, 1] | Rotation per step (radians). |
| sc | 0.96 | [0.85, 0.99] | Contraction of the spiral map. |
| leaf | 0.3 | [0.1, 0.5] | Size of the side copy. |

## Source (`.atr`)

```text
name: Spiral IFS
family: IFS
desc: A two-map IFS whose dominant map is a slow rotation-and-shrink — fern-like spirals of spirals.
tags: ifs, 2d
dims: 2
warmup: 30
ic: 0 0 0

param rot = 0.25 [0.05, 1.0] "Rotation per step (radians)."
param sc = 0.96 [0.85, 0.99] "Contraction of the spiral map."
param leaf = 0.3 [0.1, 0.5] "Size of the side copy."

choose {
  0.9: x' = sc*(x*cos(rot) - y*sin(rot));  y' = sc*(x*sin(rot) + y*cos(rot))
  0.1: x' = leaf*x + 1;                    y' = leaf*y
}
```

Render it: `attractr render spiral_ifs --size 2048x2048 --report md`
