"""Injection-Screening: verdaechtige Anweisungs-Muster im Crawl-Korpus flaggen.

Der Korpus ist UNTRUSTED Input ans LLM. Entscheidend: Das Grounding-Gate hilft
gegen Prompt-Injection prinzipiell NICHT — injizierter Text auf einer Quellseite
steht woertlich im Korpus und besteht die Verbatim-Pruefung. Das Gate beweist
Herkunft, nicht Legitimitaet. Die realen Verteidigungen sind das strikte Schema,
die kuratierten offiziellen URLs und der menschliche Review.

Dieses Modul macht die Flanke SICHTBAR: eine kleine, bewusst hochpraezise
Heuristik fuer Anweisungs-Muster («ignore previous instructions», «du bist
jetzt …», «system prompt», …), die auf Behoerdenseiten nichts verloren haben.

Politik: **Flag, kein Gate.** Ein Treffer blockiert nichts und verwirft nichts —
False Positives duerfen keine Daten kosten. Der Befund landet als Flag beim
Reviewer (Flags-Datei + PR-Body) und schaltet dort einen zusaetzlichen
Checklisten-Punkt frei. Reine stdlib.
"""
from __future__ import annotations

import re

# Praefix, an dem PR-Body/Checkliste Injection-Flags erkennen.
FLAG_PREFIX = "INJECTION-VERDACHT"

# Zeichen Kontext um einen Treffer (fuer den Reviewer-Snippet).
SNIPPET_CHARS = 60

# Bewusst enge, hochpraezise Muster (Deutsch + Englisch). Lieber ein
# uebersehener exotischer Trick als Dauerrauschen, das Reviewer abstumpft.
# Legitimer Verwaltungstext («Den Anweisungen der Polizei ist Folge zu
# leisten») trifft KEINES dieser Muster.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore/disregard instructions",
        re.compile(
            # Verb + 1..n Qualifier («all previous», «alle vorherigen») + Nomen.
            r"\b(?:ignor\w*|disregard|vergiss|missachte)\s+"
            r"(?:(?:all\w*|any|previous|prior|the\s+above|alle|s(?:ae|ä)mtliche|"
            r"vorherige\w*|bisherige\w*|obige\w*)\s+)+"
            r"(?:instructions?|rules?|anweisungen|instruktionen|regeln)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "persona override («du bist jetzt» / «you are now»)",
        re.compile(r"\b(?:du bist (?:jetzt|ab jetzt|nun)|you are now)\b", re.IGNORECASE),
    ),
    (
        "system prompt",
        re.compile(r"\bsystem\s*-?\s*prompts?\b", re.IGNORECASE),
    ),
    (
        "output steering («antworte ausschliesslich» / «respond only»)",
        re.compile(
            r"\b(?:antworte|gib)\s+(?:nur|ausschliesslich)\b"
            r"|\brespond\s+only\s+with\b|\boutput\s+only\b",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt injection (Meta-Begriff)",
        re.compile(r"\bprompt[\s-]?injection\b", re.IGNORECASE),
    ),
    (
        "assistant addressing («als KI/Sprachmodell»)",
        re.compile(
            r"\b(?:als|as an?)\s+(?:ki[\s-]?(?:modell|assistent\w*)?|"
            r"sprachmodell|ai\s+(?:model|assistant)|language\s+model)\b",
            re.IGNORECASE,
        ),
    ),
)

_WS = re.compile(r"\s+")


def _snippet(text: str, start: int, end: int) -> str:
    lo = max(0, start - SNIPPET_CHARS)
    hi = min(len(text), end + SNIPPET_CHARS)
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(text) else ""
    return prefix + _WS.sub(" ", text[lo:hi]).strip() + suffix


def screen(text: str) -> list[tuple[str, str]]:
    """Prueft einen Text auf Injection-Muster.

    Rueckgabe: Liste (Muster-Name, Kontext-Snippet) — je Muster hoechstens der
    erste Treffer (ein Flag pro Muster genuegt dem Reviewer; kein Rauschen).
    """
    findings: list[tuple[str, str]] = []
    if not isinstance(text, str) or not text.strip():
        return findings
    for name, pattern in PATTERNS:
        m = pattern.search(text)
        if m:
            findings.append((name, _snippet(text, m.start(), m.end())))
    return findings


def screen_url_texts(url_texts: dict[str, str]) -> list[str]:
    """Screent die Snapshots je URL und formatiert Reviewer-Flags.

    Politik: Flag, kein Gate — die Extraktion laeuft weiter; der Reviewer
    entscheidet. Das Praefix FLAG_PREFIX schaltet im PR-Body den
    Injection-Checklisten-Punkt frei.
    """
    flags: list[str] = []
    for url, text in url_texts.items():
        for name, snippet in screen(text):
            flags.append(
                f"{FLAG_PREFIX} auf {url}: Muster «{name}» — Kontext: "
                f"«{snippet}». Quelle manuell pruefen; Extraktion NICHT blockiert "
                "(Flag, kein Gate)."
            )
    return flags
