"""Translation plumbing: tr() seam, .qm loading, attractor overlays."""

import os

from attractr.core.attractors.overlays import apply_overlay, load_overlay
from attractr.core.attractors.registry import registry
from attractr.i18n import available_locales, tr


def test_tr_without_app_returns_source():
    assert tr("Render") == "Render"


def test_german_qm_ships_and_translates(qapp):
    from attractr.i18n import install_translators, remove_translators

    assert "de" in available_locales()
    loaded = install_translators(qapp, "de")
    assert "attractr_de.qm" in loaded
    assert tr("&File") == "&Datei" and tr("Render preset") == "Render-Voreinstellung"
    remove_translators(qapp)  # leave the app in English for the other tests
    assert tr("&File") == "&File"


def test_attractor_overlay(monkeypatch):
    monkeypatch.setenv("ATTRACTR_LANG", "de")
    ov = load_overlay()
    assert "lorenz" in ov
    de = apply_overlay(registry.get("lorenz"), ov["lorenz"])
    assert de.description.startswith("Der berühmte") and de.params[0].hint.startswith("σ (Prandtl-Zahl)")
    assert de.program == registry.get("lorenz").program  # equations untouched
    monkeypatch.delenv("ATTRACTR_LANG")
    assert os.environ.get("ATTRACTR_LANG") is None
