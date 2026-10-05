"""Plausibilitaets-Hinweise fuer das, was das Grounding-Gate NICHT prueft. Nur stdlib.

Das Gate belegt, dass es einen Schritt gibt (woertliches Zitat). Ob die KANTEN
stimmen und ob der AKTEUR in der Quelle vorkommt, prueft es nicht — beides ist
LLM-Behauptung. Dieses Modul macht zwei mechanisch billige Gegenproben:

* **Reihenfolge:** Stehen die Zitate von Vorgaenger und Nachfolger auf derselben
  Seite, und steht der Vorgaenger auf JEDER gemeinsamen Seite hinter dem
  Nachfolger, widerspricht die Kante der Textreihenfolge.
* **Akteur:** Die Rollenbezeichnung (gender-neutral normalisiert wie beim
  Actor-Abgleich im Merge) muss irgendwo im Korpus vorkommen.

Politik: **Flag, kein Gate.** Textreihenfolge ist nicht immer Prozess-
reihenfolge (eine Seite kann mit dem Ergebnis beginnen), und eine Behoerde kann
in der Quelle anders heissen als ihre Kurzrolle. Ein Treffer verwirft darum
nichts; er landet beim Reviewer (Flags-Datei + PR-Body + Checklisten-Punkt).
"""

from __future__ import annotations

import re

from .grounding import Corpus
from .merge import _UMLAUT_MAP, _norm_actor

ORDER_FLAG_PREFIX = "HINWEIS REIHENFOLGE"
ACTOR_FLAG_PREFIX = "HINWEIS AKTEUR"

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _dep_id(dep) -> int:
    return dep["step_id"] if isinstance(dep, dict) else dep


def _label_de(step: dict) -> str:
    label = step.get("label")
    return label.get("de", "?") if isinstance(label, dict) else "?"


def order_flags(process: dict, step_quotes: dict[int, str], pages: dict[str, Corpus]) -> list[str]:
    """Kanten, deren Vorgaenger-Zitat auf JEDER gemeinsamen Seite hinter dem
    Nachfolger-Zitat steht. Kanten ohne gemeinsame Seite sind nicht beurteilbar
    und bleiben still (keine Vermutung)."""
    positions: dict[int, dict[str, int]] = {}
    for step in process.get("steps", []):
        sid = step.get("step_id")
        quote = step_quotes.get(sid, "")
        if not quote:
            continue
        found = {url: pos for url, page in pages.items() if (pos := page.find(quote)) >= 0}
        if found:
            positions[sid] = found

    flags: list[str] = []
    labels = {s.get("step_id"): _label_de(s) for s in process.get("steps", [])}
    for step in process.get("steps", []):
        sid = step.get("step_id")
        for dep in step.get("depends_on", []):
            pid = _dep_id(dep)
            pred, succ = positions.get(pid), positions.get(sid)
            if not pred or not succ:
                continue
            common = sorted(set(pred) & set(succ))
            if common and all(pred[u] > succ[u] for u in common):
                flags.append(
                    f"{ORDER_FLAG_PREFIX}: Kante {pid} -> {sid} («{labels.get(pid, '?')}» vor "
                    f"«{labels.get(sid, '?')}»), aber auf {', '.join(common)} steht das Zitat "
                    "des Vorgaengers HINTER dem des Nachfolgers. Reihenfolge gegen die "
                    "Originalseite pruefen (Flag, kein Gate)."
                )
    return flags


def actor_flags(process: dict, corpus_text: str) -> list[str]:
    """Akteure, deren normalisierte Bezeichnung nirgends im Korpus vorkommt.

    Normalform wie `merge._norm_actor` (Gender-Suffix weg, Umlaute
    transliteriert, nur [a-z0-9]); der Korpus wird gleich verdichtet, sodass
    «Halter:in» auch «Hundehalterinnen» trifft. Bewusst grosszuegig: nur eine
    Rolle, die in KEINER Schreibweise vorkommt, wird gemeldet."""
    haystack = _NON_ALNUM.sub("", corpus_text.lower().translate(_UMLAUT_MAP))
    by_actor: dict[str, list[int]] = {}
    for step in process.get("steps", []):
        actor = step.get("actor")
        if isinstance(actor, str) and actor.strip():
            by_actor.setdefault(actor.strip(), []).append(step.get("step_id"))

    flags: list[str] = []
    for actor, sids in by_actor.items():
        key = _norm_actor(actor)
        if key and key not in haystack:
            flags.append(
                f"{ACTOR_FLAG_PREFIX}: Rolle «{actor}» (Schritt {', '.join(map(str, sids))}) "
                "kommt im Quelltext nicht vor — Bezeichnung gegen die Originalseite "
                "pruefen (Flag, kein Gate)."
            )
    return flags
