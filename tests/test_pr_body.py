#!/usr/bin/env python3
"""Tests fuer den PR-Body (Reviewer-UI + Markdown-Neutralisierung) — reine stdlib.

`pr.build_pr_body` ist pur (kein Netz, kein Token); die Modul-Importe von
`tessera.pr` sind stdlib-rein (httpx lazy), damit diese Tests in der
dependency-freien CI laufen.

Dazu der Folge-Commit fuer meta.herkunft (`_folge_commit_herkunft`) gegen
einen Test-Double-Client: kein Netz, kein httpx.

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
    SOURCE_LABEL,
    _folge_commit_herkunft,
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


def test_review_notes_shown_to_reviewers_neutralised() -> None:
    proc = SimpleNamespace(id="hund-anmelden", review_notes="Zieldatei hat actors[] (halter)\n  <b>x</b>")
    body = build_pr_body(proc, _process(), [], META)
    assert "## Hinweise fuer Reviewer (kuratiert, nicht im Prompt)" in body, body
    assert "Zieldatei hat actors" in body and "<b>" not in body, body
    assert "Hinweise fuer Reviewer" not in build_pr_body(PROC, _process(), [], META)


class _HttpFehler(Exception):
    pass


class _Antwort:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    def raise_for_status(self) -> _Antwort:
        if not self.ok:
            raise _HttpFehler("HTTP 409")
        return self


class _Client:
    """Test-Double: zeichnet put/post auf, scheitert auf Wunsch beim PUT."""

    def __init__(self, put_ok: bool = True) -> None:
        self.put_ok = put_ok
        self.puts: list[tuple[str, dict]] = []
        self.posts: list[tuple[str, dict]] = []

    def put(self, url: str, json: dict) -> _Antwort:
        self.puts.append((url, json))
        return _Antwort(self.put_ok)

    def post(self, url: str, json: dict) -> _Antwort:
        self.posts.append((url, json))
        return _Antwort()


def _folge(client: _Client, process: dict, *, neu: bool = False) -> None:
    _folge_commit_herkunft(
        client,
        "https://api.github.com/repos/o/r",
        PROC,
        "stadt-zuerich-next/data/prozesse/zh/hund-anmelden.json",
        "tessera/hund-anmelden-2026-10-28",
        process,
        412,
        "blob-sha-1",
        "body",
        neu=neu,
        http_error=_HttpFehler,
    )


def _mit_meta(herkunft: dict | None) -> dict:
    p = _process()
    p["schema_version"] = "0.2.0"
    p["disclaimer_key"] = "Prozesse.disclaimer"
    p["meta"] = {"erstellt": "2026-06-06"}
    if herkunft is not None:
        p["meta"]["herkunft"] = herkunft
    return p


def test_folge_commit_setzt_herkunft_und_label() -> None:
    import base64  # noqa: PLC0415
    import json  # noqa: PLC0415

    client = _Client()
    _folge(client, _mit_meta({"art": "redaktion"}))
    assert len(client.puts) == 1, client.puts
    url, put = client.puts[0]
    assert url.endswith("/contents/stadt-zuerich-next/data/prozesse/zh/hund-anmelden.json")
    assert put["sha"] == "blob-sha-1" and put["branch"] == "tessera/hund-anmelden-2026-10-28"
    # Re-Run-Guard in open_draft_pr erkennt nur 'feat(prozesse):'-Commits als eigene.
    assert put["message"].startswith("feat(prozesse):") and "#412" in put["message"]
    doc = json.loads(base64.b64decode(put["content"]).decode())
    assert doc["meta"]["herkunft"] == {"art": "gemischt", "tessera_prs": [412]}
    assert client.posts == [
        ("https://api.github.com/repos/o/r/issues/412/labels", {"labels": [SOURCE_LABEL]})
    ]


def test_folge_commit_raet_nicht_ohne_herkunft() -> None:
    """Bestehende Datei ohne Herkunft: kein Folge-Commit, nur das Label."""
    client = _Client()
    _folge(client, _mit_meta(None))
    assert client.puts == []
    assert len(client.posts) == 1


def test_folge_commit_fehler_bricht_nicht_ab() -> None:
    """Scheitert der PUT, bleibt der PR stehen (best effort); Label trotzdem."""
    client = _Client(put_ok=False)
    _folge(client, _mit_meta({"art": "gemischt", "tessera_prs": [156]}))
    assert len(client.puts) == 1 and len(client.posts) == 1


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
