#!/usr/bin/env python3
"""Tests fuer das Preflight-Crawl-Gate (Frische + robots-Sperre) — reine stdlib.

`preflight` haelt seine Modul-Importe stdlib-rein (httpx/openpyxl lazy), damit
genau diese Gate-Logik in der dependency-freien CI testbar ist. Das Gate
verfaellt nach MAX_GATE_AGE_DAYS: robots.txt kann sich aendern, ein altes
«erlaubt» ist keine Freigabe mehr.

Aufruf: python tests/test_preflight_gate.py — Exit 0 = alle Tests gruen.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tessera import preflight  # noqa: E402

PROC = SimpleNamespace(id="hund-anmelden")


def _iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _entry(*, allowed: bool = True, checked_at: object = None, blocked: list | None = None) -> dict:
    entry: dict = {"allowed": allowed, "blocked_urls": blocked or []}
    if checked_at is not None:
        entry["checked_at"] = checked_at
    return entry


def _with_gate(entry: dict | None):
    """Schreibt ein Gate-File in ein Temp-Verzeichnis und patcht GATE_FILE."""
    tmp = Path(tempfile.mkdtemp()) / "preflight-gate.json"
    gate = {} if entry is None else {PROC.id: entry}
    tmp.write_text(json.dumps(gate), encoding="utf-8")
    preflight.GATE_FILE = tmp


def _expect_blocked(substr: str) -> None:
    try:
        preflight.require_allowed(PROC)
    except SystemExit as exc:
        assert substr in str(exc), f"{substr!r} nicht in: {exc}"
    else:
        raise AssertionError(f"SystemExit mit {substr!r} erwartet, Gate liess durch")


def test_fresh_allowed_passes() -> None:
    _with_gate(_entry(checked_at=_iso(0)))
    preflight.require_allowed(PROC)  # darf nicht raisen


def test_max_age_boundary_passes() -> None:
    _with_gate(_entry(checked_at=_iso(preflight.MAX_GATE_AGE_DAYS)))
    preflight.require_allowed(PROC)  # genau an der Grenze: noch frisch


def test_stale_gate_blocks() -> None:
    _with_gate(_entry(checked_at=_iso(preflight.MAX_GATE_AGE_DAYS + 1)))
    _expect_blocked("nicht frisch")


def test_missing_checked_at_blocks() -> None:
    # Alt-Gate ohne checked_at gilt als nicht frisch (kein stilles Durchwinken).
    _with_gate(_entry())
    _expect_blocked("nicht frisch")


def test_invalid_checked_at_blocks() -> None:
    _with_gate(_entry(checked_at="gestern"))
    _expect_blocked("nicht frisch")


def test_future_checked_at_blocks() -> None:
    _with_gate(_entry(checked_at=_iso(-3)))
    _expect_blocked("nicht frisch")


def test_robots_disallow_blocks() -> None:
    # Frisch, aber robots-gesperrt: die Sperre bleibt die Sperre.
    _with_gate(_entry(allowed=False, checked_at=_iso(0), blocked=["https://example.org/x"]))
    _expect_blocked("robots.txt")


def test_missing_entry_blocks() -> None:
    _with_gate(None)
    _expect_blocked("Kein Preflight-Ergebnis")


def test_missing_gate_file_blocks() -> None:
    preflight.GATE_FILE = Path(tempfile.mkdtemp()) / "gibt-es-nicht.json"
    _expect_blocked("Kein Preflight-Ergebnis")


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
