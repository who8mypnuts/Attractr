# Attractr Formula DSL — specification (draft for review)

The formula language is the **single source of truth** for every attractor — built-in or
user-written. One text → parser → AST → three back-ends:

```
                    ┌──────────────┐
   .atr text ──────▶│  parser      │──▶ AST ──┬──▶ codegen_numba  → @njit step()   (CPU engine, fp64)
                    │ (Pratt, ours)│          ├──▶ codegen_glsl   → GLSL step()    (GPU engines, fp32/fp64)
                    └──────────────┘          ├──▶ pretty/LaTeX   → Info panel, docs, reports
                                              └──▶ symbolic (sympy, optional) → Jacobian for Lyapunov
```

Why our own parser instead of Python `ast`/`eval`: the grammar must be *identical* on CPU
and GPU, must be safe to run on untrusted text, and must reject anything we cannot
translate to GLSL. A Pratt parser for this grammar is ~300 lines.

## 1. File structure

```text
# comments start with '#'
name: Clifford                         # display name (required)
kind: map                              # map | flow | ifs | escape
dims: 3                                # 2 or 3 (default 3)
desc: A classic 2-D iterative map lifted into 3-D ...
ref: https://paulbourke.net/fractals/clifford/

param a = -1.4  [-3, 3]   "Horizontal sine drive — ..."
param b =  1.6  [-3, 3]
param c =  1.0  [-3, 3]
param d =  0.7  [-3, 3]
param e =  1.5  [-3, 3]
param f =  0.5  [-3, 3]

x' = sin(a*y) + c*cos(a*x)
y' = sin(b*x) + d*cos(b*y)
z' = sin(e*y) + f*cos(e*z)
```

Header keys (all optional except `name`): `kind`, `dims`, `desc`, `ref`, `author`,
`dt` (default step for flows), `ic` (nominal initial condition `x y z [w]` — the optional
fourth number seeds `w`, which is otherwise 0),
`warmup` (steps to discard), `jitter` (spread of the initial conditions), `camera`
(default yaw/pitch/roll/zoom), `palette`, `style`, `tags`, `lyapunov` (λ₁ hint shown in the
Info panel) and `boost` (iteration multiplier ≥ 1 — use it on Poincaré-section programs so
that a normal points-per-pixel setting still yields a dense picture; the stats report the
boosted budget).

`param NAME = DEFAULT [MIN, MAX] "hint"` — min/max are soft slider bounds; optional
`step=` and `int` flag (`param n = 3 [3, 12] int`).

### Statements

| Form | Meaning |
|---|---|
| `x' = expr` / `y' = expr` / `z' = expr` / `w' = expr` | map update (all right-hand sides use **old** values) |
| `dx = expr` / `dy = expr` / `dz = expr` / `dw = expr` | flow derivative |
| `t = expr` | local temporary (may be used in later lines; first letter lowercase identifier not x/y/z/w) |
| `depth = expr` | optional: depth value for 2-D maps lifted into 3-D (Icon uses `Re(z^n)`) |
| `color = expr` | optional: per-point colour driver (overrides the "Colour source" setting when present) |
| `plot = ex, ey[, ez]` | optional: what is *drawn* instead of `(x, y, z)` — any expressions of the state (two expressions → a 2-D image) |
| `section = expr` | optional: Poincaré section — a point is plotted only when `expr` changes sign between consecutive steps (direction: header `section_dir`) |
| `on_section { stmts }` | optional: assignments to `x'`/`y'`/`z'`/`w'` applied after each plotted crossing (return maps; needs `section`) |
| `choose { p1: stmts ; p2: stmts ; ... }` | IFS: pick one block at random with the given probabilities (normalised) |

Exactly one of `{x',y',z',w'}` or `{dx,dy,dz,dw}` sets must be present (a 2-D system may omit
`z'`/`dz`; it is treated as 0).

### The fourth state variable `w`

Every trajectory carries four numbers `(x, y, z, w)`. `w` is never drawn directly; it is a
free extra dimension for:

* **hyperchaotic 4-D systems** (Rössler hyperchaos, Lorenz–Stenflo, …) — write `dw = …` and
  use `plot = x, y, z` (the default) or `plot = x, y, w` to pick a 3-D projection;
* **driven / non-autonomous systems** — `dw = 1` turns `w` into time, so
  `dy = … + gamma*cos(omega*w)` is a forcing term (Duffing, van der Pol, Ueda);
* anything you want to hide from the picture — counters, phases, auxiliary accumulators.

`w` is reset to `ic[3]` (default 0) when a trajectory restarts after diverging.

### `kind: escape` — escape-time systems (Buddhabrot and friends)

```text
name: Buddhabrot
kind: escape
dims: 2
region: -2.2 1.2 -1.7 1.7     # where orbit starts are drawn from (xmin xmax ymin ymax [zmin zmax])
bailout: 2                    # an orbit has escaped once |(x, y, z)| > bailout
max_iter: 500                 # orbits still bounded after this many steps are discarded
min_iter: 20                  # orbits that escape sooner than this are discarded
x' = x*x - y*y + x0
y' = 2*x*y + y0
color = w
```

An escape-time system draws **the paths of orbits that escape**. Every trajectory starts at
a uniformly random point of `region`; that start is visible to the update statements as
`x0`, `y0`, `z0` (in the Mandelbrot iteration it is the constant *c*). The orbit is
iterated without drawing until it either escapes (radius > `bailout`, or diverges) or runs
for `max_iter` steps. Bounded orbits are discarded; an orbit that escaped after *n* ≥
`min_iter` steps is **replayed** from its start and its *n* − 1 bounded points are drawn,
then a new start is chosen. During the replay `w` holds the escape count *n*, so
`color = w` colours by escape time; `w` cannot be assigned. Statements use map syntax
(`x' =`), `choose` and `section` are not allowed, and `x0`/`y0`/`z0` are reserved only in
this kind (the polynomial map keeps its `x0`… coefficients). The frame is the start region
(no attractor to sample), the Lyapunov probe reports *escape-time*, and because most
iterations are spent probing, escape programs usually set `boost:` (10–30). The
`gl_points` engine does not run escape programs; the other engines share the same orbit
state machine.

### `on_section { … }` — return maps with memory

```text
on_section {
  w' = z          # remember this crossing's z for the next one
}
```

The block holds assignments to `x'`, `y'`, `z'`, `w'` (and temporaries) that are applied to
the state **right after a point has been plotted at a section crossing**. Because the
plotted point is evaluated before the block runs, `plot = w, z, 0` with the block above
draws (zₙ, zₙ₊₁) — the classic Lorenz return map of successive z maxima — and
`section_dir: down` with `section = x*y - beta*z` (that is, dz) selects the maxima. Events
fire during warm-up as well, so the memory is valid before the first plotted point. The
`gl_points` engine cannot run programs with an `on_section` block (the engine selector
skips it).

### `plot` and `section`

`plot` decouples *what is integrated* from *what is drawn*. Before projection the kernel
evaluates the three plot expressions; framing, depth, gap filling and colouring all use
the plotted point. `plot = x, y` (two expressions) marks the attractor as 2-D.

`section = expr` keeps only the points where `expr` crosses zero (strict sign change between
the previous and the current step), i.e. a **Poincaré section** of the flow. The header
`section_dir: both | up | down` (default `both`) restricts the crossing direction
(`up` = − → +, `down` = + → −); with `section = dz` and `section_dir: down` a point is
plotted at every **maximum** of z. Gap filling is
automatically disabled because consecutive plotted points are no longer neighbours. A
section plots one point per crossing, so a flow that crosses every ~500 steps needs a
**much higher points-per-pixel** setting than a normal render (the stats panel shows the
plotted fraction). For a periodically-driven system with `dw = 1` use
`section = sin(omega*w/2)` to sample once per forcing period (a stroboscopic map).

## 2. Expressions

* Literals: `1`, `0.5`, `1e-3`, `pi`, `e`, `tau`.
* Variables: `x y z` (state), params, temporaries, `t_step` (iteration index, float),
  `rand()` (uniform [0,1)), `randn()` (normal).
* Operators (precedence low→high): `+ -` · `* / %` · unary `-` · `^` (right assoc.).
  Comparison `< <= > >= == !=` and logical `and or not` are allowed **only** inside
  `select(cond, a, b)`.
* Functions: `sin cos tan asin acos atan atan2 sinh cosh tanh asinh acosh atanh exp log
  log2 log10 sqrt cbrt abs sign floor ceil round fract mod pow min max clamp mix
  smoothstep step select hypot`.
  Complex helpers for icons: `re_pow(x, y, n)`, `im_pow(x, y, n)` (real/imag part of
  (x+iy)^n, codegen expands to a loop or closed form).

Anything not in this list is a parse error with a caret and message shown in the editor.

## 3. Semantics guaranteed identical on CPU and GPU

* All state and arithmetic in **float64 on CPU**, **float32 on GPU preview**, float64 on
  the precision GPU engine when the device supports `GL_ARB_gpu_shader_fp64` (trig
  functions then use our own fp64 polynomial implementations because GLSL has none).
  The test-suite renders every built-in at low resolution on CPU and GPU and requires the
  histograms to agree statistically (KL divergence below a threshold) — bit-exactness is
  impossible for chaotic systems and not needed.
* `rand()` — xorshift32 per trajectory on both back-ends with the same seeding scheme so
  IFS renders are reproducible across engines.
* Divergence: if any component (including `w`) is non-finite or `|v| > 1e6`, the trajectory
  is re-seeded (counted in stats as a *restart*).
* `%`/`mod` follow GLSL `mod` (result has the sign of the divisor); numba codegen
  emulates that.

## 4. Validation pipeline (runs on every keystroke, debounced 300 ms)

1. Parse → syntax errors (line/col).
2. Semantic checks: unknown identifiers, wrong arity, `x'` assigned twice, mixing `x'` and
   `dx`, probabilities in `choose` ≤ 0, unused params (warning).
3. GLSL compile of the generated preview shader (fast, ~10 ms) → driver errors mapped back
   to source lines.
4. Quick numeric probe on CPU (1 000 steps × 64 trajectories, fp64): diverges? fixed
   point? estimate largest Lyapunov exponent → badge: **chaotic / periodic / divergent**.
5. Preview restarts with the new formula; numba compilation of the CPU version happens in
   the background thread and is only *needed* for CPU rendering (cached on disk by hash).

## 5. Examples

Flow:
```text
name: Lorenz
kind: flow
dt: 0.005
ic: (0.1, 0, 0)
param sigma = 10 [0, 20]  "σ (Prandtl number) — fluid viscosity. Standard value is 10."
param rho   = 28 [0, 50]
param beta  = 2.6667 [0, 5]
dx = sigma*(y - x)
dy = x*(rho - z) - y
dz = x*y - beta*z
```

IFS (Barnsley fern with 3-D twist):
```text
name: Barnsley Fern
kind: ifs
param width = 1.0 [0.7, 1.3]
param lean  = 0.0 [-0.2, 0.2]
param twist = 0.2 [0, 0.6]
choose {
  0.01: x' = 0;                        y' = 0.16*y;                                  z' = 0.16*z
  0.85: cy = 0.85*y; cz = 0.85*z
        x' = 0.85*width*x + (0.04+lean)*y
        y' = -(0.04+lean)*x + cos(twist)*cy - sin(twist)*cz + 1.6
        z' = sin(twist)*cy + cos(twist)*cz
  0.07: x' = 0.2*x - 0.26*y;  y' = 0.23*x + 0.22*y + 1.6;  z' = 0.3*z
  0.07: x' = -0.15*x + 0.28*y; y' = 0.26*x + 0.24*y + 0.44; z' = 0.3*z
}
```

Symmetric icon (general):
```text
name: Symmetric Icon
kind: map
param lam = -2.5 [-4, -1]
param al  =  5.0 [1, 8]
param be  = -1.8 [-3, 0.5]
param ga  =  1.0 [0.1, 2]
param om  =  0.0 [-1, 1]
param n   =  3   [3, 12] int
zz   = x*x + y*y
ren  = re_pow(x, y, n)
imn  = im_pow(x, y, n)
t    = lam + al*zz + be*ren
cr   = re_pow(x, -y, n-1)          # conj(z)^(n-1)
ci   = im_pow(x, -y, n-1)
x'   = t*x - om*y + ga*cr
y'   = t*y + om*x + ga*ci
depth = ren
```

Driven oscillator and its stroboscopic Poincaré section (uses `w` as time):
```text
name: Duffing (driven)
kind: flow
dt: 0.01
ic: 0.1 0 0 0
param delta = 0.3 [0, 1]
param gamma = 0.5 [0, 1]
param omega = 1.2 [0.5, 2]
dx = y
dy = x - x^3 - delta*y + gamma*cos(omega*w)
dz = 0
dw = 1
plot = x, y, 0
section = sin(omega*w/2)      # remove this line for the full phase-space flow
```

Hyperchaotic Rössler (4-D, projected onto x, y, z):
```text
name: Rössler hyperchaos
kind: flow
dt: 0.005
ic: -10 -6 0 10
param a = 0.25 [0, 0.5]
param b = 3 [0, 5]
param c = 0.5 [0, 1]
param d = 0.05 [0, 0.2]
dx = -y - z
dy = x + a*y + w
dz = b + x*z
dw = -c*z + d*w
```

## 6. Editor UX (see Plan §7.4)

Syntax highlighting (keywords, params, state vars, functions, numbers, comments), line
numbers, error squiggles + message bar, autocompletion of functions/params, live status
badge (compiled in N ms · Lyapunov λ≈…), "Insert template" menu (map / flow / ifs /
icon), "Fork built-in" (opens any built-in attractor's source as a starting point),
"Save to my attractors" (`~/.attractr/attractors/*.atr`, hot-reloaded into the browser).
