"""Component-Contract: typisierte, VALIDIERTE I/O-Grenzen zwischen Pipeline-Schritten.

Konzeptionell adaptiert vom ODTP-Component-Muster (ETH/EPFL, github.com/odtp-org):
eine Komponente ist EINE Transformation mit explizit typisierter Ein- und Ausgabe,
und die Grenzen zwischen Komponenten werden geprueft. Uebernommen ist NUR die Idee
— KEIN ODTP-Code, keine Orchestrator-Runtime, kein Ontology-/Digital-Twin-Stack,
keine Dependency. Reine stdlib.

Warum ueberhaupt: Die Extraktions-Strecke lief bisher als lineare Prozedur, und nur
die GESAMTausgabe wurde am Ende (im `validate`-/`pr`-Schritt) geprueft. Ein Fehler
in einem Zwischenstand — ein Extraktor, der die Kardinalregel verletzt; ein leerer
Korpus; ein gegateter Prozess, der den Vertrag bricht — fiel erst spaet oder gar
nicht auf. Jede Component validiert daher ihre EINGABE und ihre AUSGABE gegen einen
(Teil-)Vertrag; eine Verletzung stoppt den Schritt HART mit klarer, lokalisierbarer
Meldung (welche Component, welche Seite, welches Feld), statt stillschweigend
fehlerhafte Daten weiterzureichen.

Die Teil-Vertraege (siehe `contracts.py`) leiten sich aus dem kanonischen Validator
ab, nie daneben: der Datenvertrag der Maschinerie bleibt die eine Wahrheitsquelle.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

I = TypeVar("I")
O = TypeVar("O")

# Ein Contract prueft einen Wert und gibt die Liste der GEFUNDENEN Probleme zurueck
# (leere Liste = gueltig). Bewusst simpel: kein Schema-Framework, nur eine Funktion.
# So bleiben Contracts einzeln, dependency-frei testbar (Dict-Fixtures).
Contract = Callable[[object], list[str]]


class ComponentError(Exception):
    """Eine Component-Grenze wurde verletzt (Eingabe- oder Ausgabe-Vertrag).

    Traegt Component-Name, Seite und die konkreten Probleme — der Schritt stoppt
    hart, statt Muell weiterzureichen. Die Meldung ist lokalisierbar: sie nennt,
    WO (Component + Seite) und WAS (Feld/Regel) gebrochen ist.
    """

    def __init__(self, component: str, side: str, problems: list[str]):
        self.component = component
        self.side = side
        self.problems = list(problems)
        joined = "; ".join(self.problems) if self.problems else "(kein Detail)"
        super().__init__(f"[{component}] {side}-Vertrag verletzt: {joined}")


def _accept_all(_value: object) -> list[str]:
    """Leerer Vertrag: akzeptiert alles (fuer Grenzen ohne Vorbedingung)."""
    return []


@dataclass(frozen=True)
class Component(Generic[I, O]):
    """Eine benannte Transformation mit validierter Ein- und Ausgabe.

    * `check_input`  laeuft VOR der Transformation; Verletzung -> ComponentError.
    * `transform`    die eigentliche Transformation (Ein-Ausgabe explizit typisiert).
    * `check_output` laeuft NACH der Transformation; Verletzung -> ComponentError.
    """

    name: str
    transform: Callable[[I], O]
    check_input: Contract = _accept_all
    check_output: Contract = _accept_all

    def run(self, value: I) -> O:
        problems = self.check_input(value)
        if problems:
            raise ComponentError(self.name, "Eingabe", problems)
        result = self.transform(value)
        problems = self.check_output(result)
        if problems:
            raise ComponentError(self.name, "Ausgabe", problems)
        return result


def run_pipeline(components: list[Component], value):
    """Verkettet Components; jede Grenze wird validiert. Die ERSTE Verletzung
    stoppt die Kette hart (ComponentError) — kein stilles Weiterreichen."""
    for component in components:
        value = component.run(value)
    return value
