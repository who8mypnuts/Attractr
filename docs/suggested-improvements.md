# Suggested improvements — status

This file started as a wish-list after the plan was implemented. Everything in the
original list has now been done (see the *Post-plan additions* section of
[changelog.md](changelog.md)); the table below records where each item landed, followed
by the items that were tried and dropped and a fresh list of what could come next.

## 1. Implemented

| Item | Where |
|---|---|
| DSL: 4th state variable `w` (`w'`, `dw`, `ic: x y z w`) | `core/formula/*`, all four engines; [formula_dsl.md](formula_dsl.md) |
| DSL: `plot = ex, ey[, ez]` | same |
| DSL: `section = expr` (Poincaré sections, gap filling auto-off) + `boost:` header | same |
| 34 new attractors (driven oscillators, stroboscopic maps, 4-D hyperchaos, sections, jerk systems, Zaslavskii, Cathala, Martin maps, Ushiki, icon extension, restricted chaos game, 8 IFS classics) + 18 curated presets | `resources/attractors/**`, `resources/presets/curated.json`; [attractor_catalog.md §3b](attractor_catalog.md) |
| GPU develop pass | `core/render/develop/gpu_develop.py`, `shaders/develop.comp`; [render_styles.md](render_styles.md) |
| Progressive final renders: Finish now, checkpoints, resume, live job thumbnails | `core/render/checkpoint.py`, engines, `gui/controllers/render_job.py`, Jobs panel; [checkpoints.md](checkpoints.md) |
| Slider ergonomics (wheel/arrow modifiers, nudge buttons, value history, copy/paste) | `gui/widgets/slider_spin.py` |
| Drag & drop (palettes, gallery images, `.atr`, `.attractr`, gradients, share codes) | `gui/dragdrop.py`, viewport, gallery, gradient editor |
| Render presets, batch rendering (GUI + `attractr batch`), queue notification | `core/project/render_presets.py`, `core/project/batch.py`, `cli/cmd_batch.py`, render dialog, main window |
| Per-style recommended quality hint | render dialog (`RECOMMENDED_PPP`) |
| Thumbnail cache limit | `core/io/cache.py`, Preferences |
| Search panel polynomial-map mode | `gui/panels/search_panel.py` |
| SVG orbit export | `core/io/svg_export.py`, `cli/cmd_svg.py`, File menu |
| i18n scaffolding | `attractr/i18n.py`, `resources/i18n/` (strings not yet wrapped) |
| Robust framing / Lyapunov seeding for small-basin systems | `core/render/framing.py`, `core/analysis/lyapunov.py` |

## 2. Tried and dropped

* **Burning Ship / Mandelbrot "orbit cloud"** — escape-time iterations have no bounded
  attractor; the framing sample is dominated by escaping orbits. Would need a
  Buddhabrot-style renderer (plot only orbits that escape, framed on the parameter plane)
  — a different program.
* **Duffing–van der Pol map** `x' = y, y' = -b x + (a - c y²) y` — no chaotic parameter
  set found in a quick random scan; not included.
* **Hadley** / **Langford** as separate entries — identical to Lorenz-84 / Aizawa; a
  curated preset ("Hadley spring") covers the requested regime instead.

## 3. What could come next

1. **Return maps with memory** — `section` plots the crossing point; a *return map*
   (x_{n+1} vs x_n at successive crossings, e.g. the Lorenz map of successive z maxima)
   needs the previous crossing value to be stored at the event. A DSL hook such as
   `on_section: w = x` (assignments executed only when the section fires) would make
   every textbook return map a two-line program.
2. **Buddhabrot-style escape renderer** — a fourth kind (`kind: escape`) where each
   trajectory starts at a random point of a region, is iterated until it escapes or hits a
   step limit, and only escaping orbits are plotted. Shares the accumulation/develop
   pipeline; needs its own framing (the start region) and kernel loop.
3. **String wrapping for translations** — the `tr()` seam exists; wrapping the ~600
   user-visible literals and adding a German/French `.ts` is mechanical work, plus a
   per-locale overlay format for `.atr` descriptions and hints.
4. **Resume across sizes** — a checkpoint stores buffers at output resolution; allowing a
   resumed render to change supersampling / splat radius would need the supersampled
   buffers (×ss² memory) to be stored.
5. **Tiled "Finish now"** — for multi-tile GPU renders the soft stop leaves later tiles at
   the reduced budget (documented); a fairer policy would render every remaining tile to
   the same fraction as the one in progress, which requires knowing the time budget
   rather than a flag.
6. **Gallery → batch re-render** — select several gallery entries and re-render them with
   a render preset (the batch machinery takes a folder today; a list of settings would be
   a five-line addition).
7. **GPU develop for Liquid / Solid** — screen-space normals and lighting as a second
   compute pass (a 3×3 neighbourhood), leaving only equalisation and image backgrounds on
   the CPU.
8. **Per-parameter history persistence** — the *Recent values* list lives in the widget;
   storing it in the project (per attractor/parameter) would make it survive sessions.
