"""Hochrisiko-Rechtsfaelle: zentrale Registry + erhoehte Review-Politik.

Drei handgeschriebene v0-Prozesse leben bereits im Repo `maschinerie-zuerich`
und tragen das **hoechste Reputationsrisiko** (eine falsche Frist/Gebuehr, auf die
sich jemand verlaesst, ist realer Schaden): Baubewilligung (`baugesuch`),
Sozialhilfe (`sozialhilfe`) und Veranstaltungsbewilligung (`veranstaltung`).

Als menschlich reviewte v0-Daten sind sie legitim. Diese Registry ist die EINE
Wahrheitsquelle dafuer, welche Leistungen als hochriskant gelten — sie wird vom
Vertrags-Validator und vom PR-Writer konsumiert.

**Politik-Stand (v2, bewusste Ausnahme):** `veranstaltung` ist als EINZIGER der
drei Faelle in `sources.yaml` fuer die automatische Extraktion freigeschaltet —
mit maximalem Gate (erhoehter Review unten) und ausschliesslich als **Draft-PR**,
den nur ein Mensch mergt. `baugesuch` und `sozialhilfe` bleiben bewusst
ausgeschlossen (existenzielles bzw. streitanfaelligstes Risiko). Freigeschaltet
oder nicht: alle drei bleiben in `HIGH_RISK_IDS`, damit der erhoehte Gate greift,
wo immer sie durch die Pipeline laufen.

Politik fuer hochriskante Faelle (wo immer sie durch die Pipeline laufen, z.B.
beim Merge gegen eine bestehende Datei oder bei der Validierung):

* **Erhoehter Kardinalregel-/Grounding-Review:** Jede bindende Reference MUSS
  woertlich belegt sein. Eine `unverifiziert`e oder unbelegte Reference ist hier
  ein FEHLER, kein blosser Hinweis — ein reputationskritischer Prozess darf kein
  ungrounded Frist-/Gebuehren-Label tragen.
* **Sichtbarer Hochrisiko-Disclaimer:** Diese drei sollen einen deutlich
  sichtbaren Hinweis tragen (von der Maschinerie gerendert). `HIGH_RISK_DISCLAIMER_KEY`
  ist die Empfehlung dafuer.

Reine stdlib, keine Dependencies — vom dependency-freien Validator importierbar.
"""
from __future__ import annotations

# Die drei reputationskritischen Faelle. Alle bleiben hier registriert (der
# erhoehte Gate greift immer); die Automatik-Freischaltung steuert sources.yaml.
HIGH_RISK_IDS: frozenset[str] = frozenset({"baugesuch", "sozialhilfe", "veranstaltung"})

# i18n-Key fuer den sichtbaren Hochrisiko-Hinweis. Kanonisch ist der Key-Satz im
# Ziel-Repo maschinerie-zuerich; die handmodellierte veranstaltung.json traegt
# dort `Prozesse.disclaimerHochrisiko` — dagegen ist dies abgeglichen (nicht
# unilateral erfunden, vgl. Kardinalregel/Cross-Repo-Grenze).
HIGH_RISK_DISCLAIMER_KEY = "Prozesse.disclaimerHochrisiko"

# Menschlich lesbare Begruendung je Fall — fuer Reviewer-Hinweise und Doku.
HIGH_RISK_RATIONALE: dict[str, str] = {
    "baugesuch": (
        "Baubewilligung: Eingabe-/Einsprache-/Rekursfristen und Gebuehren sind "
        "rechtlich bindend und streitanfaellig."
    ),
    "sozialhilfe": (
        "Sozialhilfe: existenzielle Anspruchs-, Melde- und Rueckforderungsfristen "
        "— eine falsche Angabe trifft besonders verletzliche Personen."
    ),
    "veranstaltung": (
        "Veranstaltungsbewilligung: Eingabefristen, Auflagen und Gebuehren sind "
        "bindend; verpasste Fristen kippen die Bewilligung."
    ),
}


def is_high_risk(proc_id: object) -> bool:
    """True, wenn die Leistungs-id als hochriskant gilt."""
    return isinstance(proc_id, str) and proc_id in HIGH_RISK_IDS


def is_high_risk_disclaimer(disclaimer_key: object) -> bool:
    """Heuristik: traegt der disclaimer_key einen erkennbaren Hochrisiko-Hinweis?

    Bewusst tolerant (substring), damit verschiedene kanonische Key-Schemata des
    Ziel-Repos akzeptiert werden, ohne einen exakten Wert vorzuschreiben.
    """
    if not isinstance(disclaimer_key, str):
        return False
    key = disclaimer_key.lower()
    return any(marker in key for marker in ("high_risk", "hochrisiko", "high-risk", "risk"))
