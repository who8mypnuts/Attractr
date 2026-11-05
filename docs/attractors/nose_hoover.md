# Nosé–Hoover

`nose_hoover` · flow · 3-D · family: Flows

![Nosé–Hoover](images/nose_hoover.png)

The Nosé–Hoover thermostat oscillator with its temperature parameter exposed (Sprott A is the special case a = 1). Conservative: chaotic seas threaded by regular tori rather than an attractor.

## Equations

```text
dx/dt = y
dy/dt = −x + y · z
dz/dt = a − y²
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| a | 1.5 | [0.2, 4] | a — thermostat temperature (a = 1 is Sprott A). |

Integration: RK4, default dt = 0.02, initial condition (0.0, 5.0, 0.0, 0.0).

## References

- W. G. Hoover, "Remark on some simple chaotic flows", Phys. Rev. E 51 (1995)

## Source (`.atr`)

```text
name: Nosé–Hoover
family: Flows
desc: The Nosé–Hoover thermostat oscillator with its temperature parameter exposed (Sprott A is the special case a = 1). Conservative: chaotic seas threaded by regular tori rather than an attractor.
ref: W. G. Hoover, "Remark on some simple chaotic flows", Phys. Rev. E 51 (1995)
tags: flow, conservative, 3d
dt: 0.02
ic: 0 5 0
camera: 25 20 0 1

param a = 1.5 [0.2, 4] "a — thermostat temperature (a = 1 is Sprott A)."

dx = y
dy = -x + y*z
dz = a - y^2
```

Render it: `attractr render nose_hoover --size 2048x2048 --report md`
