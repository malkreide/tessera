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

from tessera.evaluate import (  # noqa: E402
    PairingError,
    evaluate,
    pair_by_label,
    parse_actor_map,
    parse_pairing,
    propose_pairing,
    render_report,
)
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


# --- Paarungsdatei (manuelle Gruppen) ----------------------------------------

# Extraktion feiner zerlegt: 1+2 = Hand 1 (zwei Kanaele), 3 = Hand 3, 4 = Hand 4;
# Hand 2 fehlt in der Extraktion, Extraktion 5 hat keine Entsprechung.
FINE = _extracted(
    [
        _step(1, "Halter:in", "Hund online anmelden", []),
        _step(2, "Halter:in", "Hund am Schalter anmelden", []),
        _step(3, "Steueramt", "Abgabe festlegen", [1, 2]),
        _step(4, "Halter:in", "Zahlen", [3]),
        _step(5, "Halter:in", "Hundekurs besuchen", []),
    ]
)


def _pairing(**over):
    data = {
        "leistung": "hund-anmelden",
        "status": "vorschlag",
        "gruppen": [
            {
                "extraktion": {1: "Hund online anmelden", 2: "Hund am Schalter anmelden"},
                "hand": {1: "Hund online oder am Schalter anmelden"},
                "notiz": "Kanaele einzeln",
            },
            {"extraktion": {3: "Abgabe festlegen"}, "hand": {3: "Hundeabgabe veranlagen"}},
            {"extraktion": {4: "Zahlen"}, "hand": {4: "Rechnung bezahlen"}},
            {"extraktion": {5: "Hundekurs besuchen"}, "hand": {}, "notiz": "Zusatzinfo"},
            {
                "extraktion": {},
                "hand": {2: "Registrierung in der Hundedatenbank pruefen"},
                "nicht_belegbar": True,
                "notiz": "behoerdenintern",
            },
        ],
    }
    data.update(over)
    return data


def test_pairing_groups_drive_recall_and_precision() -> None:
    rep = evaluate(FINE, CANONICAL, pairing=_pairing(), pairing_source="`x.pairs.yaml`")
    assert (rep.can_matched, rep.can_steps) == (3, 4) and rep.step_recall == 0.75
    assert (rep.ext_matched, rep.ext_steps) == (4, 5) and rep.step_precision == 0.8
    assert rep.step_recall_groundable == 1.0, rep.step_recall_groundable  # 3/3 ohne Hand 2
    assert rep.missing_steps == [
        "2 «Registrierung in der Hundedatenbank pruefen» (nicht belegbar) — behoerdenintern"
    ], rep.missing_steps
    assert rep.extra_steps == ["5 «Hundekurs besuchen» — Zusatzinfo"], rep.extra_steps


def test_pairing_edges_between_groups() -> None:
    rep = evaluate(FINE, CANONICAL, pairing=_pairing())
    # 1->3 und 2->3 fallen auf dieselbe Gruppenkante; Hand fuehrt 1->2->3: Abkuerzung.
    assert len(rep.edges_shortcut) == 1 and rep.edges_shortcut[0].startswith("1 -> 3"), rep.edges_shortcut
    assert len(rep.edges_exact) == 1 and rep.edges_exact[0].startswith("3 -> 4"), rep.edges_exact
    assert not rep.edges_reversed and not rep.edges_unsupported and not rep.edges_missed


def test_pairing_n_to_m_group_label_and_actor() -> None:
    data = _pairing()
    data["gruppen"][1] = {
        "extraktion": {3: "Abgabe festlegen"},
        "hand": {3: "Hundeabgabe veranlagen", 4: "Rechnung bezahlen"},
    }
    data["gruppen"][2] = {"extraktion": {4: "Zahlen"}, "hand": {}}
    rep = evaluate(FINE, CANONICAL, pairing=data)
    # Akteur von Schritt 3 (Steueramt) passt zu einem der beiden Handschritte.
    assert not rep.actors_mismatch, rep.actors_mismatch
    text = render_report(rep, "`fixture`")
    assert "| 3 «Abgabe festlegen» | 3 «Hundeabgabe veranlagen», 4 «Rechnung bezahlen» |" in text


def test_pairing_rejects_stale_incomplete_and_duplicate() -> None:
    data = _pairing()
    data["gruppen"][0]["extraktion"][1] = "Hund anmelden (alt)"  # veraltetes Label
    data["gruppen"][2]["hand"] = {3: "Hundeabgabe veranlagen"}  # Hand 3 doppelt, Hand 4 fehlt
    data["gruppen"][3]["extraktion"] = {9: "gibt es nicht"}  # unbekannt; Extraktion 5 fehlt
    try:
        parse_pairing(data, FINE, CANONICAL)
    except PairingError as exc:
        joined = " | ".join(exc.problems)
        assert "weicht vom aktuellen" in joined, joined
        assert "Schritt 3 schon in" in joined, joined
        assert "Schritt 9 gibt es nicht" in joined, joined
        assert "hand: Schritt(e) [4] fehlen" in joined and "extraktion: Schritt(e) [5] fehlen" in joined, (
            joined
        )
    else:
        raise AssertionError("veraltete/unvollstaendige Paarung haette abgelehnt werden muessen")


def test_pairing_rejects_bad_header_and_misplaced_flag() -> None:
    data = _pairing(leistung="andere", status="ok")
    data["gruppen"][3]["nicht_belegbar"] = True  # hat Extraktionsschritte
    try:
        parse_pairing(data, FINE, CANONICAL)
    except PairingError as exc:
        joined = " | ".join(exc.problems)
        assert "leistung" in joined and "status" in joined and "nicht_belegbar: nur" in joined, joined
    else:
        raise AssertionError("haette abgelehnt werden muessen")


def test_propose_pairing_roundtrips_and_covers_everything() -> None:
    proposal = propose_pairing(FINE, CANONICAL)
    assert proposal["status"] == "vorschlag" and proposal["leistung"] == "hund-anmelden"
    groups, status = parse_pairing(proposal, FINE, CANONICAL)  # Vorschlag ist gueltig
    assert status == "vorschlag"
    assert sorted(sid for g in groups for sid, _ in g.ext) == [1, 2, 3, 4, 5]
    assert sorted(sid for g in groups for sid, _ in g.can) == [1, 2, 3, 4]


def test_report_marks_manual_pairing_and_status() -> None:
    text = render_report(
        evaluate(FINE, CANONICAL, pairing=_pairing(), pairing_source="`x.pairs.yaml`"), "`f`"
    )
    assert "Schritt-Paarung: von Hand, `x.pairs.yaml` (Status: vorschlag" in text, text
    assert "Recall ohne nicht belegbare Handschritte | 100% (3/3)" in text, text
    assert "| Extraktion | Handdatei | Notiz |" in text
    heuristic = render_report(evaluate(FINE, CANONICAL), "`f`")
    assert "Heuristik" in heuristic and "--propose-pairs" in heuristic


# --- Akteur-Zuordnung (akteure: in der Paarungsdatei) ------------------------

# Extraktion mit Quellnamen statt Handdatei-IDs; 1:1 gepaart.
SOURCE_NAMES = _extracted(
    [
        _step(1, "Hundehalter:in", "Hund anmelden", []),
        _step(2, "Kreisbuero Stadt", "Registrierung pruefen", [1]),
        _step(3, "hundeportal.ch", "Abgabe veranlagen", [2]),
    ]
)


def _named_pairing(akteure=None) -> dict:
    data = {
        "leistung": "hund-anmelden",
        "status": "vorschlag",
        "gruppen": [
            {"extraktion": {1: "Hund anmelden"}, "hand": {1: "Hund online oder am Schalter anmelden"}},
            {
                "extraktion": {2: "Registrierung pruefen"},
                "hand": {2: "Registrierung in der Hundedatenbank pruefen"},
            },
            {"extraktion": {3: "Abgabe veranlagen"}, "hand": {3: "Hundeabgabe veranlagen"}},
            {"extraktion": {}, "hand": {4: "Rechnung bezahlen"}},
        ],
    }
    if akteure is not None:
        data["akteure"] = akteure
    return data


def test_actor_map_resolves_source_names() -> None:
    before = evaluate(SOURCE_NAMES, CANONICAL, pairing=_named_pairing())
    assert len(before.actors_unmapped) == 3 and not before.actors_mismatch, before.actors_unmapped
    rep = evaluate(
        SOURCE_NAMES,
        CANONICAL,
        pairing=_named_pairing(
            {"Hundehalter:in": "halter", "Kreisbuero Stadt": "steueramt", "hundeportal.ch": None}
        ),
    )
    assert not rep.actors_unmapped, rep.actors_unmapped
    assert rep.actors_declared_none == ["Schritt 3: «hundeportal.ch»"], rep.actors_declared_none
    # Zuordnung aktiviert die Pruefung: Schritt 2 ist in der Handdatei kreisbuero.
    assert len(rep.actors_mismatch) == 1 and "Handdatei: kreisbuero" in rep.actors_mismatch[0], (
        rep.actors_mismatch
    )


def test_actor_map_open_entry_counts_as_unmapped() -> None:
    rep = evaluate(
        SOURCE_NAMES, CANONICAL, pairing=_named_pairing({"Hundehalter:in": "", "hundeportal.ch": None})
    )
    assert "Schritt 1: «Hundehalter:in»" in rep.actors_unmapped, rep.actors_unmapped
    text = render_report(rep, "`f`")
    assert "bewusst ohne / falsch zugeordnet | 2 / 1 / 0 |" in text, text
    assert "`kreisbuero` (Kreisbüro)" in text, text  # Hilfe: actors[] der Handdatei


def test_actor_map_rejects_stale_name_unknown_id_and_missing_actors() -> None:
    try:
        parse_actor_map(
            {"akteure": {"Gibt es nicht": "halter", "Hundehalter:in": "amt"}}, SOURCE_NAMES, CANONICAL
        )
    except PairingError as exc:
        joined = " | ".join(exc.problems)
        assert "«Gibt es nicht» kommt in der Extraktion nicht vor" in joined, joined
        assert "'amt' ist keine actors[]-ID" in joined, joined
    else:
        raise AssertionError("haette abgelehnt werden muessen")
    no_actors = {k: v for k, v in CANONICAL.items() if k != "actors"}
    try:
        parse_actor_map({"akteure": {"Hundehalter:in": "halter"}}, SOURCE_NAMES, no_actors)
    except PairingError as exc:
        assert "keine actors[]" in exc.problems[0], exc.problems
    else:
        raise AssertionError("ohne actors[] haette abgelehnt werden muessen")


def test_propose_lists_open_actor_names() -> None:
    proposal = propose_pairing(SOURCE_NAMES, CANONICAL)
    assert proposal["akteure"] == {"Hundehalter:in": "", "Kreisbuero Stadt": "", "hundeportal.ch": ""}, (
        proposal
    )
    assert parse_actor_map(proposal, SOURCE_NAMES, CANONICAL) == {}  # alles offen, aber gueltig
    assert "akteure" not in propose_pairing(FINE, CANONICAL)  # Freitext trifft ID/Label


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
