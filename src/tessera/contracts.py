"""Teil-Vertraege fuer die Component-Grenzen der Extraktions-Strecke. Nur stdlib.

Jede Funktion prueft EINEN Zwischenstand und gibt die Liste der gefundenen
Probleme zurueck (leer = gueltig) — das Format, das `component.Contract` erwartet.
So sind die Grenzen zwischen den Schritten einzeln, dependency-frei testbar
(Dict-Fixtures, kein pydantic, kein LLM, kein Netz).

Die Vertraege leiten sich vom kanonischen Vertrag ab, NIE daneben:

* `no_binding_values` teilt die EINE Kardinalregel-Regex (`binding.BINDING_VALUE`)
  mit dem Vertrags-Validator.
* `grounded_ok` delegiert die Endkontrolle an den kanonischen Validator selbst
  (`scripts/validate_contract.py`) — kein zweites, driftgefaehrdetes Schema.
* `struktur_only` erzwingt genau die Invariante, die der feldweise Merge der
  Maschinerie schuetzt: tessera liefert `de` + LEERE en/fr/it und darf nie eine
  belegte Handuebersetzung ueberschreiben.

Die Teil-Schemas fuer die fruehen Zwischenstaende (Extraktor-Ausgabe, Kern-
Vertrag vor dem Grounding) sind bewusst schlank: sie fangen strukturelle Grob-
fehler und Kardinalregel-Verstoesse frueh, statt die volle Endvalidierung zu
duplizieren.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .binding import BINDING_VALUE

_LOCALES_TRANSLATED = ("en", "fr", "it")


def _i18n_texts(obj: object):
    """Alle gerenderten String-Werte eines i18n-Objekts (de/en/fr/it/ls)."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            if isinstance(val, str):
                yield key, val


def _binding_hits(where: str, i18n: object, problems: list[str]) -> None:
    for loc, text in _i18n_texts(i18n):
        hit = BINDING_VALUE.search(text)
        if hit:
            problems.append(
                f"{where}.{loc}: Kardinalregel verletzt — bindende Zahl "
                f"{hit.group(0)!r} gehoert in eine Reference, nicht in {text!r}"
            )


# --- Grenze 1: Crawl-Korpus -------------------------------------------------
def nonempty_corpus(corpus_text: object) -> list[str]:
    """Der Extraktor braucht belegbaren Text; ein leerer Korpus wuerde nur
    Halluzinationen erlauben. Harter Stopp statt stiller Leerausgabe."""
    if not isinstance(corpus_text, str) or not corpus_text.strip():
        return ["Korpus ist leer — keine brauchbaren Snapshots (zuerst `tessera crawl`)."]
    return []


# --- Grenze 2: Extraktor-Ausgabe (XProcess-Dict) ----------------------------
def xprocess_wellformed(xp: object) -> list[str]:
    """Strukturelle Grobpruefung der Extraktor-Ausgabe, BEVOR sie weiterlaeuft.

    Faengt fruh: fehlender Titel, keine Schritte, doppelte/ungueltige step_ids,
    ein Schritt oder eine Reference ohne Belegstelle (source_quote), und
    Kardinalregel-Verstoesse in Labels/Bedingungen. Das eigentliche Grounding
    (woertlicher Abgleich gegen den Korpus) macht spaeter grounding.apply_gate;
    hier geht es nur um Wohlgeformtheit."""
    problems: list[str] = []
    if not isinstance(xp, dict):
        return ["Extraktor-Ausgabe ist kein Objekt."]

    title = xp.get("title")
    if not isinstance(title, dict) or not isinstance(title.get("de"), str) or not title["de"].strip():
        problems.append("title.de fehlt oder ist leer.")
    _binding_hits("title", title, problems)

    steps = xp.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append("steps: nicht-leere Liste erwartet.")
        steps = []
    seen: set[int] = set()
    for i, step in enumerate(steps):
        where = f"steps[{i}]"
        if not isinstance(step, dict):
            problems.append(f"{where}: Objekt erwartet.")
            continue
        sid = step.get("step_id")
        if not isinstance(sid, int) or isinstance(sid, bool) or sid < 1:
            problems.append(f"{where}.step_id: integer >= 1 erwartet.")
        elif sid in seen:
            problems.append(f"{where}.step_id: {sid} nicht eindeutig.")
        else:
            seen.add(sid)
        if not isinstance(step.get("actor"), str) or not step["actor"].strip():
            problems.append(f"{where}.actor: nicht-leerer String erwartet.")
        _binding_hits(f"{where}.label", step.get("label"), problems)
        # Belegbarkeit: das Grounding-Gate braucht eine Belegstelle; ohne
        # source_quote wuerde der Schritt dort ohnehin verworfen — hier frueh
        # als Wohlgeformtheits-Problem melden.
        sq = step.get("source_quote")
        if not isinstance(sq, str) or not sq.strip():
            problems.append(f"{where}.source_quote: Belegstelle fehlt (nicht belegbarer Schritt).")
        for d in step.get("depends_on", []) or []:
            if isinstance(d, dict):
                _binding_hits(f"{where}.depends_on.condition", d.get("condition"), problems)

    for i, ref in enumerate(xp.get("references", []) or []):
        where = f"references[{i}]"
        if not isinstance(ref, dict):
            problems.append(f"{where}: Objekt erwartet.")
            continue
        _binding_hits(f"{where}.label", ref.get("label"), problems)
        if not isinstance(ref.get("source_url"), str) or not ref["source_url"].strip():
            problems.append(f"{where}.source_url: Deep-Link fehlt.")
    return problems


# --- Grenze 3: Kern-Vertrag (to_contract-Ausgabe, vor dem Grounding) ---------
def struktur_only(process: object) -> list[str]:
    """tessera liefert struktur-only: `de` gefuellt, en/fr/it LEER. Diese
    Invariante schuetzt der feldweise Merge der Maschinerie — eine nicht-leere
    en/fr/it aus der Extraktion wuerde beim Merge eine belegte Handuebersetzung
    verdraengen koennen. Darum hier als harte Grenze: gibt der Extraktions-Pfad
    je eine gefuellte Uebersetzung aus, ist das ein Vertragsbruch (Regression-
    Guard), kein blosser Hinweis."""
    problems: list[str] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            # Ein i18n-Objekt erkennt man am 'de'-Schluessel.
            if isinstance(node.get("de"), str):
                for loc in _LOCALES_TRANSLATED:
                    val = node.get(loc)
                    if isinstance(val, str) and val.strip():
                        problems.append(
                            f"{path}.{loc}: nicht-leere Uebersetzung {val!r} — tessera "
                            "liefert struktur-only (de + leere en/fr/it); der Merge "
                            "der Maschinerie fuellt Uebersetzungen, tessera nie."
                        )
            for key, val in node.items():
                walk(val, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                walk(item, f"{path}[{idx}]")

    walk(process, "")
    return problems


def core_contract(process: object) -> list[str]:
    """Kern-Vertrag der to_contract-Ausgabe VOR dem Grounding: Pflichtfelder da,
    struktur-only eingehalten, keine bindende Zahl in gerenderten Feldern.

    Die vollstaendige Graph-/Referenz-Integritaet prueft erst `grounded_ok` am
    Ende (kanonischer Validator) — hier faengt der Vertrag die groben Brueche,
    bevor das Grounding laeuft."""
    problems: list[str] = []
    if not isinstance(process, dict):
        return ["Kern-Vertrag: Objekt erwartet."]
    for field in ("id", "title", "target_audience", "steps", "source_url", "disclaimer_key"):
        if field not in process:
            problems.append(f"Pflichtfeld fehlt: {field}")
    problems += struktur_only(process)
    problems += no_binding_values(process)
    return problems


def no_binding_values(process: object) -> list[str]:
    """Kardinalregel ueber die gerenderten i18n-Felder des Kern-Vertrags
    (title, preconditions, steps[].label + .depends_on.condition, references[].label)."""
    problems: list[str] = []
    if not isinstance(process, dict):
        return problems
    _binding_hits("title", process.get("title"), problems)
    for i, pc in enumerate(process.get("preconditions", []) or []):
        _binding_hits(f"preconditions[{i}]", pc, problems)
    for i, step in enumerate(process.get("steps", []) or []):
        if not isinstance(step, dict):
            continue
        _binding_hits(f"steps[{i}].label", step.get("label"), problems)
        for j, d in enumerate(step.get("depends_on", []) or []):
            if isinstance(d, dict):
                _binding_hits(f"steps[{i}].depends_on[{j}].condition", d.get("condition"), problems)
    for i, ref in enumerate(process.get("references", []) or []):
        if isinstance(ref, dict):
            _binding_hits(f"references[{i}].label", ref.get("label"), problems)
    return problems


# --- Grenze 4: gegateter End-Vertrag (kanonischer Validator) -----------------
def grounded_ok(process: object) -> list[str]:
    """Endkontrolle: der gegatete Prozess MUSS den kanonischen Vertrags-Validator
    bestehen. Delegiert an `scripts/validate_contract.py` — kein zweites Schema,
    keine Drift. Nur Fehler (nicht Hinweise) sind hier Grenzverletzungen."""
    root = Path(__file__).resolve().parents[2]
    scripts = str(root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from validate_contract import Report, validate  # noqa: PLC0415

    rep = Report(Path("component"))
    validate(process, rep)
    return list(rep.errors)
