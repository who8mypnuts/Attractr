# Troubleshooting

## Where to look first

Every run writes `~/.attractr/logs/attractr.log` (render plans: size, supersampling, engine,
tile layout, GPU budget, fallbacks) and `~/.attractr/logs/crash.log` (a Python stack trace
written by `faulthandler` when the process dies from a segfault / abort inside a GPU
driver, numba or Qt — the cases where the window simply disappears). Attach both when
reporting a crash. `attractr -v render …` shows the same information on the console.

## "The render reached N % and the program vanished"

A process that dies without a Python traceback was killed from outside Python: the GPU
driver aborted (out of video memory is the classic cause) or the kernel's OOM killer
reclaimed host memory. Large renders — A3 at 300 dpi with 2× supersampling is a
10 000 × 7 000 accumulation (70 Mpixel) — used to allocate tile images sized by a fixed
768 MB budget and re-allocated them for every tile and round; on a 2–4 GB card that can
exhaust VRAM mid-render. Since 0.1:

* the tile budget is derived from the **free VRAM** (`GL_NVX_gpu_memory_info` /
  `GL_ATI_meminfo`; 35 % of what is free, 64 MB … 2 GB; 256 MB when the driver cannot be
  queried; a share of host RAM for software renderers), tiles are capped at 4096², and
  only the image planes the look needs are allocated;
* one image set (sized for the largest tile) is allocated **once** per render and reused
  by every tile and round — no allocation churn;
* allocations are checked (`GL_OUT_OF_MEMORY` → a clean error) and any GPU failure makes
  the pipeline **continue on the CPU engine from the last uniform partial**, so the points
  accumulated so far are kept (the report notes it);
* partial results are box-filtered without float64 copies and are paced by their own
  cost, so a 70-Mpixel render no longer spends most of its time — and memory — on
  snapshots;
* the render dialog shows the estimated host memory and warns when it exceeds ~60 % of
  the free RAM; the CPU engine sizes its per-thread buffers from the available RAM.

If a driver still misbehaves: `ATTRACTR_GPU_BUDGET_MB=128 attractr …` forces smaller
tiles, `--engine cpu` avoids the GPU altogether, and `ATTRACTR_CPU_BUDGET_MB` bounds the
CPU engine's buffers. Lower the supersampling before lowering the size: 2× supersampling
quadruples every accumulation buffer.

## Other symptoms

| Symptom | Cause / fix |
|---|---|
| `engine gl_compute failed … restarting on the CPU engine` in the log | the driver rejected the compute shader or an allocation; the image is still produced. Update drivers, or prefer `opencl` / `gl_points` in Preferences |
| Preview is black after switching engines | fixed in 0.1: each engine makes its own GL context current; if it recurs, set *Preview engine* to `cpu` and report the log |
| Solid style full of holes | needs ≥ 30 points/pixel — the render dialog warns |
| Sections / escape systems look sparse or take long | they plot a fraction of the iterations; their `boost:` header multiplies the budget (visible in the dialog's point count) |
| Checkpoint refuses to resume | size changed (pixel size is fixed), or a legacy tiled checkpoint on a different engine |
