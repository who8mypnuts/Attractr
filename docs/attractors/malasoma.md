# Malasoma jerk

`malasoma` · flow · 3-D · family: Flows

![Malasoma jerk](images/malasoma.png)

Malasoma's jerk equation x''' = −a·x'' + x·x' − x — the simplest chaotic jerk with a bilinear term, equivariant under x → −x.

## Equations

```text
dx/dt = y
dy/dt = z
dz/dt = −a · z + x · y − x
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 2.05 | [1.9, 2.2] | a — damping. |

Integration: RK4, default dt = 0.02, initial condition (1.0, 0.0, 0.0, 0.0).

## References

- J.-M. Malasoma, "What is the simplest dissipative chaotic jerk equation which is parity invariant?", Phys. Lett. A 264 (2000)

## Source (`.atr`)

```text
name: Malasoma jerk
family: Flows
desc: Malasoma's jerk equation x''' = −a·x'' + x·x' − x — the simplest chaotic jerk with a bilinear term, equivariant under x → −x.
ref: J.-M. Malasoma, "What is the simplest dissipative chaotic jerk equation which is parity invariant?", Phys. Lett. A 264 (2000)
tags: flow, jerk, 3d
dt: 0.02
ic: 1 0 0
jitter: 0.02
camera: 25 20 0 1

param a = 2.05 [1.9, 2.2] "a — damping."

dx = y
dy = z
dz = -a*z + x*y - x
```

Render it: `attractr render malasoma --size 2048x2048 --report md`
