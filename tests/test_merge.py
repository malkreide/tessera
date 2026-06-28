#!/usr/bin/env python3
"""Tests fuer den feldweisen Merge gegen handgepflegte Zieldateien.

Reine stdlib (CI-faehig ohne Dependencies). Aufruf:
    python tests/test_merge.py — Exit 0 = alle Tests gruen.

Deckt ab:
  (a) bestehende en/fr/it/ls/description bleiben erhalten, wenn die Extraktion
      sie leer liefert,
  (b) neue Felder/Schritte/References werden ergaenzt,
  (c) der Merge ist stabil ueber step_id/reference_id/actor.id (index-unabhaengig),
  (d) nicht sauber mergebare Faelle werfen MergeConflict (Aufrufer ueberspringt).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts"))

from tessera.merge import MergeConflict, merge_process, normalize_i18n  # noqa: E402
from validate_contract import Report, validate  # noqa: E402


def _contract_ok(doc: dict) -> Report:
    rep = Report(Path("synthetic"))
    validate(doc, rep)
    return rep


def _existing() -> dict:
    """Handgepflegte Zieldatei mit vollstaendigen Uebersetzungen + description."""
    return {
        "schema_version": "0.1.0",
        "id": "hund-anmelden",
        "lebenslage_ref": "hund-anmelden",
        "title": {
            "de": "Hund anmelden",
            "en": "Register a dog",
            "fr": "Annoncer un chien",
            "it": "Registrare un cane",
            "ls": "Sie haben einen Hund. Sie melden den Hund an.",
        },
        "description": {"de": "Wie Sie Ihren Hund in der Stadt anmelden.", "en": "How to register."},
        "target_audience": "bevoelkerung",
        "preconditions": [{"de": "Wohnsitz in Zuerich", "en": "Residence in Zurich"}],
        "steps": [
            {
                "step_id": 2,  # bewusst NICHT in Reihenfolge -> Stabilitaetstest
                "actor": "Veterinaeramt",
                "label": {"de": "Registrierung pruefen", "en": "Check registration", "fr": "Vérifier"},
                "description": {"de": "Das Amt prueft.", "en": "The office checks."},
                "depends_on": [1],
            },
            {
                "step_id": 1,
                "actor": "Halter:in",
                "label": {"de": "Hund anmelden", "en": "Register dog", "ls": "Sie melden den Hund an."},
                "depends_on": [],
                "reference_ids": [1],
            },
        ],
        "references": [
            {
                "reference_id": 1,
                "label": {"de": "Anmeldefrist", "en": "Registration deadline", "fr": "Délai"},
                "source_url": "https://www.stadt-zuerich.ch/hund",
                "source_quote": "innert zehn Tagen",
                "status": "verifiziert",
                "retrieved_at": "2026-01-01",
            }
        ],
        "actors": [
            {"id": "halter", "label": {"de": "Halter:in", "en": "Owner"}, "type": "antragsteller"}
        ],
        "source_url": "https://www.stadt-zuerich.ch/hund",
        "retrieved_at": "2026-01-01",
        "disclaimer_key": "process.disclaimer.unofficial",
    }


def _extraction() -> dict:
    """Struktur-only Extraktion: de gesetzt, en/fr/it LEER, neue Struktur dazu."""
    return {
        "$schema": "../../../schemas/opengov-process-schema.json",
        "schema_version": "0.1.0",
        "id": "hund-anmelden",
        "lebenslage_ref": "hund-anmelden",
        "city": "zh",
        "title": {"de": "Hund anmelden", "en": "", "fr": "", "it": ""},
        "target_audience": "bevoelkerung",
        "steps": [
            {
                "step_id": 1,
                "actor": "Halter:in",
                "label": {"de": "Hund online oder am Schalter anmelden", "en": "", "fr": "", "it": ""},
                "depends_on": [],
                "reference_ids": [1],
            },
            {
                "step_id": 2,
                "actor": "Veterinaeramt",
                "label": {"de": "Registrierung pruefen", "en": "", "fr": "", "it": ""},
                "depends_on": [1],
            },
            {
                "step_id": 3,  # NEUER Schritt
                "actor": "Steueramt",
                "label": {"de": "Veranlagung der Hundeabgabe", "en": "", "fr": "", "it": ""},
                "depends_on": [{"step_id": 2, "condition": {"de": "Registrierung bestaetigt"}}],
                "reference_ids": [2],
            },
        ],
        "references": [
            {
                "reference_id": 1,
                "label": {"de": "Anmeldefrist", "en": "", "fr": "", "it": ""},
                "source_url": "https://www.stadt-zuerich.ch/hund",
                "source_quote": "innert zehn Tagen",
                "status": "verifiziert",
                "retrieved_at": "2026-06-14",
            },
            {
                "reference_id": 2,  # NEUE Reference
                "label": {"de": "Hoehe der Hundeabgabe", "en": "", "fr": "", "it": ""},
                "source_url": "https://www.stadt-zuerich.ch/hundeabgabe",
                "source_quote": "Die Hundeabgabe betraegt",
                "status": "verifiziert",
                "retrieved_at": "2026-06-14",
            },
        ],
        "source_url": "https://www.stadt-zuerich.ch/hund",
        "retrieved_at": "2026-06-14",
        "disclaimer_key": "process.disclaimer.unofficial",
    }


def test_a_existing_translations_preserved() -> None:
    """(a) Belegte en/fr/it/ls/description duerfen NICHT geleert werden."""
    merged, report = merge_process(_existing(), _extraction())
    assert merged["title"]["en"] == "Register a dog"
    assert merged["title"]["fr"] == "Annoncer un chien"
    assert merged["title"]["it"] == "Registrare un cane"
    assert merged["title"]["ls"].startswith("Sie haben einen Hund")
    # description-Block bleibt vollstaendig erhalten.
    assert merged["description"]["de"].startswith("Wie Sie")
    assert merged["description"]["en"] == "How to register."
    # preconditions-Uebersetzung bleibt erhalten.
    assert merged["preconditions"][0]["en"] == "Residence in Zurich"

    s1 = next(s for s in merged["steps"] if s["step_id"] == 1)
    assert s1["label"]["en"] == "Register dog"
    assert s1["label"]["ls"] == "Sie melden den Hund an."
    s2 = next(s for s in merged["steps"] if s["step_id"] == 2)
    assert s2["label"]["fr"] == "Vérifier"
    assert s2["description"]["en"] == "The office checks."

    r1 = next(r for r in merged["references"] if r["reference_id"] == 1)
    assert r1["label"]["fr"] == "Délai"
    a1 = next(a for a in merged["actors"] if a["id"] == "halter")
    assert a1["label"]["en"] == "Owner"

    # Schutzfaelle wurden als 'preserved' protokolliert (en/fr/it/ls, nicht de).
    assert any("title.en" in p for p in report.preserved)
    assert any("steps[2].label.fr" in p for p in report.preserved)
    assert not any(p.endswith(".de") for p in report.preserved)


def test_a_de_gap_is_filled_but_existing_de_wins() -> None:
    """de der Extraktion fuellt nur Luecken; bestehendes de gewinnt."""
    merged, _ = merge_process(_existing(), _extraction())
    s1 = next(s for s in merged["steps"] if s["step_id"] == 1)
    # Bestehendes de gewinnt gegen abweichendes Extraktions-de.
    assert s1["label"]["de"] == "Hund anmelden"


def test_b_new_steps_and_references_added() -> None:
    """(b) Neue Schritte/References/Felder werden ergaenzt."""
    merged, report = merge_process(_existing(), _extraction())
    step_ids = sorted(s["step_id"] for s in merged["steps"])
    assert step_ids == [1, 2, 3]
    ref_ids = sorted(r["reference_id"] for r in merged["references"])
    assert ref_ids == [1, 2]
    # Neuer Schritt 3 ist vollstaendig uebernommen.
    s3 = next(s for s in merged["steps"] if s["step_id"] == 3)
    assert s3["actor"] == "Steueramt"
    # Fehlendes additives Feld (city, $schema) wurde ergaenzt.
    assert merged["city"] == "zh"
    assert "$schema" in merged
    assert any("steps[3] (neu)" in a for a in report.added)
    assert any("references[2] (neu)" in a for a in report.added)
    assert any("city" in a for a in report.added)


def test_c_merge_stable_over_business_keys() -> None:
    """(c) Stabil ueber step_id/reference_id/actor.id trotz vertauschter Reihenfolge.

    Bestehende Reihenfolge bleibt; gemerged wird ueber Schluessel, nicht Index.
    """
    existing = _existing()  # steps in Reihenfolge [2, 1]
    extraction = _extraction()  # steps in Reihenfolge [1, 2, 3]
    merged, _ = merge_process(existing, extraction)
    # Bestehende Reihenfolge [2, 1] bleibt, neuer Schritt 3 wird angehaengt.
    assert [s["step_id"] for s in merged["steps"]] == [2, 1, 3]
    # Schritt 2 wurde mit dem RICHTIGEN Extraktions-Schritt 2 gemerged
    # (nicht mit Index-0 = Extraktions-Schritt 1).
    s2 = next(s for s in merged["steps"] if s["step_id"] == 2)
    assert s2["actor"] == "Veterinaeramt"
    assert s2["label"]["de"] == "Registrierung pruefen"


def test_c_missing_field_filled_from_extraction() -> None:
    """Fehlendes Feld (reference_ids an Schritt 2) wird aus Extraktion ergaenzt."""
    existing = _existing()
    extraction = _extraction()
    # Schritt 2 der Extraktion bekommt reference_ids, das bestehend fehlt.
    for s in extraction["steps"]:
        if s["step_id"] == 2:
            s["reference_ids"] = [2]
    merged, _ = merge_process(existing, extraction)
    s2 = next(s for s in merged["steps"] if s["step_id"] == 2)
    assert s2.get("reference_ids") == [2]


def test_normalize_leichte_sprache_alias() -> None:
    """leichte_sprache der Extraktion wird auf ls gemappt."""
    assert normalize_i18n({"de": "x", "leichte_sprache": "einfach"})["ls"] == "einfach"
    # Vorhandenes nicht-leeres ls gewinnt gegen Alias.
    out = normalize_i18n({"de": "x", "ls": "schon da", "leichte_sprache": "alt"})
    assert out["ls"] == "schon da"


def test_alias_fills_missing_ls_in_merge() -> None:
    """ls-Luecke wird durch leichte_sprache der Extraktion gefuellt."""
    existing = _existing()
    # title hat ls; entfernen wir es, damit die Extraktion es fuellen kann.
    del existing["title"]["ls"]
    extraction = _extraction()
    extraction["title"]["leichte_sprache"] = "Einfacher Titel."
    merged, _ = merge_process(existing, extraction)
    assert merged["title"]["ls"] == "Einfacher Titel."


def test_e_actor_remapped_to_existing_id() -> None:
    """(e) Freitext-Actor der Extraktion wird gender-neutral auf die
    bestehende actors[].id abgebildet ('Halter:in' -> 'halter')."""
    merged, report = merge_process(_existing(), _extraction())
    s1 = next(s for s in merged["steps"] if s["step_id"] == 1)
    assert s1["actor"] == "halter", s1["actor"]
    assert any("steps[1].actor" in r and "'halter'" in r for r in report.remapped_actors)


def test_e_actor_remapped_across_umlaut_transliteration() -> None:
    """(e) Umlaut-Schreibweise des LLM ('Fundbüro') wird auf die ASCII-id
    ('fundbuero') abgebildet — ue=ü-Aequivalenz, kein Fuzzy-Matching.
    Realfall aus dem fundsache-Lauf (Schritt-actor 'Fundbüro')."""
    existing = {
        "schema_version": "0.1.0",
        "id": "fundsache",
        "lebenslage_ref": "fundsache",
        "title": {"de": "Fundsache"},
        "target_audience": "bevoelkerung",
        "steps": [
            {"step_id": 1, "actor": "fundbuero", "label": {"de": "Fund erfassen"}, "depends_on": []},
        ],
        "actors": [
            {"id": "fundbuero", "label": {"de": "Fundbüro der Stadtpolizei Zürich"}, "type": "behoerde"},
            {"id": "person", "label": {"de": "Findende oder verlierende Person"}, "type": "antragsteller"},
        ],
        "source_url": "https://www.stadt-zuerich.ch/vbz/de/beratung-service/fundbuero.html",
        "retrieved_at": "2026-06-28",
        "disclaimer_key": "Prozesse.disclaimer",
    }
    extraction = {
        "id": "fundsache",
        "steps": [
            {"step_id": 2, "actor": "Fundbüro", "label": {"de": "Gegen Ausweis aushaendigen"}, "depends_on": [1]},
        ],
    }
    merged, report = merge_process(existing, extraction)
    s2 = next(s for s in merged["steps"] if s["step_id"] == 2)
    assert s2["actor"] == "fundbuero", s2["actor"]
    assert not report.unmapped_actors
    rep = _contract_ok(merged)
    assert rep.ok, rep.errors


def test_e_unknown_actor_flagged_not_invented() -> None:
    """(e) Ein Actor ohne passenden actors[]-Eintrag wird GEFLAGGT, nicht
    geraten: kein neuer actors[]-Eintrag, der Wert bleibt unveraendert stehen."""
    existing = _existing()
    extraction = _extraction()
    extraction["steps"].append(
        {
            "step_id": 4,
            "actor": "Hundeausbildner:in",  # kein actors[]-Eintrag
            "label": {"de": "Praxiskurs in AMICUS eintragen", "en": "", "fr": "", "it": ""},
            "depends_on": [3],
        }
    )
    merged, report = merge_process(existing, extraction)
    s4 = next(s for s in merged["steps"] if s["step_id"] == 4)
    assert s4["actor"] == "Hundeausbildner:in"  # unveraendert
    assert not any(a.get("id") == "hundeausbildner" for a in merged["actors"])  # nichts erfunden
    assert any("steps[4].actor" in u and "Hundeausbildner" in u for u in report.unmapped_actors)


def _existing_all_halter() -> dict:
    """Minimale Zieldatei, deren Schritte alle die Rolle Halter:in tragen und
    deren actors[] genau einen Eintrag `halter` hat (Freitext vs. id)."""
    return {
        "schema_version": "0.1.0",
        "id": "hund-anmelden",
        "lebenslage_ref": "hund-anmelden",
        "title": {"de": "Hund anmelden"},
        "target_audience": "bevoelkerung",
        "steps": [
            {"step_id": 1, "actor": "Halter:in", "label": {"de": "Anmelden"}, "depends_on": []},
        ],
        "actors": [{"id": "halter", "label": {"de": "Hundehalter:in"}, "type": "antragsteller"}],
        "source_url": "https://www.stadt-zuerich.ch/hund",
        "retrieved_at": "2026-01-01",
        "disclaimer_key": "process.disclaimer.unofficial",
    }


def test_e_remapped_actor_passes_contract_validator() -> None:
    """Kopplung Merge<->Validator: nach dem Remap ist jeder steps[].actor eine
    actors[].id -> der Vertrags-Validator (Actor-Paritaet) ist gruen."""
    extraction = {
        "id": "hund-anmelden",
        "steps": [
            {"step_id": 1, "actor": "Halter:in", "label": {"de": "Anmelden"}, "depends_on": []},
            {"step_id": 2, "actor": "Halter:in", "label": {"de": "Bezahlen"}, "depends_on": [1]},
        ],
    }
    merged, report = merge_process(_existing_all_halter(), extraction)
    assert not report.unmapped_actors
    assert all(s["actor"] == "halter" for s in merged["steps"])
    rep = _contract_ok(merged)
    assert rep.ok, rep.errors


def test_e_unmapped_actor_fails_contract_validator() -> None:
    """Gate-Paritaet: ein unmapped Actor laesst den Vertrags-Validator scheitern
    (genau der Fehler, den die Ziel-CI wirft) — kein stilles Durchrutschen."""
    existing = _existing()
    extraction = _extraction()
    extraction["steps"].append(
        {
            "step_id": 4,
            "actor": "Hundeausbildner:in",
            "label": {"de": "Praxiskurs eintragen", "en": "", "fr": "", "it": ""},
            "depends_on": [3],
        }
    )
    merged, _ = merge_process(existing, extraction)
    rep = _contract_ok(merged)
    assert not rep.ok
    assert any("actor" in e and "Hundeausbildner" in e for e in rep.errors), rep.errors


def test_e_no_actors_leaves_free_text_actors() -> None:
    """Ohne actors[] in der Zieldatei bleibt der Freitext-Actor unangetastet
    (die kanonische Regel greift nur, wenn actors[] vorhanden ist)."""
    existing = _existing()
    del existing["actors"]
    merged, report = merge_process(existing, _extraction())
    s1 = next(s for s in merged["steps"] if s["step_id"] == 1)
    assert s1["actor"] == "Halter:in"
    assert not report.remapped_actors and not report.unmapped_actors


def test_e_ambiguous_normform_not_mapped() -> None:
    """Kollidieren zwei actors auf dieselbe Normalform, wird NICHT gemappt
    (lieber flaggen als auf den falschen Akteur zeigen)."""
    existing = _existing()
    # Zwei Eintraege, deren Labels auf dieselbe Normalform "halter" fallen
    # ("Halter:in" -> halter, "Halter" -> halter): mehrdeutig -> kein Mapping.
    existing["actors"] = [
        {"id": "halter-a", "label": {"de": "Halter:in"}, "type": "antragsteller"},
        {"id": "halter-b", "label": {"de": "Halter"}, "type": "antragsteller"},
    ]
    merged, report = merge_process(existing, _extraction())
    s1 = next(s for s in merged["steps"] if s["step_id"] == 1)
    assert s1["actor"] == "Halter:in"  # nicht gemappt (mehrdeutig)
    assert any("steps[1].actor" in u for u in report.unmapped_actors)


def test_d_conflict_on_id_mismatch() -> None:
    """(d) id-Mismatch ist nicht sauber mergebar -> MergeConflict."""
    existing = _existing()
    extraction = _extraction()
    extraction["id"] = "umzug-melden"
    try:
        merge_process(existing, extraction)
    except MergeConflict:
        return
    raise AssertionError("MergeConflict bei id-Mismatch erwartet")


def test_d_conflict_on_duplicate_keys() -> None:
    """(d) Doppelte fachliche Schluessel sind nicht eindeutig -> MergeConflict."""
    existing = _existing()
    existing["steps"].append({"step_id": 1, "actor": "X", "label": {"de": "Dup"}, "depends_on": []})
    try:
        merge_process(existing, _extraction())
    except MergeConflict:
        return
    raise AssertionError("MergeConflict bei doppeltem step_id erwartet")


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
