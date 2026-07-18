#!/usr/bin/env python3
"""Tests fuer die Extraktor-Registry (Schritt 2). Reine stdlib.

Geprueft wird der Auswahl-Kern (dependency-frei, ohne pydantic/LLM):

  * ohne spezialisierten Extraktor greift der generische Fallback,
  * ein registrierter spezialisierter Extraktor beansprucht seine Leistung
    (erster Treffer gewinnt), fuer alle anderen bleibt der Fallback,
  * ein neuer Extraktor laesst sich hinzufuegen, OHNE bestehende anzufassen,
  * das Protokoll (name/handles/extract) wird erfuellt.

Aufruf: python tests/test_registry.py — Exit 0 = alle Tests gruen.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tessera import registry  # noqa: E402
from tessera.registry import ProcessExtractor, get_extractor, register  # noqa: E402


class _Proc:
    """Minimales proc-Stand-in (nur .id — kein pydantic noetig)."""

    def __init__(self, pid: str):
        self.id = pid


def _isolated():
    """Snapshot/Restore der Registry-Globalliste fuer einen Test."""
    saved = list(registry._EXTRACTORS)
    registry._EXTRACTORS.clear()
    return saved


def _restore(saved) -> None:
    registry._EXTRACTORS.clear()
    registry._EXTRACTORS.extend(saved)


class _Veranstaltung:
    name = "veranstaltung"

    def handles(self, proc) -> bool:
        return proc.id == "veranstaltung"

    def extract(self, proc, corpus: str):  # pragma: no cover - im Test nicht aufgerufen
        return {"marker": self.name}


def test_generic_fallback_when_empty() -> None:
    saved = _isolated()
    try:
        e = get_extractor(_Proc("hund-anmelden"))
        assert e.name == "generic", e.name
    finally:
        _restore(saved)


def test_specialized_wins_for_its_process() -> None:
    saved = _isolated()
    try:
        register(_Veranstaltung)
        assert get_extractor(_Proc("veranstaltung")).name == "veranstaltung"
        # Fuer andere Leistungen bleibt der generische Fallback.
        assert get_extractor(_Proc("hund-anmelden")).name == "generic"
    finally:
        _restore(saved)


def test_first_match_wins() -> None:
    saved = _isolated()
    try:
        class _First:
            name = "first"
            def handles(self, proc) -> bool:
                return True
            def extract(self, proc, corpus: str):  # pragma: no cover
                return {}

        class _Second:
            name = "second"
            def handles(self, proc) -> bool:
                return True
            def extract(self, proc, corpus: str):  # pragma: no cover
                return {}

        register(_First)
        register(_Second)
        assert get_extractor(_Proc("x")).name == "first"
    finally:
        _restore(saved)


def test_add_without_touching_existing() -> None:
    """Ein neuer Extraktor kommt hinzu, ohne dass ein bestehender geaendert wird:
    der bestehende beansprucht unveraendert seine Leistung, der neue seine."""
    saved = _isolated()
    try:
        register(_Veranstaltung)

        class _Baugesuch:
            name = "baugesuch"
            def handles(self, proc) -> bool:
                return proc.id == "baugesuch"
            def extract(self, proc, corpus: str):  # pragma: no cover
                return {}

        register(_Baugesuch)
        assert get_extractor(_Proc("veranstaltung")).name == "veranstaltung"
        assert get_extractor(_Proc("baugesuch")).name == "baugesuch"
        assert get_extractor(_Proc("hund-anmelden")).name == "generic"
    finally:
        _restore(saved)


def test_generic_satisfies_protocol() -> None:
    assert isinstance(registry.GENERIC, ProcessExtractor)
    assert registry.GENERIC.handles(_Proc("irgendwas")) is True


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
