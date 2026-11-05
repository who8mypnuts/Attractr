# Attractr — Master Plan

> **Status: APPROVED — in implementation.** This document is the contract for what gets
> built, in what order, and how we will know it is done. Decisions from the review are in §17.
> Companion documents: [source_analysis.md](source_analysis.md) (what the three source
> folders contain, what is wrong in them), [attractor_catalog.md](attractor_catalog.md)
> (every attractor, equation, default), [formula_dsl.md](formula_dsl.md) (the user
> formula language).

---

## 0. TL;DR

Attractr is a desktop **strange-attractor studio** written in Python 3.12 + PySide6. It
merges everything from the three sample sources — the Android/C++ *Chaoscope*
re-imagining (interaction model, styles, presets, video modes, GPU compute), the pure-C
rewrite (42 flows, RK4, splats, supersampling, percentile tone-mapping, colour-by,
rotation-stable framing) and the WebGL experiment (progressive accumulation,
density-per-pixel, duotone compositing, caption overlay) — fixes the defects found in
them, and adds: a formula DSL with a code editor, a gradient editor, an animator with
keyframes + ffmpeg, statistics/info panels everywhere, render reports (md/txt/html/pdf),
a CLI, and two GPU engines (fast preview, precise final) with a multi-threaded CPU
fallback.

Build order: **core engine → GPU engines → GUI shell → editors & panels → animator →
polish/search/packaging**, six milestones, each with acceptance tests.

---

## 1. Vision, goals, non-goals

**Vision.** The program a chaos nerd wants open all day: instant feedback while
dragging sliders or the camera, a print-quality renderer for the final image, numbers
everywhere (Lyapunov exponents, coverage, histograms, timings, device info), and the
freedom to type a new formula and see it.

**Goals**

1. Faithfully reproduce every user-visible feature of the source programs (§2, matrix in
   `source_analysis.md` §5), corrected where they were wrong.
2. Responsive: the UI thread never blocks; preview updates within one frame of a change.
3. Beautiful output: float accumulation, anti-aliased splats, supersampling, proper
   render modes, 16-bit export.
4. Hardware-agnostic GPU: OpenGL 3.3/4.3 through ModernGL works on NVIDIA, AMD, Intel,
   Apple (4.1 path) and Mesa software; CPU fallback through numba is always available
   and is the *reference* implementation.
5. Extensible: attractors, palettes, render styles, engines and exporters are plug-ins
   discovered by registries; the DSL lets users add attractors without Python.
6. Scriptable: everything the GUI does, the CLI does (`attractr render|animate|list|info`).
7. Documented: every module has a page in `docs/`.

**Non-goals (v1)**: mobile/web builds, network features, 4-D+ systems (hyperchaos) beyond
the DSL's three state variables plus time, real-time ray-marched volumetrics.

---

## 2. Where the features come from (summary)

| From | We take | We fix |
|---|---|---|
| **chaoscope_original** (Android/C++) | 17 attractors + param metadata/hints/descriptions, 10 palettes, 6 styles, quality tiers, curated presets, dot-preview-while-dragging, look-change-without-reiterating, retry/undo, daily attractor, preset codes, gallery, 4 video modes, GPU compute histogram design | Euler→RK4, max-pixel→percentile tone-map, breathing bounds→sphere framing, crude Plasma/Solid→real modes, GPU fallback gaps, marketing features dropped |
| **chaoscope_rewrite** (C) | 42 flows with references, RK4 + divergence restart, unit-sphere framing, perspective, splat kernels + gap filling, supersampling, percentile normalisation, colour-by modes, cyclic palettes + phase, machine-readable catalogue, preview-then-full-render GUI pattern | single trajectory, qsort percentile, BMP-only, child-process GUI |
| **strange-attractors-webgl** | progressive per-frame accumulation, density-per-pixel iteration budget, dark/light/duotone compositing, formula+parameter caption on export, Bedhead & Fractal Dream | wrong Clifford formula, 8-bit saturating accumulation |
| **classic Chaoscope** (reference) | Search (Lyapunov), Polynomial maps, real Gas/Light/Liquid/Plasma/Solid, gradient editor, lights | — |

Full detail: [source_analysis.md](source_analysis.md).

---

## 3. Engineering principles

1. **Small files, one job each.** Target ≤ 300 lines per module, ≤ 40 lines per function.
   A module is named for the one thing it does (`tonemap.py`, `trackball.py`).
2. **DRY through single sources of truth.** Attractors are DSL files → CPU code, GPU
   code, docs, Info panel all generated. Palettes are JSON → LUTs. Settings dataclasses →
   GUI bindings, JSON schema, CLI flags and report fields all derive from one definition.
3. **Unix philosophy.** Engines are filters: `RenderSettings → RenderResult`. Developers
   (tone-mappers) are filters: `RenderResult → Image`. Exporters are filters. The CLI
   composes them; the GUI composes the same objects. Everything serialises to JSON.
4. **Negative / print separation.** *Accumulation* (iterate + histogram, expensive) is
   separate from *development* (tone-map + palette + background, cheap). Look changes
   never re-iterate. This one decision makes the app feel instant.
5. **Never block the GUI thread.** All work runs in `QThread`/`QRunnable` workers or in
   time-sliced GPU passes; communication only via Qt signals/slots (queued connections);
   cancellation via atomic flags checked between passes; progress + ETA on every job.
6. **Determinism.** Every render has a seed; same seed + same settings + same engine ⇒
   same image. Reports record everything needed to reproduce.
7. **Immutable settings objects.** `frozen=True` dataclasses flow through the system; the
   document holds the current one; workers receive copies; undo is a stack of them.
8. **Typed, tested, documented.** Type hints everywhere, `pytest` for core, offscreen Qt
   for GUI smoke tests, a doc page per package.

---

## 4. Technology decisions (verified in this sandbox)

| Concern | Choice | Why / verification |
|---|---|---|
| Language / GUI | Python 3.12, **PySide6 6.12** | required; installed and QOpenGLContext 4.3 core verified |
| Array math | **NumPy** | everywhere for buffers, LUTs, tone-mapping |
| CPU engine | **numba** `@njit(parallel=True, nogil=True, fastmath=False)` | verified 19 M points/s on 4 software threads here (≈ 50 M iterations ≈ 2.5 s); scales with cores; releases the GIL so the GUI stays live; fp64 — this is the *reference* engine |
| GPU access | **ModernGL 5.13** (+ glcontext) | thin, Pythonic OpenGL; standalone contexts for worker threads; shares the GL context of the Qt viewport. Compute shader with `imageAtomicAdd` + SSBO `atomicMax` **verified working** here on Mesa llvmpipe (GL 4.5) |
| Preview engine | GLSL **compute** (GL ≥ 4.3) with **GL 3.3 fallback** (additive point splats into R32F FBO via transform-feedback-free vertex shader iteration) | compute covers Windows/Linux on all vendors; the 3.3/4.1 path covers macOS and old drivers |
| Precision engine | same ModernGL compute core, but: fp32 with **Kahan-style compensated accumulation for flows**, optional **fp64 state** where `GL_ARB_gpu_shader_fp64` exists, float histogram (R32F atomics emulated via uint fixed-point 24.8 or two-pass), splat kernels, supersampling, tiles, multi-pass progressive | "strong and precise" = numerical care + quality features, not just bigger numbers |
| Optional extra engine | **pyopencl** (plug-in, not required) | native fp64 on AMD/NVIDIA/Intel and CPUs; only if the user installs it |
| Formula compiler | own Pratt parser → AST → numba source & GLSL source | see `formula_dsl.md`; both back-ends from one AST |
| Images | **Pillow** (PNG 8/16-bit, TIFF, JPEG, WebP), NumPy for EXR-less HDR (`.npy` float dump optional) | |
| Video | **ffmpeg** on PATH (found `/usr/bin/ffmpeg`), fallback to `imageio-ffmpeg`'s bundled binary if present | frames → H.264/H.265/ProRes/VP9/GIF |
| PDF reports | **Qt** `QTextDocument` → `QPdfWriter` (no extra dependency); HTML/Markdown/TXT from our own templates (Jinja-free f-strings) | `reportlab` available as optional upgrade |
| Persistence | JSON project files (`.attractr`), `QSettings` for preferences, `~/.attractr/` for user attractors/palettes/presets/cache | |
| Tests | pytest, pytest-qt (offscreen), hypothesis for the parser | |
| Packaging | `pyproject.toml`, `pip install -e .`, PyInstaller spec for Win/macOS/Linux (M6) | |

Minimum GPU feature levels: GL 3.3 for preview (point splats), GL 4.3 for compute
(Windows/Linux), GL 4.1 on macOS → 3.3 preview path + CPU precision engine (OpenCL
optional). CPU-only machines: numba for everything (preview at reduced points).

---

## 5. Architecture

### 5.1 Layers

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  attractr.gui  (PySide6)   MainWindow · Viewport(QOpenGLWidget) · Docks/Panels │
│     widgets: SliderSpin, GradientEditor, FormulaEditor, StatsTable, Timeline   │
│     controllers: PreviewController, RenderQueue, AnimationController           │
├──────────────────────────────────────────────────────────────────────────────┤
│  attractr.cli   (argparse)   render · animate · list · info · thumb · report    │
├──────────────────────────────────────────────────────────────────────────────┤
│  attractr.core  (no Qt imports except QtCore signals in .core.jobs)             │
│   formula/   parser → AST → codegen (numba, glsl, pretty)                       │
│   attractors/ registry of AttractorSpec (built-ins = .atr files + user files)   │
│   render/    RenderSettings · Camera · framing · engines/ · develop/ · stats    │
│   color/     Gradient · Palette registry · LUT                                  │
│   animation/ Timeline · Keyframe · easing · FrameSequence · ffmpeg              │
│   project/   Document (JSON) · presets · codes · gallery index                  │
│   report/    RenderReport → md/txt/html/pdf                                     │
│   io/        image export, naming, paths                                        │
└──────────────────────────────────────────────────────────────────────────────┘
```
`attractr.core` is importable without a display (the CLI and tests use it headless).

### 5.2 Data flow for one render

```
Document ──▶ RenderSettings (frozen) ──▶ Engine.accumulate() ──▶ RenderResult
                 │                          (GPU or CPU,             ├─ hist   float32 [H,W]  (or uint32)
                 │                           tiles, passes)          ├─ depth  float32 [H,W]  (sum of w)
                 │                                                   ├─ color  float32 [H,W,3] (sum of per-point colour) — optional
                 │                                                   ├─ zmin   float32 [H,W] (Solid mode z-buffer) — optional
                 │                                                   └─ stats  RenderStats
                 └──▶ LookSettings ──▶ Developer.develop(result, look) ──▶ RGBA image (float → 8/16-bit)
                                         (tone-map · style · palette LUT · depth/lighting · background)
```
Changing anything in `LookSettings` only re-runs `develop()` (numpy/GPU, ~10–50 ms at
4K). Changing attractor/params/camera/quality re-runs `accumulate()`.

### 5.3 Threading model

| Thread | Owns | Talks via |
|---|---|---|
| GUI thread | widgets, `Document`, `QUndoStack`, the viewport GL context | signals |
| **Preview scheduler** (GUI thread, inside `paintGL`) | progressive GPU passes with a ~8 ms budget per frame (like the WebGL loop); the GPU runs asynchronously so the frame is never blocked waiting | `QOpenGLWidget.update()` |
| **CPU preview worker** (QThread, only when no GPU) | numba accumulation in chunks (~100 ms) → posts `np.ndarray` histograms | `chunkReady(ndarray)` |
| **Render worker** (QThread, one per job, queued by `RenderQueue`) | its own ModernGL standalone context (created *in* the worker thread) or numba; precision engine; writes tiles/passes | `progress(float, eta)`, `passDone(preview ndarray)`, `finished(RenderResult)`, `failed(str)` |
| **Develop worker** (QThreadPool runnable) | re-develops the last full-size result when look changes (debounced 50 ms); coalesces — only the latest request runs | `imageReady(QImage)` |
| **Probe worker** (one-shot at startup) | GPU capability probe (context creation, compute test dispatch, fp64 check), numba warm-up compile of the current attractor | `capabilities(Caps)` |
| **Analysis worker** (QThreadPool) | Lyapunov exponent, fractal dimension, thumbnails for the attractor browser, Search candidates | `statsReady`, `thumbReady` |
| **Animation worker** (QThread) | drives the render queue frame by frame, writes PNGs, then runs ffmpeg (QProcess) | `frameDone(i, path)`, `encodingProgress` |

Cancellation: each job has a `threading.Event`; engines check it between passes/tiles
(≤ 100 ms latency). GL contexts are never shared across threads; results cross threads
as NumPy arrays.

### 5.4 Signals & slots spine

```
Document.changed(field_set)            → PreviewController.onDocumentChanged  → restart/continue preview
Document.lookChanged()                 → DevelopController.redevelop           → viewport.setImage
Viewport.cameraDragged(Camera)         → Document.setCamera (merged undo cmd)
Engine job signals                     → RenderDialog / StatusBar / Gallery
FormulaEditor.compiled(AttractorSpec)  → Document.setAttractor(spec, keepParams=True)
GradientEditor.gradientChanged(Gradient) → Document.setGradient (look change only)
Timeline.timeChanged(t)                → Document.applyKeyframeState(t) (preview follows scrubbing)
```

---

## 6. Core engine design

### 6.1 Attractor specification & registry
* `AttractorSpec` (frozen dataclass): id, name, kind (`map|flow|ifs`), dims, params
  (`ParamSpec`: symbol, name, default, soft range, hard range, step, hint, animatable),
  AST, default dt/ic/warmup, description, references, default camera/palette, tags,
  presets, source text, content hash.
* `registry.py` loads `resources/attractors/**/*.atr` (built-ins: ~52 tier-1 + ~30 tier-2)
  and `~/.attractr/attractors/*.atr` (user), watches the user dir for changes.
* Built-in catalogue = [attractor_catalog.md](attractor_catalog.md).
* Ported Android metadata (hints, descriptions) and C references go into the `.atr`
  headers.

### 6.2 Iteration & integrators
* **Trajectories**: N parallel trajectories (default 65 536 on GPU, `threads × 4096` on
  CPU), each seeded from `ic + jitter` (LCG/xorshift per trajectory, global seed).
* **Warm-up**: per-attractor default (1000 steps, as in the C++ source) — discarded.
* **Maps**: one point per step. **Flows**: RK4 default; Euler and RK2 (midpoint)
  selectable; `dt` default per system, with "substeps" option (integrate k sub-steps per
  plotted point for smoother curves without changing dt semantics).
* **Divergence**: non-finite or `|v| > 1e6` → reseed; counted. If > 50 % of trajectories
  restart in a pass → job reports "divergent" (no silent 4× retry as Android did).
* **Orbit Trace mode**: a single trajectory, points kept in order (for the animation mode
  and for the "speed/curvature" colouring that needs consecutive points — in N-trajectory
  mode each trajectory keeps its own previous point, so Light mode works everywhere).

### 6.3 Camera & framing (fixes A3, A11, C4)
* **Scene fit** (once per attractor+params, cached): sample ~65 k points after warm-up →
  bounding box centre `c` and bounding-sphere radius `R` (robust: 99.9 % percentile of
  radius to ignore stray points). World → unit space: `p_u = (p − c)/R`.
* **Camera** (`Camera` dataclass): rotation as a quaternion (edited by a trackball in the
  viewport; yaw/pitch/roll sliders read/write Euler ZYX), `zoom`, `pan (u,v)`,
  `perspective ∈ [0,1]` (0 = orthographic, C rewrite's fixed 0.5 becomes adjustable),
  `fit = sphere | bbox2d` (bbox2d = C's `--autofit` + Android's behaviour, for stills),
  `lock_bounds` (for animations).
* Projection: `q = rotate(p_u)`; `d = 1 + perspective·q.z` (clamped ≥ 0.05);
  `u = cx + focal·zoom·q.x/d + pan`, focal = `0.82·min(W,H)/2`. Depth `w = q.z` kept for
  depth/lighting styles.
* Because the fit is rotation-invariant, turntables don't "breathe" and presets don't
  need hacks.

### 6.4 Render styles (modes) — all implemented on all engines
Accumulators available per pixel: `count` (float, splat-weighted), `depth_sum`,
`zmin` (nearest depth), `color_sum[3]`, `speed_sum` (optional). Styles decide which are
needed; engines allocate only those.

| Style | Accumulates | Develop | Notes |
|---|---|---|---|
| **Gas** | count | `log(1+count)/log(1+P)` where P = percentile (default 99.8 %) → gamma → palette | classic Chaoscope; Android STANDARD |
| **Dust** | count | `(count/P)^0.25` | Android "GAS"=Dust |
| **Light** | count, color_sum (per-point colour from Colour source: speed default), curvature weight | mean colour × log-density brightness | Android Light generalised: colour source selectable |
| **Liquid** | count, depth_sum, zmin | log-density × depth attenuation `(1 − k·depth_norm)` + **screen-space normals from the zmin buffer → Phong lighting** (key light dir/colour, ambient, specular) | real depth shading, not a single multiplier |
| **Solid** | zmin, count | z-buffer surface: pixels with count ≥ threshold are opaque; normals from zmin gradient; lighting; background elsewhere; optional edge AA from count | classic "Solid" look |
| **Plasma** | count, color_sum | cyclic palette indexed by density × `bands` + `phase` (animatable) with soft glow (separable blur on a low-res copy added back) | replaces fmod hack |

Orthogonal **Colour source** (from the C rewrite `--colorby`): density (default) · x · y ·
depth · speed · radius · trajectory-index · formula `color =` expression. Any style can
use any source where it makes sense (Gas with colour-by-speed = C rewrite behaviour).

Common develop options: percentile `P` (0.9–1.0), gamma, brightness, contrast/`S`-curve,
**histogram equalisation** ("Full range", Android), invert (WebGL light mode), palette
phase & cycles, background (solid / transparent / gradient / image / procedural
Stars-Forest-Ocean-Aurora ports), vignette (optional), output dithering for 8-bit.

### 6.5 Engines
Common interface (`engines/base.py`):
```python
class Engine(Protocol):
    id: str; name: str; caps: EngineCaps            # max_size, fp64, styles, compute
    def accumulate(self, s: RenderSettings, sink: PassSink, cancel: Event) -> RenderResult
```
`PassSink.on_pass(partial_result, fraction)` lets the GUI show progressive refinement and
lets the precision engine stream tiles.

| Engine | File | Role |
|---|---|---|
| `cpu_numba` | `engines/cpu_numba.py` | reference; fp64; `prange` over trajectory slices with private histograms merged (Android design); splats + gap-fill (C design); always available |
| `gl_compute_preview` | `engines/gl_compute.py` | GL 4.3 compute: per-invocation trajectory, `imageAtomicAdd` into `r32ui` (+ `r32f` accumulators via `imageAtomicAdd` on uint fixed-point where float atomics are absent), SSBO running max; fp32; time-sliced passes (`iters_per_pass` auto-tuned to ~8 ms) |
| `gl_points_preview` | `engines/gl_points.py` | GL 3.3 fallback: trajectories advanced in a fragment shader ping-pong (state textures), points drawn additively into R32F FBO; same shader `step()` code |
| `gl_precision` | `engines/gl_precision.py` | builds on `gl_compute`: supersampling (1–4×), splat kernels r 0–4 with bilinear sub-pixel, gap filling, compensated sums, optional fp64 state (`#extension GL_ARB_gpu_shader_fp64`), **tiles** when `W·H·bytes > budget` (each tile re-runs trajectories with tile bounds — deterministic seeds make tiles consistent), multi-pass with checkpointed partial results (cancel keeps what you have), per-pass stats |
| `opencl` (optional) | `engines/opencl_engine.py` | same step code transpiled to OpenCL C (tiny codegen variant), fp64 native; loaded only if `pyopencl` imports |

`engines/selector.py` probes at startup (in a worker): creates a standalone context,
reads version/renderer/vendor, tries a 1-group compute dispatch, checks `fp64`, measures
a 0.2 s micro-benchmark (Mpts/s) for both GPU and CPU → picks defaults (preview = fastest
GPU path, final = `gl_precision` if compute else `cpu_numba`) and **shows the choice in
the status bar** ("GPU: NVIDIA RTX 3060 · compute · fp64 ✓ | CPU: 16 threads"). User can
override per job. Any GL error mid-job → job restarts on CPU with a visible notice (never
silent, fixing A5).

### 6.6 Huge renders
Histogram memory = W·H·(4 + 4·extra buffers). Budget default 1 GB (preference). Above it:
tiles of ≤ 4096² at accumulation resolution; tone-mapping needs the global percentile →
pass 1 accumulates tile histograms-of-density (4096 bins each) → global P → pass 2
develops tile by tile and writes directly into the output image (Pillow, 16-bit). Max
output tested: 16 384² (C rewrite limit) and 32 768² via tiles.

### 6.7 Statistics (the nerd layer)
`RenderStats`: iterations requested/performed, points plotted/in-bounds, restarts,
non-empty pixels & coverage %, max/percentile/mean/median density, density histogram
(256 bins), entropy of the density distribution, engine/device, passes, tiles, wall time,
points/s, memory. `DynamicsStats` (analysis worker): largest Lyapunov exponent (Benettin
renormalisation on CPU fp64; for maps via Jacobian from sympy when available, else
finite differences), Kaplan–Yorke dimension when spectrum computed (optional), box-count /
correlation dimension estimate of the projected cloud, bounding box, mean speed, period
detection (periodic orbit warning). All shown in the Stats panel and written to reports.

### 6.8 Determinism & reproducibility
`seed` in settings; per-trajectory RNG derived from `hash(seed, trajectory_id)`; tile and
pass order fixed. The report includes an `ATR1:` code (base64url JSON of the full
settings) that recreates the image.

---

## 7. GUI design

### 7.1 Main window
```
┌ Attractr ──────────────────────────────────────────────────────────────────────────────┐
│ File  Edit  View  Attractor  Render  Animate  Tools  Help                [engine badge] │
│ ⟳ Reset  🎲 Random  ⏹/▶ Preview  ⬛ Render…  🎞 Animate…  📊 Stats  📝 Report  ⚙        │
├───────────────┬──────────────────────────────────────────────┬─────────────────────────┤
│ ATTRACTOR     │                                              │ LOOK                     │
│ [browser with │            VIEWPORT (QOpenGLWidget)          │  Style  [Gas ▾]          │
│  thumbnails,  │   progressive preview, trackball, wheel zoom │  Colour source [density▾]│
│  search box,  │   HUD: pts 12.4 M · 38 Mpts/s · 94 % · GPU    │  Gradient ▓▓▓▓▓▓ [edit]  │
│  families]    │   overlay: axes gizmo, bounds, formula       │  Percentile ──●── 99.8 % │
│───────────────│                                              │  Gamma ──●── 1.00        │
│ PARAMETERS    │                                              │  Full range ☐  Invert ☐  │
│  a ──●──── -1.40│                                            │  Background [■ black ▾]  │
│  b ────●── 1.60 │                                            │  Depth/Lights ▸          │
│  … (+ dt, int.) │                                            │─────────────────────────│
│  [Randomize] [Search…] [Reset] [Fork formula]                │ CAMERA                   │
│───────────────│                                              │  yaw/pitch/roll/zoom/pan │
│ PRESETS       ├──────────────────────────────────────────────┤  persp ──●── 0.3 [reset] │
│  curated/user │ TIMELINE (dock, hidden until Animate)        │─────────────────────────│
│  daily · gallery│ ◄ ▮▮ ►  |‑‑‑◆‑‑‑‑‑‑◆‑‑‑‑‑‑‑◆‑‑‑|  0:00/0:08  │ INFO / STATS (tabs)      │
└───────────────┴──────────────────────────────────────────────┴─────────────────────────┘
 status: Clifford · 6 params · λ₁≈0.42 (chaotic) · preview 2.1 M pts (1.9 pts/px) · GPU compute fp32
```
All panels are `QDockWidget`s (movable, closable, layouts saved in `QSettings`; presets
"Explore", "Render", "Animate", "Code").

### 7.2 Viewport & interaction
* Left-drag = trackball rotate (3-D) / pan (2-D); right-drag = roll; middle/shift-drag =
  pan; wheel = zoom about cursor; double-click = reset; `Space` = toggle spin (C rewrite).
* While interacting: GPU progressive preview restarts every frame with a small budget
  (looks like a live dot cloud, sharpens when you stop); CPU-only: Android-style dot cloud
  (30k–160k points, depth-bucketed colours).
* After idle (configurable, default 300 ms): preview continues accumulating to the
  "preview points per pixel" target (WebGL intensity model).
* HUD (toggle): points, speed, coverage, engine, resolution, zoom; optional formula +
  parameter caption (WebGL infos) — also an export option.
* Overlays: orientation gizmo, bounding sphere/box, pixel probe (hover shows count/density/depth).

### 7.3 Gradient editor (dock or dialog)
* Gradient bar with draggable stops (add: double-click; remove: drag off / Del), colour
  picker (Qt colour dialog + HSV square like Android's), alpha per stop (for transparent
  glows), position spin box, distribute evenly, reverse, flip, randomize (harmonious:
  analogous/complementary generators), **interpolation space** (linear RGB, sRGB, HSV
  short/long, OKLab), **cyclic** flag + **phase** slider (C rewrite `--cycle`;
  animatable), "bands" repeat count.
* Library: built-in palettes (Android 10, C 6, WebGL duotone dark/light/colour), user
  palettes (`~/.attractr/palettes/*.json`), import/export `.ggr` (GIMP) and our JSON,
  drag a palette thumbnail onto the viewport.
* Live: every change re-develops the current preview (no re-iteration).

### 7.4 Formula editor (dock)
* `QPlainTextEdit` subclass with line numbers, `QSyntaxHighlighter` for the DSL, error
  squiggles + message bar, completion popup (functions, params), bracket matching.
* Toolbar: New (templates), Fork current built-in, Compile/Apply (auto when valid), Save
  to My Attractors, Lyapunov badge.
* Parameters declared in the text appear as sliders immediately in the Parameters panel.
* Full spec: [formula_dsl.md](formula_dsl.md).

### 7.5 Parameter / visual editor
* `SliderSpin` widget: slider + spin box + drag-to-scrub label + range expand/shrink
  buttons (double-click range to edit), logarithmic option for dt, lock 🔒 (excluded from
  randomize), keyframe ◆ button, hint tooltip (Android hints), right-click: reset/copy/
  paste/animate.
* **XY pad**: pick two params, drag a point to change both (great for Clifford a/b).
* **Variation grid** ("Mutate"): 3×3 or 4×4 thumbnails of random perturbations of the
  current params at chosen radius; click to adopt (classic explore loop).
* **Search** (classic Chaoscope): random parameters within ranges (or polynomial
  coefficients) filtered by Lyapunov > 0, bounded, coverage > threshold → thumbnail grid
  streaming in from the analysis worker; keep favourites.
* Randomize-all / randomize-params / undo-redo (`QUndoStack`, slider drags merge).

### 7.6 Info & statistics panels
* **Info**: attractor name, family, pretty formula (Unicode + optional rendered math via
  matplotlib mathtext), parameter hints, description, references, presets.
* **Stats** (live): render stats table + density histogram plot (log, with tone curve
  overlay) + dynamics stats (λ₁, dimension estimate, bounds, restarts).
* **System**: GPU/CPU probe results, engine benchmark, memory, versions.
* **Job monitor**: queue of renders/animation frames with progress/ETA, cancel.

### 7.7 Render dialog & queue
Presets (Preview 768², HD 2048², 4K 3840², 8K, custom, aspect presets incl. 1080×1920),
iterations as *points per pixel* (with absolute count and ETA from the benchmark),
engine choice, supersampling, splat radius, integrator, tiles auto, 8/16-bit, transparent
bg, caption overlay, **report format(s)** checkboxes (md/txt/html/pdf) + "open when
done", output folder + naming template (`{name}_{date}_{w}x{h}_{seed}`). Jobs go to the
queue; the dialog is non-modal.

### 7.8 Presets, daily, gallery
Curated (ported), user presets (JSON, thumbnails cached), **Attractor of the Day**
(date-seeded, validated in the analysis worker — ported logic), `ATR1:` codes
(copy/paste, clipboard detection offer), CHS1 import, gallery of exported images with
the full settings (re-open in editor, re-render bigger).

### 7.9 Preferences
Engine overrides, memory budget, thread count, preview budget (ms/frame, points/px),
debounce times, default folders, theme, ffmpeg path, report defaults, telemetry = none.

### 7.10 Theme & logo
Dark theme (QSS, palette from the "Nebula" gradient accents cyan #4FC3F7 / violet
#5B2FD1), icons as SVG (own set, consistent stroke). **Logo**: generated by
`tools/make_logo.py` — a real attractor orbit (candidate: a de Jong/Pickover orbit whose
silhouette reads as a stylised "A"; alternative: Lorenz lobes forming the counter of the
"a") drawn with depth-banded strokes and a radial dark background, exported as SVG, PNG
16–1024, `.ico`, `.icns`, plus wordmark "Attractr" in a geometric sans. Three concept
sheets will be produced in M3 for you to pick from.

---

## 8. Animator

* **Timeline dock**: tracks for any animatable property (every param, camera quaternion /
  Euler, zoom, pan, perspective, gradient phase, gamma, percentile, dt, integrator
  substeps, background colour…), keyframes (◆ buttons on controls), easing per segment
  (linear, ease-in/out, smoothstep, cubic-bezier editor, hold), loop / ping-pong,
  duration & fps, scrubbing drives the preview.
* **Helpers** (replace Android's 4 modes): Turntable (axis, revolutions), Morph A→B
  (captures two states), Param Sweep (random target ±N % with re-roll + preview
  thumbnail), Orbit Trace (grow a single trajectory; cumulative mode), Palette cycle,
  Zoom-in.
* **Rendering**: frames rendered by the precision engine through the job queue into
  `frames/{name}_{0001}.png`, resumable (skips existing), per-frame stats rows in the
  animation report, locked bounds by default, optional motion blur (sub-frame
  accumulation: n sub-steps averaged).
* **Encode**: ffmpeg detected (PATH / preference / imageio-ffmpeg) — presets H.264 mp4
  (yuv420p, CRF), H.265, ProRes 422, VP9 webm, GIF (palettegen), PNG sequence only; custom
  args; progress parsed from ffmpeg stderr; log kept.

---

## 9. Reports & export

* Image export: PNG (8/16-bit, optional alpha), TIFF 16-bit, JPEG, WebP; embedded
  metadata (PNG tEXt: settings JSON + `ATR1:` code) so any exported image can be dragged
  back into Attractr to restore its settings.
* **Render report** written next to the image on every "full" render (threshold
  configurable) in any of **.md / .txt / .html / .pdf**:
  title + thumbnail, attractor & formula, parameters table, camera, look, quality
  (iterations, pts/px, supersampling, splat, integrator, dt, seed), engine & device,
  timing (per pass/tile, pts/s), statistics (coverage, density percentiles, histogram
  sparkline/plot image, entropy), dynamics (λ₁, dimension), reproducibility block
  (`ATR1:` code, CLI command line), software versions. One template → four renderers
  (`report/render_md.py`, `render_html.py`, `render_pdf.py` via Qt, `render_txt.py`).
* Session/animation report: per-frame table + totals.

---

## 10. CLI (`attractr`)

```
attractr render  project.attractr|ATR1:code|--attractor lorenz [--param rho=28 …] -o out.png
                 --size 4096x4096 --ppp 40 --engine gl_precision|cpu --ss 2 --splat 1 --seed 7
                 --report md,html --caption
attractr animate project.attractr -o frames/ --fps 30 --encode h264 --out movie.mp4
attractr list    attractors|palettes|engines|styles [--json]
attractr info    [--json]                      # hardware probe + benchmark
attractr thumb   --attractor clifford --size 256 -o -   # PNG to stdout (pipes)
attractr report  image.png --format pdf        # regenerate a report from embedded metadata
attractr lyapunov --attractor henon --param a=1.4 …
```
The GUI's "Copy CLI command" puts the equivalent line on the clipboard.

---

## 11. Files, formats, persistence

* `.attractr` project (JSON, `schema: 1`): attractor ref or inline `.atr` source, params,
  camera, look (gradient inline), quality, animation timeline, notes. Human-readable.
* `~/.attractr/attractors/*.atr`, `palettes/*.json`, `presets/*.json`, `gallery/index.json`,
  `cache/numba/`, `cache/thumbs/`, `logs/`.
* `QSettings` for window layout/preferences. Autosave of the document every 30 s +
  crash recovery.

---

## 12. Module map (target tree)

```
Attractr/
├── pyproject.toml · README.md · LICENSE · .gitignore
├── src/attractr/
│   ├── __main__.py                 python -m attractr → gui or cli
│   ├── app.py                      QApplication, theme, settings, crash handler
│   ├── version.py
│   ├── cli/                        main.py, cmd_render.py, cmd_animate.py, cmd_list.py, cmd_info.py, cmd_report.py
│   ├── core/
│   │   ├── formula/                tokens.py, lexer.py, parser.py, ast.py, validate.py,
│   │   │                           codegen_numba.py, codegen_glsl.py, pretty.py, probe.py (quick dynamics probe)
│   │   ├── attractors/             spec.py (AttractorSpec/ParamSpec), loader.py (.atr), registry.py, presets.py
│   │   ├── math/                   quaternion.py, rotation.py, rng.py, percentile.py, stats_util.py
│   │   ├── render/
│   │   │   ├── settings.py         RenderSettings · Quality · LookSettings (frozen dataclasses + JSON)
│   │   │   ├── camera.py           Camera · projection · trackball math
│   │   │   ├── framing.py          scene fit (sphere/bbox), cached by (attractor, params, seed)
│   │   │   ├── result.py           RenderResult · RenderStats · DynamicsStats
│   │   │   ├── accumulators.py     which buffers a style needs
│   │   │   ├── engines/            base.py, selector.py, cpu_numba.py, gl_common.py (context, shader assembly),
│   │   │   │                       gl_compute.py, gl_points.py, gl_precision.py, tiles.py, opencl_engine.py (optional)
│   │   │   ├── develop/            tonemap.py, styles/{gas,dust,light,liquid,solid,plasma}.py,
│   │   │   │                       lighting.py, background.py, equalize.py, developer.py (orchestrates)
│   │   │   └── shaders/            *.glsl templates: step injection point, iterate.comp, clear.comp,
│   │   │                           tonemap.comp, points.vert/frag, develop.frag
│   │   ├── color/                  gradient.py, interpolation.py (RGB/HSV/OKLab), lut.py, palettes.py, ggr_io.py
│   │   ├── analysis/               lyapunov.py, dimension.py, periodicity.py, search.py, daily.py
│   │   ├── animation/              timeline.py, keyframe.py, easing.py, interpolate.py (quaternion slerp),
│   │   │                           helpers.py (turntable/morph/sweep/orbit), sequence.py, ffmpeg.py
│   │   ├── project/                document.py (QObject with signals), schema.py, codes.py (ATR1/CHS1), gallery.py
│   │   ├── report/                 model.py, render_md.py, render_txt.py, render_html.py, render_pdf.py, plots.py
│   │   ├── io/                     image_export.py, metadata.py (PNG text chunks), naming.py, paths.py
│   │   └── jobs/                   job.py, queue.py, worker.py (QThread wrapper with signals), cancel.py
│   ├── gui/
│   │   ├── main_window.py, actions.py, layouts.py, statusbar.py, theme/ (qss, icons/)
│   │   ├── viewport/               gl_widget.py, preview_controller.py, interaction.py, hud.py, overlays.py, pixel_probe.py
│   │   ├── panels/                 attractor_browser.py, parameters_panel.py, look_panel.py, camera_panel.py,
│   │   │                           presets_panel.py, info_panel.py, stats_panel.py, system_panel.py,
│   │   │                           jobs_panel.py, search_panel.py, gallery_panel.py
│   │   ├── widgets/                slider_spin.py, xy_pad.py, collapsible.py, color_button.py, toast.py,
│   │   │                           gradient_editor/ (bar.py, stop_handle.py, editor.py, library.py)
│   │   │                           formula_editor/ (editor.py, highlighter.py, completer.py, gutter.py, errors.py)
│   │   │                           timeline/ (timeline_widget.py, track.py, keyframe_item.py, curve_editor.py)
│   │   │                           plots.py (histogram plot via QPainter)
│   │   ├── dialogs/                render_dialog.py, animate_dialog.py, export_dialog.py, preferences_dialog.py,
│   │   │                           about_dialog.py, report_viewer.py, mutate_grid.py
│   │   └── controllers/            develop_controller.py, render_queue_controller.py, animation_controller.py,
│   │                               undo_commands.py
│   └── resources/                  attractors/*.atr, palettes/*.json, presets/curated.json, logo/, icons/, templates/
├── tools/                          make_logo.py, port_android_presets.py, gen_attractor_docs.py, bench.py
├── tests/                          unit/ (formula, codegen parity, color, tonemap, camera, schema),
│                                   engines/ (cpu vs gl statistical parity), gui/ (offscreen smoke), golden/ (low-res images)
└── docs/                           see §14
```

---

## 13. Testing & quality gates

* **Formula**: parser round-trip (`pretty(parse(s))` re-parses to same AST), hypothesis
  fuzzing (never crashes, always a clean error), every built-in `.atr` parses and compiles
  on both back-ends.
* **Parity**: for each built-in, 256² render on `cpu_numba` vs `gl_compute` vs numpy
  reference (prototype-style): normalised histograms agree (Jensen–Shannon < 0.02),
  coverage within 2 %.
* **Literature checks**: Lyapunov exponent of Lorenz (≈ 0.9), Hénon (≈ 0.42), logistic-like
  sanity; Clifford formula test against Bourke's definition (catches W1).
* **Determinism**: same seed ⇒ identical CPU image; GPU image stable across runs
  statistically.
* **Develop**: tone-map monotonicity, percentile correctness, equalisation produces flat
  CDF, palette LUT endpoints, cyclic wrap.
* **Serialisation**: project/preset/code round-trips; CHS1 samples from the Kotlin tests.
* **GUI smoke** (offscreen): window opens, every panel constructs, slider change triggers
  preview restart, render job completes and emits image, undo/redo.
* **Performance budget**: preview frame ≤ 16 ms on GPU; develop ≤ 50 ms at 4 K; CLI
  startup ≤ 1.5 s (numba cache warm).
* Lint: ruff + mypy (core strict). CI: GitHub Actions matrix (Linux offscreen) running
  all of the above.

---

## 14. Documentation plan (`docs/`)

| File | Content |
|---|---|
| `README.md` (docs index) | map of all docs |
| `PLAN.md`, `source_analysis.md`, `attractor_catalog.md`, `formula_dsl.md` | this planning set (kept updated) |
| `architecture.md` | layers, threading, data flow (from §5, expanded with sequence diagrams) |
| `engine_cpu.md`, `engine_gl.md`, `engine_selection.md` | how each engine works, shader structure, tiling, precision notes, fallback rules |
| `render_styles.md` | math of each style + colour source + develop options with example images |
| `camera.md` | framing model, conventions, animation locking |
| `gradients.md` | gradient model, interpolation spaces, file formats |
| `animation.md` | timeline model, easing, helpers, ffmpeg presets |
| `reports.md` | report fields & formats |
| `cli.md` | every command/flag with examples |
| `project_format.md` | `.attractr` schema, `.atr`, codes, metadata chunks |
| `gui_guide.md` | user guide with screenshots, shortcuts |
| `statistics.md` | definitions of every number shown (λ, dimension, coverage…) |
| `development.md` | setup, coding standards, how to add an attractor/style/engine/exporter, release |
| `changelog.md` | per-milestone |

Generated: `attractors/*.md` (one page per attractor from its `.atr` via
`tools/gen_attractor_docs.py`, with thumbnail).

---

## 15. Milestones, tasks, acceptance criteria

Estimated relative sizes are in "units" (1 unit ≈ one focused work session). Order within a
milestone is the execution order.

### M0 — Foundation (≈2 units)
- [ ] Repo scaffold: `pyproject.toml` (deps: PySide6, numpy, numba, moderngl, glcontext, Pillow; optional extras `opencl`, `dev`), `src/` layout, `ruff`/`mypy` config, `tests/` skeleton, `tools/`, `.gitignore` update.
- [ ] `docs/README.md` index + `development.md` (coding standards from §3).
- [ ] `core/math`, `core/render/settings.py` dataclasses + JSON (de)serialisation with schema version.
- [ ] `jobs/` (Job, Worker QThread wrapper, Queue, cancel) — unit tested with dummy jobs.
- **Accept**: `pip install -e .`; `pytest` green; `python -m attractr --version`.

### M1 — Core engine & CLI (≈8 units)
- [ ] Formula DSL: lexer, parser, AST, validator, `pretty`, `codegen_numba`, `codegen_glsl`; tests incl. hypothesis.
- [ ] `.atr` loader + registry; write all **tier-1** attractors as `.atr` (Android 17, C 42 incl. Sprott A–S, WebGL 2 → ~52 unique) with metadata ported (hints/descriptions/presets via `tools/port_android_presets.py`).
- [ ] Integrators (map, Euler, RK2, RK4, substeps), RNG, divergence/restart policy.
- [ ] Framing (`framing.py`) + Camera/projection (quaternion, Euler I/O, perspective, fit modes).
- [ ] `cpu_numba` engine: parallel trajectories, private histograms, splats (r 0–4 + bilinear), gap-fill, accumulators for all styles, pass/cancel/progress, stats.
- [ ] Colour: Gradient model, interpolation spaces, LUT, built-in palettes JSON (Android 10 + C 6 + duotone), `.ggr` I/O.
- [ ] Develop: tone-map (percentile, log, gamma, equalise, invert), all six styles incl. lighting from zmin, colour sources, backgrounds, 8/16-bit output with dithering.
- [ ] Image export + PNG metadata; naming templates.
- [ ] Report model + md/txt/html/pdf renderers (pdf via Qt offscreen).
- [ ] Analysis: Lyapunov (Benettin), dimension estimate, probe; daily attractor; search core.
- [ ] CLI: `render`, `list`, `info`, `thumb`, `lyapunov`, `report`.
- **Accept**: `attractr render --attractor lorenz -o lorenz.png --size 2048x2048 --report md` produces image + report in < 10 s on this 4-core sandbox; golden images for every tier-1 attractor reviewed visually (contact sheet in `docs/images/`); parity tests CPU vs numpy reference pass; λ(Lorenz) ≈ 0.9.

### M2 — GPU engines (≈6 units)
- [ ] `gl_common`: standalone context per worker thread, shader template assembly with injected `step()`, capability probe, micro-benchmark, error mapping.
- [ ] `gl_compute` preview engine (GL 4.3): clear/iterate/tonemap compute passes, time-sliced progressive accumulation, SSBO max, depth/colour/zmin accumulators.
- [ ] `gl_points` fallback (GL 3.3): state ping-pong textures + additive point FBO.
- [ ] `gl_precision`: supersampling, splats, gap-fill, compensated accumulation, fp64 option, tiles, checkpointed passes, stats.
- [ ] `selector.py` policy + user override; mid-job GL failure → CPU restart with notice.
- [ ] Optional `opencl_engine` behind extra; skipped if import fails.
- **Accept**: CPU↔GPU statistical parity tests for all tier-1; compute verified on Mesa here; 16 384² tiled render completes on CPU and GPU within memory budget; cancel latency < 200 ms; `attractr info` prints probe.

### M3 — GUI shell (≈8 units)
- [ ] `app.py`, dark theme, main window, docks, layouts, status bar engine badge, crash-safe autosave.
- [ ] `Document` (QObject, signals, undo stack with merge for slider drags).
- [ ] Viewport: QOpenGLWidget sharing context with preview engine; trackball/pan/zoom/spin; progressive preview controller (restart on change, continue on idle); CPU dot-cloud fallback; HUD; pixel probe.
- [ ] Attractor browser (thumbnails via analysis worker, families, search box), Parameters panel (`SliderSpin`, dt/integrator group, lock, randomize/reset), Camera panel, Look panel (style, colour source, gradient thumbnail, percentile, gamma, full range, invert, background, depth/lights group), Presets panel (curated/user/daily/codes), Info panel.
- [ ] Develop controller (debounced re-develop on look change at preview res and at last full render res).
- [ ] Render dialog + job queue + Jobs panel + report options + open-folder; Export dialog.
- [ ] Preferences dialog; About; keyboard shortcuts; first-run tips.
- [ ] Logo: `tools/make_logo.py` → 3 concept sheets → chosen → SVG/PNG/ICO/ICNS + window icon + splash-less About.
- **Accept**: offscreen GUI smoke tests; manual script: open → pick Thomas → drag camera at ≥ 30 fps on GPU → change gradient with no re-iteration → HD render with progress → report written → undo/redo works → reopen project restores everything.

### M4 — Editors & panels (≈6 units)
- [ ] Gradient editor (bar, stops, picker, alpha, spaces, cyclic/phase/bands, library, ggr import/export, randomize).
- [ ] Formula editor (highlighter, gutter, completer, error marks, templates, fork built-in, save to My Attractors, live compile pipeline, Lyapunov badge).
- [ ] Stats panel (live stats table, density histogram plot with tone curve, dynamics stats), System panel, XY pad, Mutate grid, Search panel.
- [ ] Caption overlay export option; gallery panel with re-open.
- **Accept**: type the Tinkerbell map from scratch → renders within 1 s of last keystroke; errors shown inline; gradient edits re-develop < 50 ms; Search finds ≥ 10 chaotic quadratic maps in under a minute on CPU.

### M5 — Animator (≈6 units)
- [ ] Timeline model (tracks/keyframes/easing/loop/ping-pong), quaternion slerp, interpolation of gradients (stop-wise) and all animatable fields.
- [ ] Timeline widget, keyframe buttons on controls, curve editor, scrubbing → preview.
- [ ] Helpers: turntable, morph A→B, param sweep (re-roll + thumbnail), orbit trace, palette cycle, zoom.
- [ ] Sequence renderer (queue, resumable, locked bounds, motion blur option, per-frame stats), animation report.
- [ ] ffmpeg detection/config, encode presets, progress parsing, GIF palettegen, log viewer; `attractr animate`.
- **Accept**: 4 s turntable of Aizawa at 1080² renders and encodes to mp4 with no framing breathing; cancelling mid-way and resuming skips finished frames; CLI produces identical frames to GUI.

### M6 — Polish, tier-2, packaging (≈5 units)
- [ ] Tier-2 attractors (maps, flows, polynomial maps, general IFS editor table, procedural backgrounds).
- [ ] Real Liquid/Solid lighting controls UI, Plasma glow, vignette.
- [ ] Performance pass (benchmarks in `tools/bench.py`, numba cache warm-up on startup, preview auto-budget).
- [ ] Accessibility/keyboard, i18n scaffolding (strings in one module; Android has es/fr/pt-BR/zh-CN we could port later).
- [ ] PyInstaller specs, release checklist, `changelog.md`, complete docs + screenshots, generated attractor pages.
- **Accept**: full docs review; all tests green on CI; packaged build launches on a clean machine.

---

## 16. Risks & mitigations

| Risk | Mitigation |
|---|---|
| GPU driver diversity (compute missing on macOS, float atomics absent, context loss) | three GPU paths + CPU reference; capability probe; every GPU failure degrades visibly, never silently; tests run on Mesa software GL |
| numba compile latency for user formulas (0.5–3 s) | GPU preview is independent of numba; CPU code compiles in background; on-disk cache keyed by AST hash |
| Float32 precision artefacts on GPU for sensitive flows (Dequan Li dt 0.0005) | precision engine: fp64 option, compensated sums, RK4, substeps; report warns when fp32 was used for a "stiff" system |
| Percentile tone-mapping over huge tiled images | histogram-of-densities approach (no sort), two-pass tiles |
| Feature creep in the GUI | milestone gates; every panel is a dock that can ship later without blocking |
| Classic Chaoscope parity ambiguity (Unravel, Polynomial C exact forms) | flagged as research items; user confirmation (Q1) |
| PySide6 + ModernGL context sharing pitfalls | viewport uses Qt's context; engines create *their own* standalone contexts in worker threads and pass NumPy arrays back; only the preview engine runs in the Qt context on the GUI thread in time slices |

---

## 17. Decisions (answered at plan review)

1. **Classic Chaoscope scope** — is the "Original Chaoscope" you mean the *folder*
   `chaoscope_original` (Android/C++ re-imagining — fully covered), or also Nicolas
   Desprez's classic Windows app (§4 of `source_analysis.md`: Search, Polynomial maps,
   lights, real Liquid/Solid)? Plan currently includes both; classic-only items sit in
   tiers 2/M6.
2. **Name & branding** — "Attractr" wordmark style: geometric/tech (default proposal) or
   hand-drawn like the WebGL "Nothing You Could Do" caption font? Logo concept: attractor
   shaped as an "A" vs. Lorenz lobes vs. abstract ribbon — three sheets will be generated
   in M3 unless you have a preference now.
3. **Package/entry-point names** — `attractr` for both GUI and CLI (`attractr` opens GUI
   when no sub-command)? OK?
4. **Integrator semantics for ported presets** — Android presets were tuned with Euler at
   a given dt. With RK4 the shapes are slightly (more correctly) different. Proposal: port
   presets with RK4 and re-tune visually; keep an "Euler (legacy)" integrator option.
5. **Render report default** — write a report automatically for every render ≥ 2048² (all
   four formats off by default except Markdown)? Or ask each time?
6. **Optional OpenCL engine** — include as opt-in plug-in (yes by default in plan) or drop
   to keep dependencies minimal?
7. **Procedural backgrounds** (Stars/Forest/Ocean/Aurora from Android) — keep (M6) or drop?
8. **Licence** for Attractr — Apache-2.0 like the Android source, MIT, or other? (Source
   attributions will be kept in `README.md` regardless.)

**Answers (approved):**

| # | Decision |
|---|---|
| 1 | **Both** — the `chaoscope_original` folder *and* the classic Desprez feature set (Search, Polynomial maps, lights, real Liquid/Solid) are in scope. |
| 2 | Geometric/tech wordmark (no hand-drawn font); logo concept sheets generated in M3 as planned. |
| 3 | `attractr` is both the GUI entry point (no sub-command) and the CLI. |
| 4 | RK4 is the default; Android presets are ported onto RK4 and re-tuned; an **Euler (legacy)** integrator stays selectable. |
| 5 | Render dialog has a **checkbox** "Write render report" for full-size renders and a **drop-down** for the format (Markdown / Text / HTML / PDF). |
| 6 | The **OpenCL engine ships by default** (`pyopencl` is a regular dependency; the engine degrades gracefully if no OpenCL platform is present). |
| 7 | Procedural backgrounds (Stars / Forest / Ocean / Aurora) are kept, full range. |
| 8 | Licence: **MIT**, with attributions to the three source projects in `README.md`. |

---

## 18. Appendix — default numbers we will start from

| Setting | Default | Origin |
|---|---|---|
| Preview canvas | viewport size, ≤ 1024² accumulation | — |
| Preview target density | 2 points/pixel (≈ 2 M at 1024²) = Android "Standard" preview | A |
| Final quality tiers | Draft 4 · Standard 12 · High 30 · Ultra 75 points/pixel (≈ 15/50/120/300 M at 2048²) | A |
| Trajectories | 65 536 GPU · threads×4096 CPU | A |
| Warm-up | 1000 steps | A |
| Bounds sample | 65 536 points, 99.9 % radius percentile, FIT 0.82 | C (+robustness) |
| Percentile P | 0.998 | C |
| Splat radius | 0 (bilinear AA) preview · 1 final | C |
| Supersampling | 1 preview · 2 final | C |
| Integrator | RK4, dt per system | C |
| Divergence | |v| > 1e6 or non-finite; 50 restarts/trajectory max | C |
| LUT size | 1024 | A |
| Dot-cloud preview | 30k / 80k / 160k points | A |
| Debounce | look 50 ms (develop), params 0 ms (preview restarts), persist 500 ms | A (tuned) |
| Video | 30 fps, H.264 CRF 18, yuv420p | A + ffmpeg defaults |
| Memory budget | 1 GB accumulation before tiling | — |

---

## 19. Implementation status (kept current)

| Milestone | Status | Notes |
|---|---|---|
| M0 Foundation | ✅ done | scaffold, settings/camera/gradient models, jobs layer, tests |
| M1 Core engine & CLI | ✅ done | DSL (lexer/parser/validator/codegen numba+GLSL+OpenCL), 53 tier-1 attractors, CPU engine, adaptive framing, six styles, palettes, exports with metadata, reports md/txt/html/pdf, Lyapunov/dimension/probe, CLI |
| M2 GPU engines | ✅ done | `gl_compute` / `gl_precision` (GL 4.3 compute, fixed-point + merge, tiles), `opencl`, `gl_points` (GL 3.3 fallback), fp64 precision mode (software double math for GLSL), selector + fallback, parity tests |
| M3 GUI shell | ✅ done | document/undo, progressive preview worker, viewport trackball/HUD/probe, all panels, render dialog + queue, dark theme, logo, presets/daily/codes, autosave/recovery, tips |
| M4 Editors & panels | ✅ done | gradient editor (+ggr), formula editor (highlighter, errors, completion, live apply, probe badge), XY pad, mutate grid, search, caption overlay, gallery, stats/system panels |
| M5 Animator | ✅ done | timeline/keys/easing, helpers (turntable, morph, sweep, palette cycle, zoom, orbit trace), locked framing, resumable sequences, motion blur, ffmpeg presets, timeline panel, animate dialog, CLI |
| M6 Polish | ✅ mostly | 26 tier-2 attractors (79 total; 119 after the post-plan additions, see changelog), procedural backgrounds, worker-process architecture (no GIL stalls), kernel warm-up, kernel variant specialisation (2–5× CPU speed-up), docs, generated attractor pages, PyInstaller spec. **i18n:** scaffolding in place (`attractr/i18n.py`: `tr()`, translator loading, `resources/i18n/`); strings are not yet wrapped — see docs/development.md |
| Post-plan round 2 | ✅ done | `on_section` return maps, `kind: escape` (Buddhabrot), translations (German UI + overlays), interleaved tiles, GPU Liquid/Solid develop, gallery re-render, persisted parameter history, resume across quality changes. See `suggested-improvements.md §3–4`. |
| Post-plan round | ✅ done | everything in `suggested-improvements.md`: DSL `w` / `plot` / `section` / `boost`, 34 attractors + 18 presets, GPU develop pass, progressive renders with Finish-now + checkpoint/resume, slider ergonomics, drag & drop, render presets + batch + notifications, quality hints, cache limit, polynomial-map search, SVG export, i18n scaffolding. Open items are listed in `suggested-improvements.md §3`. |

Deviations from the original plan worth knowing:

* The default framing for stills is the tight 2-D fit (`camera.fit = "bbox"`); animations
  lock a bounding sphere instead (§6.3 originally proposed sphere as the default).
* Thumbnails, Lyapunov probes and the daily attractor run in a **helper process**
  (`core/worker_server.py`) rather than threads: numba compilation holds the GIL and was
  stalling the GUI thread.
* The CPU kernel is generated per (formula × buffer-set × splat radius) variant; runtime
  flags cost 3× because the compiler had to assume the accumulation buffers alias.
