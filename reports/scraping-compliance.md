# Scraping-Compliance (robots.txt & Nutzungsbedingungen)

Stand: 2026-06-27 — erzeugt durch `tessera preflight`.

## Respekt-Regeln (fix)

- **User-Agent:** identifizierend — `tessera/0.1 (+https://github.com/malkreide/tessera; offene Prozess-Extraktion; Kontakt via GitHub-Issues)`
- **Rate-Limit:** 2.0s Pause zwischen Requests, Backoff bei Fehlern
- **Keine** Umgehung von Logins, Captchas oder anderen Schutzmassnahmen
- **Keine** personenbezogenen Daten in URLs, Query-Strings oder Logs

## Domains

| Domain | robots.txt | Nutzungsbedingungen |
|---|---|---|
| www.stadt-zuerich.ch | robots.txt geladen | [https://www.stadt-zuerich.ch/de/impressum.html](https://www.stadt-zuerich.ch/de/impressum.html) — manuelle Pruefung Maintainer |
| www.zh.ch | robots.txt geladen | [https://www.zh.ch/de/impressum-rechtliches.html](https://www.zh.ch/de/impressum-rechtliches.html) — manuelle Pruefung Maintainer |

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

Verdikt-Logik: Eine Leistung wird nur gecrawlt, wenn ALLE ihre URLs
fuer unseren User-Agent erlaubt sind. Bei Disallow: Leistung gesperrt,
Flag im Report — Ruecksprache mit dem Maintainer noetig.
