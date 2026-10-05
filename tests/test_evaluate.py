#!/usr/bin/env python3
"""Tests fuer `tessera eval` (Extraktion vs. Handdatei) — reine stdlib.

`evaluate.evaluate` ist rein (kein Netz, keine Datei); die Tests bauen eine
Handdatei und Extraktions-Varianten, die je eine Messgroesse gezielt treffen.

Aufruf: python tests/test_evaluate.py — Exit 0 = alle Tests gruen.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tessera.evaluate import evaluate, pair_by_label, render_report  # noqa: E402
from tessera.grounding import BRIDGE_FLAG_PREFIX  # noqa: E402

URL = "https://www.stadt-zuerich.ch/hund"


def _step(sid, actor, label, deps):
    return {"step_id": sid, "actor": actor, "label": {"de": label}, "depends_on": deps}


# Handdatei: 1 -> 2 -> 3 -> 4, mit actors[].
CANONICAL = {
    "id": "hund-anmelden",
    "title": {"de": "Hund anmelden"},
    "actors": [
        {"id": "halter", "label": {"de": "Halter:in"}, "type": "antragsteller"},
        {"id": "kreisbuero", "label": {"de": "Kreisbüro"}, "type": "behoerde"},
        {"id": "steueramt", "label": {"de": "Steueramt"}, "type": "behoerde"},
    ],
    "steps": [
        _step(1, "halter", "Hund online oder am Schalter anmelden", []),
        _step(2, "kreisbuero", "Registrierung in der Hundedatenbank pruefen", [1]),
        _step(3, "steueramt", "Hundeabgabe veranlagen", [2]),
        _step(4, "halter", "Rechnung bezahlen", [3]),
    ],
    "references": [
        {"reference_id": 1, "label": {"de": "Anmeldefrist nach Zuzug"}, "source_url": URL},
        {"reference_id": 2, "label": {"de": "Hoehe der Hundeabgabe"}, "source_url": URL},
    ],
}


def _extracted(steps, refs=None):
    return {"id": "hund-anmelden", "title": {"de": "Hund anmelden"}, "steps": steps, "references": refs or []}


def test_identical_is_perfect() -> None:
    ext = copy.deepcopy(CANONICAL)
    for s, actor in zip(ext["steps"], ("Halter:in", "Kreisbüro", "Steueramt", "Halter:in"), strict=True):
        s["actor"] = actor  # Extraktion liefert Freitext-Rollen, keine ids
    rep = evaluate(ext, CANONICAL)
    assert rep.step_recall == 1.0 and rep.step_precision == 1.0
    assert len(rep.edges_exact) == 3 and rep.edges_compared == 3
    assert not (rep.edges_shortcut or rep.edges_reversed or rep.edges_unsupported or rep.edges_missed)
    assert len(rep.ref_pairs) == 2 and not rep.refs_url_differs
    assert rep.actors_checked and not rep.actors_unmapped and not rep.actors_mismatch


def test_missing_step_and_shortcut_edge() -> None:
    # Schritt 2 fehlt (z.B. durchs Gate gefallen); die Extraktion fuehrt 1 -> 3.
    ext = _extracted(
        [
            _step(1, "Halter:in", "Hund online oder am Schalter anmelden", []),
            _step(2, "Steueramt", "Hundeabgabe veranlagen", [1]),
            _step(3, "Halter:in", "Rechnung bezahlen", [2]),
        ]
    )
    rep = evaluate(
        ext, CANONICAL, [f"{BRIDGE_FLAG_PREFIX}: Kante 1 -> 2", "Schritt 9 «x» -> VERWORFEN (Gate)"]
    )
    assert rep.step_recall == 0.75 and rep.step_precision == 1.0
    assert rep.missing_steps == ["2 «Registrierung in der Hundedatenbank pruefen»"], rep.missing_steps
    assert len(rep.edges_shortcut) == 1 and "1 -> 3" in rep.edges_shortcut[0], rep.edges_shortcut
    assert len(rep.edges_exact) == 1  # 3 -> 4
    assert rep.dropped_steps == 1 and rep.gate_dropout == 0.25
    assert rep.flag_counts["ueberbrueckte Kanten"] == 1


def test_reversed_edge_detected() -> None:
    # Extraktion behauptet «Rechnung bezahlen» VOR «Hund anmelden».
    ext = _extracted(
        [
            _step(1, "Halter:in", "Rechnung bezahlen", []),
            _step(2, "Halter:in", "Hund online oder am Schalter anmelden", [1]),
        ]
    )
    rep = evaluate(ext, CANONICAL)
    assert len(rep.edges_reversed) == 1 and "4 -> 1" in rep.edges_reversed[0], rep.edges_reversed


def test_unsupported_edge_between_siblings() -> None:
    # Handdatei verzweigt: 2 und 3 haengen beide nur an 1 — zwischen 2 und 3
    # gibt es keinen Pfad. Die Extraktion behauptet 2 -> 3: unbelegt.
    can = copy.deepcopy(CANONICAL)
    can["steps"][2]["depends_on"] = [1]
    ext = _extracted(
        [
            _step(1, "Kreisbüro", "Registrierung in der Hundedatenbank pruefen", []),
            _step(2, "Steueramt", "Hundeabgabe veranlagen", [1]),
        ]
    )
    rep = evaluate(ext, can)
    assert len(rep.edges_unsupported) == 1 and "2 -> 3" in rep.edges_unsupported[0], rep.edges_unsupported


def test_extra_step_and_missed_edge() -> None:
    ext = _extracted(
        [
            _step(1, "Halter:in", "Hund online oder am Schalter anmelden", []),
            _step(2, "Halter:in", "Hund beim Tierarzt impfen lassen", [1]),
            _step(3, "Kreisbüro", "Registrierung in der Hundedatenbank pruefen", []),
            _step(4, "Steueramt", "Hundeabgabe veranlagen", [3]),
        ]
    )
    rep = evaluate(ext, CANONICAL)
    assert rep.extra_steps == ["2 «Hund beim Tierarzt impfen lassen»"], rep.extra_steps
    # Handkante 1 -> 2 (anmelden -> pruefen) fehlt in der Extraktion.
    assert any(e.startswith("1 -> 2") for e in rep.edges_missed), rep.edges_missed


def test_actor_unmapped_and_mismatch() -> None:
    ext = _extracted(
        [
            _step(1, "Hundekontrolle", "Hund online oder am Schalter anmelden", []),
            _step(2, "Steueramt", "Registrierung in der Hundedatenbank pruefen", [1]),
        ]
    )
    rep = evaluate(ext, CANONICAL)
    assert rep.actors_unmapped == ["Schritt 1: «Hundekontrolle»"], rep.actors_unmapped
    assert len(rep.actors_mismatch) == 1 and "Handdatei: kreisbuero" in rep.actors_mismatch[0]


def test_reference_url_difference_and_unverified() -> None:
    refs = [
        {"reference_id": 1, "label": {"de": "Anmeldefrist nach Zuzug"}, "source_url": URL + "/fristen",
         "status": "unverifiziert"},
    ]  # fmt: skip
    rep = evaluate(_extracted([_step(1, "Halter:in", "Rechnung bezahlen", [])], refs), CANONICAL)
    assert len(rep.ref_pairs) == 1 and rep.refs_unverified == 1
    assert len(rep.refs_url_differs) == 1


def test_strict_lint_baseline_on_both_sides() -> None:
    can = copy.deepcopy(CANONICAL)
    can["steps"][3]["label"]["de"] = "Rechnung innert dreissig Tagen bezahlen"
    rep = evaluate(_extracted([_step(1, "Halter:in", "Rechnung bezahlen", [])]), can)
    assert rep.strict_hits_ext == []
    assert len(rep.strict_hits_can) == 1 and "steps[4].label.de" in rep.strict_hits_can[0]


def test_pairing_is_one_to_one_and_skips_empty_labels() -> None:
    ext = [{"step_id": 1, "label": {"de": "Hund anmelden"}}, {"step_id": 2, "label": {"de": "Hund anmelden"}}]
    can = [{"step_id": 7, "label": {"de": "Hund anmelden"}}, {"step_id": 8, "label": {"de": ""}}]
    pairs = pair_by_label(ext, can, "step_id", 0.5)
    assert [(p.ext_id, p.can_id) for p in pairs] == [(1, 7)], pairs


def test_empty_inputs_do_not_crash() -> None:
    rep = evaluate({"id": "x"}, {"id": "x"})
    assert rep.step_recall is None and rep.step_precision is None and rep.gate_dropout is None
    assert "Keine Paare" in render_report(rep, "test")


def test_report_lists_pairs_and_missing() -> None:
    ext = _extracted([_step(1, "Halter:in", "Hund online oder am Schalter anmelden", [])])
    text = render_report(evaluate(ext, CANONICAL), "`fixture`")
    assert (
        "| 1 «Hund online oder am Schalter anmelden» | 1 «Hund online oder am Schalter anmelden» | 1.0 |"
        in text
    )
    assert "## Moeglicherweise fehlende Schritte" in text
    assert "Schritt-Recall" in text and "25%" in text


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
