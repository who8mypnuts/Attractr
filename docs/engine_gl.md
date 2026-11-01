# GPU engines

Three GPU engines share one algorithm and the formula code generator
(`core/formula/codegen_glsl.py`, GLSL and OpenCL C dialects):

| Engine id | API | Role |
|---|---|---|
| `gl_compute` | OpenGL 4.3 compute (ModernGL) | interactive preview and ordinary renders |
| `gl_precision` | same shader core | final renders — tiles + supersampling + splat kernels from the settings |
| `opencl` | OpenCL 1.2 (pyopencl) | any vendor's GPU, or CPUs through POCL/Intel runtimes; ships by default |

## Algorithm (identical in `iterate.comp` and `iterate.cl`)

1. **One work item = one trajectory** (65 536 by default, 128 per group). State
   `(x, y, z, t_step)` and the xorshift RNG live in SSBOs/buffers; trajectories are
   seeded from the framing sample exactly like the CPU engine (same seeds ⇒ the same
   starting points on every engine).
2. Each dispatch advances every trajectory `steps ≤ 256` times and deposits points into
   **fixed-point (24.8) uint images** with `imageAtomicAdd`/`atomic_add`; `zmin` uses
   `atomicMin` on a monotonic float→uint key. Depth is offset/scaled into the positive range
   before fixed-point encoding (clamped to ±2); colour values are encoded relative to
   their expected range, estimated from the framing sample (`color_value_range`), so even
   tiny per-step speeds keep full resolution in the 8 fractional bits.
3. After every pass a **merge kernel** adds the uint images into **float32 accumulators**
   and clears them. The 256-step cap guarantees no 32-bit overflow per pass, and the float
   accumulators give the same precision as the CPU engine without float atomics (which are
   not in core GL 4.3 / OpenCL 1.2).
4. Passes are time-adaptive (~0.3 s) so the engine can report progress, honour
   cancellation and stream partial results to the GUI.
5. **Tiles**: when `W·H·ss²` exceeds the budget (`ATTRACTR_GPU_BUDGET_MB`, default 768 MB)
   or the texture limit, the image is rendered in tiles. Trajectories restart identically
   per tile, so tiles join seamlessly and the result is deterministic.
6. Readback → NumPy → the same `develop()` stage as the CPU engine.

## Parity

`tests/engines/test_gpu_parity.py` renders Clifford, Lorenz and the Barnsley fern on every
available GPU engine and requires the normalised histograms to agree with the CPU
reference (Jensen–Shannon divergence < 0.05 bits, coverage within 3 %). On this
development machine (Mesa llvmpipe, POCL) the divergence is ≈ 0.005–0.02 bits.

## Probing & fallback

`attractr info` / the System panel show each engine's probe: context creation, a tiny
atomic compute dispatch, fp64 support and a micro-benchmark (Mpts/s). `Quality.engine =
"auto"` picks `gl_precision → opencl → cpu` for final renders and `gl_compute → opencl →
cpu` for previews. If a GPU engine raises mid-render, the pipeline restarts the job on
the CPU engine and records the failure in the report's notes — never silently.

## Not yet implemented

* `gl_points` (GL 3.3 point-splat fallback for macOS/old drivers) — planned for M6;
  macOS users currently get the OpenCL or CPU engine.
* fp64 state on GPU (`Quality.precision = "fp64"`) — planned; the CPU engine is fp64.
