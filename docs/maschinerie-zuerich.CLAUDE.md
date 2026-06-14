<!--
  ÜBERTRAGUNGS-ARTEFAKT — Zielort: maschinerie-zuerich/CLAUDE.md (Repo-Root).

  Diese Datei gehört NICHT nach tessera, sondern in die Wurzel des Repos
  `malkreide/maschinerie-zuerich`. Sie wird hier in tessera nur versioniert
  vorgehalten, weil diese Session keinen Schreibzugriff auf das Maschinerie-Repo
  hat. Zum Übernehmen: Inhalt unterhalb dieses Kommentars 1:1 als
  `CLAUDE.md` in den Maschinerie-Root committen.

  Vor dem Committen im Zielrepo prüfen (hier aus tessera-Sicht hergeleitet,
  nicht im Maschinerie-Repo verifiziert): die genauen npm-Skriptnamen
  (`check:regression`, `validate:prozesse`), das App-Unterverzeichnis
  (`stadt-zuerich-next/`) und der Schema-Pfad (`schemas/opengov-process-schema.json`).
-->
# Projektkontext: Maschinerie Zürich – Visualisierung von Verwaltungsprozessen

> Diese Datei gilt für das Repo `maschinerie-zuerich` (Next.js-Visualisierung +
> von Hand modellierte v0-Prozesse). Sie wird von Claude Code automatisch gelesen
> und ist in jeder Session verbindlich. Das Extraktions-Repo `tessera` hat eine
> eigene `CLAUDE.md`.

## Was die Maschinerie ist – und was nicht

Die Maschinerie ist die **Visualisierungs-Schicht**: eine Next.js-App, die
Verwaltungsstrukturen und Prozess-Graphen für Bürger:innen darstellt. Sie enthält
die **von Hand modellierten v0-Prozesse** und ist **Empfänger** der Pull Requests
aus `tessera`.

- Maschinerie = Next.js-Visualisierung + v0-Handdaten + PR-Empfänger.
- Tessera = Python-Pipeline, die Prozess-Struktur extrahiert und als PR liefert.
- Die Maschinerie **crawlt und extrahiert nicht** – das ist tessera.

## Baureihenfolge ist ein Gate

v0 = 2–3 von Hand modellierte Prozesse, die im Vercel-Preview beweisen, dass
Prozess-Graphen dem Bürger helfen. Erst wenn dieser Nutzen belegt ist, automatisiert
tessera (v1). Hier nichts bauen, das diesen Nachweis voraussetzt, bevor er steht.

## Cardinal Rule – «Link, don't assert»

Rechtlich bindende Werte (Fristen, Gebühren, Rekursfristen) werden **nie** als
eigenständiger, gerenderter Wert dargestellt – immer nur als `reference` mit
Deep-Link auf die exakte Originalseite. Eine falsche bindende Angabe, auf die sich
jemand verlässt, ist realer Schaden und ein Vertrauensverlust für die ganze
Maschinerie.

## Der Datenvertrag (hier kanonisch)

- **Kanonisch** ist `docs/process-data-contract.md` und das JSON Schema
  `schemas/opengov-process-schema.json`. tessera gleicht sich darauf ab; bei
  Abweichung gilt **dieses** Repo.
- Prozess-JSONs liegen unter `data/prozesse/<city>/<id>.json`
  (z.B. `stadt-zuerich-next/data/prozesse/zh/hund-anmelden.json`).
- Locale-Keys: `de` (Pflicht), `en`, `fr`, `it`, `ls` (= Leichte Sprache).
- `id == lebenslage_ref` (kebab-case); `disclaimer_key` = i18n-Key des Hinweises.

## Regression-Guard (Handdaten) – nicht verhandelbar

- `npm run check:regression`: ein PR darf an **bestehenden** Dateien belegte
  i18n-Locale- oder `description`-Texte **nicht** leeren/entfernen (Vergleich
  feldweise + Locale-Gesamtabdeckung gegen `origin/<base>`).
- Escape-Hatch `ALLOW_PROZESS_SHRINK=1` existiert nur für bewusste, begründete
  Ausnahmen – **nicht** benutzen, um den Guard zu umgehen.
- `npm run validate:prozesse`: Schema-/Vertrags-Validierung jeder Prozess-Datei.

## Eingehende tessera-PRs

tessera liefert **struktur-only**: `de` plus leere `en/fr/it`. Solche PRs werden
**feldweise gemerged** – bestehende, belegte Übersetzungen und `description`-Blöcke
bleiben erhalten, die Extraktion füllt nur Lücken und ergänzt neue Struktur.
Review: keine Regression, Zitate (`source_quote`) wörtlich gegen die Quelle prüfen,
Kardinalregel im Label kontrollieren.

## Hochrisiko-Rechtsfälle (erhöhter Review)

`baugesuch` (Baubewilligung), `sozialhilfe`, `veranstaltung` sind als reviewte
v0-Handdaten legitim, tragen aber das **höchste Reputationsrisiko**. Für diese:
jede bindende Reference wörtlich belegt (sonst raus), und ein **sichtbarer
Hochrisiko-Disclaimer** im UI.

## Human-in-the-Loop

Kein automatischer Merge nach `main`. Jede Änderung an Prozessdaten wird von einem
Menschen reviewt – besonders bindende Werte und die Hochrisiko-Fälle.

## Credentials-Grenze (nicht verhandelbar)

Tokens/API-Keys nie in Code, Commits oder Logs. Nur ENV-Variablen. Keine
personenbezogenen Daten in URLs, Query-Strings oder Logs.

## Arbeitsweise (jede Session)

- **Erst erkunden, dann bauen:** relevante Dateien lesen, kurzen Plan zeigen.
- Kleine Commits, früh ein Draft-PR. Conventional Commits (`feat`, `fix`, `docs`, …).
- Schweizer Rechtschreibung (kein ß; «Strasse», «dass»).
- Bei Unsicherheit über Schema, Recht oder öffentlich sichtbaren Inhalt: stoppen
  und fragen.
