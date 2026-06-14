# v1-Pipeline: struktur-only-Extraktion

> **Status: umgesetzt** in `src/tessera/` (CLI: `tessera preflight | crawl |
> extract | validate | pr | run`). Der LLM-Schritt und der Cross-Repo-PR
> brauchen eine key-fähige Session (siehe «Setup»); Preflight, Crawl,
> Grounding-Gate und Validierung laufen ohne Keys.

## Was v1 ist – und was nicht

v1 extrahiert die **Struktur** (Akteure, Schritte, Reihenfolge, Abhängigkeiten) von
2–3 kuratierten Verwaltungsleistungen und liefert pro Leistung einen **Draft-PR**
gegen `maschinerie-zuerich`. Bindende Werte (Fristen, Gebühren, Rekursfristen)
erscheinen **nur** als `references` (Label + Deep-Link + wörtliche `source_quote`),
nie als Zahl in einem Schritt-Label («Link, don't assert»).

**Nicht in v1:** Discovery-Agent, PDF/Vision-Parsing, RAG-Gesetzesabgleich,
BPMN/eCH-0096-Export, Cron, automatische Leichte-Sprache/Übersetzung.

## Setup (Voraussetzungen)

**Netz-Policy** (ausgehend HTTPS):

```
i14y.admin.ch          # Pre-Flight-Katalog (ohne Auth)
www.stadt-zuerich.ch   www.zh.ch   www.amicus.ch   skos.ch
www.fedlex.admin.ch    www.zhlaw.ch
pypi.org   files.pythonhosted.org
```

**LLM-Provider** ausschliesslich über ENV (kein Key in Code/Commit/Log):

```
TESSERA_MODEL=anthropic:claude-opus-4-8     # pydantic-ai-Modellstring (Default)
ANTHROPIC_API_KEY=…                         # setzt der Maintainer (nie in Code/Log)
GITHUB_TOKEN=…                              # nur fuer den Cross-Repo-Draft-PR
TARGET_REPO=malkreide/maschinerie-zuerich   # Default
```

Ohne `GITHUB_TOKEN` landet das fertige PR-Bundle in `out/outbox/<id>/`.

**Runtime-Deps** (in `pyproject.toml` als „intended" vermerkt — Installation nach
Rückfrage): `crawl4ai`, `pydantic>=2`, `pydantic-ai`, `httpx`, `pyyaml`, `openpyxl`.
`crawl4ai` benötigt Chromium (`playwright install chromium`); ist das nicht möglich,
Fallback auf `httpx` + Trafilatura/Readability (HTML→Markdown) und Rückfrage.

## Ablauf (schlichte Schleife – kein LangGraph)

```
sources.yaml  (kuratiert, von Hand — ein Eintrag pro Leistung)
      │
[0] Pre-Flight
      ├─ I14Y-Katalog + eCH-0070-Inventar konsumieren → reports/coverage.md
      └─ robots.txt + ToU je Quelle prüfen            → reports/scraping-compliance.md
         (Disallow/ToU-Verbot → Leistung überspringen + flaggen + fragen)
      │
[1] Crawl     Crawl4AI: HTML → sauberes Markdown (rate-limited, ident. User-Agent)
      │
[2] Extract   pydantic-ai → striktes Pydantic-Schema (struktur-only)
      │       Schritte, Akteure, Reihenfolge (depends_on/DAG), references
      │
[3] Ground    jeder Schritt / jede Reference muss WÖRTLICH im Markdown auffindbar
      │       sein (source_quote). Nicht belegbar → verwerfen + flaggen, nie raten.
      │
[4] Validate  python scripts/validate_contract.py <id>.json  → Exit 0 = Pflicht
      │
[5] Emit PR   ein Draft-PR pro Leistung gegen TARGET_REPO
              Datei: stadt-zuerich-next/data/prozesse/zh/<id>.json
              existiert die Datei schon → feldweise mergen (s.u.), nicht ueberschreiben
              NIE mergen, NIE nach main pushen
```

### Merge gegen bestehende (handgepflegte) Zieldateien

Für mehrere Leistungen existieren im Ziel-Repo bereits **von Hand angereicherte**
Dateien mit vollständigen Übersetzungen (`de/en/fr/it/ls`) und `description`-Blöcken.
tessera liefert struktur-only (de plus leere `en/fr/it`). Ein blindes `PUT`-mit-`sha`
würde die reicheren Handdaten durch die ärmere Extraktion ersetzen — Übersetzungs-
und Beschreibungs-Regression. Deshalb merged `src/tessera/merge.py` **feldweise**:

- Bestehende, nicht-leere i18n-Locale-Werte (`de/en/fr/it/ls`) und `description`-
  Blöcke bleiben **immer** erhalten; die Extraktion füllt nur Lücken (leer/None/fehlend).
- Gemerged wird über **fachliche Schlüssel** (`step_id`, `reference_id`, `actor.id`),
  nicht über Array-Index — Reihenfolgeänderungen zerstören nichts.
- Neue Schritte/References/Felder werden ergänzt; bestehende Reihenfolge bleibt.
- Ist ein Fall nicht sauber mergebar (kaputtes JSON, `id`-Mismatch, doppelte
  Schlüssel) → Datei **überspringen** statt verarmen, klar geloggt, kein PR.

Der PR-Body enthält dann eine **Reviewer-Warnung** «überschreibt bestehende
handgepflegte Datei» mit den erhaltenen und ergänzten Feldern. So besteht der PR
den Ziel-Repo-Guard `npm run check:regression` (seit Ziel-PR #108) **ohne**
`ALLOW_PROZESS_SHRINK` — die Escape-Hatch wird bewusst nicht genutzt.

## Ausgabeformat

Konform zu `docs/data-contract.md` (auf das kanonische Schema von
`maschinerie-zuerich` abgeglichen). Kernfelder verpflichtend; additive Felder
(`city`, `actors`, `legal_basis`, `sources`, Step-`type`, Reference-`status` …)
optional. Ziel-Datei-Konventionen:

- `"$schema": "../../../schemas/opengov-process-schema.json"`, `"city": "zh"`
- `id == lebenslage_ref` (kebab-case, identisch zur bestehenden Lebenslage)
- `meta.lizenz: "CC-BY-4.0"`; `disclaimer_key` = i18n-Key des Ziel-Repos
- DE + Leichte Sprache (`ls`) füllen, soweit belegbar; `en/fr/it` leer
  («Übersetzung ausstehend», nicht maschinell raten)
- References, die nicht wörtlich belegt werden können: `status: "unverifiziert"`,
  `source_quote` leer, im PR als offen markieren

## Eingangskontrolle (Gate)

`scripts/validate_contract.py` ist die deterministische Eingangskontrolle: Struktur,
DAG, Referenz-Integrität, statusabhängiges Grounding-Gate und Kardinalregel-Lint.
Eine Leistung wird **nur** ausgegeben, wenn der Validator Exit 0 liefert. Das
Ziel-Repo prüft zusätzlich via eigener CI (`validate:prozesse`) — doppeltes Gate.

## Definition of Done

- [ ] `reports/coverage.md` + `reports/scraping-compliance.md` aus echten Abrufen gefüllt
- [ ] 2–3 Leistungen extrahiert, jede besteht `validate_contract.py` (Exit 0)
- [ ] jeder rechtlich relevante Wert ist belegter Link (`source_quote`), keine Zahl im Label
- [ ] ein Draft-PR pro Leistung gegen `maschinerie-zuerich`, mit Reviewer-Checkliste
- [ ] kein Merge / kein main-Push; keine Keys in Code/Commits/Logs; neue Deps bestätigt

## Stop-Bedingungen (sofort fragen)

- robots.txt/ToU verbietet eine Quelle
- Schema-Konflikt mit dem kanonischen Vertrag
- eine Reference lässt sich nicht wörtlich belegen
- `crawl4ai`/Chromium nicht installierbar
