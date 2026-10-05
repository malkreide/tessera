#!/usr/bin/env python3
"""Tests fuer den PR-Body (Reviewer-UI + Markdown-Neutralisierung) — reine stdlib.

`pr.build_pr_body` ist pur (kein Netz, kein Token); die Modul-Importe von
`tessera.pr` sind stdlib-rein (httpx lazy), damit diese Tests in der
dependency-freien CI laufen.

Aufruf: python tests/test_pr_body.py — Exit 0 = alle Tests gruen.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tessera.grounding import BRIDGE_FLAG_PREFIX  # noqa: E402
from tessera.merge import MergeReport  # noqa: E402
from tessera.plausibility import ACTOR_FLAG_PREFIX, ORDER_FLAG_PREFIX  # noqa: E402
from tessera.pr import (  # noqa: E402
    MAX_BODY_CHARS,
    _md,
    _md_code,
    build_merge_warning,
    build_pr_body,
)

PROC = SimpleNamespace(id="hund-anmelden")
META = [
    {"url": "https://www.stadt-zuerich.ch/hund", "http_status": 200, "extractor": "httpx+trafilatura"},
]


def _process() -> dict:
    return {
        "schema_version": "0.1.0",
        "id": "hund-anmelden",
        "lebenslage_ref": "hund-anmelden",
        "title": {"de": "Hund anmelden", "en": "", "fr": "", "it": "", "ls": "Sie melden den Hund an."},
        "target_audience": "bevoelkerung",
        "steps": [
            {
                "step_id": 1,
                "actor": "Halter:in",
                "label": {"de": "Hund anmelden", "ls": "Sie gehen zum Amt."},
                "depends_on": [],
                "reference_ids": [1],
            },
        ],
        "references": [
            {
                "reference_id": 1,
                "label": {"de": "Meldefrist"},
                "source_url": "https://www.stadt-zuerich.ch/hund",
                "source_quote": "innert zehn Tagen nach Uebernahme melden",
                "status": "verifiziert",
                "retrieved_at": "2026-07-04",
            },
            {
                "reference_id": 2,
                "label": {"de": "Hundeabgabe"},
                "source_url": "https://www.stadt-zuerich.ch/abgabe",
                "source_quote": "",
                "status": "unverifiziert",
                "retrieved_at": "2026-07-04",
            },
        ],
        "source_url": "https://www.stadt-zuerich.ch/hund",
        "retrieved_at": "2026-07-04",
        "disclaimer_key": "Prozesse.disclaimer",
    }


def test_reference_table_rendered() -> None:
    body = build_pr_body(PROC, _process(), [], META)
    assert "| # | Label | Deep-Link | Zitat (woertlich) | Status |" in body
    # Verifizierte Reference: Zitat als Code-Span + Haekchen.
    assert (
        "| 1 | Meldefrist | https://www.stadt-zuerich.ch/hund | `innert zehn Tagen nach Uebernahme melden` | ✅ verifiziert |"
        in body
    )
    # Unverifizierte Reference: kein Zitat (—) + Warnsymbol.
    assert "| 2 | Hundeabgabe | https://www.stadt-zuerich.ch/abgabe | — | ⚠️ unverifiziert |" in body


def test_reference_table_absent_without_refs() -> None:
    process = _process()
    process.pop("references")
    body = build_pr_body(PROC, process, [], META)
    assert "Kernpruefung" not in body


def test_no_ls_review_section() -> None:
    # tessera erzeugt keine Leichte Sprache mehr. Ein `ls` im Body kann nur aus
    # der handgepflegten Zieldatei stammen (Merge) — bereits menschlich
    # geprueft, also kein eigener Review-Abschnitt und kein Checklisten-Punkt.
    body = build_pr_body(PROC, _process(), [], META)
    rendered = body.split("## JSON")[0]
    assert "## Leichte Sprache" not in rendered
    assert "Leichte Sprache (`ls`) ist inhaltlich korrekt" not in rendered


def test_llm_text_is_markdown_neutralized() -> None:
    # Ein boesartiges Label darf weder Mention noch Checklist noch Link ausueben.
    # Geprueft wird der gerenderte Teil VOR dem JSON-Code-Fence (im Fence ist
    # der Rohtext inert: GitHub parst dort weder Mentions noch Markdown).
    process = _process()
    process["title"]["de"] = "Hund [x] anmelden @malkreide | siehe [hier](https://evil.example)"
    flags = ["Reference 1 «@malkreide [klick](https://evil.example)»: Zitat nicht woertlich im Korpus"]
    body = build_pr_body(PROC, process, flags, META)
    rendered = body.split("## JSON")[0]
    assert "@malkreide" not in rendered  # Mention entschaerft (Word-Joiner nach @)
    assert "[x]" not in rendered  # keine gefaelschte Checkbox
    assert "[hier](https://evil.example)" not in rendered  # kein aktiver Link aus LLM-Text
    assert "\\[" in rendered  # Escaping sichtbar


def test_md_code_handles_backticks() -> None:
    assert _md_code("mit `code` drin") == "`` mit `code` drin ``"
    assert _md_code("") == "—"
    assert _md("a  \n b@c") == "a b@\u2060c"


def test_body_limit_drops_json_block() -> None:
    process = _process()
    process["description"] = {"de": "x" * (MAX_BODY_CHARS + 10_000)}
    body = build_pr_body(PROC, process, [], META)
    assert len(body) < 65_536, len(body)
    assert '"schema_version"' not in body  # JSON-Block ersetzt
    assert "PR-Body-Limit" in body
    assert "out/outbox/hund-anmelden/" in body


def test_json_block_included_by_default() -> None:
    body = build_pr_body(PROC, _process(), [], META)
    assert "````json" in body  # 4-Backtick-Fence (Zitate mit ``` sprengen nichts)
    assert '"schema_version": "0.1.0"' in body


def test_bridged_edges_get_own_section_and_checklist() -> None:
    bridge = f"{BRIDGE_FLAG_PREFIX}: Kante 1 -> 3 ueberbrueckt den verworfenen Schritt 2"
    other = "Schritt 2 «Erfunden» ohne Belegstelle -> VERWORFEN (Grounding-Gate)."
    body = build_pr_body(PROC, _process(), [bridge, other], META)
    rendered = body.split("## JSON")[0]
    section = rendered.split("## ❌ Ueberbrueckte Kanten")[1].split("## Grounding-Gate")[0]
    assert _md(bridge) in section  # neutralisiert interpoliert (`>` escaped)
    general = rendered.split("## Grounding-Gate / offene Punkte")[1].split("## Reviewer-Checkliste")[0]
    assert "Kante 1" not in general  # nicht doppelt gelistet
    assert "VERWORFEN" in general
    assert "**Ueberbrueckte Kanten geprueft**" in rendered


def test_no_bridge_section_without_bridges() -> None:
    body = build_pr_body(PROC, _process(), ["Reference 2 «x»: kein Zitat"], META)
    assert "Ueberbrueckte Kanten" not in body
    assert "Reihenfolge-/Akteur-Hinweise geprueft" not in body


def test_plausibility_hints_unlock_checklist_item() -> None:
    for flag in (
        f"{ORDER_FLAG_PREFIX}: Kante 3 -> 1 widerspricht der Textreihenfolge",
        f"{ACTOR_FLAG_PREFIX}: Rolle «Steueramt» kommt im Quelltext nicht vor",
    ):
        body = build_pr_body(PROC, _process(), [flag], META)
        assert "**Reihenfolge-/Akteur-Hinweise geprueft**" in body, flag


def test_high_risk_governance_note_matches_reality() -> None:
    # Ein tessera-PR fuer einen Hochrisiko-Fall ist per Definition automatisch
    # extrahiert; die Warnung darf das Gegenteil nicht behaupten.
    process = _process()
    process["id"] = process["lebenslage_ref"] = "veranstaltung"
    process["disclaimer_key"] = "Prozesse.disclaimerHochrisiko"
    body = build_pr_body(SimpleNamespace(id="veranstaltung"), process, [], META)
    assert "HOCHRISIKO-RECHTSFALL" in body
    assert "**nicht** automatisch" not in body
    assert "**automatisch extrahiert**" in body


def test_merge_warning_renders_suspect_pairs() -> None:
    report = MergeReport()
    report.suspect_pairs.append(
        "steps[2]: bestehend «Registrierung pruefen» vs. Extraktion «Hund entwurmen» (Aehnlichkeit 0.12) — NICHT gemerged, manuell abgleichen"
    )
    warn = build_merge_warning(report, "pfad/x.json")
    assert "verdaechtige(s) ID-Paar(e) — NICHT gemerged" in warn
    assert "Registrierung pruefen" in warn


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
