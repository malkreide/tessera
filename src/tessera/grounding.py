"""Grounding-Gate: Belegbarkeit statt Selbsteinschaetzung. Nur stdlib.

Jede Reference und jeder Schritt muss als WOERTLICHE Stelle im gecrawlten
Quelltext belegbar sein. Nicht belegbar heisst:

* Reference  -> status 'unverifiziert', source_quote geleert, Flag fuer den
  Reviewer (UI rendert dann nur Label + Link, keinen Fakt).
* Schritt    -> wird VERWORFEN (nicht geraten); seine Nachfolger erben seine
  Vorgaenger, damit der Graph ein DAG bleibt; Flag fuer den Reviewer.

Es gibt bewusst keinen Score und keine Heuristik: ein Zitat ist im Korpus
auffindbar oder nicht. Normalisiert werden nur typografische Artefakte des
HTML->Markdown-Wegs (Anfuehrungszeichen, Whitespace, weiche Trennstriche,
unsichtbare Zero-Width-Zeichen, Ellipsis) — keine inhaltliche Angleichung.
"""
from __future__ import annotations

import re

from .binding import label_value_mismatch

# Typografische Varianten, die Extraktoren austauschbar liefern.
_QUOTE_MAP = str.maketrans({
    "«": '"', "»": '"', "“": '"', "”": '"', "„": '"',
    "’": "'", "‘": "'", "´": "'", "`": "'",
    " ": " ",   # geschuetztes Leerzeichen
    "‑": "-",   # non-breaking hyphen
    "–": "-", "—": "-",
    "…": "...",  # Ellipsis: HTML rendert oft das Einzelzeichen, das LLM kopiert "..."
})
# Unsichtbare Zeichen, die HTML->Markdown einstreut und die ein verbatim kopiertes
# Zitat NICHT enthaelt (oder umgekehrt): Soft-Hyphen, Zero-Width-Space/Joiner,
# Word-Joiner und ZWNBSP/BOM. `\s` faengt diese NICHT — also explizit entfernen,
# sonst faellt ein gueltiger Beleg faelschlich durchs Gate.
_ZERO_WIDTH = re.compile("[­​‌‍⁠﻿]")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")  # [Text](url) -> Text
_URL = re.compile(r"https?://\S+")
# Accessibility-Labels, die Extraktoren in Anker-Texte einbetten (kein Inhalt).
_A11Y_LABEL = re.compile(r"(?:Externer|Interner) Link:\s*", re.IGNORECASE)
_MD_NOISE = re.compile(r"[*_#>|\[\]()]")  # Markdown-Dekor, kein Inhalt
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    text = _MD_LINK.sub(r"\1", text)
    text = _ZERO_WIDTH.sub("", text.translate(_QUOTE_MAP))
    text = _A11Y_LABEL.sub("", text)
    text = _URL.sub(" ", text)
    text = _MD_NOISE.sub(" ", text)
    return _WS.sub(" ", text).strip()


class Corpus:
    """Normalisierter Belegkorpus mit Substring-Suche."""

    def __init__(self, raw: str):
        self._norm = normalize(raw)

    def contains(self, quote: str) -> bool:
        q = normalize(quote)
        return bool(q) and q in self._norm


def _dep_id(dep) -> int:
    return dep["step_id"] if isinstance(dep, dict) else dep


def apply_gate(
    process: dict,
    step_quotes: dict[int, str],
    corpus: Corpus,
) -> tuple[dict, list[str]]:
    """Wendet das Gate auf ein Vertrags-JSON an. Gibt (Prozess, Flags) zurueck.

    `process` wird nicht mutiert; es wird eine bereinigte Kopie gebaut.
    """
    flags: list[str] = []

    # --- References: nicht belegbar -> unverifiziert + leeres Zitat ----------
    references = []
    for ref in process.get("references", []):
        ref = dict(ref)
        quote = ref.get("source_quote", "")
        label_de = (ref.get("label") or {}).get("de", "?") if isinstance(ref.get("label"), dict) else "?"
        mismatch = label_value_mismatch(label_de, quote) if quote else None
        if quote and corpus.contains(quote) and not mismatch:
            ref["status"] = "verifiziert"
        else:
            if not quote.strip():
                reason = "kein Zitat angegeben"
            elif not corpus.contains(quote):
                reason = "Zitat nicht woertlich im Korpus"
            else:
                # Verbatim belegt, aber der falsche Werttyp: Default = Abstinenz.
                # Plausibel-aber-falsch (richtige Seite, falscher Wert) ist
                # gefaehrlicher als ein sichtbarer Fehlschlag.
                reason = mismatch
            flags.append(
                f"Reference {ref.get('reference_id')} «{label_de}»: "
                f"{reason} -> status 'unverifiziert', Zitat verworfen. OFFEN fuer Review."
            )
            ref["status"] = "unverifiziert"
            ref["source_quote"] = ""
        references.append(ref)

    # --- Schritte: nicht belegbar -> verwerfen + Graph neu verdrahten --------
    kept: list[dict] = []
    dropped: dict[int, list] = {}  # step_id -> dessen depends_on (fuer Rewiring)
    for step in process.get("steps", []):
        sid = step["step_id"]
        quote = step_quotes.get(sid, "")
        if quote and corpus.contains(quote):
            kept.append(dict(step))
        else:
            reason = "ohne Belegstelle" if not quote.strip() else "Belegstelle nicht woertlich im Korpus"
            flags.append(
                f"Schritt {sid} «{step.get('label', {}).get('de', '?')}» {reason} "
                "-> VERWORFEN (Grounding-Gate). Nachfolger erben seine Vorgaenger."
            )
            dropped[sid] = list(step.get("depends_on", []))

    # Rewiring: Kanten auf verworfene Schritte durch deren Vorgaenger ersetzen
    # (transitiv, da auch Vorgaenger verworfen sein koennen). Bedingungen an
    # ersetzten Kanten gehen verloren -> zusaetzliches Flag.
    def resolve(dep, seen: frozenset[int]) -> list:
        did = _dep_id(dep)
        if did not in dropped:
            return [dep]
        if did in seen:
            return []
        if isinstance(dep, dict) and dep.get("condition"):
            flags.append(
                f"Bedingung «{dep['condition'].get('de', '?')}» hing an verworfenem "
                f"Schritt {did} und wurde mit ihm verworfen. OFFEN fuer Review."
            )
        out: list = []
        for parent in dropped[did]:
            out.extend(resolve(parent, seen | {did}))
        return out

    ref_ids = {r["reference_id"] for r in references}
    for step in kept:
        new_deps: list = []
        seen_ids: set[int] = set()
        for dep in step.get("depends_on", []):
            for resolved in resolve(dep, frozenset()):
                rid = _dep_id(resolved)
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    new_deps.append(resolved)
        step["depends_on"] = new_deps
        if step.get("reference_ids"):
            valid = [r for r in step["reference_ids"] if r in ref_ids]
            if valid:
                step["reference_ids"] = valid
            else:
                step.pop("reference_ids")

    out = dict(process)
    out["steps"] = kept
    if references:
        out["references"] = references
    return out, flags
