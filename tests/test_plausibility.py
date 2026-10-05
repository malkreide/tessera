#!/usr/bin/env python3
"""Tests fuer die Plausibilitaets-Hinweise (Reihenfolge + Akteur) — reine stdlib.

Beide Proben sind Flags, kein Gate: sie veraendern den Prozess nie, sie melden
nur, was das Grounding-Gate nicht prueft.

Aufruf: python tests/test_plausibility.py — Exit 0 = alle Tests gruen.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tessera.grounding import Corpus  # noqa: E402
from tessera.plausibility import (  # noqa: E402
    ACTOR_FLAG_PREFIX,
    ORDER_FLAG_PREFIX,
    actor_flags,
    order_flags,
)

PAGE_A = "https://example.org/hund"
PAGE_B = "https://example.org/hund/anmeldung"

TEXT_A = (
    "Zuerst melden Hundehalterinnen und Hundehalter den Hund beim Kreisbuero an. "
    "Danach registriert die Tierarztpraxis den Mikrochip in der Datenbank. "
    "Zum Schluss stellt das Kreisbuero eine Bestaetigung per Post zu."
)
TEXT_B = "Die Anmeldung beim Kreisbuero ist online oder am Schalter moeglich."

Q1 = "melden Hundehalterinnen und Hundehalter den Hund beim Kreisbuero an"
Q2 = "registriert die Tierarztpraxis den Mikrochip in der Datenbank"
Q3 = "stellt das Kreisbuero eine Bestaetigung per Post zu"
QB = "Die Anmeldung beim Kreisbuero ist online oder am Schalter moeglich"


def _pages() -> dict[str, Corpus]:
    return {PAGE_A: Corpus(TEXT_A), PAGE_B: Corpus(TEXT_B)}


def _process(deps: dict[int, list]) -> dict:
    labels = {1: "Hund anmelden", 2: "Chip registrieren", 3: "Bestaetigung erhalten", 4: "Online melden"}
    actors = {1: "Halter:in", 2: "Tierarztpraxis", 3: "Kreisbuero", 4: "Halter:in"}
    return {
        "id": "hund-anmelden",
        "steps": [
            {"step_id": sid, "actor": actors[sid], "label": {"de": labels[sid]}, "depends_on": d}
            for sid, d in deps.items()
        ],
    }


QUOTES = {1: Q1, 2: Q2, 3: Q3, 4: QB}


def test_order_consistent_no_flag() -> None:
    process = _process({1: [], 2: [1], 3: [2]})
    assert order_flags(process, QUOTES, _pages()) == []


def test_order_contradiction_flagged() -> None:
    # Kante 3 -> 1: das Zitat von 3 steht auf derselben Seite HINTER dem von 1.
    process = _process({3: [], 1: [3]})
    flags = order_flags(process, QUOTES, _pages())
    assert len(flags) == 1, flags
    assert flags[0].startswith(ORDER_FLAG_PREFIX)
    assert "Kante 3 -> 1" in flags[0] and PAGE_A in flags[0], flags


def test_order_conditional_edge_checked() -> None:
    process = _process({3: [], 1: [{"step_id": 3, "condition": {"de": "falls erledigt"}}]})
    assert len(order_flags(process, QUOTES, _pages())) == 1


def test_order_different_pages_not_judged() -> None:
    # 4 steht nur auf Seite B, 3 nur auf Seite A: keine gemeinsame Seite ->
    # nicht beurteilbar, kein Flag (keine Vermutung).
    process = _process({4: [], 3: [4]})
    assert order_flags(process, QUOTES, _pages()) == []


def test_order_ignores_missing_quotes() -> None:
    process = _process({1: [], 2: [1]})
    assert order_flags(process, {1: Q1}, _pages()) == []


def test_order_does_not_mutate_process() -> None:
    process = _process({3: [], 1: [3]})
    before = repr(process)
    order_flags(process, QUOTES, _pages())
    assert repr(process) == before


def test_actor_found_with_gender_and_compound() -> None:
    # «Halter:in» -> «halter» steckt in «Hundehalterinnen»; Umlaut-Transliteration
    # wie im Merge (Kreisbüro == Kreisbuero).
    process = _process({1: [], 2: [1], 3: [2]})
    process["steps"][2]["actor"] = "Kreisbüro"
    assert actor_flags(process, TEXT_A) == []


def test_actor_absent_flagged_once_with_steps() -> None:
    process = _process({1: [], 2: [1], 3: [2]})
    process["steps"][0]["actor"] = "Steueramt"
    process["steps"][2]["actor"] = "Steueramt"
    flags = actor_flags(process, TEXT_A)
    assert len(flags) == 1, flags
    assert flags[0].startswith(ACTOR_FLAG_PREFIX)
    assert "«Steueramt»" in flags[0] and "Schritt 1, 3" in flags[0], flags


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
