# Engine selection & fallback

| Purpose | Order tried (`Quality.engine = "auto"`) |
|---|---|
| preview (viewport, thumbnails, search) | `gl_compute` → `opencl` → `cpu` |
| final (render dialog, CLI, animation) | `gl_precision` → `opencl` → `cpu` |

Each engine is probed once per process (`attractr info`, Statistics → System): context
creation, a tiny atomic compute dispatch, fp64 support, a 0.25 s micro-benchmark. An
engine that fails its probe is marked unavailable with the reason.

Failures during a render (driver reset, out of memory, shader compile error for an exotic
formula) never lose the job: the pipeline restarts it on the CPU engine and appends a note
to the report (`RenderStats.notes`). The preview worker remembers a failure and stays on
the CPU for the session; the status bar shows which engine is in use.

Users may force an engine per render (Render dialog → Engine) or for previews
(Preferences → Preview engine).
