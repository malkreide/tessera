#!/usr/bin/env python3
"""Tests fuer die Re-Verifikation (Link-Rot + Drift). Reine stdlib, CI-faehig.

Der HTTP-Fetch wird injiziert (Fake-Fetcher), sodass kein Netz/httpx noetig ist.

Aufruf: python tests/test_verify.py — Exit 0 = alle Tests gruen.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tessera import reach  # noqa: E402
from tessera.grounding import Corpus  # noqa: E402
from tessera.verify import Fetched, restrict_hosts, verify_process  # noqa: E402

LIVE_PAGE = "Sie muessen Ihren Hund innert zehn Tagen melden. Die jaehrliche Hundeabgabe betraegt CHF 175."


def _process() -> dict:
    return {
        "id": "hund-anmelden",
        "source_url": "https://example.org/hund",
        "references": [
            {  # Zitat steht auf der Live-Seite -> ok
                "reference_id": 1,
                "label": {"de": "Meldefrist"},
                "source_url": "https://example.org/hund",
                "source_quote": "innert zehn Tagen melden",
                "status": "verifiziert",
            },
            {  # Zitat steht NICHT mehr auf der Seite -> Drift
                "reference_id": 2,
                "label": {"de": "Hundeabgabe"},
                "source_url": "https://example.org/abgabe",
                "source_quote": "die Abgabe betraegt CHF 200",
                "status": "verifiziert",
            },
            {  # Label benennt Frist, Zitat belegt aber keinen Wert -> Label<->Wert
                "reference_id": 3,
                "label": {"de": "Rekursfrist"},
                "source_url": "https://example.org/hund",
                "source_quote": "Sie muessen Ihren Hund melden",
                "status": "verifiziert",
            },
        ],
    }


def _fetcher(mapping):
    def fetch(url):
        return mapping.get(url, Fetched(state=reach.NETERROR))

    return fetch


def test_offline_label_value_only() -> None:
    rep = verify_process(_process())  # kein fetch -> netzfrei
    assert not rep.online
    assert rep.links == [] and rep.drifts == []
    ids = {f.reference_id for f in rep.label_value}
    assert ids == {3}, ids  # nur Ref 3: Frist-Label, Zitat ohne Dauer


def test_online_drift_and_ok() -> None:
    fetch = _fetcher(
        {
            "https://example.org/hund": Fetched(state=reach.OK, status=200, text=LIVE_PAGE),
            "https://example.org/abgabe": Fetched(
                state=reach.OK, status=200, text="Andere Seite ohne das Zitat."
            ),
        }
    )
    rep = verify_process(_process(), fetch=fetch)
    by_id = {d.reference_id: d for d in rep.drifts}
    assert by_id[1].kind == "ok"
    assert by_id[2].kind == "drift"
    assert rep.data_problem  # Drift ist ein Datenproblem


def test_dead_link_is_data_problem() -> None:
    fetch = _fetcher(
        {
            "https://example.org/hund": Fetched(state=reach.DEAD, status=404),
            "https://example.org/abgabe": Fetched(state=reach.OK, status=200, text=LIVE_PAGE),
        }
    )
    rep = verify_process(_process(), fetch=fetch)
    assert any(link.state == reach.DEAD for link in rep.links)
    assert rep.data_problem
    # Ref 1 verweist auf die tote Seite -> Drift 'unerreichbar' (nicht 'drift').
    by_id = {d.reference_id: d for d in rep.drifts}
    assert by_id[1].kind == "unerreichbar"


def test_blocked_is_not_data_problem() -> None:
    # Policy-Block (403) ist ein Umgebungsbefund, KEIN Datenproblem.
    fetch = _fetcher(
        {
            "https://example.org/hund": Fetched(state=reach.BLOCKED, status=403),
            "https://example.org/abgabe": Fetched(state=reach.BLOCKED, status=403),
        }
    )
    rep = verify_process(_process(), fetch=fetch)
    assert any(link.state == reach.BLOCKED for link in rep.links)
    assert not rep.data_problem  # tri-state: Umgebung != Daten


def test_spa_shell_is_ungeprueft_not_drift() -> None:
    # App-Shell ohne Inhalt: Zitat nicht auffindbar, aber als 'ungeprueft'
    # gemeldet (braucht Rendering) — nicht faelschlich als Drift.
    fetch = _fetcher(
        {
            "https://example.org/hund": Fetched(state=reach.OK, status=200, text="", spa=True),
            "https://example.org/abgabe": Fetched(state=reach.OK, status=200, text="", spa=True),
        }
    )
    rep = verify_process(_process(), fetch=fetch)
    kinds = {d.reference_id: d.kind for d in rep.drifts}
    assert kinds[1] == "ungeprueft" and kinds[2] == "ungeprueft"
    assert not rep.data_problem


def test_extract_text_fallback_decodes_entities() -> None:
    # Ohne trafilatura (CI-Fallback) muss die ToU-Versionszeile trotz HTML-
    # Entities und Tags erkannt werden.
    import builtins  # noqa: PLC0415

    from tessera import verify  # noqa: PLC0415

    raw = "<p>Version 2.2.5; Stand <b>31. M&auml;rz</b>&nbsp;2026</p><script>x()</script>"
    real_import = builtins.__import__

    def no_trafilatura(name, *args, **kwargs):
        if name == "trafilatura":
            raise ImportError("simuliert: nicht installiert")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = no_trafilatura
    try:
        text = verify.extract_text(raw)
    finally:
        builtins.__import__ = real_import
    assert Corpus(text).contains("Version 2.2.5; Stand 31. März 2026"), text
    assert "x()" not in text


def test_restrict_hosts_never_requests_unreleased_domain() -> None:
    calls: list[str] = []

    def fetch(url):
        calls.append(url)
        return Fetched(state=reach.OK, status=200, text=LIVE_PAGE)

    gated = restrict_hosts(fetch, {"example.org"})
    assert gated("https://example.org/hund").state == reach.OK
    assert gated("https://www.fedlex.admin.ch/eli/x").state == reach.GATED
    assert calls == ["https://example.org/hund"], calls  # fremde Domain nie angefragt


def test_gated_reference_domain_is_policy_not_data_problem() -> None:
    process = _process()
    process["references"][1]["source_url"] = "https://www.fedlex.admin.ch/eli/x"
    # Ref 3 driftet in der Fixture unabhaengig vom Gate — hier nur Ref 1 + 2.
    process["references"] = process["references"][:2]
    fetch = restrict_hosts(
        _fetcher({"https://example.org/hund": Fetched(state=reach.OK, status=200, text=LIVE_PAGE)}),
        {"example.org"},
    )
    rep = verify_process(process, fetch=fetch)
    link = next(x for x in rep.links if "fedlex" in x.url)
    assert link.state == reach.GATED and "ToU" in link.detail, link
    drift = next(d for d in rep.drifts if d.reference_id == 2)
    assert drift.kind == "unerreichbar" and "Policy" in drift.detail, drift
    assert not rep.data_problem  # Sperre ist Policy, kein toter Link, keine Drift


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
