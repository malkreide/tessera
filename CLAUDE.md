# Projektkontext: Tessera – Prozess-Extraktion für Maschinerie Zürich

> Diese Datei gilt für das Repo `tessera` (Extraktions-Agenten, v1–v3). Sie wird von
> Claude Code automatisch gelesen und ist in jeder Session verbindlich. Das
> Visualisierungs-Repo `maschinerie-zuerich` hat eine eigene `CLAUDE.md`.

## Was Tessera ist – und was nicht

Tessera ist die **Automatisierungs-Schicht**: KI-Agenten, die die Prozess-Struktur
von Verwaltungsleistungen extrahieren und als Pull Request an das **separate** Repo
`maschinerie-zuerich` liefern. Tessera enthält **keine** Visualisierung – das ist
die Maschinerie. Tessera produziert Daten, die Maschinerie konsumiert sie.

- Tessera = Python-Pipeline (v1–v3).
- Maschinerie = Next.js-Visualisierung + die von Hand modellierten v0-Prozesse +
  Empfänger der PRs.

## Baureihenfolge ist ein Gate

**Baue hier nichts, bevor v0 im Maschinerie-Repo gemergt und im Vercel-Preview als
nützlich bestätigt ist.** v0 (2–3 von Hand modellierte Prozesse) beweist, dass
Prozess-Graphen dem Bürger überhaupt helfen. Tessera automatisiert erst, wenn dieser
Nutzen belegt ist – nicht vorher.

## Cardinal Rule – «Link, don't assert»

Zwei Datenklassen, strikt getrennt:

1. **Strukturdaten** (Akteur, Schritt, Reihenfolge, Abhängigkeit): werden extrahiert
   und ausgegeben.
2. **Rechtlich bindende Werte** (Fristen, Gebühren, Rekursfristen): werden **niemals**
   als eigenständige, autoritative Werte ausgegeben. Stattdessen als Referenz mit
   Deep-Link auf die exakte Originalseite.

Begründung: Eine falsche bindende Angabe, auf die sich jemand verlässt, ist realer
Schaden und ein Vertrauensverlust für die ganze Maschinerie. Risiko wird
weggedesignt, nicht wegtechnisiert.

## Der Datenvertrag

Tessera muss exakt das Format produzieren, das die Maschinerie erwartet. Der Vertrag
liegt in `docs/data-contract.md`. **Kanonisch ist das in v0 definierte Schema im
Maschinerie-Repo**, sobald es existiert; der Vertrag hier wird darauf abgeglichen.
Bei Abweichung: stoppen und fragen, nicht raten.

## Belegbarkeit statt Selbsteinschätzung (Grounding-Gate)

Jeder extrahierte Schritt und jede Referenz muss als **wörtliche Stelle** im
gecrawlten Quelltext belegbar sein (`source_quote`). Lässt sich etwas nicht belegen,
wird es **verworfen und für den Reviewer geflaggt** – nicht ausgegeben. Es gibt
**keinen** LLM-Selbsteinschätzungs-Score als Publish-Schwelle.

## Pre-Flight-Checks (vor jedem Crawl)

1. **Katalog konsumieren, nicht entdecken:** I14Y Public API (Behördenleistungen,
   ohne Auth) und eCH-0070-Leistungsinventar (XLSX) abrufen; Abdeckung pro Leistung
   nach `reports/coverage.md` schreiben. Keinen Discovery-Agenten bauen.
2. **Rechtsfläche prüfen:** `robots.txt` und Nutzungsbedingungen der Quellseiten
   lesen; Funde nach `reports/scraping-compliance.md`. Respektieren: Rate-Limit,
   identifizierender User-Agent, keine Umgehung technischer Schutzmassnahmen. Bei
   Disallow/ToU-Verbot: stoppen und fragen.

## Tooling

- **Crawl4AI**: HTML → sauberes Markdown.
- **Pydantic / Pydantic AI**: striktes Schema, deterministische Validierung.
- **LLM-Provider** über ENV (kein Key im Code).
- **Cross-Repo-PR** via `gh` CLI / GitHub API gegen `TARGET_REPO`
  (Default `malkreide/maschinerie-zuerich`).

## Credentials-Grenze (nicht verhandelbar)

- Tokens und API-Keys werden **niemals** in Code, Commits oder Logs geschrieben.
- Du fasst keine Credentials an und richtest keine Tokens ein – das macht der
  Maintainer. Nutze ausschliesslich ENV-Variablen.
- Keine personenbezogenen Daten in URLs, Query-Strings oder Logs.

## Human-in-the-Loop

Output landet **immer** als PR gegen das Ziel-Repo – ein PR pro Leistung, mit
menschenlesbarer Zusammenfassung, dem JSON und einer Reviewer-Checkliste. Die
Pipeline merged **nie** und pusht **nie** nach `main` (weder hier noch im Ziel-Repo).

## Arbeitsweise (jede Session)

- **Erst erkunden, dann bauen:** relevante Dateien lesen, Plan in 5–10 Zeilen zeigen,
  bevor Code geschrieben wird.
- Kleine Commits, früh ein Draft-PR. Conventional Commits (`feat`, `fix`, `docs`, …).
- Neue Dependencies, Schema-Änderungen, Umstrukturierungen nur nach Rückfrage.
- So einfach wie möglich: schwere Orchestrierung (z.B. LangGraph) nur, wenn der
  Kontrollfluss es wirklich braucht – sonst eine schlichte Schleife.
- Schweizer Rechtschreibung in Inhalten und Doku (kein ß; «Strasse», «dass»).
- Bei Unsicherheit über Schema, Quelle, Recht oder öffentlich sichtbaren Inhalt:
  stoppen und fragen.

## Explizit NICHT in v1 (erst v2/v3, und nur bei Bedarf)

Discovery-Agent, PDF/Vision-Parsing, RAG-Gesetzesabgleich, BPMN/eCH-0096-Export,
Cron, automatische Leichte-Sprache-Generierung.
