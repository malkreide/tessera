"""Bindende Werte erkennen — geteilte stdlib-Heuristiken (keine Dependencies).

Zwei verschiedene Empfindlichkeiten fuer zwei verschiedene Zwecke:

* KARDINALREGEL-Lint (`BINDING_VALUE`): faengt eine *konkrete* bindende Zahl
  (Ziffer + Einheit) in gerendertem Text. Bewusst eng — gerenderte Labels sind
  kurze, kuratierte Texte; ausgeschriebene Zahlen sind dort selten. Diese Regex
  ist die EINE Wahrheitsquelle, die der Vertrags-Validator konsumiert.

* LABEL<->WERT-Gate (`binding_label_kind` + `quote_substantiates`): prueft, ob
  ein source_quote tatsaechlich den Werttyp belegt, den sein Reference-Label
  benennt. Hier wird breiter gematcht (auch ausgeschriebene Fristen wie «zehn
  Tagen»), denn der gefaehrlichste Fehler ist der plausibel-aber-falsche Treffer:
  ein «Gebuehr»-Label, dessen Zitat nur eine Frist enthaelt, oder ein
  «Meldefrist»-Label, dessen Zitat gar keine Dauer nennt. Das Gate faengt
  mechanisch den sauber entscheidbaren Teil («das Zitat belegt KEINEN Wert des
  richtigen Typs»). Ob eine *vorhandene* Zahl die *richtige* ist (Einsprache- vs.
  Zahlungsfrist), bleibt menschliches Urteil — das automatisiert dieses Modul
  bewusst nicht.

Reine stdlib (`re`), damit der dependency-freie Validator es importieren kann.
"""
from __future__ import annotations

import re

# --- Kardinalregel-Lint: konkrete bindende Zahl (Ziffer + Einheit) -----------
# Identisch zur frueheren Definition im Validator; hierher gezogen als EINE
# Wahrheitsquelle. Aenderungen wirken auf den Kardinalregel-Lint.
_UNIT = (
    r"(?:CHF|Fr\.?|Franken|%|Prozent|Tag(?:e|en)?|Woche(?:n)?|Monat(?:e|en)?|"
    r"Jahr(?:e|en)?|Werktag(?:e|en)?)"
)
BINDING_VALUE = re.compile(
    rf"(?:\d[\d'.,]*\s*{_UNIT}\b)|(?:(?:CHF|Fr\.?)\s*\d)",
    re.IGNORECASE,
)

# --- Label<->Wert-Gate: Werttyp aus dem Label, Wert-Beleg im Zitat -----------
# Ausgeschriebene Kardinalzahlen, wie sie in Fristen vorkommen («innert zehn
# Tagen»). Laengere Varianten zuerst, damit die Alternation greedy korrekt
# matcht.
_WORD_NUM = (
    r"f(?:ue|ü)nfzehn|vierzehn|dreizehn|zw(?:oe|ö)lf|"
    r"f(?:ue|ü)nfzig|dreissig|dreißig|vierzig|sechzig|siebzig|achtzig|"
    r"neunzig|zwanzig|hundert|"
    r"elf|zehn|neun|acht|sieben|sechs|f(?:ue|ü)nf|vier|drei|zwei|"
    r"eine[mnrs]?|ein"
)
_TIME_UNIT = (
    r"Tag(?:e|en)?|Woche(?:n)?|Monat(?:e|en)?|Jahr(?:e|en)?|Werktag(?:e|en)?|"
    r"Stunde(?:n)?|Minute(?:n)?"
)
_MONTH = (
    r"Januar|Februar|M(?:ä|ae)rz|April|Mai|Juni|Juli|August|September|"
    r"Oktober|November|Dezember"
)

# Eine Dauer/Frist ist belegt durch: Ziffer+Zeiteinheit, ausgeschriebene
# Zahl+Zeiteinheit, ein Datum (30. Juni) oder ein ISO-Datum.
_TIME_VALUE = re.compile(
    rf"(?:(?:\d[\d'.,]*|\b(?:{_WORD_NUM}))\s*(?:{_TIME_UNIT})\b)"
    rf"|(?:\b\d{{1,2}}\.\s*(?:{_MONTH})\b)"
    rf"|(?:\b\d{{4}}-\d{{2}}-\d{{2}}\b)",
    re.IGNORECASE,
)

# Ein Geldbetrag/Satz: CHF/Fr./Franken + Ziffer (beide Reihenfolgen) oder
# Ziffer + Prozent.
_MONEY_VALUE = re.compile(
    r"(?:(?:CHF|Fr\.?|Franken)\s*\d)"
    r"|(?:\d[\d'.,]*\s*(?:CHF|Fr\.?|Franken|%|Prozent)\b)",
    re.IGNORECASE,
)

# Label-Stichwoerter -> Werttyp. Substring-Match auf das kleingeschriebene
# Label; deutsche Komposita tragen den Stamm (Anmeldefrist -> frist,
# Hundeabgabe -> abgabe, Bearbeitungsgebuehr -> gebuehr).
_MONEY_TERMS = (
    "gebuehr", "gebühr", "kosten", "betrag", "tarif", "abgabe", "steuer",
    "preis", "entgelt", "ansatz", "zuschlag",
)
_TIME_TERMS = (
    "frist", "gueltig", "gültig", "dauer", "laufzeit", "bearbeitungszeit",
    "termin",
)


def binding_label_kind(text: str) -> str | None:
    """Welchen Werttyp benennt dieses Reference-Label?

    Rueckgabe: 'money', 'time', 'any' (beides genannt) oder None (kein
    erkennbarer bindender Werttyp -> Gate greift nicht).
    """
    if not isinstance(text, str):
        return None
    low = text.lower()
    money = any(t in low for t in _MONEY_TERMS)
    time = any(t in low for t in _TIME_TERMS)
    if money and time:
        return "any"
    if money:
        return "money"
    if time:
        return "time"
    return None


def quote_substantiates(kind: str, quote: str) -> bool:
    """Belegt das Zitat einen Wert des erwarteten Typs?

    'money' -> Geldbetrag/Satz; 'time' -> Dauer/Frist/Datum; 'any' -> einer von
    beiden. Ist `kind` None/unbekannt, gibt es nichts zu pruefen (True).
    """
    if not isinstance(quote, str) or not quote.strip():
        return False
    if kind == "money":
        return bool(_MONEY_VALUE.search(quote))
    if kind == "time":
        return bool(_TIME_VALUE.search(quote))
    if kind == "any":
        return bool(_MONEY_VALUE.search(quote) or _TIME_VALUE.search(quote))
    return True


def label_value_mismatch(label_text: str, quote: str) -> str | None:
    """Praktischer Einzelaufruf fuer References.

    Gibt eine kurze Begruendung zurueck, wenn das Label einen bindenden Werttyp
    benennt, das Zitat ihn aber NICHT belegt — sonst None. Ein leeres Zitat ist
    hier KEIN Befund (das faengt das Grounding-Gate ueber die Verbatim-Pruefung).
    """
    kind = binding_label_kind(label_text)
    if kind is None:
        return None
    if not isinstance(quote, str) or not quote.strip():
        return None
    if quote_substantiates(kind, quote):
        return None
    expect = {"money": "Betrag/Gebuehr", "time": "Frist/Dauer/Datum", "any": "Frist oder Betrag"}[kind]
    return (
        f"Label benennt einen bindenden Wert ({expect}), das Zitat belegt aber "
        f"keinen solchen Wert"
    )
