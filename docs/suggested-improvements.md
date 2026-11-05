# Suggested improvements

Ideas that are **not implemented** — collected here for review. Nothing in this file
changes the program; each item notes the effort and what it would touch.

## 1. More attractors for the library

All of these fit the existing formula DSL (maps, flows or IFS with `choose`), so each one
is a single `.atr` file once its parameters are verified with *Search*/the Lyapunov probe.

### Maps (2-D / 3-D)

| Name | Equations (DSL) | Why it is interesting |
|---|---|---|
| **Zaslavskii web map** | `x' = mod(x + v*(1 + mu*y) + eps*v*mu*cos(2*pi*x), 1)` `y' = exp(-r)*(y + eps*cos(2*pi*x))` | stochastic web / dissipative sea; classic textbook map |
| **Cathala** | `x' = a*x + y` `y' = b + x^2` | minimal quadratic map with a thin, folded attractor |
| **Martin "Quadrup-Two"** | `x' = y - sign(x)*sin(log(abs(b*x - c)))*atan((log(abs(c*x - b)))^2)` `y' = a - x` | Hopalong's wilder sibling (lace-like bursts) |
| **Martin "Threeply"** | `x' = y - sign(x)*abs(sin(x)*cos(b) + c - x*sin(a + b + c))` `y' = a - x` | third Martin map from the *Scientific American* column |
| **Chossat–Golubitsky "Symmetry in Chaos" icons (D_n with extra terms)** | extend `symmetric_icon` with the `delta*|z|^2` and `p` (pinwheel) terms | covers every icon in the book's gallery |
| **Ushiki** | `x' = (a - x - b*y)*x` `y' = (c - y - d*x)*y` | predator–prey map with a spiky 2-D attractor |
| **Dejong variants (“Strange Attractor No. 4–7”)** | `x' = sin(a*y) + c*cos(a*x) + ... *cos(b*x)` families from Pickover's *Computers, Pattern, Chaos and Beauty* | cheap additions with known-good constants |
| **Burning Ship / Mandelbrot escape as IFS-like map** | `x' = x^2 - y^2 + cx` `y' = 2*abs(x*y) + cy` for many random starts with escape reseeding | gives a "chaotic fill" view of escape-time fractals |
| **Gumowski–Mira variants** | `x' = y + a*y*(1 - b*y^2) + f(x)` with different `f` | several classic GM shapes ("pearl", "cloud") |
| **Duffing–van der Pol map** | `x' = y` `y' = -b*x + (a - c*y^2)*y` | bridge between the Duffing and van der Pol families |
| **Lorenz map / Rössler map** (Poincaré sections) | needs a small DSL extension (`section = expr`) to sample a flow only when a plane is crossed | 1-D/2-D return maps are a staple of chaos teaching |

### Flows (3-D ODEs)

| Name | Equations (DSL) | Parameters |
|---|---|---|
| **Nosé–Hoover (a ≠ 1)** | `dx = y` `dy = -x + y*z` `dz = a - y^2` | a = 1.5 |
| **Sprott–Jafari "NE" family** | e.g. NE6: `dx = y` `dy = -x + y*z` `dz = a - y^2`-style minimal systems with no equilibria | a = 0.5… |
| **Hadley (full form)** | `dx = -y^2 - z^2 - a*x + a*F` `dy = x*y - b*x*z - y + G` `dz = b*x*y + x*z - z` | already present as Lorenz-84; add the b = 4, F = 8, G = 1.2 "spring" preset |
| **Langford / Aizawa-Langford (c ≠ 0.6)** | present as Aizawa; add Langford's original parameterisation | a=0.95 b=0.7 c=0.6 d=3.5 e=0.25 f=0.1 |
| **Thomas variants (non-cyclic)** | `dx = sin(y) - b*x` `dy = sin(z) - b*y` `dz = sin(x) - b*z` with `b` per axis | interesting symmetry breaking |
| **Rayleigh–Bénard / Lorenz–Stenflo (4-D)** | needs a 4th state variable | would require the DSL to support `w'`/`dw` |
| **Wang–Sun**, **Zhou**, **Pehlivan**, **Wei**, **Sprott Case-A+**: | many quadratic 3-D flows from the 2010s literature | each is 3 lines of DSL |
| **Anishchenko–Astakhov** | `dx = m*x + y - x*z` `dy = -x` `dz = -g*z + g*step(0, x)*x^2` | piecewise; m = 1.2, g = 0.5 |
| **Rössler hyperchaos (4-D)** | needs 4-D state | |
| **Elegant chaos (Sprott 2010) collection** | dozens of "elegant" jerk systems `dz = -a*z - y + f(x)` with |f| = abs, sign, x^2… | the book lists them all with parameters |
| **Driven systems** (Duffing, van der Pol, Ueda) | `dt = 1` as a third state and plot `(x, y)` only | needs a "plot only these coordinates" option in the DSL (e.g. `plot = x, y, 0`) |

### IFS / chaos-game additions

Sierpinski carpet (8 maps), Vicsek fractal, Koch snowflake (4 maps), Lévy C-curve,
Pythagoras tree, **de Rham curves**, **Barnsley's "leaf" and "tree"**, Hutchinson random
trees, the **"Chaos game on a regular n-gon with restriction rules"** family
(e.g. pentagon, no repeated vertex) — each a short `choose { … }` block.

### Needed DSL extensions to unlock the rest

* `w'` / `dw` — a 4th state variable (hyperchaotic systems, driven oscillators).
* `plot = expr, expr, expr` — choose what is drawn (Poincaré sections, projections).
* `section = expr` — sample a flow only when an expression changes sign.

## 2. Three program improvements

1. **GL 3.3 point-splat engine (`gl_points`)** — planned in M2 and still deferred. It
   would give hardware acceleration on macOS (OpenGL 4.1, no compute) and on older
   Intel/ARM drivers. Design: trajectories live in two RGBA32F ping-pong textures; a
   fragment shader advances them (same generated `step()`), a vertex shader reads the
   state texture and emits `gl_Points` with additive blending into an R32F framebuffer.
   Effort: ~2 days; touches `core/render/engines/gl_points.py` and a new shader pair.
2. **GPU develop pass + "hot" look changes on the GPU** — today the histogram is read
   back to NumPy and developed on the CPU (≈ 30–80 ms at 1024², seconds at 8K). Running
   tone-mapping, palette lookup and lighting in a compute/fragment shader would make
   gradient/gamma edits instant even for full-size renders kept on the GPU, and allow a
   16K "print preview" without readback. Effort: ~2 days; `develop.comp`, a GPU
   percentile (histogram reduction), `DevelopController` selecting the GPU path.
3. **Progressive refinement for final renders + pause/resume** — the precision engine
   already works in passes; exposing them as a *progressive* final render (show the
   image improving in the viewport, allow "stop here and save", save/load checkpoints of
   the accumulation buffers as `.npz`) would let very long renders survive interruptions
   and let users judge quality early. Effort: ~1 day (job checkpoint files, a "Finish
   now" button, resuming passes from stored buffers).

## 3. Three quality-of-life improvements

1. **Parameter "nudge + scrub" ergonomics** — `Ctrl`-wheel over a slider for fine steps,
   arrow keys with `Shift`/`Ctrl` multipliers, and a small "±10 % / ±1 %" button pair on
   each `SliderSpin`; plus a *parameter history* drop-down (last 20 values) so a good
   value found by accident can be recovered without undo-stepping through everything.
2. **Palette and preset drag-and-drop** — drag a palette swatch from the gradient
   library onto the viewport to apply it, drag a gallery image onto the viewport to
   re-open its settings, and drag `.atr` files onto the window to import them. All three
   are a `dragEnterEvent/dropEvent` on the viewport plus existing functions.
3. **Render presets & batch** — named render presets ("Instagram 1080²", "A3 print 300 dpi
   16-bit + PDF report") in the render dialog, and a "batch render queue from a folder of
   `.attractr` projects / a preset list" command (`attractr batch dir/`) so an overnight
   run produces a whole portfolio with reports. Also a desktop notification when the
   queue finishes.

## 4. Smaller items noticed during implementation

* The **Solid** style needs ≥ 20 points/pixel to look clean; a per-style "recommended
  quality" hint in the render dialog would help.
* Thumbnails for *user* formulas are keyed by content hash, so editing a formula
  generates new cache files; a cache pruning preference (max MB) would keep
  `~/.attractr/cache/thumbs` bounded.
* The **Search** panel could get a "polynomial map" mode that searches the 30-coefficient
  Sprott map space directly (the classic Chaoscope behaviour) with its own default
  ranges, rather than requiring the Polynomial Sprott attractor to be selected first.
* Export of the current view as **SVG polylines** (orbit trace) would give vector art for
  plotters/laser cutters — a small addition to the orbit-trace helper.
