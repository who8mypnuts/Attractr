# Render styles & development

Development turns the accumulation buffers into an image and is cheap, so every control
below updates instantly without re-iterating.

## Tone mapping (all styles)

```
P        = percentile(count > 0, look.percentile)        # default 99.8 %
density  = log(1 + count) / log(1 + P)                  # Gas law ("Dust" uses (count/P)^0.25)
density  = equalise(density)          if look.equalize  # histogram equalisation
density  = curve(density)             gamma → brightness → contrast S-curve → invert
```

## Styles

| Style | Buffers | Colour | Alpha |
|---|---|---|---|
| **Gas** | count (+depth) | palette(density) — or palette(colour-value) × density when a colour source is set | density |
| **Dust** | count | as Gas with the 4th-root law | density |
| **Light** | count, cv_sum | palette(colour value, default *speed*) × density (+ bloom) | 1.5·density |
| **Liquid** | count, depth_sum, zmin | palette(density × depth attenuation) × Phong lighting from screen-space normals of the nearest-depth buffer | 2·density |
| **Solid** | count, zmin | opaque surface where density > threshold; palette by nearest depth; lit; anti-aliased edge. Needs a dense render (≥ 20 points/pixel) for clean surfaces | step(threshold) |
| **Plasma** | count | cyclic palette of `fract(density × bands + phase)` (+ bloom) | 2·density |

## Colour sources

`density` (default) · `x` `y` `z` (view-space coordinates) · `depth` · `speed` (step length)
· `radius` · `index` (trajectory index) · `curvature` (turn angle) · `formula` (the DSL
`color =` expression). Values are normalised by their 1–99 % range over non-empty pixels
and the palette is indexed by the per-pixel mean.

## Background

`solid` · `transparent` (straight-alpha PNG) · `gradient` (vertical) · `image` (cover-fit
photo) · `procedural` (`stars`, `forest`, `ocean`, `aurora` — deterministic per seed).

## Output

Float RGBA → 8-bit (with triangular dithering) or 16-bit PNG. Exported PNGs embed the
full settings JSON and an `ATR1:` code in `tEXt` chunks.

## Where the develop pass runs

`develop(result, look)` is NumPy code (`core/render/develop/*.py`). For **large images
(≥ 1.5 Mpixel)** the same formulas run as OpenGL 4.3 compute shaders (driver
`gpu_develop.py`): `shaders/develop.comp` for the per-pixel styles (Gas, Dust, Light,
Plasma) and `shaders/develop_light.comp` for the lit styles (Liquid, Solid — a global
fill-height scan, then per row chunk with a 2-row halo: height field → 3×3 binomial blur →
central-difference normals → Phong → style → composite). The count / colour / depth /
nearest-depth buffers are uploaded in row chunks, the shader writes straight-alpha RGBA
and the result is read back. The handful of global scalars (normaliser percentile, 1–99 %
ranges of colour value, depth and surface depth) are still estimated on the CPU from a
strided subsample. Looks the shaders do not cover — histogram equalisation (*Full
range*), bloom (`glow > 0`), image / procedural backgrounds — always use the CPU path. The GPU pass switches itself off for the session after the first
OpenGL failure; it can be disabled in *Preferences → GPU develop* or with
`attractr render --develop cpu`. `tests/engines/test_gpu_develop.py` checks that both paths
agree to within 8-bit quantisation.
