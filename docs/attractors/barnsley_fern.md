# Barnsley Fern

`barnsley_fern` · ifs · 3-D · family: IFS

![Barnsley Fern](images/barnsley_fern.png)

Iterated function system. Four affine maps applied at random produce a fractal fern; the twist knob spirals the fronds out of the plane into 3-D (twist = 0 is the classic flat fern).

## Equations

```text
with p = 0.01:
    x′ = 0
    y′ = 0.16 · y
    z′ = 0.16 · z
with p = 0.85:
    cy = 0.85 · y
    cz = 0.85 · z
    x′ = 0.85 · width · x + (0.04 + lean) · y
    y′ = −(0.04 + lean) · x + cos(twist) · cy − sin(twist) · cz + 1.6
    z′ = sin(twist) · cy + cos(twist) · cz
with p = 0.07:
    x′ = 0.2 · x − 0.26 · y
    y′ = 0.23 · x + 0.22 · y + 1.6
    z′ = 0.3 · z
with p = 0.07:
    x′ = −0.15 · x + 0.28 · y
    y′ = 0.26 · x + 0.24 · y + 0.44
    z′ = 0.3 · z
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| width | 1 | [0.7, 1.3] | Width — fattens or thins each leaflet. |
| lean | 0 | [-0.2, 0.2] | Lean — shears the whole fern sideways. |
| twist | 0.2 | [0, 0.6] | Twist — rotation of the y–z plane per frond (radians); spirals the fern into 3-D. |

## References

- M. Barnsley, "Fractals Everywhere" (1988)

## Source (`.atr`)

```text
name: Barnsley Fern
family: IFS
desc: Iterated function system. Four affine maps applied at random produce a fractal fern; the twist knob spirals the fronds out of the plane into 3-D (twist = 0 is the classic flat fern).
ref: M. Barnsley, "Fractals Everywhere" (1988)
tags: ifs, classic, 3d
warmup: 50
ic: 0 0 0
palette: matrix
camera: 0 0 0 1

param width = 1.0 [0.7, 1.3] "Width — fattens or thins each leaflet."
param lean = 0.0 [-0.2, 0.2] "Lean — shears the whole fern sideways."
param twist = 0.2 [0, 0.6] "Twist — rotation of the y–z plane per frond (radians); spirals the fern into 3-D."

choose {
  0.01: x' = 0
        y' = 0.16*y
        z' = 0.16*z
  0.85: cy = 0.85*y
        cz = 0.85*z
        x' = 0.85*width*x + (0.04 + lean)*y
        y' = -(0.04 + lean)*x + cos(twist)*cy - sin(twist)*cz + 1.6
        z' = sin(twist)*cy + cos(twist)*cz
  0.07: x' = 0.2*x - 0.26*y
        y' = 0.23*x + 0.22*y + 1.6
        z' = 0.3*z
  0.07: x' = -0.15*x + 0.28*y
        y' = 0.26*x + 0.24*y + 0.44
        z' = 0.3*z
}
```

Render it: `attractr render barnsley_fern --size 2048x2048 --report md`
