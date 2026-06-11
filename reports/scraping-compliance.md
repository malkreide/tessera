# Scraping-Compliance (Pre-Flight)

> **Vorlage.** Wird vom Pre-Flight-Lauf aus echten Abrufen gefüllt. Bei
> `robots.txt = Disallow` oder ToU-Verbot: Quelle **nicht** crawlen, Leistung
> flaggen, Rückfrage an den Maintainer.

Vor jedem Crawl wird je Quell-Domain geprüft: `robots.txt`, Nutzungsbedingungen,
sowie die selbst gesetzten Respekt-Regeln (Rate-Limit, identifizierender
User-Agent, **keine** Umgehung technischer Schutzmassnahmen).

## Respekt-Regeln (fix)

- **User-Agent:** identifizierend, z.B. `tessera-bot/0.1 (+https://github.com/malkreide/tessera)`
- **Rate-Limit:** konservativ (z.B. ≤ 1 Request / 2 s pro Domain), Backoff bei Fehlern
- **Keine** Umgehung von Logins, Captchas oder anderen Schutzmassnahmen
- **Keine** personenbezogenen Daten in URLs, Query-Strings oder Logs

## Domain-Prüfung

| Domain | robots.txt (Crawl erlaubt?) | ToU geprüft? | relevante Pfade | Entscheid |
|---|---|---|---|---|
| www.stadt-zuerich.ch | offen | offen | /…/hundekontrolle.html, /pd/…/anmeldung_zuzug.html | offen |
| www.zh.ch | offen | offen | /…/hunde.html | offen |
| www.amicus.ch | offen | offen | / | offen |
| skos.ch | offen | offen | /skos-richtlinien | offen |
| www.fedlex.admin.ch | offen | offen | /eli/… | offen |
| www.zhlaw.ch | offen | offen | /Erlass/… | offen |

**Legende:** `erlaubt` / `disallow` / `offen`. Entscheid `crawlen` nur bei
`robots.txt = erlaubt` **und** ToU ohne Verbot; sonst `überspringen` (mit Begründung).
