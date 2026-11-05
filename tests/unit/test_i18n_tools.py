"""The source-rewriting translation tools must only touch what they claim to."""

import importlib.util
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SAMPLE = '''from PySide6.QtWidgets import QLabel, QPushButton

lbl = QLabel("Héllo — wörld")          # non-ASCII before a literal: byte offsets ≠ char offsets
btn = QPushButton(f"Reset to {lbl}")   # f-string: must stay
already = QLabel(tr("Done"))
key = QLabel("#ff0000")                # no letters: skipped
w.setToolTip("Tip")
'''


def test_wrap_tr_is_precise_and_idempotent(tmp_path):
    wrap = _load("wrap_tr")
    f = tmp_path / "sample.py"
    f.write_text(SAMPLE, encoding="utf-8")
    assert wrap.wrap_file(f) == 2
    out = f.read_text(encoding="utf-8")
    assert 'QLabel(tr("Héllo — wörld"))' in out and 'setToolTip(tr("Tip"))' in out
    assert 'QPushButton(f"Reset to {lbl}")' in out and 'QLabel(tr("Done"))' in out and 'QLabel("#ff0000")' in out
    assert "from attractr.i18n import tr" in out
    assert wrap.wrap_file(f) == 0  # nothing left to wrap
    compile(out, "sample.py", "exec")


def test_extract_ts_keeps_finished_translations(tmp_path, monkeypatch):
    extract = _load("extract_ts")
    src = tmp_path / "gui"
    src.mkdir()
    (src / "a.py").write_text('x = tr("Render")\ny = tr("Cancel")\n', encoding="utf-8")
    monkeypatch.setattr(extract, "OUT_DIR", tmp_path)
    assert extract.main(["xx", "--src", str(src)]) == 0
    ts = tmp_path / "attractr_xx.ts"
    text = ts.read_text(encoding="utf-8")
    assert text.count("<message>") == 2 and 'type="unfinished"' in text
    ts.write_text(text.replace('<source>Cancel</source>\n        <translation type="unfinished"></translation>',
                               "<source>Cancel</source>\n        <translation>Abbrechen</translation>"), encoding="utf-8")
    (src / "a.py").write_text('x = tr("Render")\ny = tr("Cancel")\nz = tr("New")\n', encoding="utf-8")
    extract.main(["xx", "--src", str(src)])
    text = ts.read_text(encoding="utf-8")
    assert "<translation>Abbrechen</translation>" in text and text.count("<message>") == 3
