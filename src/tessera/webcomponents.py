"""Web-Komponenten des Stadt-Zuerich-Designsystems vor der Text-Extraktion
aufloesen. Nur stdlib.

stadt-zuerich.ch rendert Tabellen und Zwischentitel als Custom Elements, die
erst das JavaScript im Browser zu sichtbarem HTML macht:

* ``<stzh-datatable columns="[JSON]" rows="[JSON]">`` — die Tabelle steht als
  JSON in Attributen. trafilatura sieht kein ``<table>`` und verwirft sie samt
  Inhalt. Im fundsache-Pilot fehlte so die ganze Gebuehrentabelle («Gebuehren
  bei Abholung»), ebenso ein Rechenbeispiel auf kita-platz/faq.html.
* ``<stzh-heading level="2">`` — Zwischentitel; trafilatura verwirft sie als
  unbekannte Elemente, der Abschnittskontext («Gebuehren bei Abholung») ginge
  verloren.

`expand` ersetzt beide durch gewoehnliches HTML, BEVOR trafilatura laeuft:

* jede Tabellenzeile wird ein Absatz «Spaltenkopf: Zelle; Spaltenkopf: Zelle»
  (so liest auch ein Screenreader eine Tabelle vor). Jedes Textstueck stammt
  woertlich von der Seite; nur die Spaltenkoepfe wiederholen sich je Zeile. So
  bleibt eine Zelle mit ihrer Einheit zitierbar («Gebühr in CHF: 10.00») — in
  einer Markdown-Tabelle stuende die Waehrung nur im Kopf, und das Label<->Wert-
  Gate fände im Zitat keinen Betrag.
* ``<stzh-heading level=N>`` wird ``<hN>``.

Unlesbares JSON laesst das Element unveraendert (kein Raten, kein Abbruch).
"""

from __future__ import annotations

import html
import json
import re

# Attribute duerfen ein rohes «>» enthalten (``&lt;strong>`` im JSON) — darum
# werden gequotete Werte als Ganzes uebersprungen statt an «>» zu enden.
_ATTRS = r"""((?:[^>"']|"[^"]*"|'[^']*')*)"""
_DATATABLE = re.compile(rf"<stzh-datatable\b{_ATTRS}>(.*?)</stzh-datatable\s*>", re.S | re.I)
_HEADING = re.compile(rf"<stzh-heading\b{_ATTRS}>(.*?)</stzh-heading\s*>", re.S | re.I)
_ATTR = re.compile(r"""([\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

CELL_SEP = "; "


def _attrs(raw: str) -> dict[str, str]:
    return {m.group(1).lower(): html.unescape(m.group(2) or m.group(3) or "") for m in _ATTR.finditer(raw)}


def _text(fragment: object) -> str:
    """Zelleninhalt (darf HTML wie <strong> tragen) -> reiner, gestauchter Text."""
    if not isinstance(fragment, str):
        return ""
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", fragment))).strip()


def _row_paragraphs(columns: list, rows: list) -> list[str]:
    heads = [_text(c.get("text")) if isinstance(c, dict) else "" for c in columns]
    out: list[str] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        parts = []
        for i, cell in enumerate(row):
            value = _text(cell.get("value")) if isinstance(cell, dict) else _text(cell)
            if not value:
                continue
            head = heads[i] if i < len(heads) else ""
            parts.append(f"{head}: {value}" if head else value)
        if parts:
            out.append(CELL_SEP.join(parts))
    return out


def _expand_datatable(m: re.Match) -> str:
    attrs = _attrs(m.group(1))
    try:
        columns = json.loads(attrs.get("columns", "[]"))
        rows = json.loads(attrs.get("rows", "[]"))
    except ValueError:
        return m.group(0)
    if not isinstance(columns, list) or not isinstance(rows, list):
        return m.group(0)
    paragraphs = "".join(f"<p>{html.escape(p, quote=False)}</p>" for p in _row_paragraphs(columns, rows))
    # Slot-Inhalt (typisch die Tabellen-Ueberschrift) bleibt vor der Tabelle stehen.
    return f"{m.group(2)}<div>{paragraphs}</div>"


def _expand_heading(m: re.Match) -> str:
    level = _attrs(m.group(1)).get("level", "2")
    n = int(level) if level.isdigit() and 1 <= int(level) <= 6 else 2
    return f"<h{n}>{m.group(2)}</h{n}>"


def expand(raw_html: str) -> str:
    """stzh-Datentabellen und -Zwischentitel in gewoehnliches HTML aufloesen."""
    if "stzh-" not in raw_html:
        return raw_html
    # Tabellen zuerst: ihre Ueberschrift steckt als stzh-heading im Slot.
    return _HEADING.sub(_expand_heading, _DATATABLE.sub(_expand_datatable, raw_html))
