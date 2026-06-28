#!/usr/bin/env python3
"""Tests fuer die Top-Level-Feld-Allowlist des Vertrags-Validators.

Reine stdlib (CI-faehig ohne Dependencies). Aufruf:
    python tests/test_contract_fields.py — Exit 0 = alle Tests gruen.

Hintergrund: tessera merged die struktur-only Extraktion verlustfrei in die
handgepflegte Zieldatei (maschinerie-zuerich) und erhaelt dabei deren additive
kanonische Felder. Der Vertrags-Validator muss exakt die kanonischen Felder
erlauben — sonst lehnt er einen gemergten Stand ab, den die Ziel-CI akzeptiert
(Gate-Paritaet). Deckt ab:
  * 'bewertung' (kanonisches additives Feld) wird akzeptiert;
  * ein echtes Fremdfeld wird weiterhin als 'Unbekanntes Feld' abgelehnt
    (Gegenprobe: die Allowlist gated noch).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from validate_contract import Report, validate  # noqa: E402


def _minimal_process() -> dict:
    """Minimaler, gueltiger struktur-only Prozess (risikoarm, ohne actors[])."""
    return {
        "schema_version": "0.1.0",
        "id": "muster-prozess",
        "lebenslage_ref": "muster-prozess",
        "title": {"de": "Muster-Prozess"},
        "target_audience": "bevoelkerung",
        "steps": [
            {
                "step_id": 1,
                "actor": "buerger",
                "label": {"de": "Antrag stellen"},
                "depends_on": [],
            }
        ],
        "source_url": "https://www.stadt-zuerich.ch/muster",
        "retrieved_at": "2026-06-28",
        "disclaimer_key": "process.disclaimer.unofficial",
    }


def test_baseline_is_valid() -> None:
    """Absicherung: das Fixture ist ohne Zusatzfeld gueltig."""
    rep = Report(Path("synthetic"))
    validate(_minimal_process(), rep)
    assert rep.ok, rep.errors


def test_bewertung_field_is_accepted() -> None:
    """'bewertung' ist ein kanonisches additives Feld und darf nicht als
    'Unbekanntes Feld' abgelehnt werden — sonst scheitert ein gemergter Stand,
    den die Ziel-CI akzeptiert."""
    proc = _minimal_process()
    # Form bewusst opak gehalten: tessera erzeugt 'bewertung' nie selbst und
    # validiert dessen interne Struktur nicht — das tut kanonisch das Ziel-Repo.
    proc["bewertung"] = {"sterne": 4}
    rep = Report(Path("synthetic"))
    validate(proc, rep)
    assert rep.ok, rep.errors
    assert not any("bewertung" in e for e in rep.errors)


def test_unknown_field_still_rejected() -> None:
    """Gegenprobe: die Allowlist gated weiterhin — ein echtes Fremdfeld ist
    ein Fehler."""
    proc = _minimal_process()
    proc["quatsch"] = 123
    rep = Report(Path("synthetic"))
    validate(proc, rep)
    assert not rep.ok
    assert any("Unbekanntes Feld: quatsch" in e for e in rep.errors)


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
