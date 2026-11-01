# Gradients & palettes

A **Gradient** is an ordered list of stops `(position, r, g, b, a)` plus an
**interpolation space** (`rgb`, `linear` light, `hsv` shortest hue arc, `hsv_long`,
`oklab` perceptual) and a **cyclic** flag. Engines never see stops — only a 1024-entry
RGBA LUT (`Gradient.lut(size, phase, cycles)`); `phase` rotates and `cycles` repeats
the palette, both animatable, both instant (development only).

## Editor (Look → Edit…, or `G`)

* Bar with draggable stop handles: drag to move, **double-click the bar to add** a stop
  with the interpolated colour, `Delete` to remove the selected stop, `+ stop`/`− stop`.
* Embedded colour picker (HSV square + RGB/HTML fields), position and alpha spin boxes.
* Interpolation space, cyclic toggle, Reverse, Distribute, Randomize (analogous /
  complementary / triadic / monochrome / rainbow schemes).
* Library: built-in palettes (10 from the Android app, 6 from the C renderer, WebGL
  duotone/dark/light, two OKLab ramps) and user palettes; **Save as…** writes
  `~/.attractr/palettes/<id>.json`; **Import/Export** handles GIMP `.ggr` and JSON.
* Every change applies live to the preview (no re-iteration) and is one undo step per
  drag.

## Alpha

Stop alpha multiplies the style's alpha, so a gradient can fade low densities out
completely — useful with the `transparent` background for compositing.
