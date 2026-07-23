"""Mitgelieferte spezialisierte Extraktoren — Aggregator fuer die Selbst-Registrierung.

Jedes Modul hier registriert seinen Extraktor per Seiteneffekt (`@register`).
`registry` importiert dieses Paket EINMAL am Modulende; dadurch stehen die
Built-ins in `registry._EXTRACTORS`, bevor `get_extractor` sie braucht.

Einen neuen Prozesstyp hinzufuegen — OHNE bestehende Extraktoren anzufassen:
1. ein Modul `tessera/extractors/<typ>.py` mit einem `@register`-ten Extraktor
   anlegen (Protokoll: name/handles/extract; Importe von pydantic/LLM lazy),
2. es hier importieren (eine Zeile).

Die Import-Reihenfolge ist zugleich die Auswahl-Reihenfolge (erster `handles`-
Treffer gewinnt); der generische Extraktor bleibt der Fallback.
"""
from __future__ import annotations

from . import veranstaltung  # noqa: F401 — Seiteneffekt: registriert VeranstaltungExtractor

__all__ = ["veranstaltung"]
