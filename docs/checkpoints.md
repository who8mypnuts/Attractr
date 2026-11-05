# Progressive renders, "Finish now" and checkpoints

Every engine accumulates in **passes** (a few hundred milliseconds each) and hands the
buffers so far to a *sink* callback. Three features are built on that:

## 1. Live progress

The Jobs panel shows a small thumbnail of each running render that updates with every
partial result (`core/render/thumb.py` box-filters the buffers to ≤ 112 px before
developing them, so the cost is negligible even for 16K renders). For tiled GPU renders
the thumbnail updates once per completed tile.

## 2. Finish now (soft stop)

`CancelToken.finish()` asks the engine to stop at the next pass boundary **and still
return a complete result**, which is then developed, saved and reported like any other.
The statistics carry `finished_early = True` and a note with the percentage of the budget
that was reached.

* GUI: the ⏹ button of a job row.
* CLI: `attractr render … --finish-after SEC` (a soft time limit).

Tiled GPU renders are **interleaved**: every tile is visited in 8 rounds (its trajectory
state stays on the GPU, the big accumulation images are re-uploaded per visit), so all
tiles are always within one round of each other. A soft stop therefore yields a uniform
image (every tile ends at the same step count), partial results arrive once per round,
and checkpoints of tiled renders are ordinary uniform checkpoints.

## 3. Checkpoints & resume

A **checkpoint** (`*.attractr-ckpt.npz`) is the set of accumulation buffers at output
resolution (count, Σdepth, nearest depth, Σcolour) together with the settings, the
framing and how much of the budget they contain (`core/render/checkpoint.py`).

| Where | When it is written | Where it goes |
|---|---|---|
| GUI render jobs | every *N* minutes (Preferences → *Render checkpoint every*, default 2 min; 0 = off) and when the 💾 button is pressed | `<output folder>/checkpoints/<render name>.attractr-ckpt.npz` |
| CLI | `--checkpoint-every MIN` | next to the output file |

The file is deleted as soon as the finished image has been saved; it survives a cancel,
a crash, a power cut or Ctrl-C.

Resuming — *Render → Resume from checkpoint…* or `attractr render --resume FILE`
(`-o`, `--report` etc. still apply; the attractor, parameters, camera and quality come
from the file) — starts a new accumulation of the **remaining** budget with a different
trajectory seed (`seed + 1 000 003 × segment`, so no random stream is replayed), forces
the framing stored in the file (pixels must line up exactly) and adds the saved buffers
to the fresh ones. The result is statistically indistinguishable from an uninterrupted
render (`tests/unit/test_checkpoint.py`). A resumed job writes further checkpoints with
an incremented `segment`, so a render can be interrupted any number of times.

Checkpoints are **uniform** (`tiles_done = 0`): every pixel holds `iterations_done`
points' worth of accumulation, whatever engine or tiling produced it, so a checkpoint can
be resumed on any engine. (A legacy *tiled* shape — `tiles_done > 0`, the first *n* tiles
complete — is still readable; it must be resumed with the same engine/tiling.)

Changing quality on resume: the buffers are stored box-filtered to output resolution —
exactly what the final image uses, so nothing is lost — and the remaining budget is
accumulated independently, so it **may use a different supersampling factor, splat
radius, engine or precision** (`attractr render --resume FILE --ss 1 --splat 2`; the
remaining points simply land with the new settings). Only the pixel size is fixed: a
checkpoint of a different width × height is refused. Points per pixel can be raised as
well — the engine renders `new budget − points already done`.
