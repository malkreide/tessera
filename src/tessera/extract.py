"""LLM-Extraktion: Crawl-Markdown -> striktes XProcess-Schema (struktur-only).

Provider und Modell kommen AUSSCHLIESSLICH aus ENV-Variablen:

* TESSERA_MODEL      pydantic-ai-Modellstring, Default "anthropic:claude-opus-4-8"
* ANTHROPIC_API_KEY  (bzw. der zum Provider passende Key) — wird vom Provider-SDK
                     gelesen; tessera fasst den Key selbst nie an und loggt ihn nie.

Ohne Key bricht der Schritt mit einer klaren Meldung ab — es gibt keinen
stillen Fallback und kein Raten.
"""
from __future__ import annotations

import os

from .config import ProcessSource
from .schema import XProcess

DEFAULT_MODEL = "anthropic:claude-opus-4-8"

_KEY_ENV_BY_PREFIX = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}

INSTRUCTIONS = """\
Du extrahierst die PROZESS-STRUKTUR einer Schweizer Verwaltungsleistung aus
offiziellen Webseiten (als Markdown-Snapshots mitgeliefert). Du gibst NUR
Struktur aus — Akteure, Schritte, Reihenfolge, Abhaengigkeiten — niemals
rechtlich bindende Werte als Fakten.

REGELN (verbindlich):

1. KARDINALREGEL «Link, don't assert»: In Schritt-Labels und Bedingungen darf
   KEINE Zahl mit bindender Einheit stehen (keine Fristen wie «innert 14 Tagen»,
   keine Betraege wie «CHF 175», keine Prozente). Fristen, Gebuehren, Steuern
   und Rekursfristen erscheinen AUSSCHLIESSLICH als references: ein Label OHNE
   die Zahl (z.B. «Meldefrist bei Zuzug»), die exakte Quell-URL der Seite, auf
   der die Angabe steht, und als source_quote das WOERTLICHE Zitat des Satzes.

2. BELEGBARKEIT: Jeder Schritt und jede Reference braucht ein source_quote,
   das ZEICHENGETREU (woertlich, keine Paraphrase) im mitgelieferten Quelltext
   vorkommt. Kopiere die Stelle exakt. Was du nicht woertlich belegen kannst,
   gibst du NICHT aus — lieber weniger Schritte als geratene. Wenn du eine
   Reference fuer wichtig haeltst, aber kein woertliches Zitat findest, lass
   source_quote leer (sie wird dann als unverifiziert geflaggt).

3. GRAPH: step_ids ab 1, eindeutig. depends_on verweist auf Vorgaenger;
   genau die Start-Schritte haben ein leeres depends_on. Der Graph muss ein
   DAG sein (keine Zyklen, kein Selbstbezug). Bedingte Kanten (z.B. Ausgang
   einer Entscheidung) als {step_id, condition}.

4. SPRACHE: Deutsch mit Schweizer Rechtschreibung (kein ß). Feld `ls` =
   Leichte Sprache: kurze Saetze, direkte Anrede («Sie melden den Hund an.»),
   nur fuellen, soweit der Inhalt aus der Quelle belegt ist — sonst leer
   lassen. KEINE Uebersetzungen in andere Sprachen.

5. actor: kurze, konsistente Rollenbezeichnung (z.B. «Halter:in»,
   «Steueramt», «Kreisbuero») — so, wie die Quelle die Stelle nennt.

6. preconditions: nur Voraussetzungen, die die Quelle explizit nennt,
   ebenfalls ohne bindende Zahlen.
"""


def _require_key(model: str) -> None:
    prefix = model.split(":", 1)[0].lower()
    env = _KEY_ENV_BY_PREFIX.get(prefix)
    if env and not os.environ.get(env):
        raise SystemExit(
            f"LLM-Key fehlt: ENV-Variable {env} ist nicht gesetzt (Modell {model!r}).\n"
            "Keys richtet der Maintainer ein (CLAUDE.md, Credentials-Grenze); "
            "tessera liest sie nur aus dem ENV. Abbruch ohne Extraktion."
        )


def extract_process(proc: ProcessSource, corpus: str) -> XProcess:
    model = os.environ.get("TESSERA_MODEL", DEFAULT_MODEL)
    _require_key(model)

    from pydantic_ai import Agent  # noqa: PLC0415 — Import erst nach Key-Check

    agent = Agent(model, output_type=XProcess, instructions=INSTRUCTIONS)
    prompt = (
        f"Leistung: {proc.service_name} (id: {proc.id}, "
        f"target_audience: {proc.target_audience}).\n"
        f"Hinweise aus der kuratierten Liste: {proc.notes or '—'}\n\n"
        "Extrahiere die Prozess-Struktur aus den folgenden Quell-Snapshots. "
        "Jeder Snapshot beginnt mit <<<QUELLE url>>> — verwende fuer jede "
        "Reference die URL des Snapshots, in dem ihr Zitat steht.\n"
        f"{corpus}"
    )
    result = agent.run_sync(prompt)
    return result.output
