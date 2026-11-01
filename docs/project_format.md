# File formats

## `.attractr` project (JSON)

```json
{ "schema": 1, "app": "Attractr", "version": "0.1.0",
  "settings": { "attractor": "lorenz", "source": null, "params": {"sigma": 10, ...},
                "camera": {...}, "quality": {...}, "look": {... "gradient": {...}} },
  "animation": { ... timeline (milestone 5) ... },
  "notes": "" }
```
`settings.source` carries the inline `.atr` text for user formulas so a project is
self-contained. Unknown keys are ignored on load (forward compatibility); a newer `schema`
is rejected with a clear message.

## `.atr` attractor definition

See [formula_dsl.md](formula_dsl.md). Built-ins live in `resources/attractors/<family>/`,
user files in `~/.attractr/attractors/`.

## Palettes (JSON)

`{"name", "id", "space": "rgb|linear|hsv|hsv_long|oklab", "cyclic": bool, "stops": [[pos, r, g, b, a], …]}`
— one per file in `~/.attractr/palettes/`, or a `{"palettes": [...]}` list (built-ins).

## Codes

* `ATR1:` — base64url(zlib(settings JSON)); found anywhere in pasted text.
* `CHS1:` — Chaoscope (Android) preset codes are imported: attractor/palette/style names
  are mapped, `dt` parameters become integrator settings (`euler` to match the source).

## Image metadata

PNG `tEXt` chunks `attractr:settings` (JSON), `attractr:code` (ATR1), `attractr:version`.
