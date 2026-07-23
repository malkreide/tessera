"""Spezialisierter Extraktor fuer die Hochrisiko-Leistung `veranstaltung`.

Beispiel dafuer, dass die Zoo-artige Registry (Schritt 2) traegt: ein neuer,
einzeln testbarer Extraktor kommt hinzu, OHNE bestehende anzufassen und ohne die
Strecke (`steps.py`) zu aendern. Er beansprucht ueber `handles(proc)` genau die
Leistung `veranstaltung` (der erste Hochrisiko-Fall, der in `sources.yaml` fuer
die automatische Extraktion freigeschaltet ist) und faellt fuer alle anderen
Leistungen NICHT ein — dort bleibt der generische Zwei-Pass-Extraktor.

Was er anders macht: Er reicht dem bestehenden LLM-Pfad (`extract.extract_process`)
eine kuratierte DOMAENEN-HILFE mit — die kanonischen Akteure der handmodellierten
Zieldatei, die typische Struktur (Gesuch -> Pruefung -> Fachstellen ->
Auflagen/Teilbewilligungen -> Entscheid, Rekurs als bedingter Zweig) und eine
verscharfte Kardinalregel-Erinnerung. Der Hint aendert NUR die Instruktion; er
kann keine unbelegte Ausgabe erzwingen: Belegbarkeit, Grounding-Gate,
Kardinalregel und der Hochrisiko-Validator laufen unveraendert nachgelagert
(zentral, nicht hier dupliziert). Der sichtbare Hochrisiko-Disclaimer wird
ebenfalls zentral gesetzt (`schema.to_contract` anhand `risk.HIGH_RISK_IDS`),
nicht vom Extraktor.

Struktur-only bleibt Pflicht (wie fuer jeden Extraktor, durch die Component-
Grenzen erzwungen): jedes i18n-Feld traegt `de` und LEERE en/fr/it, damit der
feldweise Merge der Maschinerie keine belegte Handuebersetzung verdraengt.

stdlib-rein: pydantic/LLM werden erst in `extract(...)` (lazy) importiert, damit
die Registry ohne Runtime-Deps importierbar und der Auswahl-Kern testbar bleibt.
"""
from __future__ import annotations

from ..registry import register

# Kuratierte Domaenen-Hilfe. BEWUSST OHNE bindende Zahl (Kardinalregel): keine
# Frist-, Gebuehren- oder Prozentangabe im Klartext — der Test haelt das ehrlich
# (BINDING_VALUE_STRICT darf hier NICHT anschlagen). Der Hint benennt die
# bindenden Werte nur als Reference-KANDIDATEN, nie mit ihrem Wert.
VERANSTALTUNG_HINT = """\
Dies ist die HOCHRISIKO-Leistung «Veranstaltung auf oeffentlichem Grund
(Bewilligung)». Ausgabe ausschliesslich als Draft-PR, Merge nur durch einen
Menschen. Nutze die folgenden Strukturhinweise NUR, soweit der mitgelieferte
Quelltext sie WOERTLICH belegt — erfinde nichts, rate keine Rolle und keinen
Schritt hinzu.

AKTEURE (konsistente Rollennamen, an die handmodellierte Zieldatei angeglichen):
- «veranstalter»: die gesuchstellende Person oder Organisation.
- «stapo-bew»: die staedtische Bewilligungsbehoerde, die das Gesuch entgegennimmt
  und den Entscheid faellt.
- «fachstellen»: beigezogene Fachstellen fuer Teilaspekte (etwa Laerm/Immissionen,
  Sicherheit und Sanitaet, Ausschank/Wirtschaft, Nutzung des oeffentlichen Grundes).
- «statthalter»: das Statthalteramt als Rekurs-/Beschwerdeinstanz.
Verwende exakt DIESE Bezeichnungen, wenn die Quelle die jeweilige Stelle nennt.
Eine Rolle, die die Quelle nicht belegt, laesst du weg — sie wird im PR geflaggt,
nicht geraten.

TYPISCHE STRUKTUR (nur belegte Schritte uebernehmen, Reihenfolge aus der Quelle):
Gesuch einreichen -> Pruefung durch die Bewilligungsbehoerde -> Einbezug der
Fachstellen fuer die betroffenen Teilaspekte -> Auflagen/Teilbewilligungen ->
Entscheid/Bewilligung. Ein Rekurs beim Statthalteramt ist ein bedingter,
nachgelagerter Zweig — nur aufnehmen, wenn die Quelle ihn belegt.

KARDINALREGEL (hier besonders streng — ein unbelegter bindender Wert ist ein
Validator-FEHLER, kein Hinweis): Bindende Werte wie die Vorlauffrist (das Gesuch
ist im Voraus einzureichen), Bewilligungsgebuehren, kostenpflichtige Auflagen oder
Rekursfristen gehoeren AUSSCHLIESSLICH in eine Reference — Label OHNE die Zahl
(etwa «Vorlauffrist fuer das Gesuch», «Bewilligungsgebuehr»), plus Deep-Link auf
die exakte Quellseite und das WOERTLICHE source_quote. Niemals als Wert in einem
Schritt-Label oder einer Bedingung.

STRUKTUR-ONLY: Jedes i18n-Feld traegt `de`; en/fr/it bleiben LEER (Uebersetzungen
fuellt allein die Maschinerie). Feld `ls` (Leichte Sprache) nur, soweit belegt.
"""


@register
class VeranstaltungExtractor:
    """Beansprucht `veranstaltung`; reicht die kuratierte Domaenen-Hilfe in den
    bestehenden Zwei-Pass-LLM-Pfad. Erfuellt das `registry.ProcessExtractor`-
    Protokoll (name/handles/extract)."""

    name = "veranstaltung"

    def handles(self, proc) -> bool:
        return getattr(proc, "id", None) == "veranstaltung"

    def extract(self, proc, corpus: str):
        from .. import extract  # noqa: PLC0415 — pydantic/LLM erst hier

        return extract.extract_process(proc, corpus, domain_hint=VERANSTALTUNG_HINT)
