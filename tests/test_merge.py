#!/usr/bin/env python3
"""Tests fuer den Abgleich gegen handgepflegte Zieldateien (`merge.sync_existing`).

Reine stdlib (CI-faehig ohne Dependencies). Aufruf:
    python tests/test_merge.py — Exit 0 = alle Tests gruen.

Deckt ab:
  (a) die Handdatei bleibt unveraendert bis auf `retrieved_at`; Schritte werden
      nie gemerged oder angehaengt,
  (b) References gleichen ueber (Seite ohne Fragment, normalisiertes Zitat) ab —
      nie ueber reference_id; der Status bleibt, Neues ist nur Vorschlag,
  (c) eine bestaetigte Paarung zeigt die Zuordnung, nur Ungepaartes ist
      Vorschlag; ohne Aenderung meldet der Bericht `changed = False`,
  (d) nicht abgleichbare Faelle werfen MergeConflict (Aufrufer ueberspringt),
  (e) meta.herkunft bleibt beim Abgleich unveraendert; apply_herkunft (nur fuer
      neue Dateien genutzt) traegt die eigene PR-Nummer nach, raet nie.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts"))

from validate_contract import Report, validate  # noqa: E402

from tessera.merge import MergeConflict, apply_herkunft, ref_key, sync_existing  # noqa: E402


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
        "actors": [{"id": "halter", "label": {"de": "Halter:in", "en": "Owner"}, "type": "antragsteller"}],
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


def _mit_herkunft(herkunft: dict | None) -> dict:
    doc = _existing()
    doc["schema_version"] = "0.2.0"
    doc["meta"] = {"erstellt": "2026-06-06", "maintainer": "malkreide"}
    if herkunft is not None:
        doc["meta"]["herkunft"] = herkunft
    return doc


def _without_dates(doc: dict) -> dict:
    out = copy.deepcopy(doc)
    out.pop("retrieved_at", None)
    for r in out.get("references", []):
        r.pop("retrieved_at", None)
    return out


def test_a_hand_file_unchanged_except_retrieved_at() -> None:
    existing, extraction = _existing(), _extraction()
    before = copy.deepcopy(existing)
    out, report = sync_existing(existing, extraction)
    assert existing == before and extraction == _extraction(), "Eingaben duerfen nicht mutiert werden"
    assert _without_dates(out) == _without_dates(existing)
    assert out["retrieved_at"] == "2026-06-14"
    assert out["references"][0]["retrieved_at"] == "2026-06-14"
    assert report.refreshed == ["retrieved_at", "references[1].retrieved_at"], report.refreshed
    assert report.changed


def test_a_steps_never_merged_or_appended() -> None:
    """Gleiche step_id, anderes Label, neuer Schritt 3: nichts davon landet in der
    Datei — alles steht als Vorschlag im Bericht (ohne Paarung: alle Schritte)."""
    out, report = sync_existing(_existing(), _extraction())
    assert out["steps"] == _existing()["steps"]
    assert [p["step_id"] for p in report.step_proposals] == [1, 2, 3]
    p3 = report.step_proposals[2]
    assert p3["label"] == "Veranlagung der Hundeabgabe" and p3["actor"] == "Steueramt"
    assert p3["vorgaenger"] == ["Registrierung pruefen"]  # Kanten als Labels, nicht als IDs
    assert p3["belege"] == ["Hoehe der Hundeabgabe"]


def test_a_result_passes_contract_validator_like_hand_file() -> None:
    out, _ = sync_existing(_existing(), _extraction())
    assert _contract_ok(out).errors == _contract_ok(_existing()).errors


def test_b_reference_matched_by_page_and_quote_not_by_id() -> None:
    """Anderes reference_id, Deep-Link mit Anker, typografische Anfuehrungszeichen:
    dieselbe Stelle auf derselben Seite -> wiedergefunden."""
    existing = _existing()
    existing["references"][0]["source_url"] = "https://www.stadt-zuerich.ch/hund/#frist"
    existing["references"][0]["source_quote"] = "Melden Sie den Hund «innert zehn Tagen» an."
    extraction = _extraction()
    extraction["references"][0]["reference_id"] = 7
    extraction["references"][0]["source_quote"] = 'Melden Sie den Hund "innert zehn Tagen" an.'
    out, report = sync_existing(existing, extraction)
    assert report.refs_confirmed == [(1, "Anmeldefrist")], report.refs_confirmed
    assert out["references"][0]["retrieved_at"] == "2026-06-14"
    assert out["references"][0]["source_url"].endswith("#frist")  # Deep-Link bleibt


def test_b_same_id_other_quote_is_not_a_match() -> None:
    """Gleiche reference_id, anderes Zitat: NICHT wiedergefunden, Datum bleibt."""
    extraction = _extraction()
    extraction["references"][0]["source_quote"] = "Die Hundeabgabe ist jaehrlich zu bezahlen."
    out, report = sync_existing(_existing(), extraction)
    assert report.refs_not_found == [(1, "Anmeldefrist")]
    assert out["references"][0]["retrieved_at"] == "2026-01-01"
    assert len(report.ref_proposals) == 2


def test_b_new_reference_is_proposal_not_appended() -> None:
    out, report = sync_existing(_existing(), _extraction())
    assert [r["reference_id"] for r in out["references"]] == [1]
    assert [r["reference_id"] for r in report.ref_proposals] == [2]


def test_b_status_never_changed() -> None:
    """Wiedergefundenes Zitat einer unverifizierten Reference: Status bleibt,
    der Bericht meldet es (verifizieren tut ein Mensch)."""
    existing = _existing()
    existing["references"][0]["status"] = "unverifiziert"
    out, report = sync_existing(existing, _extraction())
    assert out["references"][0]["status"] == "unverifiziert"
    assert report.refs_confirmed_unverified == [(1, "Anmeldefrist")]


def test_b_reference_without_quote_not_comparable() -> None:
    existing = _existing()
    existing["references"][0]["source_quote"] = ""
    out, report = sync_existing(existing, _extraction())
    assert report.refs_without_quote == [(1, "Anmeldefrist")]
    assert out["references"][0]["retrieved_at"] == "2026-01-01"
    assert ref_key({"source_url": "https://x.ch", "source_quote": "  "}) is None


def test_c_confirmed_pairing_shows_pairs_and_proposes_rest() -> None:
    out, report = sync_existing(
        _existing(), _extraction(), pairing=[([1], [1]), ([2], [2]), ([], [9])], pairing_note="verwendet"
    )
    assert report.step_pairs == [
        ([(1, "Hund online oder am Schalter anmelden")], [(1, "Hund anmelden")]),
        ([(2, "Registrierung pruefen")], [(2, "Registrierung pruefen")]),
    ]
    assert [p["step_id"] for p in report.step_proposals] == [3]
    assert report.pairing_note == "verwendet"
    assert out["steps"] == _existing()["steps"]  # Paarung spielt nichts ein


def test_c_nothing_to_change() -> None:
    """Gleiche Daten wie in der Handdatei: changed False (pr oeffnet keinen PR)."""
    extraction = _extraction()
    extraction["retrieved_at"] = "2026-01-01"
    extraction["references"][0]["retrieved_at"] = "2026-01-01"
    out, report = sync_existing(_existing(), extraction)
    assert out == _existing() and not report.changed and not report.refreshed


def test_d_conflict_on_id_mismatch() -> None:
    """(d) id-Mismatch ist nicht abgleichbar -> MergeConflict."""
    extraction = _extraction()
    extraction["id"] = "umzug-melden"
    for bad in ((_existing(), extraction), ([], _extraction())):
        try:
            sync_existing(*bad)
        except MergeConflict:
            continue
        raise AssertionError(
            f"MergeConflict erwartet: {bad[1].get('id') if isinstance(bad[1], dict) else bad}"
        )


def test_e_sync_keeps_meta_and_herkunft() -> None:
    """(e) Abgleich-PR aendert keine Inhalte -> meta (inkl. herkunft) bleibt."""
    existing = _mit_herkunft({"art": "redaktion"})
    out, _ = sync_existing(existing, _extraction())
    assert out["meta"] == existing["meta"]
    assert out["schema_version"] == "0.2.0"


def test_e_apply_herkunft_redaktion_wird_gemischt() -> None:
    doc = _mit_herkunft({"art": "redaktion"})
    out, note = apply_herkunft(doc, 400, neu=False)
    assert note is None
    assert out["meta"]["herkunft"] == {"art": "gemischt", "tessera_prs": [400]}
    assert out["meta"]["maintainer"] == "malkreide"  # restliches meta bleibt
    assert doc["meta"]["herkunft"] == {"art": "redaktion"}, "Eingabe darf nicht mutiert werden"
    # Das Fixture ist bewusst nicht actor-paritaetisch; geprueft wird hier nur,
    # dass der nachgetragene Herkunfts-Stand die Vertragsregeln erfuellt.
    errs = _contract_ok(out).errors
    assert not any("herkunft" in e for e in errs), errs


def test_e_apply_herkunft_ergaenzt_sortiert_ohne_dublette() -> None:
    doc = _mit_herkunft({"art": "gemischt", "tessera_prs": [169, 164], "geprueft_am": "2026-10-01"})
    out, _ = apply_herkunft(doc, 164, neu=False)
    assert out["meta"]["herkunft"] == {
        "art": "gemischt",
        "tessera_prs": [164, 169],
        "geprueft_am": "2026-10-01",
    }
    out, _ = apply_herkunft(doc, 401, neu=False)
    assert out["meta"]["herkunft"]["tessera_prs"] == [164, 169, 401]
    assert out["meta"]["herkunft"]["geprueft_am"] == "2026-10-01"  # setzt nur ein Mensch


def test_e_apply_herkunft_neu_ist_tessera() -> None:
    doc = _extraction()  # schema_version 0.1.0, kein meta
    out, note = apply_herkunft(doc, 402, neu=True)
    assert note is None
    assert out["meta"] == {"herkunft": {"art": "tessera", "tessera_prs": [402]}}
    assert out["schema_version"] == "0.2.0"  # herkunft verlangt Vertrag >= 0.2.0


def test_e_apply_herkunft_raet_nicht() -> None:
    """Bestehende Datei ohne Herkunft: unveraendert, Hinweis an den Reviewer."""
    doc = _mit_herkunft(None)
    out, note = apply_herkunft(doc, 403, neu=False)
    assert out is doc
    assert note and "nicht geraten" in note and "#403" in note


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
