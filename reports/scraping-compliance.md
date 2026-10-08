# Scraping-Compliance (robots.txt & Nutzungsbedingungen)

Stand: 2026-10-08 — erzeugt durch `tessera preflight`.

## Respekt-Regeln (fix)

- **User-Agent:** identifizierend — `tessera/0.1 (+https://github.com/malkreide/tessera; offene Prozess-Extraktion; Kontakt via GitHub-Issues)`
- **Rate-Limit:** 2.0s Pause zwischen Requests, Backoff bei Fehlern
- **Keine** Umgehung von Logins, Captchas oder anderen Schutzmassnahmen
- **Keine** personenbezogenen Daten in URLs, Query-Strings oder Logs

## Domains

| Domain | robots.txt | Nutzungsbedingungen | ToU-Pruefung (Maintainer) | ToU-Gate |
|---|---|---|---|---|
| www.stadt-zuerich.ch | robots.txt geladen | [https://www.stadt-zuerich.ch/de/service/rechtliche-hinweise.html](https://www.stadt-zuerich.ch/de/service/rechtliche-hinweise.html) | ausstehend (geprueft —; Fassung «—») | **GESPERRT** — ToU-Pruefung ausstehend — der Maintainer entscheidet (terms_of_use in sources.yaml) |
| www.zh.ch | robots.txt geladen | [https://www.zh.ch/de/nutzungshinweise.html](https://www.zh.ch/de/nutzungshinweise.html) | ausstehend (geprueft —; Fassung «—») | **GESPERRT** — ToU-Pruefung ausstehend — der Maintainer entscheidet (terms_of_use in sources.yaml) |

## Geprüfte URLs

| Leistung | URL | robots-Verdikt |
|---|---|---|
| `hund-anmelden` | https://www.stadt-zuerich.ch/de/stadtleben/veranstaltungen-und-bewilligungen/hundekontrolle.html | erlaubt |
| `hund-anmelden` | https://www.stadt-zuerich.ch/de/stadtleben/veranstaltungen-und-bewilligungen/hundekontrolle/anmeldung.html | erlaubt |
| `hund-anmelden` | https://www.zh.ch/de/umwelt-tiere/tiere/haustiere-heimtiere/hunde.html | erlaubt |
| `umzug-melden` | https://www.stadt-zuerich.ch/de/lebenslagen/einwohner-services/umziehen-melden.html | erlaubt |
| `umzug-melden` | https://www.stadt-zuerich.ch/de/lebenslagen/einwohner-services/umziehen-melden/zuzug.html | erlaubt |
| `umzug-melden` | https://www.stadt-zuerich.ch/de/lebenslagen/einwohner-services/umziehen-melden/umzug.html | erlaubt |
| `umzug-melden` | https://www.stadt-zuerich.ch/de/lebenslagen/einwohner-services/umziehen-melden/wegzug.html | erlaubt |
| `fundsache` | https://www.stadt-zuerich.ch/vbz/de/beratung-service/fundbuero.html | erlaubt |
| `fundsache` | https://www.stadt-zuerich.ch/vbz/de/beratung-service/fundbuero/verloren.html | erlaubt |
| `fundsache` | https://www.stadt-zuerich.ch/vbz/de/beratung-service/fundbuero/gefunden.html | erlaubt |
| `fundsache` | https://www.stadt-zuerich.ch/vbz/de/beratung-service/fundbuero/versteigerung.html | erlaubt |
| `fundsache` | https://www.stadt-zuerich.ch/vbz/de/beratung-service/fundbuero/rechtsgrundlage.html | erlaubt |
| `parkplatz` | https://www.stadt-zuerich.ch/de/mobilitaet/parkieren/parkbewilligungen.html | erlaubt |
| `parkplatz` | https://www.stadt-zuerich.ch/de/mobilitaet/parkieren/parkbewilligungen/anwohnerparkkarte.html | erlaubt |
| `parkplatz` | https://www.stadt-zuerich.ch/de/mobilitaet/parkieren/parkbewilligungen/anwohnerparkkarte/antragsformular-ap-privatpersonen.html | erlaubt |
| `parkplatz` | https://www.stadt-zuerich.ch/de/mobilitaet/parkieren/rechtliche-grundlagen/agb.html | erlaubt |
| `kita-platz` | https://www.stadt-zuerich.ch/de/lebenslagen/jugend-und-familie/fruehe-kindheit/familienergaenzende-kinderbetreuung/betreuungskosten-und-subventionen.html | erlaubt |
| `kita-platz` | https://www.stadt-zuerich.ch/de/lebenslagen/jugend-und-familie/fruehe-kindheit/familienergaenzende-kinderbetreuung/kitaplatz-finden.html | erlaubt |
| `kita-platz` | https://www.stadt-zuerich.ch/de/lebenslagen/jugend-und-familie/fruehe-kindheit/familienergaenzende-kinderbetreuung/faq.html | erlaubt |
| `veranstaltung` | https://www.stadt-zuerich.ch/de/stadtleben/veranstaltungen-und-bewilligungen/veranstaltungen.html | erlaubt |
| `veranstaltung` | https://www.stadt-zuerich.ch/de/stadtleben/veranstaltungen-und-bewilligungen/veranstaltungen/fest-sportveranstaltung-quartierfest.html | erlaubt |
| `veranstaltung` | https://www.stadt-zuerich.ch/de/stadtleben/veranstaltungen-und-bewilligungen/veranstaltungen/infrastruktur-sicherheit.html | erlaubt |

## Crawl-Gate je Leistung

| Leistung | robots | Nutzungsbedingungen |
|---|---|---|
| `hund-anmelden` | frei | **GESPERRT** (www.stadt-zuerich.ch, www.zh.ch) |
| `umzug-melden` | frei | **GESPERRT** (www.stadt-zuerich.ch) |
| `fundsache` | frei | **GESPERRT** (www.stadt-zuerich.ch) |
| `parkplatz` | frei | **GESPERRT** (www.stadt-zuerich.ch) |
| `kita-platz` | frei | **GESPERRT** (www.stadt-zuerich.ch) |
| `veranstaltung` | frei | **GESPERRT** (www.stadt-zuerich.ch) |

Verdikt-Logik: Eine Leistung wird nur gecrawlt, wenn ALLE ihre URLs
fuer unseren User-Agent erlaubt sind (robots.txt) UND fuer JEDE ihrer
Domains eine ToU-Pruefung des Maintainers mit Verdikt «erlaubt», Datum,
Begruendung und Fassungs-Kennung vorliegt, deren Fassung noch auf der
Live-Seite steht (terms_of_use in sources.yaml). Sonst: gesperrt —
Ruecksprache mit dem Maintainer noetig.
