# Architecture

See PLAN.md §5 for the design rationale. This page tracks the implemented structure.

```
RenderSettings ──► resolve_spec() ──► Engine.accumulate() ──► RenderResult ──► develop() ──► Developed ──► save_image()
 (frozen)           registry /         cpu · gl_* · opencl       count, depth,     styles,        RGBA float    PNG/JPEG/…
                    inline .atr                                  zmin, cv, stats   background                   + metadata
                                                                                                  └──► write_report() md/txt/html/pdf
```

* `core/formula` — DSL → AST → numba / GLSL / OpenCL code; single source of truth.
* `core/attractors` — `AttractorSpec` + registry (built-in and user `.atr` files).
* `core/render` — settings, camera, framing, engines, develop (styles), stats, pipeline.
* `core/color` — gradients (stops → LUT in several interpolation spaces), palette library.
* `core/analysis` — Lyapunov, dimension, probe (classification), search, daily.
* `core/project` — serialisation, project files, codes.
* `core/report`, `core/io`, `core/jobs` — reports, image I/O, cancellable jobs.
* `cli` — thin argparse layer. `gui` — PySide6 (milestone 3).

## Threading

Core functions are synchronous and cancellable (`CancelToken`) with progress callbacks
(`ProgressTracker`). The GUI wraps them in `Job`s executed on `JobThread`s managed by a
`JobQueue`; results cross threads as NumPy arrays via Qt signals.
