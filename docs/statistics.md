# Statistics — what every number means

## Render statistics (from the accumulation buffers)

| Name | Definition |
|---|---|
| Iterations requested / done | points budget (`ppp × W × H`) and points actually iterated |
| Points landed in frame | total splat weight deposited inside the image |
| Trajectory restarts | re-seeds after divergence (non-finite or |v| > 1e6) |
| Non-empty pixels / coverage | pixels with count > 0 and their fraction of the image |
| Max / mean / median density | over non-empty pixels |
| Percentile count | the count value mapped to full brightness (`look.percentile`) |
| Density entropy | Shannon entropy (bits) of the normalised count distribution — higher = more evenly spread |
| Density histogram | 64 log-spaced bins of the non-empty counts |
| Throughput | iterations done / accumulation seconds |

## Dynamics (analysis worker / `--dynamics`)

| Name | Method |
|---|---|
| Largest Lyapunov exponent λ₁ | Benettin two-trajectory renormalisation on a trajectory started on the attractor (per unit time for flows, per iteration for maps). > 0 chaotic, ≈ 0 quasi-periodic, < 0 periodic/fixed point. Validated: Lorenz ≈ 0.906, Hénon ≈ 0.419 |
| Box-counting dimension | slope of log(occupied boxes) vs log(1/box size) on the 3-D sample cloud |
| Correlation dimension | Grassberger–Procaccia on a 2000-point sub-sample |
| Bounding radius / box | from the framing sample |
