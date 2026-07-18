"""Leichte Zoo-artige Registry fuer Prozess-Extraktoren.

Konzeptionell adaptiert vom ODTP-Gedanken austauschbarer Komponenten — ein
Extraktor ist eine einzeln testbare, ERSETZBARE Einheit statt eines Astes in
einer monolithischen Funktion. KEIN ODTP-Code, keine Runtime, keine Dependency.

Auswahl OHNE Config-Feld: welcher Extraktor eine Leistung bearbeitet, leitet die
Registry aus der Leistung selbst ab (`handles(proc)` — z.B. `risk.is_high_risk`
oder eine id/Muster-Bedingung). Der generische Zwei-Pass-LLM-Extraktor ist der
Fallback; er greift, solange kein spezialisierter Extraktor die Leistung
beansprucht.

Einen neuen Prozesstyp hinzufuegen, OHNE bestehende Extraktoren anzufassen:

    from .registry import register, ProcessExtractor

    @register
    class VeranstaltungExtractor:
        name = "veranstaltung"
        def handles(self, proc) -> bool:
            return proc.id == "veranstaltung"
        def extract(self, proc, corpus: str):
            ...  # eigenes Prompt-/Schema-Vorgehen, gibt ein XProcess zurueck

Vertrag an jeden Extraktor (durch die Component-Grenzen aus contracts.py
erzwungen, nicht hier dupliziert): die Ausgabe ist **struktur-only** — jedes
i18n-Feld traegt `de` und LEERE en/fr/it. So kann die Extraktion beim feldweisen
Merge der Maschinerie nie eine belegte Handuebersetzung oder `description`
verdraengen (Regression-Guard). Uebersetzungen fuellt allein die Maschinerie.

Reiner Auswahl-Kern (stdlib, dependency-frei testbar): `handles`/`get_extractor`
rufen kein pydantic; der LLM-Aufruf im generischen Extraktor ist lazy.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ProcessExtractor(Protocol):
    """Eine austauschbare Extraktions-Einheit.

    * `name`     stabiler Bezeichner (Logs/Tests).
    * `handles`  beansprucht diese Leistung? (rein, ohne LLM/Netz).
    * `extract`  Korpus -> XProcess (struktur-only; siehe Modul-Docstring).
    """

    name: str

    def handles(self, proc) -> bool: ...

    def extract(self, proc, corpus: str): ...


# Spezialisierte Extraktoren in Registrierungsreihenfolge (erster Treffer gewinnt).
_EXTRACTORS: list[ProcessExtractor] = []


def register(extractor):
    """Registriert einen spezialisierten Extraktor (Instanz oder Klasse).

    Als Klassen-Dekorator verwendbar: die Klasse wird instanziiert und die
    INSTANZ registriert (die Klasse bleibt der Rueckgabewert, damit der Name im
    Modul die Klasse bezeichnet)."""
    instance = extractor() if isinstance(extractor, type) else extractor
    _EXTRACTORS.append(instance)
    return extractor


def registered() -> list[ProcessExtractor]:
    """Aktuell registrierte spezialisierte Extraktoren (ohne den Fallback)."""
    return list(_EXTRACTORS)


class GenericExtractor:
    """Fallback: der bisherige generische Zwei-Pass-LLM-Extraktor (extract.py).

    Beansprucht jede Leistung (Fallback). Der LLM-Aufruf ist lazy — die Registry
    bleibt ohne pydantic/Key importier- und auswaehlbar."""

    name = "generic"

    def handles(self, proc) -> bool:  # noqa: ARG002 — Fallback greift immer
        return True

    def extract(self, proc, corpus: str):
        from . import extract  # noqa: PLC0415 — pydantic erst hier

        return extract.extract_process(proc, corpus)


GENERIC = GenericExtractor()


def get_extractor(proc) -> ProcessExtractor:
    """Waehlt den Extraktor fuer eine Leistung: der erste spezialisierte, dessen
    `handles(proc)` True ist, sonst der generische Fallback."""
    for extractor in _EXTRACTORS:
        if extractor.handles(proc):
            return extractor
    return GENERIC
