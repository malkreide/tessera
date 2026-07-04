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

from tessera.merge import MergeReport  # noqa: E402
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
    assert "| 1 | Meldefrist | https://www.stadt-zuerich.ch/hund | `innert zehn Tagen nach Uebernahme melden` | ✅ verifiziert |" in body
    # Unverifizierte Reference: kein Zitat (—) + Warnsymbol.
    assert "| 2 | Hundeabgabe | https://www.stadt-zuerich.ch/abgabe | — | ⚠️ unverifiziert |" in body


def test_reference_table_absent_without_refs() -> None:
    process = _process()
    process.pop("references")
    body = build_pr_body(PROC, process, [], META)
    assert "Kernpruefung" not in body


def test_ls_section_lists_all_ls_texts() -> None:
    body = build_pr_body(PROC, _process(), [], META)
    assert "## Leichte Sprache (`ls`)" in body
    assert "- `title`: `Sie melden den Hund an.`" in body
    assert "- `steps[1].label`: `Sie gehen zum Amt.`" in body


def test_ls_section_absent_without_ls() -> None:
    process = _process()
    process["title"].pop("ls")
    process["steps"][0]["label"].pop("ls")
    body = build_pr_body(PROC, process, [], META)
    assert "## Leichte Sprache" not in body


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
