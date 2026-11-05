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
