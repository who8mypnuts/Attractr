# Attractr documentation

| Document | Purpose | Status |
|---|---|---|
| [PLAN.md](PLAN.md) | **Master plan** — vision, principles, technology decisions, architecture, GUI design, milestones with acceptance criteria, risks, open questions | draft for approval |
| [source_analysis.md](source_analysis.md) | Inventory of the three source codebases: what to keep, what to fix, what to drop | draft |
| [attractor_catalog.md](attractor_catalog.md) | Every attractor Attractr will ship with — equations, parameters, defaults, sources, tiers | draft |
| [formula_dsl.md](formula_dsl.md) | Specification of the user formula language (single source of truth for CPU/GPU code) | draft |

## Implementation docs

| Document | Content |
|---|---|
| [architecture.md](architecture.md) | layers, data flow, threading |
| [development.md](development.md) | setup, standards, how to add attractors/styles/engines |
| [cli.md](cli.md) | every command and flag |
| [engine_cpu.md](engine_cpu.md) | the numba reference engine |
| [camera.md](camera.md) | framing + projection model |
| [render_styles.md](render_styles.md) | tone mapping, styles, colour sources, backgrounds |
| [statistics.md](statistics.md) | definitions of every reported number |
| [reports.md](reports.md) | render report formats and sections |
| [project_format.md](project_format.md) | `.attractr`, `.atr`, palettes, codes, PNG metadata |
| [engine_gl.md](engine_gl.md) | GPU engines (GL compute, OpenCL), tiling, parity |
| [engine_selection.md](engine_selection.md) | auto selection order and fallback rules |
| [gradients.md](gradients.md) | gradient model and editor |
| [animation.md](animation.md) | timeline, keyframes, helpers, rendering, ffmpeg |
| [gui_guide.md](gui_guide.md) | panels, viewport, shortcuts |
| [changelog.md](changelog.md) | release notes |
| [attractors/](attractors/README.md) | generated page per attractor |
| `images/contact_sheet.png` | every built-in attractor at default settings |
