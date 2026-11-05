# Thomas (asymmetric)

`thomas_asym` · flow · 3-D · family: Flows

![Thomas (asymmetric)](images/thomas_asym.png)

René Thomas' cyclically symmetric labyrinth with a separate damping per axis. Breaking the symmetry stretches the woolly ball along one direction and changes which tunnels the orbit prefers.

## Equations

```text
dx/dt = sin(y) − b1 · x
dy/dt = sin(z) − b2 · y
dz/dt = sin(x) − b3 · z
```

## Parameters

| Name | Default | Range | Meaning |
|---|---|---|---|
| b1 | 0.132 | [0, 0.4] | Damping on x. |
| b2 | 0.093 | [0, 0.4] | Damping on y. |
| b3 | 0.172 | [0, 0.4] | Damping on z. |

Integration: RK4, default dt = 0.05, initial condition (0.1, 0.0, 0.0, 0.0).

## References

- R. Thomas, "Deterministic chaos seen in terms of feedback circuits", Int. J. Bifurcation and Chaos 9 (1999)

## Source (`.atr`)

```text
name: Thomas (asymmetric)
family: Flows
desc: René Thomas' cyclically symmetric labyrinth with a separate damping per axis. Breaking the symmetry stretches the woolly ball along one direction and changes which tunnels the orbit prefers.
ref: R. Thomas, "Deterministic chaos seen in terms of feedback circuits", Int. J. Bifurcation and Chaos 9 (1999)
tags: flow, 3d
dt: 0.05
ic: 0.1 0 0
camera: 25 20 0 1

param b1 = 0.132 [0, 0.4] "Damping on x."
param b2 = 0.093 [0, 0.4] "Damping on y."
param b3 = 0.172 [0, 0.4] "Damping on z."

dx = sin(y) - b1*x
dy = sin(z) - b2*y
dz = sin(x) - b3*z
```

Render it: `attractr render thomas_asym --size 2048x2048 --report md`
