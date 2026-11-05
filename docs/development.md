# Development guide

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # PySide6, numpy, numba, moderngl, pyopencl, Pillow + dev tools
pytest                           # unit + engine tests (offscreen Qt)
ruff check src tests tools       # lint
attractr list attractors         # smoke test
```

Optional: `pip install -e ".[cl-cpu]"` installs the POCL OpenCL CPU runtime so the OpenCL
engine can be exercised on machines without a GPU driver.

Environment variables:

| Variable | Effect |
|---|---|
| `ATTRACTR_HOME` | user data dir (default `~/.attractr`): attractors, palettes, presets, numba cache, logs |
| `ATTRACTR_CPU_BUDGET_MB` | memory budget for the CPU engine's private histograms (default 1024) |
| `QT_QPA_PLATFORM=offscreen` | headless Qt (tests, PDF reports on servers) |

## Layout

```
src/attractr/
  core/      pure logic, importable without a display (CLI + tests)
  cli/       argparse sub-commands (thin wrappers over core)
  gui/       PySide6 widgets, controllers, dialogs
  resources/ .atr attractors, palettes JSON, presets, icons, logo
tools/       one-off scripts (contact sheet, logo generator, benchmarks)
tests/       unit/ · engines/ · gui/ · golden/
docs/        this documentation
```

## Coding standards

* Small modules (≈ ≤ 300 lines) and small functions; a module's docstring states the one
  thing it does.
* `from __future__ import annotations`, type hints everywhere, `dataclass(frozen=True)` for
  settings/value objects.
* No Qt imports under `attractr.core` except `attractr.core.jobs` (signals) and the PDF
  renderer.
* Everything that runs longer than ~50 ms runs in a `Job` (see `core/jobs`) and reports
  progress; never block the GUI thread.
* Errors shown to the user are `FormulaError`/`ValueError` with a message; tracebacks go to
  the log.
* Tests: every bug fix adds a regression test; every attractor must parse and render in the
  contact sheet (`python tools/contact_sheet.py`).

## How to add…

**…an attractor** — drop a `.atr` file into `src/attractr/resources/attractors/<family>/`
(see [formula_dsl.md](formula_dsl.md)). It appears in the GUI browser, `attractr list`, the
contact sheet and the generated docs. Add curated presets to `resources/presets/curated.json`.

**…a palette** — add an entry to `resources/palettes/builtin.json` (stops are
`[pos, r, g, b, a]` in 0..1).

**…a render style** — implement `style_<name>(ctx) -> (rgb, alpha)` in
`core/render/develop/styles.py`, register it in `STYLES`, declare which buffers it needs in
`core/render/accumulators.py`, and add it to `STYLES` in `core/render/settings.py`.

**…an engine** — subclass `Engine` (`core/render/engines/base.py`), implement `probe()` and
`accumulate()`, and register a factory in `engines/selector.py`. Use the formula code
generators (`core/formula/codegen_*.py`) so the engine supports every attractor.

**…a CLI command** — add `cli/cmd_<name>.py` with `add_parser(sub)` and register it in
`cli/main.py`.

## Release checklist

1. `pytest` and `ruff` green; contact sheet regenerated and reviewed.
2. `version.py` bumped; `docs/changelog.md` updated.
3. `python -m build`; PyInstaller specs (M6) produce launchable bundles.

## Packaging

`pip install pyinstaller && pyinstaller attractr.spec` builds a one-folder bundle in
`dist/Attractr/` (Windows `.exe` with the `.ico`, macOS `.app` when run on macOS, Linux
binary). The bundle contains no pre-compiled numba kernels — they are compiled into
`~/.attractr/cache` on first run (the GUI does this in a background process).

## Helper processes

The GUI starts `python -m attractr.core.worker_server` (thumbnails, formula probes, daily
attractor) and, on first run, `python -m attractr.core.warmup` (kernel pre-compilation).
Both are ordinary subprocesses of the same interpreter; they inherit `ATTRACTR_HOME`.


## Internationalisation

Scaffolding only: `attractr/i18n.py` provides `tr()` (Qt `translate` in the `attractr`
context, safe without a QApplication) and `install_translators()` (loads
`resources/i18n/attractr_<locale>.qm` + Qt's `qtbase_<locale>.qm` for the system locale
or `ATTRACTR_LANG`). Strings are **not yet wrapped** — when a translation is wanted, wrap
the user-visible literals of a panel in `tr("…")`, run `pyside6-lupdate`, translate, and
`pyside6-lrelease` (see `resources/i18n/README.md`). Attractor descriptions and parameter
hints live in the `.atr` files and would need a parallel mechanism (per-locale `.atr`
overlays) — deliberately left for later.
