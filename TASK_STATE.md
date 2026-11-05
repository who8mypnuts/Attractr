# TASK_STATE — review loop over the recent branch changes

Scope: the commits after `b873b34` on `master` (round-2 features: `on_section`, `kind: escape`,
interleaved tiles, GPU Liquid/Solid develop, gallery re-render, parameter history, i18n, and the
large-render robustness fix). Nothing is committed during this review (instruction).

## How to run

```bash
export ATTRACTR_HOME=/tmp/attractr_home QT_QPA_PLATFORM=offscreen PATH=$PATH:/home/model/.local/bin
cd /workspace/Attractr
ruff check src tests tools            # lint
timeout 290 python3 -m pytest tests -q  # 106 tests before the review (all passing)
```

## Last successful commands
- `ruff check src tests tools` — clean (after cycle 4)
- `pytest tests -q -o addopts=""` — 122 passed (after cycle 4)

## Known failures
- none

## Rubric score (evidence after each cycle)
| Cycle | Architecture /40 | DRY /30 | Comments /20 | Tests /10 | Total | Verdict |
|---|---|---|---|---|---|---|
| 0 (as found) | 28 | 18 | 16 | 8 | 70 | below gate: three copies of the interleaved-tile loop, 200-line `accumulate` methods, duplicated `_assemble`/`_tile_size`/budget logic, `main_window` growing past 600 lines |
| 1 | 33 | 25 | 17 | 9 | 84 | structural pass (tiling / setup / host planes / render actions) |
| 2 | 36 | 27 | 18 | 9 | 90 | GPU template method, layering, docstrings, damaged-checkpoint & tool tests |
| 3 | 37 | 28 | 18 | 9 | 92 | CPU engine on the shared schedule; kw-only tuning |
| 4 | 37 | 28 | 19 | 9 | **93** | validator split, resume folder rule + test, logging idempotence — all gates met |

## Findings log

### Cycle 1 — structural pass (systemic issues first)

| # | Critic | Severity | Subsystem | Finding | Root cause | Correction |
|---|---|---|---|---|---|---|
| 1 | DRY / Architect | **critical** | engines | The interleaved-tile loop (rounds, per-tile progress, finish-now, partial pacing, progress text) existed three times (gl_engines, opencl_engine, gl_points) — ~150 lines each, drifting already | scheduling was written inside each engine's `accumulate` | `engines/tiling.py`: `TileSchedule` drives the loop once; engines implement the 4-method `TileVisitor` protocol |
| 2 | DRY | high | engines | Render setup (framing, lock, resume plan, camera, projection constants, colour range, warm-up/budget stats) copied in all four engines | no shared "plan" object | `engines/setup.py`: `prepare()` → immutable `RenderPlan` used by every engine; `apply_lock`/`effective_camera`/`splat_kernel`/`escape_config` moved there (they were defined in `cpu_numba` and imported by the GPU engines) |
| 3 | DRY | high | engines | `_assemble`, host plane allocation and tile-size maths duplicated per engine | same | `tiling.HostPlanes` (planes + slab/store + assemble), `tile_side`/`tile_layout`/`largest_tile`, `downsample` in one place |
| 4 | Architect | high | engines | `accumulate` methods of 200+ lines with nested closures mutating outer state | everything inline | each engine's `accumulate` is now ~45 lines: compile → prepare → tiles → schedule.run → stats; device details live in `_GLTileVisitor` / `_CLTileVisitor` / `_PointsTileVisitor`; CPU engine split into `_ThreadBuffers`, `_KernelRunner`, `_warm_up`, `_passes` |
| 5 | Defensive | medium | engines/tiling | "Finish now" on a tiled render left tiles up to one round apart | `finish_at` was taken from the tile in progress | `finish_at` = most advanced tile; tiles behind catch up (uniform); covered by `test_schedule_soft_finish_is_uniform_and_hard_cancel_raises` |
| 6 | Defensive | medium | engines/cpu | `t_step` restarted from the *step* count after warm-up while the kernel advances it per *sub-step* (wrong `t_step` for `substeps > 1`) | CPU passed `done + steps_done`, GPU passed `steps × substeps` | `_KernelRunner.t_base += steps × substeps` |
| 7 | Defensive | medium | tests | edge tiles (smaller than the shared image set) were untested; private-method monkeypatching in tests | — | `tile_budget_bytes` engine attribute as the documented seam; `test_edge_tiles_match_untiled` on all three GPU engines; pure-Python schedule tests |
| 8 | DRY | medium | gui | `render/*` QSettings keys and job construction repeated in quick/resume/batch/re-render and the dialogs | no prefs object | `gui/state/render_prefs.py` (`RenderPrefs.load().job(...)`, key constants) |
| 9 | Architect | medium | gui | `main_window.py` at 646 lines with render commands + tray notification inline | window as god object | `gui/controllers/render_actions.py` (`RenderActions`); window only wires actions (550 lines) |
| 10 | DRY | medium | develop | `gpu_develop._run` / `_run_lit` repeated uniform setup, buffer binding and chunking; module-level globals for context state | two paths grown separately | `_GpuDeveloper` class: shared `_tone_uniforms`, `_bound` context manager, `_chunks`; named flag / binding constants |
| 11 | Comments | low | engines | new helpers lacked docstrings; magic numbers (1e30, 0.12, bindings) unexplained | — | docstrings on every new class/function; named constants (`NO_DEPTH`, `RELIEF_SCALE`, `BIND_*`, `FLAG_*`) |

Regression check vs. the pre-review tree: **improved** — all 106 original tests still pass, 10 added; edge-tile parity 1.000 on gl_compute / opencl / gl_points; GPU-develop parity unchanged.

Score after cycle 1: Architecture 33 · DRY 25 · Comments 17 · Tests 9 → **84** (gate not yet met: architecture/DRY just under).

### Cycle 2 — critique of the code produced in cycle 1

| # | Critic | Severity | Subsystem | Finding | Root cause | Correction |
|---|---|---|---|---|---|---|
| 1 | DRY | high | engines | the three GPU `accumulate` methods were still ~45 identical lines (open → prepare → tiles → schedule → assemble) | scheduling extracted, orchestration not | `engines/gpu_base.py`: `TiledGpuEngine` template method with five abstract hooks (`_open`, `_trajectory_count`, `_budget_bytes`, `_bytes_per_pixel`, `_visitor`); engines are now hooks + a visitor (gl_engines 360, opencl 337, gl_points 342 lines) |
| 2 | Architect | medium | engines | visitors required an implicit `create_tile_state()` call before `run()` | two-phase construction | visitors allocate in `__init__` (given the active tiles) and free in `release()`; `_set_render_uniforms` moved out of the engine class |
| 3 | Architect | medium | gui | `gui/state/render_prefs.py` imported a controller (`RenderJob`) — layering inversion | job factory placed on the prefs object | `RenderPrefs` is pure state; `make_job()` lives in `render_actions.py` |
| 4 | Architect | low | engines/tiling | `TileSchedule.run` mixed the round loop and the per-tile loop with a walrus condition | — | split into `run` (rounds) and `_visit` (one tile to its target) |
| 5 | DRY | low | engines | GPU budget constants duplicated in `opencl_engine` | copy | imported from `gl_common` |
| 6 | DRY | low | tests | `app` fixture and `pump()` duplicated in two GUI test modules | — | moved to `tests/conftest.py` |
| 7 | Comments | medium | many | ~130 new / changed functions and classes without docstrings | — | Google-style one-liners added (`/tmp/add_docs.py`, reviewed by hand); stale mentions removed |
| 8 | Defensive | medium | checkpoint | `Checkpoint.load` leaked `KeyError` / `BadZipFile` on damaged files; the GUI resume action only caught `(OSError, ValueError, KeyError)` | — | `load` normalises to `ValueError`/`OSError` (documented in *Raises*); test `test_checkpoint_load_rejects_damaged_files` |
| 9 | Defensive | medium | tools | `wrap_tr.py` wrapped hex colours (`"#ff0000"`) as messages; no test for a source-rewriting tool | letter heuristic | `HEX_COLOUR` exclusion; `tests/unit/test_i18n_tools.py` covers byte-vs-char offsets, f-strings, idempotence and `.ts` merge |
| 10 | Defensive | low | gui | `RenderPrefs` / `make_job` had no tests | — | `tests/gui/test_render_prefs.py` |

Regression check vs. cycle 1: **improved** (121 passed; parity tests identical).

Score after cycle 2: Architecture 36 · DRY 27 · Comments 18 · Tests 9 → **90**.

### Cycle 3 — critique of the cycle-2 code

| # | Critic | Severity | Subsystem | Finding | Root cause | Correction |
|---|---|---|---|---|---|---|
| 1 | DRY | medium | engines/cpu | the CPU engine kept its own pass loop (adaptive steps, pacer, soft finish, progress) — a second copy of what `TileSchedule` does | CPU was left out of the extraction | `_CpuAccumulation` implements `TileVisitor`; the CPU buffer is one tile driven by the same `TileSchedule` (cpu_numba 219 lines, no pass loop) |
| 2 | Defensive | **high** | engines/tiling | positional `TileSchedule(...)` tuning arguments were mis-ordered in the new CPU call (`min_steps` landed in `skip_tiles` → zero active tiles, empty image) — caught by the engine tests | ten positional dataclass fields | tuning fields are `kw_only`; both call sites use keywords |
| 3 | Architect | low | engines/cpu | `_passes` took nine parameters | state scattered | state lives on `_CpuAccumulation` |
| 4 | Comments | low | engines/tiling, gpu_base, render_job | unused `label` field / `supports_finish` attribute; redundant `astype` | leftovers | removed |
| 5 | Comments | low | docs | architecture / CPU engine docs did not describe the new layering | — | `docs/architecture.md` engines diagram, `docs/engine_cpu.md` updated |

Regression check vs. cycle 2: **improved** (121 passed; the cycle-3 regression was caught by `test_cpu_engine` before being recorded).

Score after cycle 3: Architecture 37 · DRY 28 · Comments 18 · Tests 9 → **92**.

### Cycle 4 — critique of the cycle-3 code and the remaining round-2 modules

| # | Critic | Severity | Subsystem | Finding | Root cause | Correction |
|---|---|---|---|---|---|---|
| 1 | Architect | medium | formula/validate | `validate()` had grown the escape-kind and `on_section` rules inline (~40 lines in one function) | rules appended in place | `_check_escape()` and `_check_on_section()` with docstrings; `validate()` reads as a list of checks |
| 2 | Defensive | medium | gui/render_actions | "Resume from checkpoint…" derived the output folder as `<file>/../..` for *any* chosen file — a CLI-made checkpoint next to an image would resume into a surprising folder | assumption about the GUI layout | folder = parent of a `checkpoints/` dir, else the preferred output folder; covered by `test_resume_render_picks_output_folder_from_checkpoint_location` (also checks that a damaged file is reported, not raised) |
| 3 | Defensive | low | io/logging_setup | calling `setup_logging` twice in one process would add duplicate file handlers | no guard | idempotent (returns once the crash file is open) |
| 4 | Architect | low | gui/render_actions | `RenderActions` could only be built with a real `MainWindow` (QObject parent) → untestable in isolation | — | duck-typed window; `QObject` parent only when it is one |
| 5 | Comments | low | formula/parser, tiling | `parse_on_section` had no docstring; dataclass docstring spacing | — | fixed |
| 6 | DRY | low | gui/render_dialog | settings provider called twice for one estimate | — | single call |

Regression check vs. cycle 3: **improved** (122 passed).

## Exit-gate check
* Overall 93 / 100 ≥ 90 ✔ · Architecture 37/40 (92 %) ✔ · DRY 28/30 (93 %) ✔ · Comments 19/20 (95 %) ✔ · Tests 9/10 (90 %) ✔
* Zero critical failures ✔ (cycle-1 critical — triplicated scheduling — resolved)
* `ruff` clean, 122 tests pass (`pytest tests -q -o addopts=""`) ✔
* Nothing committed (per instructions); `git status` lists the working-tree changes.

## Residual notes for a future session
* `cpu_kernel_template.py` necessarily mirrors the escape / section logic of the GLSL and OpenCL kernels in three languages; parity tests (`tests/engines/test_gpu_parity.py`) are the guard.
* Pre-existing code outside the reviewed commit range (formula parser internals, older panels) still has undocumented private helpers; not in scope here.
