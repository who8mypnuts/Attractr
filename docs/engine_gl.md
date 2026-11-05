# GPU engines

Three GPU engines share one algorithm and the formula code generator
(`core/formula/codegen_glsl.py`, GLSL and OpenCL C dialects):

| Engine id | API | Role |
|---|---|---|
| `gl_compute` | OpenGL 4.3 compute (ModernGL) | interactive preview and ordinary renders |
| `gl_precision` | same shader core | final renders — tiles + supersampling + splat kernels from the settings |
| `opencl` | OpenCL 1.2 (pyopencl) | any vendor's GPU, or CPUs through POCL/Intel runtimes; ships by default |
| `gl_points` | OpenGL 3.3 (ModernGL) | fallback for macOS (GL 4.1, no compute) and old drivers — see below |

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

## Tiling

Images whose accumulation buffers exceed the GPU budget are split into square tiles (at
most 4096²). The budget is 35 % of the **free VRAM** reported by `GL_NVX_gpu_memory_info`
/ `GL_ATI_meminfo` (clamped to 64 MB … 2 GB), 256 MB when the driver cannot be queried, a
share of host RAM for software renderers, or `ATTRACTR_GPU_BUDGET_MB` when set; OpenCL
uses a quarter of the device's global memory. Only the planes the look needs (count, and
depth / nearest depth / colour when used) are allocated, as one image set sized for the
largest tile that every tile and round reuses (edge tiles use a corner of it through
viewport reads/writes). Allocation failures surface as a clean error that the pipeline
turns into a CPU continuation from the last partial (see troubleshooting.md). Tiles are rendered
**interleaved** in `INTERLEAVE_ROUNDS = 8` rounds: the per-tile trajectory state (state,
RNG, previous point, stats — a few MB) lives on the device for the whole render, while the
tile's accumulation images are created on each visit and restored from the host copies
(`_upload`) / read back (`_readback`). The extra transfer costs a few hundred
milliseconds per tile per round, negligible next to a multi-minute render, and buys
uniform progress: live partials once per round, uniform checkpoints and a uniform
"Finish now". The same scheme is used by the OpenCL and `gl_points` engines.

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

## Precision (fp32 / fp64)

`Quality.precision` (Render dialog → *Precision*, CLI `--precision fp64`) switches the
trajectory state and all formula arithmetic to **double precision** on the GPU:

* **OpenCL** uses the device's native `double` math (`cl_khr_fp64`).
* **OpenGL** has `double` arithmetic (`GL_ARB_gpu_shader_fp64`) but no transcendental
  functions for it, so `shaders/prelude_fp64.glsl` implements `sin cos tan exp log atan
  atan2 asin acos sinh cosh tanh …` in software (Cody–Waite range reduction + short
  polynomials). `tests/engines/test_fp64_math.py` checks every function against libm to
  5 × 10⁻¹⁴ relative error.

Consumer GPUs execute fp64 at 1/8–1/32 of their fp32 rate, so `auto` means fp32; use fp64
for stiff flows with tiny time steps (Dequan Li, three-scroll) or when you need CPU-identical
trajectories. The projection/splat stage always runs in fp32 — pixel positions do not need
more.

## `gl_points` (OpenGL 3.3 fallback)

Trajectories live in 256×256 textures (state, RNG, previous position). Each pass renders
a full-screen quad whose fragment shader advances every trajectory by one step (ping-pong
targets), then a vertex shader reads the new state with `texelFetch` and emits one
`GL_POINTS` vertex per trajectory into an RGBA32F framebuffer with additive blending
(count, Σdepth, Σcolour); the nearest-depth buffer is drawn a second time with
`GL_MIN` blending. Flows draw `GL_LINES` from the previous to the new position with
weight 1/length (gap filling). Limitations: nearest-pixel splats (use supersampling for
anti-aliasing), fp32 only, no restart statistics. Selection order puts it after the
compute engines and before the CPU.
