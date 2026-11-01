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
