# CPU engine (`cpu`)

The reference implementation. numba-compiled, fp64 state, multi-threaded.

## Pipeline

1. **Compile** — the attractor's DSL program is turned into Python source
   (`core/formula/codegen_numba.py`) defining `step()` (map update or RK4/RK2/Euler step of
   `deriv()`) and `color_fn()`. The CPU kernel template
   (`core/render/engines/cpu_kernel_template.py`) is appended and the whole module is
   written to `~/.attractr/cache/numba/` so numba's disk cache persists across runs. First
   compile of a new attractor takes a few seconds; later runs are instant.
2. **Framing** (`core/render/framing.py`) — 256 trajectories are warmed up and sampled
   (512 steps each). Warm-up continues in rounds until the bounding sphere stops changing
   (slowly unfolding systems such as Rössler need this). Result: centre, radius, bbox, and
   optional 2-D tight fit (`camera.fit = "bbox"`). Cached per (attractor, params, dt, seed).
3. **Seeding** — accumulation trajectories (default `threads × 4096`) start from random
   points of the framing sample (already on the attractor) plus a 1 % jitter, then run a
   short decorrelation warm-up (64 steps).
4. **Accumulation** — each thread owns a contiguous slice of trajectories and a private set
   of float32 buffers (`count`, optionally `depth_sum`, `zmin`, `cv_sum`). The whole buffer
   is driven as a single tile by the shared `TileSchedule` (see architecture.md): passes of
   adaptive length (~0.35 s) report progress, check cancellation / *Finish now* and emit
   paced partial results. Points are projected with the camera model (see camera.md) and
   deposited with a bilinear 2×2 splat (radius 0) or a soft-disk kernel (radius 1–4). For
   flows, consecutive points are connected by up to 64 interpolated sub-splats of weight
   1/n (“gap filling”, from the C rewrite) so fast stretches draw as continuous curves.
5. **Merge** — private buffers are summed (min for `zmin`), supersampled buffers are
   box-filtered to the output size, statistics are computed.

## Divergence policy

A trajectory whose state becomes non-finite or exceeds |1e6| is re-seeded at the nominal
initial condition + jitter and counted as a *restart*. The report shows the count.

## Threads & memory

`numba.get_num_threads()` workers, reduced so that private buffers fit the memory budget
(`ATTRACTR_CPU_BUDGET_MB`, else a quarter of the available RAM, 512 MB … 8 GB). Very
large images are tiled by the GPU engines; on the CPU a huge buffer simply means fewer
threads.

## Determinism

Same settings + seed ⇒ identical image (per-trajectory xorshift states derived from the
seed; slices and merge order fixed).
