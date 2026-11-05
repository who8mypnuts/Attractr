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

## Engines (`core/render/engines`)

```
setup.prepare()  ──►  RenderPlan (framing, camera, projection, colour range, budget, warm-up)
                          │
        ┌─────────────────┴──────────────────┐
   cpu_numba.CpuEngine            gpu_base.TiledGpuEngine (template method)
   _CpuAccumulation (visitor)        │  hooks: _open · _trajectory_count · _budget_bytes
                                     │         _bytes_per_pixel · _visitor
                                     ├── gl_engines   (_GLTileVisitor, _TileImages)
                                     ├── opencl_engine (_CLTileVisitor)
                                     └── gl_points    (_PointsTileVisitor)
   all drive  tiling.TileSchedule.run(visitor)  ──►  tiling.HostPlanes.assemble() ──► RenderResult
```

* `setup.py` — everything every engine derives from the settings, computed once.
* `tiling.py` — tile layout, host planes, and the interleaved round-robin schedule
  (adaptive steps per pass, soft finish, paced partials, progress); engines only implement
  the four-method `TileVisitor` protocol (`select`, `warm_up`, `run_pass`, `readback`).
* `gpu_base.py` — the shared GPU `accumulate`; each GPU engine is ~five hooks plus a visitor.
* `base.py` — `Engine` interface, `ResumePlan` (checkpoint continuation), `PartialPacer`.

## Threading

Core functions are synchronous and cancellable (`CancelToken`) with progress callbacks
(`ProgressTracker`). The GUI wraps them in `Job`s executed on `JobThread`s managed by a
`JobQueue`; results cross threads as NumPy arrays via Qt signals.
