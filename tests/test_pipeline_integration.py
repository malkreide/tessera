#!/usr/bin/env python3
"""Integrationstest der key-/netzfreien Pipeline-Strecke.

Geprueft wird die Strecke `extract -> to_contract -> grounding.apply_gate ->
validate_contract`, OHNE LLM-Aufruf und OHNE Netz: der LLM-Schritt wird durch
eine fest verdrahtete Extraktions-Antwort ersetzt (so, wie `to_contract` sie aus
einer `XProcess`-Ausgabe baut). Damit faellt genau der gefaehrliche, sonst nur
mit Keys testbare Uebergang unter Test:

  * ein woertlich belegter Schritt bleibt erhalten,
  * ein nicht belegter (erfundener) Schritt wird VERWORFEN und der Graph
    transitiv neu verdrahtet,
  * eine Reference, deren Zitat den falschen Werttyp belegt (Gebuehr-Label,
    aber nur eine Frist im Zitat), wird zur Abstinenz heruntergestuft,
  * eine Reference ohne woertlichen Beleg wird `unverifiziert`,
  * und das gegatete Endergebnis besteht den Vertrags-Validator (Exit-0-Pfad).

Reine stdlib, laeuft in CI ohne Dependencies. Der `to_contract`-Schritt lebt in
`tessera.schema` und braucht pydantic (Runtime-Dep, in CI bewusst nicht
installiert). Der Test deckt die Strecke daher mit einer fest verdrahteten
Vertrags-Fixture ab (immer aktiv); ist pydantic vorhanden, wird zusaetzlich
geprueft, dass `to_contract` aus der aequivalenten `XProcess` genau diese Fixture
erzeugt (sonst sauber uebersprungen, nicht stillschweigend bestanden).

Aufruf: python tests/test_pipeline_integration.py — Exit 0 = alle Tests gruen.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from tessera.grounding import Corpus, apply_gate  # noqa: E402
from validate_contract import Report, validate  # noqa: E402

# to_contract braucht pydantic (Runtime-Dep). Fehlt es (CI ohne Deps), wird der
# Faithfulness-Test sauber uebersprungen — die Strecke selbst testet die Fixture.
try:
    from tessera.schema import (  # noqa: E402
        XProcess,
        XReference,
        XStep,
        XText,
        to_contract,
    )

    HAVE_PYDANTIC = True
except ModuleNotFoundError:  # pragma: no cover - haengt von der Umgebung ab
    HAVE_PYDANTIC = False


class _Skip(Exception):
    """Test bewusst uebersprungen (z.B. fehlende optionale Dependency)."""


PROC_ID = "umzug-melden"
SOURCE_URL = "https://www.stadt-zuerich.ch/de/lebenslagen/einwohner-services/umziehen-melden.html"
RETRIEVED_AT = "2026-06-28"

# Mini-Korpus, wie ihn der Crawl liefern wuerde (SSR-Markdown, ein Snapshot).
CORPUS_TEXT = """
# Umzug innerhalb der Stadt melden

Wer umzieht, meldet die neue Adresse beim Kreisbuero. Die Anmeldung ist online
ueber den eUmzug-Dienst oder am Schalter moeglich. Nach der Meldung bestaetigt
das Kreisbuero die Adressaenderung.

Die Anmeldung muss innert 14 Tagen nach Umzug erfolgen.
"""

# Fest verdrahtete Extraktions-Antwort, bereits auf den Vertrag abgebildet — exakt
# das, was `to_contract` aus der aequivalenten `XProcess` baut (alle References
# starten als 'verifiziert'; das Grounding-Gate stuft danach ggf. herab). Diese
# Fixture treibt die Strecke auch ohne pydantic.
FIXED_PROCESS: dict = {
    "$schema": "../../../schemas/opengov-process-schema.json",
    "schema_version": "0.1.0",
    "id": PROC_ID,
    "lebenslage_ref": PROC_ID,
    "city": "zh",
    "title": {"de": "Umzug melden", "en": "", "fr": "", "it": ""},
    "target_audience": "bevoelkerung",
    "steps": [
        {
            "step_id": 1,
            "actor": "Einwohner:in",
            "label": {"de": "Neue Adresse beim Kreisbuero melden", "en": "", "fr": "", "it": ""},
            "depends_on": [],
            "reference_ids": [1, 2],
        },
        {
            # Erfunden: kein woertlicher Beleg -> muss verworfen werden.
            "step_id": 2,
            "actor": "Kreisbuero",
            "label": {"de": "Antrag intern vorpruefen", "en": "", "fr": "", "it": ""},
            "depends_on": [1],
        },
        {
            "step_id": 3,
            "actor": "Kreisbuero",
            "label": {"de": "Adressaenderung bestaetigen", "en": "", "fr": "", "it": ""},
            "depends_on": [2],
        },
    ],
    "source_url": SOURCE_URL,
    "retrieved_at": RETRIEVED_AT,
    "disclaimer_key": "Prozesse.disclaimer",
    "references": [
        {
            # Sauber belegt, Werttyp (Frist) passt zum Label -> bleibt verifiziert.
            "reference_id": 1,
            "label": {"de": "Meldefrist bei Umzug", "en": "", "fr": "", "it": ""},
            "source_url": SOURCE_URL,
            "source_quote": "innert 14 Tagen nach Umzug",
            "status": "verifiziert",
            "retrieved_at": RETRIEVED_AT,
        },
        {
            # Zitat ist woertlich im Korpus, belegt aber eine Frist statt einer
            # Gebuehr (Label benennt eine Gebuehr) -> Abstinenz.
            "reference_id": 2,
            "label": {"de": "Bearbeitungsgebuehr", "en": "", "fr": "", "it": ""},
            "source_url": SOURCE_URL,
            "source_quote": "innert 14 Tagen nach Umzug",
            "status": "verifiziert",
            "retrieved_at": RETRIEVED_AT,
        },
        {
            # Zitat steht nicht im Korpus -> unverifiziert (verbatim-Pruefung).
            "reference_id": 3,
            "label": {"de": "Gueltigkeit der Bestaetigung", "en": "", "fr": "", "it": ""},
            "source_url": SOURCE_URL,
            "source_quote": "Diese Belegstelle steht nirgends im Korpus.",
            "status": "verifiziert",
            "retrieved_at": RETRIEVED_AT,
        },
    ],
}

# Interne Schritt-Belegstellen (werden nicht publiziert; Input fuers Gate).
FIXED_STEP_QUOTES: dict[int, str] = {
    1: "meldet die neue Adresse beim Kreisbuero",
    2: "",  # erfunden -> kein Beleg
    3: "bestaetigt das Kreisbuero die Adressaenderung",
}


def _gated() -> tuple[dict, list[str]]:
    """Strecke ab to_contract-Ausgabe: Grounding-Gate auf die Fixture anwenden."""
    return apply_gate(FIXED_PROCESS, FIXED_STEP_QUOTES, Corpus(CORPUS_TEXT))


def test_grounded_step_survives() -> None:
    gated, _ = _gated()
    step1 = next(s for s in gated["steps"] if s["step_id"] == 1)
    assert step1["label"]["de"] == "Neue Adresse beim Kreisbuero melden"
    # Beide References bleiben referenziert (auch die herabgestufte existiert noch).
    assert step1["reference_ids"] == [1, 2], step1["reference_ids"]


def test_ungrounded_step_dropped_and_rewired() -> None:
    gated, flags = _gated()
    ids = [s["step_id"] for s in gated["steps"]]
    assert ids == [1, 3], ids  # erfundener Schritt 2 verworfen
    step3 = next(s for s in gated["steps"] if s["step_id"] == 3)
    assert step3["depends_on"] == [1], step3["depends_on"]  # 3 -> 2 -> 1 transitiv
    assert any("Schritt 2" in f and "VERWORFEN" in f for f in flags), flags


def test_label_value_abstinence() -> None:
    gated, flags = _gated()
    ref2 = next(r for r in gated["references"] if r["reference_id"] == 2)
    assert ref2["status"] == "unverifiziert"
    assert ref2["source_quote"] == ""
    assert any("Reference 2" in f and "bindenden Wert" in f for f in flags), flags


def test_unverifiable_reference_downgraded() -> None:
    gated, flags = _gated()
    ref3 = next(r for r in gated["references"] if r["reference_id"] == 3)
    assert ref3["status"] == "unverifiziert"
    assert ref3["source_quote"] == ""
    assert any("Reference 3" in f and "woertlich" in f for f in flags), flags
    # Die sauber belegte Reference bleibt unangetastet.
    ref1 = next(r for r in gated["references"] if r["reference_id"] == 1)
    assert ref1["status"] == "verifiziert"
    assert ref1["source_quote"] == "innert 14 Tagen nach Umzug"


def test_gated_output_passes_contract_validator() -> None:
    gated, _ = _gated()
    rep = Report(Path("synthetic"))
    validate(gated, rep)
    assert rep.ok, rep.errors


def test_to_contract_matches_fixture() -> None:
    """Mit pydantic: `to_contract` aus der aequivalenten XProcess muss exakt die
    Fixture (Prozess + Schritt-Belegstellen) erzeugen. Ohne pydantic uebersprungen."""
    if not HAVE_PYDANTIC:
        raise _Skip("pydantic nicht installiert (CI ohne Runtime-Deps)")

    x = XProcess(
        title=XText(de="Umzug melden"),
        steps=[
            XStep(
                step_id=1,
                actor="Einwohner:in",
                label=XText(de="Neue Adresse beim Kreisbuero melden"),
                depends_on=[],
                reference_ids=[1, 2],
                source_quote="meldet die neue Adresse beim Kreisbuero",
            ),
            XStep(
                step_id=2,
                actor="Kreisbuero",
                label=XText(de="Antrag intern vorpruefen"),
                depends_on=[1],
                source_quote="",
            ),
            XStep(
                step_id=3,
                actor="Kreisbuero",
                label=XText(de="Adressaenderung bestaetigen"),
                depends_on=[2],
                source_quote="bestaetigt das Kreisbuero die Adressaenderung",
            ),
        ],
        references=[
            XReference(
                reference_id=1,
                label=XText(de="Meldefrist bei Umzug"),
                source_url=SOURCE_URL,
                source_quote="innert 14 Tagen nach Umzug",
            ),
            XReference(
                reference_id=2,
                label=XText(de="Bearbeitungsgebuehr"),
                source_url=SOURCE_URL,
                source_quote="innert 14 Tagen nach Umzug",
            ),
            XReference(
                reference_id=3,
                label=XText(de="Gueltigkeit der Bestaetigung"),
                source_url=SOURCE_URL,
                source_quote="Diese Belegstelle steht nirgends im Korpus.",
            ),
        ],
    )
    process, step_quotes = to_contract(
        x,
        proc_id=PROC_ID,
        target_audience="bevoelkerung",
        source_url=SOURCE_URL,
        retrieved_at=RETRIEVED_AT,
    )
    assert process == FIXED_PROCESS, process
    assert step_quotes == FIXED_STEP_QUOTES, step_quotes


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    skipped = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
        except _Skip as exc:
            skipped += 1
            print(f"[SKIP] {t.__name__}: {exc}")
        except AssertionError as exc:
            failed += 1
            print(f"[FAIL] {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed - skipped}/{len(tests)} Tests gruen, {skipped} uebersprungen.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
