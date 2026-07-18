#!/usr/bin/env python3
"""Tests fuer die Component-Contract-Schicht (Schritt 1). Reine stdlib.

Geprueft wird die Mechanik der validierten Grenzen und die Teil-Vertraege
(`contracts.py`) mit Dict-Fixtures — ohne pydantic, ohne LLM, ohne Netz:

  * eine Component fuehrt Eingabe-Check -> Transform -> Ausgabe-Check aus,
  * eine verletzte Eingabe/Ausgabe stoppt HART (ComponentError, richtige Seite),
  * run_pipeline verkettet und stoppt bei der ersten Verletzung,
  * die Teil-Vertraege fangen: leeren Korpus, fehlende Belegstelle, Kardinalregel-
    Verstoss, gefuellte Uebersetzung (struktur-only / Regression-Guard) und einen
    kanonisch ungueltigen Endstand.

Aufruf: python tests/test_component.py — Exit 0 = alle Tests gruen.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from tessera import contracts  # noqa: E402
from tessera.component import Component, ComponentError, run_pipeline  # noqa: E402


# --- Component-Mechanik ------------------------------------------------------
def test_component_runs_and_validates() -> None:
    c = Component("double", lambda x: x * 2)
    assert c.run(3) == 6


def test_input_violation_hard_stops() -> None:
    c = Component(
        "needs-positive",
        lambda x: x,
        check_input=lambda x: [] if x > 0 else ["muss > 0 sein"],
    )
    try:
        c.run(-1)
    except ComponentError as exc:
        assert exc.component == "needs-positive"
        assert exc.side == "Eingabe"
        assert "muss > 0 sein" in str(exc)
    else:
        raise AssertionError("ComponentError erwartet")


def test_output_violation_hard_stops() -> None:
    c = Component(
        "bad-output",
        lambda x: x,
        check_output=lambda x: ["kaputte Ausgabe"],
    )
    try:
        c.run(1)
    except ComponentError as exc:
        assert exc.side == "Ausgabe"
    else:
        raise AssertionError("ComponentError erwartet")


def test_pipeline_stops_at_first_violation() -> None:
    seen: list[str] = []

    def track(name: str):
        def t(x):
            seen.append(name)
            return x
        return t

    pipe = [
        Component("a", track("a")),
        Component("b", track("b"), check_output=lambda x: ["stop hier"]),
        Component("c", track("c")),  # darf nie laufen
    ]
    try:
        run_pipeline(pipe, 0)
    except ComponentError as exc:
        assert exc.component == "b"
    else:
        raise AssertionError("ComponentError erwartet")
    assert seen == ["a", "b"], seen  # 'c' lief nicht


# --- Teil-Vertraege ----------------------------------------------------------
def test_nonempty_corpus() -> None:
    assert contracts.nonempty_corpus("etwas Text") == []
    assert contracts.nonempty_corpus("") != []
    assert contracts.nonempty_corpus("   ") != []


_GOOD_XPROCESS = {
    "title": {"de": "Hund anmelden"},
    "steps": [
        {
            "step_id": 1,
            "actor": "Halter:in",
            "label": {"de": "Hund online anmelden"},
            "depends_on": [],
            "source_quote": "Sie melden den Hund online oder am Schalter an.",
        }
    ],
    "references": [
        {
            "reference_id": 1,
            "label": {"de": "Meldefrist bei Zuzug"},
            "source_url": "https://example.ch/hund",
            "source_quote": "innert 14 Tagen anmelden",
        }
    ],
}


def test_xprocess_wellformed_accepts_good() -> None:
    assert contracts.xprocess_wellformed(_GOOD_XPROCESS) == []


def test_xprocess_wellformed_missing_quote() -> None:
    bad = {**_GOOD_XPROCESS, "steps": [{**_GOOD_XPROCESS["steps"][0], "source_quote": ""}]}
    problems = contracts.xprocess_wellformed(bad)
    assert any("source_quote" in p for p in problems), problems


def test_xprocess_wellformed_binding_value_in_label() -> None:
    bad = {
        **_GOOD_XPROCESS,
        "steps": [{**_GOOD_XPROCESS["steps"][0], "label": {"de": "Innert 14 Tagen anmelden"}}],
    }
    problems = contracts.xprocess_wellformed(bad)
    assert any("Kardinalregel" in p for p in problems), problems


def test_xprocess_wellformed_duplicate_step_id() -> None:
    s = _GOOD_XPROCESS["steps"][0]
    bad = {**_GOOD_XPROCESS, "steps": [s, {**s, "depends_on": [1]}]}
    problems = contracts.xprocess_wellformed(bad)
    assert any("nicht eindeutig" in p for p in problems), problems


def test_struktur_only_flags_translation() -> None:
    filled = {"title": {"de": "Titel", "en": "Title", "fr": "", "it": ""}}
    problems = contracts.struktur_only(filled)
    assert any(".en" in p for p in problems), problems
    # de + leere en/fr/it ist erlaubt.
    ok = {"title": {"de": "Titel", "en": "", "fr": "", "it": ""}}
    assert contracts.struktur_only(ok) == []


def test_core_contract_missing_field() -> None:
    problems = contracts.core_contract({"title": {"de": "x", "en": "", "fr": "", "it": ""}})
    assert any("Pflichtfeld fehlt" in p for p in problems), problems


def test_grounded_ok_delegates_to_validator() -> None:
    # Ein bekannt gueltiges Beispiel besteht; ein invalid-* Beispiel nicht.
    import json  # noqa: PLC0415

    good = json.loads((ROOT / "examples" / "hund-anmelden.json").read_text(encoding="utf-8"))
    assert contracts.grounded_ok(good) == [], contracts.grounded_ok(good)
    bad = json.loads(
        (ROOT / "examples" / "invalid-binding-value-in-label.json").read_text(encoding="utf-8")
    )
    assert contracts.grounded_ok(bad) != []


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
