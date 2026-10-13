#!/usr/bin/env python3
"""Tests fuer webcomponents.expand (stzh-Datentabellen/-Zwischentitel) — reine stdlib.

Die Fixture bildet die echte Struktur von stadt-zuerich.ch nach (fundsache-Pilot,
verloren.html): die Tabelle steht als JSON in Attributen, Zellen tragen HTML wie
``&lt;strong>`` — mit einem ROHEN «>» im Attributwert, an dem ein naiver
``[^>]*``-Tag-Regex scheitert.

Aufruf: python tests/test_webcomponents.py — Exit 0 = alle Tests gruen.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tessera.binding import label_value_mismatch  # noqa: E402
from tessera.verify import extract_text  # noqa: E402
from tessera.webcomponents import expand  # noqa: E402

# Gekuerzt aus verloren.html (Stand 2026-10-13), Struktur unveraendert.
DATATABLE = (
    '<stzh-datatable columns="[{&#34;key&#34;:&#34;HFsKX&#34;,&#34;text&#34;:&#34;&lt;strong>'
    "Verkaufswert (VW) in CHF&lt;/strong>&#34;},{&#34;key&#34;:&#34;haOUq&#34;,&#34;text&#34;:"
    '&#34;&lt;strong>Gebühr in  CHF&lt;/strong>&#34;,&#34;align&#34;:&#34;left&#34;}]" '
    'rows="[[{&#34;value&#34;:&#34;Dokumente/Gegenstände/Bargeld bis 50.00&#34;},{&#34;value&#34;:'
    "&#34;5.00&#34;,&#34;align&#34;:&#34;left&#34;}],[{&#34;value&#34;:&#34;über 50.00&#34;},"
    "{&#34;value&#34;:&#34;10.00&#34;}],[{&#34;value&#34;:&#34;über 2'000.00&#34;},{&#34;value&#34;:"
    "&#34;5% des VW&#34;}],[{&#34;value&#34;:&#34;&lt;strong>Zuschlag für Express-Serviceauftrag"
    '&lt;/strong>&#34;},{&#34;value&#34;:&#34;&lt;strong>50.00&lt;/strong>&#34;}]]" hide-search>\n'
    '    <stzh-heading level="2" slot="heading" id="gebuehren_bei_abholung">Gebühren bei Abholung'
    "</stzh-heading>\n</stzh-datatable>"
)
PAGE = f"<html><body><main><p>Einleitung zum Fundbüro.</p>{DATATABLE}<p>Danach.</p></main></body></html>"


def test_datatable_rows_become_self_describing_paragraphs() -> None:
    out = expand(PAGE)
    assert "<stzh-datatable" not in out, out
    assert (
        "<p>Verkaufswert (VW) in CHF: Dokumente/Gegenstände/Bargeld bis 50.00; Gebühr in CHF: 5.00</p>" in out
    ), out
    assert "<p>Verkaufswert (VW) in CHF: über 50.00; Gebühr in CHF: 10.00</p>" in out, out
    assert "Gebühr in CHF: 5% des VW" in out, out
    # Zellen-HTML (<strong>) ist weg, der Text bleibt; doppelte Leerzeichen gestaucht.
    assert "Zuschlag für Express-Serviceauftrag; Gebühr in CHF: 50.00" in out, out
    assert "<strong>" not in out


def test_slot_heading_survives_as_real_heading() -> None:
    out = expand(PAGE)
    assert "<h2>Gebühren bei Abholung</h2>" in out, out
    assert out.index("Gebühren bei Abholung") < out.index("über 50.00")


def test_heading_levels_and_fallback() -> None:
    assert expand('<stzh-heading level="3">A</stzh-heading>') == "<h3>A</h3>"
    assert expand("<stzh-heading>B</stzh-heading>") == "<h2>B</h2>"
    assert expand('<stzh-heading level="9">C</stzh-heading>') == "<h2>C</h2>"


def test_broken_json_and_plain_pages_stay_untouched() -> None:
    broken = '<stzh-datatable columns="[{" rows="[]"></stzh-datatable>'
    assert expand(broken) == broken
    plain = "<html><body><table><tr><td>A</td></tr></table></body></html>"
    assert expand(plain) == plain


def test_cell_text_is_escaped_not_executed() -> None:
    evil = (
        '<stzh-datatable columns="[{&#34;text&#34;:&#34;Kopf&#34;}]" '
        'rows="[[{&#34;value&#34;:&#34;&lt;img src=x onerror=alert(1)&gt; 5 &amp;lt;b&amp;gt;&#34;}]]">'
        "</stzh-datatable>"
    )
    out = expand(evil)
    # Tags in Zellen werden entfernt, entitaetskodiertes Markup bleibt maskierter Text.
    assert "<p>Kopf: 5 &lt;b&gt;</p>" in out, out
    assert "<img" not in out and "onerror" not in out, out


def test_table_quote_now_substantiates_fee_label() -> None:
    # Die aufgeloeste Zeile traegt die Einheit aus dem Spaltenkopf mit: ein Zitat
    # daraus belegt den Betrag fuer das Label<->Wert-Gate.
    quote = "Verkaufswert (VW) in CHF: über 50.00; Gebühr in CHF: 10.00"
    assert label_value_mismatch("Gebühr bei Abholung eines Fundgegenstandes", quote) is None
    # Auch der Drift-Abgleich (verify --online) sieht die Zeile — mit wie ohne trafilatura.
    assert quote in extract_text(PAGE), extract_text(PAGE)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"[FAIL] {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} Tests gruen.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
