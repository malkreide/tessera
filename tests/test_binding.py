#!/usr/bin/env python3
"""Tests fuer die Bindewert-Heuristiken (reine stdlib, CI-faehig ohne Deps).

Aufruf: python tests/test_binding.py — Exit 0 = alle Tests gruen.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tessera.binding import (  # noqa: E402
    BINDING_VALUE,
    binding_label_kind,
    label_value_mismatch,
    quote_substantiates,
)


def test_label_kind() -> None:
    assert binding_label_kind("Meldefrist bei Zuzug") == "time"
    assert binding_label_kind("Anmeldefrist") == "time"
    assert binding_label_kind("Gueltigkeit des Ausweises") == "time"
    assert binding_label_kind("Hoehe der jaehrlichen Hundeabgabe") == "money"
    assert binding_label_kind("Bearbeitungsgebuehr") == "money"
    assert binding_label_kind("Rekursfrist und Gebuehr") == "any"
    assert binding_label_kind("Erforderliche Gesuchsunterlagen") is None


def test_quote_substantiates_time() -> None:
    assert quote_substantiates("time", "innert zehn Tagen melden")      # wordnum + unit
    assert quote_substantiates("time", "Sie haben 14 Tage Zeit")        # digit + unit
    assert quote_substantiates("time", "bis am 30. Juni einreichen")    # date
    assert quote_substantiates("time", "gueltig bis 2027-12-31")        # ISO-date
    assert not quote_substantiates("time", "online oder am Schalter")   # keine Dauer


def test_quote_substantiates_money() -> None:
    assert quote_substantiates("money", "Die Abgabe betraegt CHF 175 pro Jahr")
    assert quote_substantiates("money", "kostet 50 Franken")
    assert quote_substantiates("money", "ein Zuschlag von 8 Prozent")
    assert not quote_substantiates("money", "innert 30 Tagen zu bezahlen")  # nur Frist


def test_label_value_mismatch_catches_wrong_type() -> None:
    # B5: Gebuehr-Label, aber das Zitat belegt nur eine Frist -> Befund.
    assert label_value_mismatch("Bearbeitungsgebuehr", "innert 30 Tagen zu bezahlen")
    # Frist-Label ohne jeden Wert -> Befund (Platzhalter-Zitat).
    assert label_value_mismatch("Rekursfrist", "ILLUSTRATIVES FIXTURE")
    # Passende Faelle -> kein Befund.
    assert label_value_mismatch("Meldefrist", "innert zehn Tagen melden") is None
    assert label_value_mismatch("Hundeabgabe", "CHF 175 pro Jahr") is None
    # Label ohne Bindewert-Typ -> nie ein Befund.
    assert label_value_mismatch("Gesuchsunterlagen", "irgendein Text") is None
    # Leeres Zitat ist hier KEIN Label<->Wert-Befund (faengt das Verbatim-Gate).
    assert label_value_mismatch("Meldefrist", "") is None


def test_cardinal_lint_regex_unchanged() -> None:
    # Die Kardinalregel-Regex bleibt eng (Ziffer + Einheit), unveraendert.
    assert BINDING_VALUE.search("innert 14 Tagen")
    assert BINDING_VALUE.search("CHF 175")
    assert BINDING_VALUE.search("8 Prozent")
    # Ausgeschriebene Zahl ist fuer den Kardinalregel-Lint bewusst KEIN Treffer.
    assert not BINDING_VALUE.search("innert zehn Tagen")


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
