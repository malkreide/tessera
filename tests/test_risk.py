#!/usr/bin/env python3
"""Tests fuer die Hochrisiko-Registry und den erhoehten Validator-Review.

Reine stdlib (CI-faehig ohne Dependencies). Aufruf:
    python tests/test_risk.py — Exit 0 = alle Tests gruen.

Deckt ab:
  * Registry: baugesuch/sozialhilfe/veranstaltung sind hochriskant, andere nicht;
  * erhoehter Review: hochriskanter Prozess mit unverifiziert/ungrounded Reference
    ist ein FEHLER (Normalfall: nur Hinweis);
  * ein vollstaendig belegter hochriskanter Prozess ist gueltig und wird als
    high_risk markiert;
  * Disclaimer-Empfehlung greift (Hinweis, kein Fehler).
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from tessera.risk import (  # noqa: E402
    HIGH_RISK_DISCLAIMER_KEY,
    HIGH_RISK_IDS,
    is_high_risk,
    is_high_risk_disclaimer,
)
from validate_contract import Report, validate  # noqa: E402


def _high_risk_process() -> dict:
    """Vollstaendig belegter hochriskanter Prozess (gueltig)."""
    return {
        "schema_version": "0.1.0",
        "id": "baugesuch",
        "lebenslage_ref": "baugesuch",
        "title": {"de": "Baugesuch einreichen"},
        "target_audience": "bevoelkerung",
        "steps": [
            {
                "step_id": 1,
                "actor": "Bauherrschaft",
                "label": {"de": "Baugesuch einreichen"},
                "depends_on": [],
                "reference_ids": [1],
            }
        ],
        "references": [
            {
                "reference_id": 1,
                "label": {"de": "Rekursfrist gegen den Bauentscheid"},
                "source_url": "https://www.zh.ch/baurecht",
                "source_quote": "innert der gesetzlichen Frist",
                "status": "verifiziert",
                "retrieved_at": "2026-06-14",
            }
        ],
        "source_url": "https://www.stadt-zuerich.ch/baugesuch",
        "retrieved_at": "2026-06-14",
        "disclaimer_key": HIGH_RISK_DISCLAIMER_KEY,
    }


def test_registry_membership() -> None:
    assert HIGH_RISK_IDS == frozenset({"baugesuch", "sozialhilfe", "veranstaltung"})
    assert is_high_risk("baugesuch")
    assert is_high_risk("sozialhilfe")
    assert is_high_risk("veranstaltung")
    assert not is_high_risk("hund-anmelden")
    assert not is_high_risk(None)


def test_disclaimer_heuristic() -> None:
    assert is_high_risk_disclaimer(HIGH_RISK_DISCLAIMER_KEY)
    assert is_high_risk_disclaimer("Prozesse.disclaimer.hochrisiko")
    assert not is_high_risk_disclaimer("process.disclaimer.unofficial")
    assert not is_high_risk_disclaimer(None)


def test_valid_high_risk_passes_and_is_flagged() -> None:
    rep = Report(Path("synthetic"))
    validate(_high_risk_process(), rep)
    assert rep.ok, rep.errors
    assert rep.high_risk is True


def test_unverified_reference_is_error_for_high_risk() -> None:
    proc = _high_risk_process()
    proc["references"][0]["status"] = "unverifiziert"
    proc["references"][0].pop("source_quote")
    rep = Report(Path("synthetic"))
    validate(proc, rep)
    assert not rep.ok
    assert any("HOCHRISIKO" in e and "unverifiziert" in e for e in rep.errors)


def test_same_unverified_reference_is_only_warning_for_low_risk() -> None:
    """Gegenprobe: dieselbe ungrounded Reference ist bei einer risikoarmen
    Leistung gueltig (nur Hinweis) — der Fehler kommt allein vom Hochrisiko-Gate."""
    proc = _high_risk_process()
    proc["id"] = "hund-anmelden"
    proc["lebenslage_ref"] = "hund-anmelden"
    proc["references"][0]["status"] = "unverifiziert"
    proc["references"][0].pop("source_quote")
    rep = Report(Path("synthetic"))
    validate(proc, rep)
    assert rep.ok, rep.errors
    assert rep.high_risk is False


def test_missing_quote_is_error_for_high_risk() -> None:
    proc = _high_risk_process()
    proc["references"][0]["source_quote"] = "   "  # leer/whitespace
    rep = Report(Path("synthetic"))
    validate(proc, rep)
    assert not rep.ok
    assert any("HOCHRISIKO" in e for e in rep.errors)


def test_non_high_risk_disclaimer_warns_not_fails() -> None:
    proc = _high_risk_process()
    proc["disclaimer_key"] = "process.disclaimer.unofficial"
    rep = Report(Path("synthetic"))
    validate(proc, rep)
    assert rep.ok, rep.errors  # Disclaimer-Empfehlung ist nur ein Hinweis
    assert any("HOCHRISIKO" in w and "Disclaimer" in w for w in rep.warnings)


def test_high_risk_warning_survives_cp1252_stdout() -> None:
    """Regression (Windows/Python 3.14): der Validator druckt den ⚠-Hochrisiko-
    Hinweis. Unter einer nicht-UTF-8-Ausgabe (cp1252, Default fuer eine Windows-
    Pipe) crashte das mit UnicodeEncodeError und liess `pr.validate_merged`
    faelschlich scheitern (kein PR). Der Validator stellt seine Ausgabe jetzt auf
    UTF-8; hier via PYTHONIOENCODING=cp1252 reproduziert (schlaegt ohne Fix fehl)."""
    import os  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_contract.py"),
            str(ROOT / "examples" / "baugesuch.json"),  # gueltiger Hochrisiko-Fall
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert "UnicodeEncodeError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr or result.stdout
    assert "HOCHRISIKO" in result.stdout, result.stdout


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"[FAIL] {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} Tests gruen.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
