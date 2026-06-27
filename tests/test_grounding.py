#!/usr/bin/env python3
"""Tests fuer das Grounding-Gate (reine stdlib, CI-faehig ohne Dependencies).

Aufruf: python tests/test_grounding.py — Exit 0 = alle Tests gruen.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from tessera.grounding import Corpus, apply_gate, normalize  # noqa: E402
from validate_contract import Report, validate  # noqa: E402

CORPUS_TEXT = """
# Hundekontrolle

Sie muessen Ihren Hund **innert zehn Tagen** nach Uebernahme bei Ihrer
Wohngemeinde melden. Der*die eingetragene Halter*in muss den Hund ebenfalls
bei AMICUS registrieren. Die Anmeldung ist online oder am Schalter moeglich.
"""


def _process() -> tuple[dict, dict[int, str]]:
    process = {
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
                "label": {"de": "Hund anmelden", "en": "", "fr": "", "it": ""},
                "depends_on": [],
                "reference_ids": [1],
            },
            {
                "step_id": 2,
                "actor": "Amt",
                "label": {"de": "Erfundener Zwischenschritt", "en": "", "fr": "", "it": ""},
                "depends_on": [1],
            },
            {
                "step_id": 3,
                "actor": "Steueramt",
                "label": {"de": "Registrierung pruefen", "en": "", "fr": "", "it": ""},
                "depends_on": [{"step_id": 2, "condition": {"de": "Anmeldung erfasst"}}],
            },
        ],
        "references": [
            {
                "reference_id": 1,
                "label": {"de": "Meldefrist", "en": "", "fr": "", "it": ""},
                "source_url": "https://example.org/hunde",
                "source_quote": "innert zehn Tagen nach Uebernahme bei Ihrer Wohngemeinde melden",
                "status": "verifiziert",
                "retrieved_at": "2026-06-11",
            },
            {
                "reference_id": 2,
                "label": {"de": "Erfundene Gebuehr", "en": "", "fr": "", "it": ""},
                "source_url": "https://example.org/hunde",
                "source_quote": "Dieses Zitat steht nirgends im Korpus.",
                "status": "verifiziert",
                "retrieved_at": "2026-06-11",
            },
        ],
        "source_url": "https://example.org/hunde",
        "retrieved_at": "2026-06-11",
        "disclaimer_key": "Prozesse.disclaimer",
    }
    step_quotes = {
        1: "Die Anmeldung ist online oder am Schalter moeglich.",
        2: "",  # kein Beleg -> muss verworfen werden
        3: "muss den Hund ebenfalls bei AMICUS registrieren",
    }
    return process, step_quotes


def test_normalize_typography() -> None:
    assert normalize("«innert  zehn Tagen»") == normalize('"innert zehn Tagen"')
    assert normalize("**innert zehn Tagen**") == "innert zehn Tagen"
    assert Corpus(CORPUS_TEXT).contains("innert zehn Tagen nach Uebernahme")


def test_normalize_markdown_links() -> None:
    # Linksyntax mitten im Satz darf den woertlichen Abgleich nicht brechen.
    corpus = Corpus(
        "Der Hund muss bei [Externer Link:AMICUS](http://www.amicus.ch) "
        "registriert werden."
    )
    assert corpus.contains("muss bei AMICUS registriert werden")
    # Auch wenn das Zitat die Linksyntax mitkopiert:
    assert corpus.contains("bei [Externer Link:AMICUS](http://www.amicus.ch) registriert")


def test_reference_gate() -> None:
    process, quotes = _process()
    gated, flags = apply_gate(process, quotes, Corpus(CORPUS_TEXT))
    by_id = {r["reference_id"]: r for r in gated["references"]}
    assert by_id[1]["status"] == "verifiziert"
    assert by_id[1]["source_quote"]
    assert by_id[2]["status"] == "unverifiziert"
    assert by_id[2]["source_quote"] == ""
    assert any("Reference 2" in f for f in flags)


def test_step_drop_and_rewire() -> None:
    process, quotes = _process()
    gated, flags = apply_gate(process, quotes, Corpus(CORPUS_TEXT))
    ids = [s["step_id"] for s in gated["steps"]]
    assert ids == [1, 3], ids  # Schritt 2 verworfen
    step3 = gated["steps"][1]
    assert step3["depends_on"] == [1], step3["depends_on"]  # Nachfolger erbt Vorgaenger
    assert any("Schritt 2" in f for f in flags)
    assert any("Bedingung" in f for f in flags)  # Bedingung an verworfener Kante geflaggt


def test_transitive_rewire() -> None:
    process, quotes = _process()
    process["steps"].append(
        {
            "step_id": 4,
            "actor": "Amt",
            "label": {"de": "Auch erfunden", "en": "", "fr": "", "it": ""},
            "depends_on": [2],
        }
    )
    process["steps"].append(
        {
            "step_id": 5,
            "actor": "Halter:in",
            "label": {"de": "Bestaetigung erhalten", "en": "", "fr": "", "it": ""},
            "depends_on": [4],
        }
    )
    quotes[4] = ""  # ebenfalls verworfen
    quotes[5] = "online oder am Schalter"
    gated, _ = apply_gate(process, quotes, Corpus(CORPUS_TEXT))
    step5 = next(s for s in gated["steps"] if s["step_id"] == 5)
    assert step5["depends_on"] == [1], step5["depends_on"]  # 4 -> 2 -> 1 transitiv


def test_label_value_abstinence() -> None:
    # Zitat ist WOERTLICH im Korpus, aber das Label benennt eine Gebuehr, das
    # Zitat belegt nur eine Frist -> Default = Abstinenz (downgrade, Flag).
    process, quotes = _process()
    process["references"].append(
        {
            "reference_id": 3,
            "label": {"de": "Hundeabgabe", "en": "", "fr": "", "it": ""},
            "source_url": "https://example.org/hunde",
            "source_quote": "innert zehn Tagen nach Uebernahme",  # verbatim, aber Frist
            "status": "verifiziert",
            "retrieved_at": "2026-06-11",
        }
    )
    gated, flags = apply_gate(process, quotes, Corpus(CORPUS_TEXT))
    ref3 = next(r for r in gated["references"] if r["reference_id"] == 3)
    assert ref3["status"] == "unverifiziert"
    assert ref3["source_quote"] == ""
    assert any("Reference 3" in f and "bindenden Wert" in f for f in flags), flags


def test_strict_label_value_promotes_hint_to_error() -> None:
    # Eine verifizierte Reference mit verbatim-Zitat, dessen Wert nicht zum Label
    # passt (Gebuehr-Label, aber nur eine Frist im Zitat). Standard = Hinweis
    # (gueltig); strenger Modus = Fehler.
    process, _ = _process()
    process["references"] = [
        {
            "reference_id": 1,
            "label": {"de": "Bearbeitungsgebuehr", "en": "", "fr": "", "it": ""},
            "source_url": "https://example.org/hunde",
            "source_quote": "innert 30 Tagen zu bezahlen",  # Frist, keine Gebuehr
            "status": "verifiziert",
            "retrieved_at": "2026-06-11",
        }
    ]
    # Die erfundenen Schritte/Bedingungen wuerden sonst Cross-Refs brechen; nur
    # die belegten Schritte behalten.
    process["steps"] = [process["steps"][0]]
    process["steps"][0].pop("reference_ids", None)

    lax = Report(Path("synthetic"))
    validate(process, lax)
    assert lax.ok, lax.errors  # Standard: nur ein Hinweis
    assert any("Label<->Wert" in w for w in lax.warnings), lax.warnings

    strict = Report(Path("synthetic"))
    validate(process, strict, strict_label_value=True)
    assert not strict.ok  # strenger Modus: Fehler
    assert any("Label<->Wert" in e for e in strict.errors), strict.errors


def test_gated_output_passes_contract_validator() -> None:
    process, quotes = _process()
    gated, _ = apply_gate(process, quotes, Corpus(CORPUS_TEXT))
    rep = Report(Path("synthetic"))
    validate(gated, rep)
    assert rep.ok, rep.errors


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
