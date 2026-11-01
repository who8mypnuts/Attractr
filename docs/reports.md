# Render reports

Written next to the image as `<image>_report.<fmt>` with side files in
`<image>_report/` (thumbnail, density-histogram plot). Formats: **Markdown**, **Text**,
**HTML** (self-contained dark theme), **PDF** (via Qt's `QTextDocument`).

Sections: Attractor (description, formula, kind, integrator) · Parameters (value, default,
range, meaning) · Camera & framing · Look · Quality & engine · Timing · Statistics
(+ histogram) · Dynamics (optional) · Reproducibility (`ATR1:` code, CLI command,
software versions).

GUI: the render dialog has a **Write report** checkbox and a format drop-down; the CLI uses
`--report md,html,…` and `--dynamics`. `attractr report image.png` regenerates a report
from the settings embedded in any Attractr PNG.
