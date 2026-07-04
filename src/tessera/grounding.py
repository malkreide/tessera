"""Grounding-Gate: Belegbarkeit statt Selbsteinschaetzung. Nur stdlib.

Jede Reference und jeder Schritt muss als WOERTLICHE Stelle im gecrawlten
Quelltext belegbar sein. Nicht belegbar heisst:

* Reference  -> status 'unverifiziert', source_quote geleert, Flag fuer den
  Reviewer (UI rendert dann nur Label + Link, keinen Fakt).
* Schritt    -> wird VERWORFEN (nicht geraten); seine Nachfolger erben seine
  Vorgaenger, damit der Graph ein DAG bleibt; Flag fuer den Reviewer.

Zwei zusaetzliche Schaerfen:

* **Per-URL-Grounding (References):** Ist `corpus_by_url` uebergeben, muss das
  Zitat einer Reference auf der Seite ihrer `source_url` stehen — nicht bloss
  irgendwo im Gesamt-Korpus. Der Deep-Link verspricht «die exakte Originalseite»;
  ein Zitat von einer anderen Seite waere ein falsches Versprechen. Schritte und
  Dokumente tragen keine URL und bleiben beim Gesamt-Korpus.
* **Mindest-Spezifitaet:** Zitate unter MIN_QUOTE_CHARS normalisierten Zeichen
  belegen nichts — ein Ein-Wort-Substring-Treffer ist Zufall, kein Beleg. Der
  Extraktions-Prompt verlangt ohnehin den ganzen Satz.

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


# Mindestlaenge eines Zitats nach Normalisierung. Darunter ist ein Substring-
# Treffer kein Beleg («Anmeldung» steht auf jeder Seite). Der Prompt verlangt
# den ganzen Satz; ein legitimes Zitat unterschreitet das praktisch nie.
MIN_QUOTE_CHARS = 25


def _too_unspecific(quote: str) -> bool:
    return len(normalize(quote)) < MIN_QUOTE_CHARS


def _url_key(url: object) -> str:
    """Konservative URL-Normalform fuer den Seiten-Abgleich (nur Whitespace/
    Trailing-Slash — kein Fuzzy-Matching)."""
    return str(url or "").strip().rstrip("/")


def _dep_id(dep) -> int:
    return dep["step_id"] if isinstance(dep, dict) else dep


def apply_gate(
    process: dict,
    step_quotes: dict[int, str],
    corpus: Corpus,
    doc_quotes: dict[tuple[int, int], str] | None = None,
    *,
    corpus_by_url: dict[str, Corpus] | None = None,
) -> tuple[dict, list[str]]:
    """Wendet das Gate auf ein Vertrags-JSON an. Gibt (Prozess, Flags) zurueck.

    `process` wird nicht mutiert; es wird eine bereinigte Kopie gebaut.
    `doc_quotes` (optional) traegt die internen Belegstellen der Dokumente je
    (step_id, Dokument-Index); fehlt es, werden Dokumente nicht gegated.
    `corpus_by_url` (optional) traegt den Korpus je Quell-URL; ist es gesetzt,
    muss das Zitat einer Reference auf der Seite IHRER source_url stehen
    (per-URL-Grounding) — fehlt es, genuegt der Gesamt-Korpus (Altverhalten).
    """
    flags: list[str] = []
    # None = Aufrufer verwaltet Dokument-Grounding nicht -> Dokumente unberuehrt.
    # Dict (auch leer) = gaten; ein Dokument ohne bekanntes Zitat wird verworfen.
    gate_documents = doc_quotes is not None
    doc_quotes = doc_quotes or {}
    # Normalisierte URL -> Seiten-Korpus (None = per-URL-Grounding nicht aktiv).
    pages = (
        {_url_key(u): c for u, c in corpus_by_url.items()}
        if corpus_by_url is not None
        else None
    )

    # --- References: nicht belegbar -> unverifiziert + leeres Zitat ----------
    references = []
    for ref in process.get("references", []):
        ref = dict(ref)
        quote = ref.get("source_quote", "")
        label_de = (ref.get("label") or {}).get("de", "?") if isinstance(ref.get("label"), dict) else "?"
        reason: str | None = None
        if not quote.strip():
            reason = "kein Zitat angegeben"
        elif _too_unspecific(quote):
            reason = (
                f"Zitat zu unspezifisch (unter {MIN_QUOTE_CHARS} normalisierten "
                "Zeichen) — ganzen Satz zitieren"
            )
        elif not corpus.contains(quote):
            reason = "Zitat nicht woertlich im Korpus"
        elif pages is not None:
            # Per-URL-Grounding: der Deep-Link verspricht die exakte Seite.
            page = pages.get(_url_key(ref.get("source_url")))
            if page is None:
                reason = (
                    "source_url gehoert zu keinem gecrawlten Snapshot — "
                    "Deep-Link nicht pruefbar"
                )
            elif not page.contains(quote):
                found_on = [u for u, c in corpus_by_url.items() if c.contains(quote)]
                hint = f"; woertlich gefunden auf: {', '.join(found_on)}" if found_on else ""
                reason = "Zitat steht nicht auf der Seite der angegebenen source_url" + hint
        if reason is None:
            # Verbatim belegt, aber der falsche Werttyp: Default = Abstinenz.
            # Plausibel-aber-falsch (richtige Seite, falscher Wert) ist
            # gefaehrlicher als ein sichtbarer Fehlschlag.
            reason = label_value_mismatch(label_de, quote)
        if reason is None:
            ref["status"] = "verifiziert"
        else:
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
        if quote and not _too_unspecific(quote) and corpus.contains(quote):
            kept.append(dict(step))
        else:
            if not quote.strip():
                reason = "ohne Belegstelle"
            elif _too_unspecific(quote):
                reason = (
                    f"mit zu unspezifischem Zitat (unter {MIN_QUOTE_CHARS} "
                    "normalisierten Zeichen)"
                )
            else:
                reason = "Belegstelle nicht woertlich im Korpus"
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
        # Dokumente: faktische Behauptungen -> wie Schritte/References belegbar.
        # Nicht woertlich belegt -> verwerfen + flaggen (nie raten).
        if gate_documents and step.get("documents"):
            sid = step["step_id"]
            kept_docs: list[dict] = []
            for i, doc in enumerate(step["documents"]):
                quote = doc_quotes.get((sid, i), "")
                if quote and not _too_unspecific(quote) and corpus.contains(quote):
                    kept_docs.append(doc)
                else:
                    label_de = (doc.get("label") or {}).get("de", "?") if isinstance(doc.get("label"), dict) else "?"
                    if not quote.strip():
                        reason = "ohne Belegstelle"
                    elif _too_unspecific(quote):
                        reason = (
                            f"mit zu unspezifischem Zitat (unter {MIN_QUOTE_CHARS} "
                            "normalisierten Zeichen)"
                        )
                    else:
                        reason = "Belegstelle nicht woertlich im Korpus"
                    flags.append(
                        f"Dokument «{label_de}» bei Schritt {sid} {reason} "
                        "-> VERWORFEN (Grounding-Gate)."
                    )
            if kept_docs:
                step["documents"] = kept_docs
            else:
                step.pop("documents")

    out = dict(process)
    out["steps"] = kept
    if references:
        out["references"] = references
    return out, flags
