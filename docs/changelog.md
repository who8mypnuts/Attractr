# Changelog

## 0.1.0 (in development)

Milestones M0–M6 of the plan:

* Formula DSL (maps, flows, IFS) with numba, GLSL and OpenCL back-ends; 79 built-in attractors.
* Engines: CPU (numba, fp64, threaded), OpenGL 4.3 compute (preview + tiled precision), OpenCL, OpenGL 3.3 point-splat fallback; fp64 precision mode on GPU (software double math for GLSL); automatic selection and fallback.
* Fixes after review: colour-source/style changes now re-accumulate when they need new buffers; the formula editor dock can be enlarged or popped out; side panels scroll instead of enforcing large minimum heights.
* Six render styles (Gas, Dust, Light, Liquid, Solid, Plasma), colour sources, backgrounds incl. procedural themes.
* PySide6 GUI: progressive preview, docks for everything, gradient editor, formula editor, search, mutate grid, presets, daily attractor, gallery, jobs.
* Animator: timeline/keyframes/easing, helpers, locked framing, frame sequences, ffmpeg encoding.
* Reports (Markdown/Text/HTML/PDF), statistics, Lyapunov/dimension analysis, CLI.

### Post-plan additions (suggested-improvements round)

* **DSL**: fourth state variable `w` (`w' = …` / `dw = …`, `ic: x y z w`), `plot = ex, ey[, ez]`
  (what is drawn), `section = expr` (Poincaré sections — gap filling is switched off
  automatically), `boost:` header (iteration multiplier for sparse sections). All four
  engines (CPU, GL compute, OpenCL, GL points) implement the new semantics identically.
* **34 new attractors** (113 total): driven Duffing / Ueda / van der Pol and their
  stroboscopic maps, Rössler hyperchaos and Lorenz–Stenflo (4-D), Lorenz and Rössler
  Poincaré sections, Wei, Wang–Sun, Anishchenko–Astakhov, Nosé–Hoover, Thomas (asymmetric),
  four jerk systems (Linz–Sprott, Sprott quadratic/cubic, Malasoma), Zaslavskii, Cathala,
  Quadrup-Two, Threeply, Ushiki, Gumowski–Mira (extended), Symmetric Icon (extended, with
  eight *Symmetry in Chaos* presets), restricted chaos game on an n-gon, and eight IFS
  classics (Sierpinski carpet, Vicsek, Koch, Lévy C, Pythagoras tree, de Rham, maple leaf,
  fractal tree). 18 new curated presets.
* **GPU develop pass**: Gas/Dust/Light/Plasma looks of images ≥ 1.5 Mpixel are developed by an
  OpenGL 4.3 compute shader (`develop.comp`) when available — identical output, a fraction of the
  time at 4K–16K. CPU fallback for Liquid/Solid, equalisation, bloom and image backgrounds.
  Preference toggle and `attractr render --develop cpu|gpu|auto`.
* **Progressive final renders**: live thumbnails in the Jobs panel, ⏹ *Finish now* (soft stop that
  still saves/reports), periodic **checkpoints** (`*.attractr-ckpt.npz`) with *Render → Resume from
  checkpoint…* / `attractr render --resume FILE`, `--checkpoint-every`, `--finish-after`.
  Resumed renders use a fresh trajectory seed per segment and reproduce the full budget exactly.
* **Quality of life**: slider scrubbing (wheel/arrow keys with Ctrl = fine, Shift = coarse, − / + nudge
  buttons, per-parameter *Recent values* history, copy/paste); drag & drop of palettes, gallery images,
  `.atr`, `.attractr`, gradient files and share codes onto the viewport/window; **render presets**
  (named size/quality/format/report recipes, built-in + user), **Batch render folder…** /
  `attractr batch FOLDER --preset NAME`, desktop notification when the queue finishes.
* Smaller items: per-style *recommended points-per-pixel* warning in the render dialog (Solid ≥ 30,
  Liquid ≥ 20); thumbnail-cache size limit (Preferences, pruned oldest-first); Search panel
  **polynomial-map mode** (the classic Chaoscope 30-coefficient Sprott search, with adjustable
  coefficient magnitude, independent of the selected attractor); **SVG export** of the orbit trace
  (File menu / `attractr svg`).
* i18n scaffolding (`attractr.i18n.tr`, `.qm` loading for the system locale / `ATTRACTR_LANG`).
* Framing/analysis robustness: trajectories that escape (or wander ≫ the median extent)
  during the framing sample are ignored, and the Lyapunov probe starts from a typical
  on-attractor state — small-basin systems no longer get a blown-up frame or a spurious
  "divergent" badge.
