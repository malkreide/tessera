#!/usr/bin/env python3
"""Tests fuer den spezialisierten `veranstaltung`-Extraktor (Registry-Beispiel).

Der Auswahl-Kern und der Hint sind stdlib-rein pruefbar (kein pydantic/LLM/Netz):

  * die Registry waehlt fuer `veranstaltung` den spezialisierten Extraktor, fuer
    alle anderen Leistungen bleibt der generische Fallback (Selbst-Registrierung
    beim Import greift),
  * der Extraktor erfuellt das Protokoll (name/handles/extract),
  * die kuratierte Domaenen-Hilfe benennt die kanonischen Akteure und die
    Reference-Disziplin — und traegt selbst KEINEN bindenden Wert (Kardinalregel-
    Guard: BINDING_VALUE_STRICT darf im Hint nicht anschlagen).

Zusaetzlich, NUR wenn pydantic vorhanden ist (Runtime-Dep, in CI bewusst nicht
installiert): der optionale `domain_hint` in `extract.build_*_prompt` ist
rueckwaertskompatibel — leerer Hint ergibt den byte-identischen Prompt wie zuvor,
ein gesetzter Hint fuegt den abgesetzten Block ein. Ohne pydantic sauber
uebersprungen, nicht stillschweigend bestanden.

Aufruf: python tests/test_extractors_veranstaltung.py — Exit 0 = alle Tests gruen.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tessera import registry  # noqa: E402
from tessera.binding import BINDING_VALUE_STRICT  # noqa: E402
from tessera.extractors.veranstaltung import (  # noqa: E402
    VERANSTALTUNG_HINT,
    VeranstaltungExtractor,
)
from tessera.registry import ProcessExtractor  # noqa: E402

# extract.py importiert schema (pydantic) am Modulkopf — nur mit pydantic ladbar.
try:
    from tessera import extract  # noqa: E402

    HAVE_PYDANTIC = True
except ModuleNotFoundError:  # pragma: no cover - haengt von der Umgebung ab
    HAVE_PYDANTIC = False


class _Skip(Exception):
    """Test bewusst uebersprungen (fehlende optionale Dependency)."""


class _Proc:
    """Minimales proc-Stand-in (Attribute, die die Prompts/Auswahl lesen)."""

    def __init__(self, pid: str, *, service_name: str = "X", notes: str = ""):
        self.id = pid
        self.service_name = service_name
        self.target_audience = "bevoelkerung"
        self.notes = notes


# --- Registry-Auswahl (stdlib) ----------------------------------------------
def test_registry_selects_veranstaltung() -> None:
    assert registry.get_extractor(_Proc("veranstaltung")).name == "veranstaltung"


def test_registry_falls_back_for_others() -> None:
    for pid in ("hund-anmelden", "umzug-melden", "baugesuch", "sozialhilfe"):
        assert registry.get_extractor(_Proc(pid)).name == "generic", pid


def test_extractor_is_registered_builtin() -> None:
    """Der Built-in registriert sich beim Import von `tessera.registry` selbst."""
    assert "veranstaltung" in {e.name for e in registry.registered()}


def test_extractor_satisfies_protocol() -> None:
    ex = VeranstaltungExtractor()
    assert isinstance(ex, ProcessExtractor)
    assert ex.handles(_Proc("veranstaltung")) is True
    assert ex.handles(_Proc("hund-anmelden")) is False


# --- Kuratierte Domaenen-Hilfe (stdlib) -------------------------------------
def test_hint_names_canonical_actors() -> None:
    for actor in ("veranstalter", "stapo-bew", "fachstellen", "statthalter"):
        assert actor in VERANSTALTUNG_HINT, actor


def test_hint_enforces_reference_discipline() -> None:
    low = VERANSTALTUNG_HINT.lower()
    assert "reference" in low
    assert "vorlauffrist" in low  # bindender Wert wird als Reference-Kandidat benannt
    assert "en/fr/it bleiben leer" in low  # struktur-only reingeschrieben


def test_hint_carries_no_binding_value() -> None:
    """Der Hint selbst nennt keinen bindenden Wert (Ziffer/Wort + Einheit, Betrag,
    Datum). Sonst wuerde die Domaenen-Hilfe die Kardinalregel unterlaufen, die sie
    einschaerfen soll."""
    hit = BINDING_VALUE_STRICT.search(VERANSTALTUNG_HINT)
    assert hit is None, f"bindender Wert im Hint: {hit.group(0)!r}"


# --- domain_hint-Threading in den Prompts (nur mit pydantic) ----------------
def test_empty_hint_prompt_is_unchanged() -> None:
    """Rueckwaertskompatibilitaet: ohne Hint (Default) ist der Prompt exakt der
    fruehere — Default-Aufruf == explizit leerer Hint, und der abgesetzte Block
    fehlt vollstaendig."""
    if not HAVE_PYDANTIC:
        raise _Skip("pydantic nicht installiert (CI ohne Runtime-Deps)")
    proc = _Proc("hund-anmelden", service_name="Hund anmelden", notes="—")
    corpus = "<<<QUELLE https://example.test>>>\n# Korpus"
    base = extract.build_extract_prompt(proc, corpus)
    assert base == extract.build_extract_prompt(proc, corpus, "")
    assert base == extract.build_extract_prompt(proc, corpus, "   \n  ")
    assert "KURATIERTE DOMAENEN-HINWEISE" not in base
    # Review-Prompt gleichermassen.
    rbase = extract.build_review_prompt(proc, corpus, "{}")
    assert rbase == extract.build_review_prompt(proc, corpus, "{}", "")
    assert "KURATIERTE DOMAENEN-HINWEISE" not in rbase


def test_hint_is_inserted_when_present() -> None:
    if not HAVE_PYDANTIC:
        raise _Skip("pydantic nicht installiert (CI ohne Runtime-Deps)")
    proc = _Proc("veranstaltung", service_name="Veranstaltung", notes="—")
    corpus = "<<<QUELLE https://example.test>>>\n# Korpus"
    p = extract.build_extract_prompt(proc, corpus, VERANSTALTUNG_HINT)
    assert "KURATIERTE DOMAENEN-HINWEISE" in p
    assert "stapo-bew" in p
    assert p.endswith(corpus)  # Korpus bleibt am Ende
    r = extract.build_review_prompt(proc, corpus, "{}", VERANSTALTUNG_HINT)
    assert "KURATIERTE DOMAENEN-HINWEISE" in r
    assert "stapo-bew" in r


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
