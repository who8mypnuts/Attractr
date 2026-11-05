# Fractal tree

`barnsley_tree` · ifs · 2-D · family: IFS

![Fractal tree](images/barnsley_tree.png)

A symmetric branching tree from four affine maps — a trunk, two rotated branches and a small bud. The branch angle and shrink are exposed so it can be turned from a broccoli into a bare winter tree.

## Equations

```text
a = deg · 3.141592654 / 180
c = shrink · cos(a)
s = shrink · sin(a)
with p = 0.05:
    x′ = 0
    y′ = 0.5 · y
with p = 0.4:
    x′ = c · x − s · y
    y′ = s · x + c · y + 0.2
with p = 0.4:
    x′ = c · x + s · y
    y′ = −s · x + c · y + 0.2
with p = 0.15:
    x′ = 0.1 · x
    y′ = 0.1 · y + 0.2
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| deg | 45 | [10, 80] | Branch angle (degrees). |
| shrink | 0.6 | [0.4, 0.75] | Branch scale per level. |

## References

- M. F. Barnsley, "Fractals Everywhere" (1988); coefficients via P. Bourke

## Source (`.atr`)

```text
name: Fractal tree
family: IFS
desc: A symmetric branching tree from four affine maps — a trunk, two rotated branches and a small bud. The branch angle and shrink are exposed so it can be turned from a broccoli into a bare winter tree.
ref: M. F. Barnsley, "Fractals Everywhere" (1988); coefficients via P. Bourke
tags: ifs, 2d, classic
dims: 2
warmup: 20
ic: 0 0.5 0

param deg = 45 [10, 80] "Branch angle (degrees)."
param shrink = 0.6 [0.4, 0.75] "Branch scale per level."

a = deg*pi/180
c = shrink*cos(a)
s = shrink*sin(a)
choose {
  0.05: x' = 0;               y' = 0.5*y
  0.40: x' = c*x - s*y;       y' = s*x + c*y + 0.2
  0.40: x' = c*x + s*y;       y' = -s*x + c*y + 0.2
  0.15: x' = 0.1*x;           y' = 0.1*y + 0.2
}
```

Render it: `attractr render barnsley_tree --size 2048x2048 --report md`
