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

## 3. Second round — all implemented

| Item | Where |
|---|---|
| Return maps with memory: `on_section { … }` + `section_dir:` | `core/formula/*`, all kernels; Lorenz / Rössler return maps; [formula_dsl.md](formula_dsl.md) |
| Escape-time renderer: `kind: escape` (Buddhabrot technique) | kernels (CPU / GL compute / OpenCL), `x0 y0 z0`, `region/bailout/max_iter/min_iter`; Buddhabrot, Burning Ship, Tricorn, Julia escape orbits |
| Translations: `tr()` wrapping, `.ts` tooling, German UI, `.atr` overlays | `tools/wrap_tr.py`, `tools/extract_ts.py`, `tools/extract_attractor_strings.py`, `resources/i18n/`, `core/attractors/overlays.py` |
| Resume with different supersampling / splat / engine | already supported by the output-resolution checkpoint design — now tested and documented ([checkpoints.md](checkpoints.md)) |
| Uniform "Finish now" for tiled renders | **interleaved tiles** (8 rounds) in all GPU engines — uniform progress, per-round partials and uniform checkpoints as a bonus ([engine_gl.md](engine_gl.md)) |
| Gallery → batch re-render | Gallery multi-select + *Re-render…* with a render preset |
| GPU develop for Liquid / Solid | `shaders/develop_light.comp` (height field, blur, normals, Phong; chunked with halos) |
| Persisted parameter history | `history` in the project file; sliders are seeded from it |

## 4. What could come next

1. **Anti-Buddhabrot / Nebulabrot** — `kind: escape` variants that draw the *bounded* orbits
   (or colour channels by three different `max_iter` values): a `plot_bounded:` header and
   a per-channel render would do it.
2. **Importance sampling for escape systems** — most Buddhabrot starts are wasted inside the
   set; a coarse "escape map" of the region (first pass) could bias the starts towards the
   boundary, a 5–20× speed-up.
3. **Return-map event on GL points** — `gl_points` skips `on_section` / escape programs; a
   second update pass could store the pre-event state so the vertex shader can plot it.
4. **More locales** — the tooling is in place; French/Spanish `.ts` files and the remaining
   attractor overlays are translation work, not code.
5. **Per-tile time budgets** — interleaving already keeps tiles uniform; a time-based
   "finish in N minutes" could set `finish_at` from the measured pass rate.
6. **Render-preset sharing** — export/import of `render_presets.json` entries as ATR-style
   codes for pasting into issues/forums.
