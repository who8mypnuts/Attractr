# Pythagoras tree

`pythagoras_tree` · ifs · 2-D · family: IFS

![Pythagoras tree](images/pythagoras_tree.png)

The Pythagoras tree drawn with the chaos game plus a *condensation set*: two maps stack the two smaller squares on the unit square, and a third "map" (weight 0.3) re-seeds inside the trunk so the whole tree — not just its canopy — is filled in.

## Equations

```text
a = deg · 3.141592654 / 180
c = cos(a)
s = sin(a)
with p = 1:
    x′ = c · (c · x − s · y)
    y′ = c · (s · x + c · y) + 1
with p = 1:
    x′ = s · (c · x + s · y) + c · c
    y′ = s · (−s · x + c · y) + 1 + c · s
with p = 0.3:
    x′ = rand()
    y′ = rand()
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| deg | 45 | [20, 70] | Tilt of the left branch (45° is the symmetric tree). |

## References

- A. E. Bosman, "Het wondere onderzoekingsveld der vlakke meetkunde" (1957)

## Source (`.atr`)

```text
name: Pythagoras tree
family: IFS
desc: The Pythagoras tree drawn with the chaos game plus a *condensation set*: two maps stack the two smaller squares on the unit square, and a third "map" (weight 0.3) re-seeds inside the trunk so the whole tree — not just its canopy — is filled in.
ref: A. E. Bosman, "Het wondere onderzoekingsveld der vlakke meetkunde" (1957)
tags: ifs, 2d, classic
dims: 2
warmup: 10
ic: 0.5 0.5 0

param deg = 45 [20, 70] "Tilt of the left branch (45° is the symmetric tree)."

a  = deg*pi/180
c  = cos(a)
s  = sin(a)
choose {
  1:     x' = c*(c*x - s*y);           y' = c*(s*x + c*y) + 1
  1:     x' = s*(c*x + s*y) + c*c;     y' = s*(-s*x + c*y) + 1 + c*s
  0.3:   x' = rand();                  y' = rand()
}
```

Render it: `attractr render pythagoras_tree --size 2048x2048 --report md`
