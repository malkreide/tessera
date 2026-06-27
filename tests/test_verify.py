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
from tessera.verify import Fetched, verify_process  # noqa: E402

LIVE_PAGE = (
    "Sie muessen Ihren Hund innert zehn Tagen melden. "
    "Die jaehrliche Hundeabgabe betraegt CHF 175."
)


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
    fetch = _fetcher({
        "https://example.org/hund": Fetched(state=reach.OK, status=200, text=LIVE_PAGE),
        "https://example.org/abgabe": Fetched(state=reach.OK, status=200, text="Andere Seite ohne das Zitat."),
    })
    rep = verify_process(_process(), fetch=fetch)
    by_id = {d.reference_id: d for d in rep.drifts}
    assert by_id[1].kind == "ok"
    assert by_id[2].kind == "drift"
    assert rep.data_problem  # Drift ist ein Datenproblem


def test_dead_link_is_data_problem() -> None:
    fetch = _fetcher({
        "https://example.org/hund": Fetched(state=reach.DEAD, status=404),
        "https://example.org/abgabe": Fetched(state=reach.OK, status=200, text=LIVE_PAGE),
    })
    rep = verify_process(_process(), fetch=fetch)
    assert any(l.state == reach.DEAD for l in rep.links)
    assert rep.data_problem
    # Ref 1 verweist auf die tote Seite -> Drift 'unerreichbar' (nicht 'drift').
    by_id = {d.reference_id: d for d in rep.drifts}
    assert by_id[1].kind == "unerreichbar"


def test_blocked_is_not_data_problem() -> None:
    # Policy-Block (403) ist ein Umgebungsbefund, KEIN Datenproblem.
    fetch = _fetcher({
        "https://example.org/hund": Fetched(state=reach.BLOCKED, status=403),
        "https://example.org/abgabe": Fetched(state=reach.BLOCKED, status=403),
    })
    rep = verify_process(_process(), fetch=fetch)
    assert any(l.state == reach.BLOCKED for l in rep.links)
    assert not rep.data_problem  # tri-state: Umgebung != Daten


def test_spa_shell_is_ungeprueft_not_drift() -> None:
    # App-Shell ohne Inhalt: Zitat nicht auffindbar, aber als 'ungeprueft'
    # gemeldet (braucht Rendering) — nicht faelschlich als Drift.
    fetch = _fetcher({
        "https://example.org/hund": Fetched(state=reach.OK, status=200, text="", spa=True),
        "https://example.org/abgabe": Fetched(state=reach.OK, status=200, text="", spa=True),
    })
    rep = verify_process(_process(), fetch=fetch)
    kinds = {d.reference_id: d.kind for d in rep.drifts}
    assert kinds[1] == "ungeprueft" and kinds[2] == "ungeprueft"
    assert not rep.data_problem


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
