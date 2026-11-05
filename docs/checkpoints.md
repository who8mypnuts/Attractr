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

Tiled renders: a tile that is complete when the request arrives stays complete; the tile
in progress stops where it is and every *later* tile receives the same reduced budget.
The image is therefore uniform only when the request arrives during the first tile —
prefer a checkpoint + resume for very large renders.

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

Two checkpoint shapes exist:

* **uniform** (`tiles_done = 0`) — every pixel holds `iterations_done` points' worth of
  accumulation (CPU engine, single-tile GPU renders);
* **tiled** (`tiles_done > 0`) — the first *n* tiles of a tiled GPU render are complete
  and the rest empty; resuming skips those tiles. Such a checkpoint must be resumed with
  the same engine on a device that produces the same tiling (the file records the tile
  count and the engine refuses otherwise); it cannot fall back to the CPU engine.

Limitations: the supersampled buffers are stored already box-filtered to output
resolution, which is exactly what the final image uses, so nothing is lost — but a
checkpoint cannot be resumed at a *different* size, supersampling or splat radius.
