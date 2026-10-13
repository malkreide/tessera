#!/usr/bin/env python3
"""Tests fuer die Modell-Settings der LLM-Extraktion (`extract.model_settings`).

Hintergrund: pydantic-ai schickt an Anthropic ohne Angabe max_tokens=4096. Ein
XProcess mit woertlichen Zitaten ueber mehrere Seiten ist laenger; die API schliesst
die abgeschnittene Tool-Eingabe zu gueltigem, aber unvollstaendigem JSON, und der
Lauf scheitert mit «steps: Field required» (fundsache-Pilot). Geprueft wird:

  * anthropic:-Modelle bekommen DEFAULT_MAX_TOKENS_ANTHROPIC,
  * andere Provider behalten ihren Default (kein max_tokens),
  * TESSERA_MAX_TOKENS ueberschreibt beides; Unsinn bricht klar ab,
  * temperature bleibt bei Modellen ohne Sampling weg.

Dazu der Prompt-Inhalt: `review_notes` (nur fuer Menschen) erreichen den Prompt
nie, und `notes` duerfen die Zieldatei nicht nennen (sonst kopiert das Modell den
Massstab, gegen den `tessera eval` misst — so im Pilot mit den Akteur-IDs).

`extract` importiert schema (pydantic) am Modulkopf; ohne pydantic werden die Tests
sauber uebersprungen, nicht stillschweigend bestanden.

Aufruf: python tests/test_extract_settings.py — Exit 0 = alle Tests gruen.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    from tessera import extract  # noqa: E402

    HAVE_PYDANTIC = True
except ModuleNotFoundError:  # pragma: no cover - haengt von der Umgebung ab
    HAVE_PYDANTIC = False


class _Skip(Exception):
    """Test bewusst uebersprungen (fehlende optionale Dependency)."""


class _Env:
    """Setzt/entfernt TESSERA_MAX_TOKENS fuer die Dauer eines Tests."""

    def __init__(self, value: str | None):
        self.value = value

    def __enter__(self):
        self.old = os.environ.pop("TESSERA_MAX_TOKENS", None)
        if self.value is not None:
            os.environ["TESSERA_MAX_TOKENS"] = self.value

    def __exit__(self, *exc):
        os.environ.pop("TESSERA_MAX_TOKENS", None)
        if self.old is not None:
            os.environ["TESSERA_MAX_TOKENS"] = self.old


def _need_pydantic() -> None:
    if not HAVE_PYDANTIC:
        raise _Skip("pydantic nicht installiert")


def test_anthropic_default_lifts_4096_limit() -> None:
    _need_pydantic()
    with _Env(None):
        s = extract.model_settings(extract.DEFAULT_MODEL)
    assert s.get("max_tokens") == extract.DEFAULT_MAX_TOKENS_ANTHROPIC, s
    assert extract.DEFAULT_MAX_TOKENS_ANTHROPIC > 4096
    assert "temperature" not in s, "Default-Modell akzeptiert kein Sampling"


def test_other_provider_keeps_its_default() -> None:
    _need_pydantic()
    with _Env(None):
        s = extract.model_settings("openai:gemma3:4b")
    assert "max_tokens" not in s, s
    assert s.get("temperature") == extract.TEMPERATURE


def test_env_overrides() -> None:
    _need_pydantic()
    with _Env("64000"):
        assert extract.model_settings(extract.DEFAULT_MODEL)["max_tokens"] == 64000
        assert extract.model_settings("openai:gemma3:4b")["max_tokens"] == 64000


def test_env_rejects_nonsense() -> None:
    _need_pydantic()
    for bad in ("abc", "0", "-5"):
        with _Env(bad):
            try:
                extract.model_settings(extract.DEFAULT_MODEL)
            except SystemExit as exc:
                assert "TESSERA_MAX_TOKENS" in str(exc)
            else:
                raise AssertionError(f"{bad!r} haette abbrechen muessen")


def _proc(**over):
    from tessera.config import ProcessSource  # noqa: PLC0415

    data = {
        "id": "kita-platz",
        "service_name": "Kita",
        "target_audience": "bevoelkerung",
        "official_urls": ["https://www.stadt-zuerich.ch/kita"],
        "notes": "NOTE-MARKER fuer das Modell",
        "review_notes": "REVIEW-MARKER: Zieldatei hat actors[] (eltern, kita)",
    }
    data.update(over)
    return ProcessSource(**data)


def test_review_notes_never_reach_prompt() -> None:
    _need_pydantic()
    proc = _proc()
    for prompt in (
        extract.build_extract_prompt(proc, "<<<QUELLE https://x>>>"),
        extract.build_review_prompt(proc, "<<<QUELLE https://x>>>", "{}"),
    ):
        assert "REVIEW-MARKER" not in prompt and "eltern" not in prompt, prompt
    assert "NOTE-MARKER" in extract.build_extract_prompt(proc, "")


def test_notes_must_not_name_the_target_file() -> None:
    _need_pydantic()
    from pydantic import ValidationError  # noqa: PLC0415

    for leak in (
        "Bestehende Zieldatei hat Akteure",
        "laut Handdatei",
        "actors[] (a, b)",
        "handmodellierte Datei",
    ):
        try:
            _proc(notes=leak)
        except ValidationError as exc:
            assert "review_notes" in str(exc), exc
        else:
            raise AssertionError(f"{leak!r} haette abgelehnt werden muessen")


def test_sources_yaml_keeps_target_out_of_notes() -> None:
    _need_pydantic()
    from tessera.config import load_sources  # noqa: PLC0415

    procs = load_sources().processes  # wirft, falls notes die Zieldatei nennen
    assert any(p.review_notes for p in procs)


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
