"""Info panel: name, formula, description, parameter meanings, references."""

from __future__ import annotations

import html

from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

from attractr.core.attractors.spec import AttractorSpec
from attractr.gui.state.document import Document


class InfoPanel(QWidget):
    def __init__(self, doc: Document, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        lay.addWidget(self.view)
        doc.attractorChanged.connect(self.refresh)
        doc.changed.connect(lambda s, t: self.refresh(self.doc.spec) if "params" in t else None)
        self.refresh(doc.spec)

    def refresh(self, spec: AttractorSpec) -> None:
        vals = self.doc.settings.param_dict
        eq = "<br>".join(html.escape(line) for line in spec.formula_text())
        params = "".join(
            f"<tr><td><b>{html.escape(p.name)}</b></td><td>{vals.get(p.name, p.default):.6g}</td><td style='color:#aaa'>{html.escape(p.hint)}</td></tr>"
            for p in spec.params
        )
        refs = "".join(f"<li>{_link(r)}</li>" for r in spec.references)
        extra = []
        if spec.is_flow:
            extra.append(f"default dt = {spec.dt:g}")
        if spec.lyapunov_hint is not None:
            extra.append(f"λ₁ ≈ {spec.lyapunov_hint:g} at defaults")
        if spec.analysis.uses_w:
            extra.append("4 state variables")
        if spec.analysis.has_section:
            extra.append("Poincaré section")
        if spec.analysis.has_event:
            extra.append("section events")
        if spec.is_escape:
            extra.append(f"escape-time: region {spec.region[:4]}, bailout {spec.bailout:g}, {spec.min_iter}–{spec.max_iter} iterations")
        doc = f"""
        <h2 style='color:#4fc3f7;margin-bottom:2px'>{html.escape(spec.name)}</h2>
        <p style='color:#888;margin-top:0'>{spec.kind} · {spec.dims}-D · {html.escape(spec.family)}{' · ' + ' · '.join(extra) if extra else ''}</p>
        <p>{html.escape(spec.description)}</p>
        <pre style='background:#161622;padding:8px;border-radius:6px;color:#c8e6ff'>{eq}</pre>
        <table cellspacing='0' cellpadding='3'>{params}</table>
        {('<p><b>References</b></p><ul>' + refs + '</ul>') if refs else ''}
        """
        self.view.setHtml(doc)


def _link(ref: str) -> str:
    e = html.escape(ref)
    if ref.startswith("http"):
        return f"<a href='{e}'>{e}</a>"
    return e
