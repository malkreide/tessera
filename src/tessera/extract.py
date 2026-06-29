"""LLM-Extraktion: Crawl-Markdown -> striktes XProcess-Schema (struktur-only).

Provider und Modell kommen AUSSCHLIESSLICH aus ENV-Variablen:

* TESSERA_MODEL      pydantic-ai-Modellstring, Default "anthropic:claude-opus-4-8"
* ANTHROPIC_API_KEY  (bzw. der zum Provider passende Key) — wird vom Provider-SDK
                     gelesen; tessera fasst den Key selbst nie an und loggt ihn nie.
* TESSERA_REVIEW     "0"/"false"/"no"/"off" deaktiviert den Review-Pass (Default: an).

Ohne Key bricht der Schritt mit einer klaren Meldung ab — es gibt keinen
stillen Fallback und kein Raten.

GENAUIGKEIT: Die Extraktion laeuft in zwei Schritten — ein Entwurf und ein
Review-/Repair-Pass, der den Entwurf gegen DENSELBEN Korpus prueft: belegbare
fehlende Schritte ergaenzen, falsche Kanten korrigieren, Geratenes streichen.
Der Review erfindet keine Belege — das nachgelagerte Grounding-Gate
(grounding.py) verwirft danach ohnehin jedes nicht woertlich belegte Element.
Der Review hebt also den Recall, ohne das Halluzinationsrisiko zu erhoehen.

SAMPLING: Wo der Provider es akzeptiert, laeuft die Extraktion mit temperature=0
(reproduzierbarere Laeufe/Diffs). Aktuelle Anthropic-Modelle (Opus 4.7/4.8,
Fable, Mythos) akzeptieren KEINE Sampling-Parameter mehr — ein gesetztes
temperature wird dort verworfen (Warnung bzw. 400). Fuer diese Modelle lassen wir
den Parameter bewusst weg (siehe `_supports_sampling`); Reproduzierbarkeit laeuft
dort ueber Prompt und `effort`, nicht ueber Sampling. temperature=0 hat ohnehin
nie bit-identische Outputs garantiert.
"""
from __future__ import annotations

import os

from .config import ProcessSource
from .schema import XProcess

DEFAULT_MODEL = "anthropic:claude-opus-4-8"
# Deterministisch, wo akzeptiert: gleiche Quelle -> moeglichst gleiches Ergebnis.
TEMPERATURE = 0.0
_REVIEW_OFF = {"0", "false", "no", "off"}

# Anthropic-Modelle, die Sampling-Parameter (temperature/top_p/top_k) nicht mehr
# akzeptieren. Ein gesetztes temperature wird dort verworfen (Warnung bzw. 400),
# der gemeinte Determinismus verpufft also. Substring-Match auf den Modellnamen,
# damit kuenftige Datums-/Alias-Varianten mitgreifen.
_NO_SAMPLING_MODELS = (
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-fable",
    "claude-mythos",
)

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
   «Steueramt», «Kreisbuero») — so, wie die Quelle die Stelle nennt. Verwende
   fuer DENSELBEN Akteur durchgehend DIESELBE Bezeichnung (das macht spaeter
   Akteurswechsel/Medienbrueche im Graphen auswertbar).

6. preconditions: nur Voraussetzungen, die die Quelle explizit nennt,
   ebenfalls ohne bindende Zahlen. Fuelle sie, wo die Quelle sie belegt — leer
   lassen, wenn nichts dasteht.

7. type (optional, je Schritt): strukturelle Einordnung, NUR wenn eindeutig —
   eines von start | input (Eingabe/Antrag durch Buerger:in) | prozess
   (behoerdliche Bearbeitung) | entscheidung | loop | warten | ende. Im Zweifel
   weglassen (None), nicht raten.

8. documents (optional, je Schritt): Unterlagen, die der Schritt verlangt. Jedes
   Dokument braucht ein source_quote, das ZEICHENGETREU im Quelltext vorkommt
   (gleiche Regel wie fuer Schritte); ohne woertlichen Beleg KEIN Dokument
   ausgeben. `required` nur setzen, wenn die Quelle zwingend/optional klar sagt.
   Dokument-Labels tragen keine bindenden Zahlen.
"""

REVIEW_INSTRUCTIONS = """\
Du bist Reviewer:in einer bereits erstellten Extraktion derselben Schweizer
Verwaltungsleistung. Du erhaeltst die Quell-Snapshots (Markdown) UND einen
Extraktions-Entwurf (JSON). Deine Aufgabe ist NICHT, neu zu raten, sondern den
Entwurf gegen die Quelle zu pruefen und eine KORRIGIERTE, VOLLSTAENDIGE Fassung
im selben Schema auszugeben.

Pruefe und korrigiere:

1. VOLLSTAENDIGKEIT (Recall): Fehlt ein Schritt, den die Quelle WOERTLICH belegt
   (z.B. eine Online-Anmeldung, eine behoerdliche Veranlagung, ein Schalter-Gang)?
   Ergaenze ihn mit korrektem source_quote. Ergaenze NICHTS, was du nicht
   woertlich belegen kannst.

2. GRAPH-KORREKTHEIT: Stimmen depends_on-Kanten mit der in der Quelle
   beschriebenen Reihenfolge ueberein? Korrigiere falsche/fehlende Abhaengigkeiten.
   Der Graph bleibt ein DAG (keine Zyklen/Selbstbezug); genau die Start-Schritte
   haben leeres depends_on.

3. BELEGE: Jeder behaltene/ergaenzte Schritt und jede Reference traegt ein
   source_quote, das ZEICHENGETREU im mitgelieferten Quelltext vorkommt. Streiche
   Elemente, deren Beleg du nicht woertlich findest.

4. KARDINALREGEL: weiterhin KEINE bindende Zahl (Frist/Betrag/Prozent) in Labels
   oder Bedingungen — solche Werte nur als references (Label OHNE Zahl + URL +
   woertliches Zitat).

5. ZUSATZFELDER: Ergaenze fehlende, belegbare `documents` (mit woertlichem
   source_quote) und setze `type` je Schritt, wo eindeutig — beides nur belegt
   bzw. eindeutig, sonst weglassen. `preconditions`/`ls` fuellen, soweit belegt.

Behalte step_ids stabiler Schritte moeglichst bei. Sprache: Deutsch, Schweizer
Rechtschreibung (kein ß). Gib NUR das korrigierte XProcess aus.
"""


def build_extract_prompt(proc: ProcessSource, corpus: str) -> str:
    """Entwurfs-Prompt (rein, ohne LLM-Aufruf — testbar)."""
    return (
        f"Leistung: {proc.service_name} (id: {proc.id}, "
        f"target_audience: {proc.target_audience}).\n"
        f"Hinweise aus der kuratierten Liste: {proc.notes or '—'}\n\n"
        "Extrahiere die Prozess-Struktur aus den folgenden Quell-Snapshots. "
        "Jeder Snapshot beginnt mit <<<QUELLE url>>> — verwende fuer jede "
        "Reference die URL des Snapshots, in dem ihr Zitat steht.\n"
        f"{corpus}"
    )


def build_review_prompt(proc: ProcessSource, corpus: str, draft_json: str) -> str:
    """Review-Prompt (rein, ohne LLM-Aufruf — testbar). Traegt Entwurf + Korpus."""
    return (
        f"Leistung: {proc.service_name} (id: {proc.id}, "
        f"target_audience: {proc.target_audience}).\n\n"
        "ENTWURF (zu pruefen und zu korrigieren):\n"
        f"{draft_json}\n\n"
        "QUELL-SNAPSHOTS (einzige Belegquelle; jeder beginnt mit <<<QUELLE url>>>):\n"
        f"{corpus}"
    )


def _review_enabled() -> bool:
    return os.environ.get("TESSERA_REVIEW", "1").strip().lower() not in _REVIEW_OFF


def _supports_sampling(model: str) -> bool:
    """True, wenn das Modell Sampling-Parameter (temperature) akzeptiert.

    Bei aktuellen Anthropic-Modellen (Opus 4.7/4.8, Fable, Mythos) wuerde ein
    gesetztes temperature verworfen — dort geben wir keine ModelSettings mit.
    """
    name = model.split(":", 1)[-1].lower()
    return not any(marker in name for marker in _NO_SAMPLING_MODELS)


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
    from pydantic_ai.settings import ModelSettings  # noqa: PLC0415

    # temperature nur setzen, wo der Provider es akzeptiert (siehe Docstring).
    settings = ModelSettings(temperature=TEMPERATURE) if _supports_sampling(model) else None

    draft = Agent(
        model, output_type=XProcess, instructions=INSTRUCTIONS, model_settings=settings
    ).run_sync(build_extract_prompt(proc, corpus)).output

    if not _review_enabled():
        return draft

    # Review-/Repair-Pass: Entwurf gegen denselben Korpus pruefen. Das
    # Grounding-Gate filtert danach ohnehin jedes nicht belegte Element.
    reviewed = Agent(
        model, output_type=XProcess, instructions=REVIEW_INSTRUCTIONS, model_settings=settings
    ).run_sync(
        build_review_prompt(proc, corpus, draft.model_dump_json(indent=2))
    ).output
    return reviewed
