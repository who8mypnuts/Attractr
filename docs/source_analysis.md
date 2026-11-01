# Source Analysis — what we are refactoring from

This document is the inventory of the three codebases in `sample_source/`. It records
**what each one does**, **what is worth keeping**, and **what is wrong and must not be
replicated**. Every decision in [PLAN.md](PLAN.md) traces back to a row here.

> Legend: ✅ keep / port · 🔧 keep but fix · ❌ do not replicate · ✨ improve beyond source

---

## 1. `chaoscope_original/` — the Kotlin / C++ / Swift re-imagining (Lucas Balancin)

Despite the folder name this is **not** Nicolas Desprez's 2000s Windows program; it is a
modern mobile re-imagining of it (Android in production, iOS building). It is the richest
of the three sources and the primary feature reference.

### 1.1 Layout

| Part | Language | Role | Verdict |
|---|---|---|---|
| `core/attractors.cpp/.h` | C++17 | 17 attractor step functions, batch-of-trajectories layout, fast polynomial sin/cos | ✅ port equations; ✨ move to formula DSL |
| `core/renderer.cpp/.h` | C++17 | camera, auto-bounds, multi-threaded histogram, tone-map, palettes, 6 render styles, dot-preview | ✅ port pipeline; 🔧 fix tone-map & bounds |
| `android/.../cpp/gpu_renderer.cpp` | C++/GLES 3.1 | compute-shader histogram (atomic image add + atomicMax SSBO), tone-map compute, CPU bounds pre-pass | ✅ direct model for our GL compute engine |
| `android/.../ChaoscopeViewModel.kt` | Kotlin | all app behaviour: debounce, dot-preview while dragging, render scheduling, retry-on-blank, randomize/undo, presets, video export (4 modes), sweep targets, gallery | ✅ behaviour reference |
| `android/.../AttractorDefs.kt` | Kotlin | param names / defaults / ranges / hints / descriptions, 10 palettes, 6 styles, quality tiers, curated presets (3 per attractor) | ✅ port all data |
| `android/.../ui/*.kt` | Compose | 4-tab control panel (Shape/Look/Camera/Export), palette editor, tutorial, splash, themed backgrounds | ✅ feature reference only |
| `android/.../PresetSerializer.kt` | Kotlin | `CHS1:` base64url preset codes, gallery entries | ✅ port idea (new `ATR1:` codes) + import CHS1 |
| `android/.../DailyAttractor.kt` | Kotlin | date-seeded "Attractor of the Day" validated by thumbnail render | ✅ port |
| `android/.../VideoExporter.kt` | Kotlin | MediaCodec H.264 encoder | ❌ platform-specific → ffmpeg |
| `prototype/engine/*.py` | Python/NumPy | the original POC: Camera, HistogramCanvas, log tone-map, Palette LUT, CLI | ✅ useful as reference shape for our numpy code & tests |
| `prototype/assets/icon_design.py` | Python | launcher icon from a real Lorenz orbit with depth-banded strokes | ✅ technique reused for the Attractr logo |
| `ios/` | Swift | same engine, thinner UI | nothing new |

### 1.2 Render pipeline (C++ `renderAttractor`)

```
seed 65 536 trajectories (LCG, deterministic)      → reproducible
warm-up 1000 steps (discard transients)
16 batches → project (u,v[,w]) → min/max bounds, +5 % pad, zoom about centre
accumulate:  hist[px,py]++   (+ depth sum for Liquid / depthCue)
tone-map:    density = log(1+count)/log(1+maxCount)     ("Gas")
             style transforms (Dust=4th root, Plasma=fmod bands, Solid=threshold)
             optional histogram equalisation ("fullRange")
             depth shading: density *= 1 - k·depthNorm
LUT (1024 entries) → ARGB
```
Multi-threading: private per-thread histograms merged afterwards, ≤8 threads, 96 MB
memory budget. Progress through atomics (only for W ≥ 1024).

Render styles (`RenderStyle`):

| Style | Implementation | Verdict |
|---|---|---|
| Gas (STANDARD) | log density + gamma | ✅ |
| Dust (GAS=1) | `(count/max)^0.25` | ✅ (rename "Dust") |
| Liquid | log density × `(1 − 0.78·depth)` | 🔧 crude; ✨ real depth-aware shading (see Plan §6.4) |
| Plasma | `fmod(density·4, 1)` colour bands | 🔧 crude; ✨ proper cyclic-palette + phase |
| Solid | `density > 0.15 ? 1 : 0` | 🔧 crude; ✨ z-buffer solid with lighting |
| Light | per-point speed → palette, × curvature brightness, × log density | ✅ good idea; keep |

### 1.3 Interaction model worth copying

* **Dot-preview while dragging** — 30k–160k projected points, bucketed by depth into ≤64
  colour buckets, drawn as points; no histogram. Camera feels instant. ✅ (Ours: GPU
  progressive histogram is fast enough to *also* do this, but the dot cloud is the
  sub-10 ms fallback on CPU-only machines.)
* **Look changes don't re-iterate** — palette LUT is rebuilt and the dots are
  re-coloured; the full render is debounced (300 ms). ✅ Generalised in Attractr: the
  *development* stage (tone-map + palette) is separate from *accumulation* so any look
  change is instant at full quality, not just on the dots.
* **Retry on blank** — if histogram is empty, retry with 4× iterations and +15 % pad. 🔧
  Replace with deterministic divergence detection + Lyapunov check (we know *why* it's blank).
* **Single-level undo** after randomize/preset. ✨ Full QUndoStack.
* Quality tiers: Draft 1 M/15 M · Standard 2 M/50 M · High 5 M/120 M · Ultra 10 M/300 M
  (preview/HD iterations). Preview canvas 768², HD 2048², 4K 3840². ✅ defaults.
* Video: Turntable (yaw/pitch/roll axis), Morph (A→B keyframes), Orbit Trace (cumulative
  dots), Param Sweep (random target ±40 % of range, previewed before export), ping-pong,
  1–20 s @ 30 fps, 768²/1080²/1080×1920. ✅ all become presets of the general Animator.
* `fullRange` histogram equalisation toggle. ✅
* Transparent background export; solid/custom/image/procedural backgrounds (Stars,
  Forest, Ocean, Aurora). ✅ (procedural themes low priority)
* Presets: curated (3/attractor), user-saved, shareable code, gallery of exports with
  the preset that made them. ✅

### 1.4 Defects / limitations in this source (do not replicate)

| # | Issue | Where | Correction in Attractr |
|---|---|---|---|
| A1 | All flows integrated with **Euler** at fixed dt — visible distortion on Aizawa/Rössler/Thomas; dt exposed as a "parameter" that changes the shape | `attractors.cpp` | **RK4** default (from the C rewrite), Euler selectable; dt is an *integrator* setting, not an attractor parameter |
| A2 | Tone-map normalises to the **single max pixel** → one hot pixel crushes contrast | `renderer.cpp` | percentile normalisation (99.8 % default, user-adjustable) as in the C rewrite |
| A3 | **Bounds re-fitted every render from the projected 2-D extent** → framing "breathes" during turntable animations; several presets carry hacks ("twist 0.221 to avoid degenerate alignment") | `renderer.cpp`, presets | Fit the **3-D bounding sphere once** (rotation-invariant, from the C rewrite) + optional 2-D autofit; bounds are lockable and are part of the keyframe |
| A4 | `Plasma` and `Solid` styles are one-line approximations of the classic Chaoscope modes | `renderer.cpp` | Implement real modes (cyclic palette with phase; z-buffer solid with estimated normals & lighting) |
| A5 | GPU path silently falls back to CPU for Liquid/Light/depth/fullRange, no user feedback | `gpu_renderer.cpp` | All styles on GPU (depth & colour accumulators are just more buffers); engine choice visible in the status bar |
| A6 | Progress reported only for W ≥ 1024 and through globals | `renderer.cpp` | Every job reports progress/ETA through signals |
| A7 | Icon attractor hard-coded to p = 3 symmetry; IFS hard-coded to the Barnsley fern | `attractors.cpp` | General symmetric-icon (degree n, γ term) and general IFS (N affine 3-D maps + probabilities) with fern as a preset |
| A8 | Marketing/mobile features (Instagram nudge, Play review trigger, tutorial spotlight, splash, notification service) | Kotlin UI | Not applicable to desktop — dropped; tutorial replaced by a "first run" tips panel |
| A9 | Preset format: pipe-delimited lines, enums by name | `PresetSerializer.kt` | JSON project files with schema version; CHS1 import kept for compatibility |
| A10 | `fastSin` polynomial approximations in the CPU path | `attractors.cpp` | CPU path uses fp64 libm (numba); GPU preview uses hardware sin/cos; precision engine can use fp64 where supported |
| A11 | Rotation convention ZYX (Rz·Ry·Rx) with yaw about Z; the C rewrite uses yaw(z)→pitch(x)→roll(y); the WebGL has none | all | One documented camera model (trackball quaternion + Euler read-out + perspective); see Plan §6.3 |

---

## 2. `chaoscope_rewrite/` — the pure-C renderer + Win32 GUI (Shpati Koleka)

A single-file C99 renderer with 42 ODE systems, an RK4 integrator, splat kernels,
percentile normalisation, colour-by modes and a camera-orbit animation exporter. The
Win32 GUI shells out to the renderer and shows BMPs.

### 2.1 What is valuable here

| Feature | Detail | Verdict |
|---|---|---|
| **42 flow systems** | Lorenz, Rössler, Thomas, Aizawa, Halvorsen, Chen, Lü, Rucklidge, Four-wing, Dadras, Burke-Shaw, Sprott A–S (19), Arneodo, Coullet, Lorenz-84, Lorenz mod 2, Chua, Chen-Lee, Dequan Li, Three-scroll, Finance, Rabinovich-Fabrikant, Newton-Leipnik, Rikitake — each with default params, nominal initial condition, default dt, and cited references | ✅ port all (see `attractor_catalog.md`) |
| **RK4 integrator** | classic 4-stage; divergence check (`|state| > 1e6`), restart from IC, give up after 50 restarts | ✅ |
| **Bounding-sphere framing** | centre = bbox centre, scale = 1/max radius → attractor fits in unit sphere under any rotation; `FIT = 0.82`; optional `--autofit` for 2-D projected bbox with 3 % margin | ✅ core of our framing model |
| **Perspective projection** | `d = 1 + 0.5·z`, `px = cx + focal·x/d` | 🔧 make perspective strength a camera parameter (0 = orthographic) |
| **Splat kernels** | radius 0–4 soft disk, or bilinear anti-aliased sub-pixel splat (r = 0); gap filling between consecutive points with weight 1/n so density ≈ time spent | ✅ key quality feature for the precision renderer |
| **Supersampling** | `--oversample 1..8`, box-filter down | ✅ |
| **Percentile normalisation** | `NORM_PCT = 0.998` of non-empty pixels → full brightness | ✅ |
| **Colour-by modes** | density / x / y / depth / speed / radius, 1–99 % robust range, colour accumulated per pixel then mean × log-density brightness | ✅ becomes the "Colour source" setting, orthogonal to style |
| **Cyclic palettes + phase** | `--cycle` rotates the LUT; palettes rainbow/fire/ice/plasma/chaoscope/spectrum | ✅ gradient "cyclic" flag + phase (animatable) |
| **Machine-readable catalogue** | `--list-tsv` so front-ends discover systems | ✅ `attractr list --json` |
| **GUI behaviour** | any control change → quick low-res preview; full render after 900 ms idle; drag = rotate, right-drag = yaw, wheel = zoom, "Spin" toggle; dice button for seed | ✅ same interaction pattern |

### 2.2 Defects / limitations (do not replicate)

| # | Issue | Correction |
|---|---|---|
| C1 | Single trajectory → long warm-up per render, poor GPU mapping | N parallel trajectories (configurable); single-orbit mode retained for "Orbit Trace" |
| C2 | `double *dens` + `qsort` of all non-zero pixels for percentile — O(n log n) per render | Histogram-of-densities (4096 bins) to find the percentile in O(n) |
| C3 | BMP-only output, GUI talks to renderer through a child process and temp files | In-process engines, PNG/TIFF/JPEG/WebP export |
| C4 | Yaw/pitch default 180° to compensate for image orientation | Fix orientation at the projection level |
| C5 | Win32-only GUI, no threading (blocking) | PySide6, worker threads |
| C6 | Parameters beyond the first 6 not editable in GUI (`UIP = 6`) | Unlimited parameters |

---

## 3. `strange-attractors-webgl/` — Jérémie Piellard's WebGL experiment

A browser demo: 4 two-dimensional maps (De Jong, Bedhead, Clifford, Fractal Dream),
many random-start trajectories, additive point splatting into an FBO, progressive
accumulation each animation frame, three compositing modes (dark, light, colour with
picked fg/bg), an "infos" overlay drawing name/formula/parameters, and PNG download at
1024/2048/4096 with the info caption baked in.

### 3.1 What is valuable here

| Feature | Verdict |
|---|---|
| **Progressive accumulation** — draw `min(2^17, remaining)` points per animation frame until a target count is reached; UI stays at 60 fps; "points drawn" indicator | ✅ exactly how our preview engine schedules work |
| Target points = `intensity / (256·quality) · minDim²` — density expressed per pixel, so changing canvas size keeps the look | ✅ iterations expressed as *points per pixel* in Attractr UI (with absolute count shown) |
| Compositing modes: dark (additive white on black), light (inverted), colour (fg/bg lerp) | ✅ two-colour "duotone" palette preset + invert toggle |
| Info overlay with formula + parameters baked into the exported image | ✅ "Caption" export option and the report's thumbnail |
| Attractors: Bedhead, Fractal Dream (not in the other sources) | ✅ add to catalogue |
| Random starting points each batch | ✅ |

### 3.2 Defects (do not replicate)

| # | Issue | Correction |
|---|---|---|
| W1 | **Clifford formula is wrong**: `y' = sin(c·x) + d·cos(b·y)` — canonical is `y' = sin(b·x) + d·cos(b·y)` (the C++ source has it right) | Use the canonical form; add a unit test on formulas vs. literature |
| W2 | Accumulates in an **8-bit RGBA texture** with additive blending → saturates at 255; "quality" slider dims the point colour to delay saturation | Float / uint32 accumulation |
| W3 | Depends on the `Page` demopage framework, fonts from Google | n/a |

---

## 4. Reference: the classic Chaoscope 0.3.1 (Nicolas Desprez, Windows)

Not present in `sample_source/` — listed from public knowledge so the plan can aim at
*"all features of the original"*. **Please confirm or trim this list** (Plan §12, Q1).

| Classic feature | Attractr plan |
|---|---|
| Attractor types: Icon, IFS, Julia, Lorenz, Pickover, Polynomial A/B/C, Polynomial Sprott, Unravel | Icon (general), IFS (general), Julia (quaternion), Lorenz, Pickover ✅; **Polynomial maps A/B/C/Sprott** (quadratic/cubic 3-D polynomial maps with coefficient vectors) ✨ added; *Unravel* — formula not public, optional research item |
| Render modes Gas, Light, Liquid, Plasma, Solid | All five, implemented properly (Plan §6.4) |
| **Search** — random parameter search that keeps only chaotic results (Lyapunov exponent) | ✨ `Search` panel: Lyapunov + boundedness + coverage filters, thumbnails grid |
| Gradient editor | ✨ full gradient editor (Plan §7.3) |
| Mouse rotate / zoom / pan, perspective | ✅ trackball camera + perspective slider |
| Lights for Liquid/Solid (position, colour, ambient/diffuse/specular) | ✨ in render-mode settings |
| Anti-aliasing / quality, iteration count | ✅ supersampling, splat, iterations |
| Project files, batch rendering, image export with size presets | ✅ `.attractr` JSON, render queue, export dialog |

---

## 5. Consolidated feature union (what "faithful + improved" means)

```
            ┌─────────────── Android/iOS (17 attractors, 6 styles, 10 palettes, presets, video modes,
            │                dot-preview, GPU compute, daily attractor, codes, gallery)
            │
 Attractr = │  ∪  C rewrite (42 flows, RK4, splats, supersampling, percentile, colour-by,
            │                sphere framing, perspective, cyclic palettes/phase, catalogue)
            │
            │  ∪  WebGL (progressive accumulation, density-per-pixel, duotone compositing,
            │            caption overlay, Bedhead, Fractal Dream)
            │
            └  ∪  Classic Chaoscope (Search, Polynomial maps, proper Liquid/Solid/Plasma/Light,
                               gradient editor, lights)
            + new: formula DSL editor, animator/timeline, reports, stats panels, CLI
```
