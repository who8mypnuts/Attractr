# Translations

Drop compiled Qt translation files here as `attractr_<locale>.qm` (e.g. `attractr_de.qm`,
`attractr_fr_CA.qm`). They are loaded at start-up for the system locale, or for the locale
named in the `ATTRACTR_LANG` environment variable (`ATTRACTR_LANG=de attractr`).

To create one: wrap user-visible strings in the code with `tr("…")`
(`from attractr.i18n import tr`), then

```bash
pyside6-lupdate src/attractr -ts src/attractr/resources/i18n/attractr_de.ts
# translate with Qt Linguist, then
pyside6-lrelease src/attractr/resources/i18n/attractr_de.ts
```

Only strings wrapped in `tr()` are translatable; the rest of the program is still plain
English (see docs/development.md, "Internationalisation").
