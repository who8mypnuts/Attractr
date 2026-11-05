# Translations

* `attractr_<locale>.ts` / `.qm` — the GUI strings (Qt Linguist format, context `attractr`).
  Loaded at start-up for the system locale or `ATTRACTR_LANG` (`ATTRACTR_LANG=de attractr`).
* `attractors_<locale>.json` — overlays for the descriptions and parameter hints of the
  built-in `.atr` files (`{"lorenz": {"desc": "…", "hints": {"sigma": "…"}}}`).

Update / add a language (see docs/development.md):

```bash
python tools/wrap_tr.py                       # wrap new GUI literals in tr()
python tools/extract_ts.py fr                 # → attractr_fr.ts (keeps finished entries)
pyside6-lrelease src/attractr/resources/i18n/attractr_fr.ts
python tools/extract_attractor_strings.py fr  # → attractors_fr.json template
```
