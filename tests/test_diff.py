#!/usr/bin/env python3
"""Tests fuer den v2 Aenderungs-Diff (reine stdlib, Fetch injiziert — kein httpx).

Aufruf: python tests/test_diff.py — Exit 0 = alle Tests gruen.

Deckt ab:
  * Fingerprint ist normalisierungs-stabil: rein kosmetische Aenderung -> KEIN
    Treffer; inhaltliche Aenderung -> Treffer.
  * Tri-state: tot = Datenproblem; blockiert/netzfehler = Umgebung (nicht-fatal).
  * Baseline-Abgleich: neu (in sources, nicht in Baseline) / entfernt (umgekehrt).
  * Ohne Baseline: no_baseline (kein Vergleich, kein Fehler).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tessera import diff as diff_mod  # noqa: E402
from tessera import reach  # noqa: E402


class _Proc:
    """Minimaler ProcessSource-Ersatz (nur das, was diff braucht)."""

    def __init__(self, pid: str, urls: list[str]):
        self.id = pid
        self.official_urls = urls


def _fetcher(pages: dict[str, tuple[str, str]]):
    """pages: {url: (markdown, state)}; fehlende URL -> ('', netzfehler)."""
    def fetch(url: str):
        return pages.get(url, ("", reach.NETERROR))
    return fetch


def _with_tmp_fingerprints(fn):
    """Fuehrt fn mit auf ein temporaeres Verzeichnis umgebogenem FINGERPRINTS aus."""
    orig = diff_mod.FINGERPRINTS
    with tempfile.TemporaryDirectory() as d:
        diff_mod.FINGERPRINTS = Path(d)
        try:
            fn()
        finally:
            diff_mod.FINGERPRINTS = orig


URL_A = "https://example.org/a"
URL_B = "https://example.org/b"


def test_fingerprint_roundtrip_and_unchanged() -> None:
    def body() -> None:
        proc = _Proc("svc", [URL_A, URL_B])
        live = {URL_A: ("# A\n\nInhalt A.", reach.OK), URL_B: ("Inhalt B.", reach.OK)}
        entries = diff_mod.build_entries(proc, _fetcher(live), "2026-06-29")
        diff_mod.write_fingerprints("svc", entries, "2026-06-29")
        # Gleiche Seiten -> alles unveraendert.
        rep = diff_mod.diff_process(proc, _fetcher(live))
        assert not rep.data_problem, rep
        assert sorted(rep.unchanged) == sorted([URL_A, URL_B]), rep.unchanged
        assert not rep.changed and not rep.new and not rep.removed
    _with_tmp_fingerprints(body)


def test_cosmetic_change_not_flagged() -> None:
    def body() -> None:
        proc = _Proc("svc", [URL_A])
        base = {URL_A: ("Sie zahlen eine Gebuehr.", reach.OK)}
        diff_mod.write_fingerprints(
            "svc", diff_mod.build_entries(proc, _fetcher(base), "2026-06-29"), "2026-06-29"
        )
        # Nur Whitespace/Markdown/Typografie geaendert -> normalisiert identisch.
        cosmetic = {URL_A: ("**Sie**   zahlen\n\neine   Gebuehr.", reach.OK)}
        rep = diff_mod.diff_process(proc, _fetcher(cosmetic))
        assert rep.unchanged == [URL_A], rep
        assert not rep.changed
    _with_tmp_fingerprints(body)


def test_content_change_flagged() -> None:
    def body() -> None:
        proc = _Proc("svc", [URL_A])
        base = {URL_A: ("Die Frist betraegt 10 Tage.", reach.OK)}
        diff_mod.write_fingerprints(
            "svc", diff_mod.build_entries(proc, _fetcher(base), "2026-06-29"), "2026-06-29"
        )
        changed = {URL_A: ("Die Frist betraegt 30 Tage.", reach.OK)}
        rep = diff_mod.diff_process(proc, _fetcher(changed))
        assert rep.changed == [URL_A], rep
        assert rep.data_problem
    _with_tmp_fingerprints(body)


def test_dead_is_data_problem_block_is_env() -> None:
    def body() -> None:
        proc = _Proc("svc", [URL_A, URL_B])
        base = {URL_A: ("A", reach.OK), URL_B: ("B", reach.OK)}
        diff_mod.write_fingerprints(
            "svc", diff_mod.build_entries(proc, _fetcher(base), "2026-06-29"), "2026-06-29"
        )
        now = {URL_A: ("", reach.DEAD), URL_B: ("", reach.BLOCKED)}
        rep = diff_mod.diff_process(proc, _fetcher(now))
        assert rep.dead == [URL_A], rep.dead
        assert any(URL_B in e for e in rep.env), rep.env
        assert rep.data_problem  # wegen totem Link
    _with_tmp_fingerprints(body)


def test_new_and_removed_urls() -> None:
    def body() -> None:
        # Baseline kennt nur URL_A; sources fuehrt jetzt URL_A + URL_B.
        base_proc = _Proc("svc", [URL_A])
        diff_mod.write_fingerprints(
            "svc",
            diff_mod.build_entries(base_proc, _fetcher({URL_A: ("A", reach.OK)}), "2026-06-29"),
            "2026-06-29",
        )
        now_proc = _Proc("svc", [URL_A, URL_B])
        rep = diff_mod.diff_process(now_proc, _fetcher({URL_A: ("A", reach.OK), URL_B: ("B", reach.OK)}))
        assert rep.new == [URL_B], rep.new
        assert rep.removed == [], rep.removed
        assert rep.unchanged == [URL_A]
        # Umgekehrt: sources entfernt URL_A.
        gone_proc = _Proc("svc", [URL_B])
        rep2 = diff_mod.diff_process(gone_proc, _fetcher({URL_B: ("B", reach.OK)}))
        assert rep2.removed == [URL_A], rep2.removed
    _with_tmp_fingerprints(body)


def test_no_baseline() -> None:
    def body() -> None:
        proc = _Proc("svc-ohne-baseline", [URL_A])
        rep = diff_mod.diff_process(proc, _fetcher({URL_A: ("A", reach.OK)}))
        assert rep.no_baseline and not rep.data_problem
    _with_tmp_fingerprints(body)


def test_unreachable_url_not_frozen_into_baseline() -> None:
    def body() -> None:
        proc = _Proc("svc", [URL_A, URL_B])
        mixed = {URL_A: ("A", reach.OK), URL_B: ("", reach.BLOCKED)}
        entries = diff_mod.build_entries(proc, _fetcher(mixed), "2026-06-29")
        diff_mod.write_fingerprints("svc", entries, "2026-06-29")
        base = diff_mod.load_fingerprints("svc")
        assert URL_A in base and URL_B not in base, base  # Block nicht eingefroren
    _with_tmp_fingerprints(body)


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
