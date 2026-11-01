# Command line interface

`attractr` with no sub-command opens the GUI. Sub-commands:

| Command | Purpose |
|---|---|
| `attractr render TARGET [options]` | render a still image (+ report) |
| `attractr list attractors\|palettes\|engines\|styles\|colors\|integrators [--json]` | catalogue queries |
| `attractr info [--json]` | system / engine probe |
| `attractr thumb TARGET [-o file\|-]` | small PNG (to stdout for pipes) |
| `attractr lyapunov TARGET [--param k=v]` | largest Lyapunov exponent |
| `attractr report image.png --format md,pdf` | regenerate a report from embedded metadata |
| `attractr animate project.attractr` | frame sequence + ffmpeg (milestone 5) |

`TARGET` is an attractor id (`lorenz`), a `.attractr` project, a `.atr` formula file, or an
`ATR1:`/`CHS1:` code.

## Render options

```
--size WxH            output size                    --ppp N            points per pixel
--iterations N        absolute point count           --engine E         cpu | gl_compute | gl_points | gl_precision | opencl | auto
--ss N                supersampling 1..4             --splat R          splat radius 0 (bilinear AA) .. 4
--no-gap-fill         disable segment filling        --integrator I     rk4 | rk2 | euler
--dt F  --substeps N  integrator controls            --seed N           reproducibility seed
--style S             gas | dust | light | liquid | solid | plasma
--color-by C          density | x | y | z | depth | speed | radius | index | curvature | formula
--palette P           palette id                     --percentile F     density percentile → full brightness (0.998)
--gamma F --invert --equalize                        --bg #rrggbb|transparent
--camera YAW,PITCH,ROLL  --zoom F  --perspective F  --fit bbox|sphere
--param NAME=VALUE    (repeatable)                   --bits 8|16        PNG bit depth
--report md,txt,html,pdf                             --dynamics         add Lyapunov/dimension to the report
-o FILE | -           output path or PNG to stdout
```

Examples:

```bash
attractr render lorenz --size 2048x2048 --ppp 40 --palette fire --report md
attractr render clifford -p a=-1.7 -p b=1.8 --style light --color-by speed -o filigree.png
attractr render 'ATR1:eJx...' --size 4096x4096 --engine gl_precision --ss 2 --report pdf
attractr thumb aizawa --thumb-size 128 -o - | display -
attractr list palettes --json | jq '.[].id'
```

Exit codes: 0 success · 2 bad arguments / unknown attractor · 130 interrupted.
