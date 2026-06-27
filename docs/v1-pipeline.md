# v1-Pipeline: struktur-only-Extraktion

> **Status: umgesetzt** in `src/tessera/` (CLI: `tessera preflight | crawl |
> extract | validate | verify | pr | run`). Der LLM-Schritt und der Cross-Repo-PR
> brauchen eine key-fähige Session (siehe «Setup»); Preflight, Crawl,
> Grounding-Gate, Validierung und Re-Verifikation laufen ohne Keys.

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
[1] Crawl     SSR zuerst (httpx + Trafilatura: HTML → Markdown, rate-limited,
      │       ident. User-Agent). SPA-Auto-Erkennung (App-Shell-Marker / wenig
      │       Text) → Headless-Fallback (Crawl4AI) NUR für diese URL; ist der
      │       Browser n/v, App-Shell behalten + ehrlich in meta.json vermerken.
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

[*] Verify    (laufende Hygiene, propose-only) tessera verify [--online]
              netzfrei: Label↔Wert-Befunde; --online: tri-state Erreichbarkeit
              (tot/blockiert/netzfehler) + Beleg-Drift gegen die Live-Seite
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

## Hochrisiko-Rechtsfälle (erhöhter Review)

Drei Leistungen tragen das höchste Reputationsrisiko und sind in v1 bewusst von der
**automatischen** Extraktion ausgeschlossen (Ausschlussliste in `sources.yaml`):
`baugesuch` (Baubewilligung), `sozialhilfe`, `veranstaltung`. Sie existieren bereits
als **von Hand modellierte, menschlich reviewte** v0-Prozesse in der Maschinerie —
das ist legitim, ändert aber nichts am Risiko einer falschen Frist/Gebühr.

Die Registry liegt zentral in `src/tessera/risk.py` (`HIGH_RISK_IDS`). Berührt eine
dieser Leistungen die Pipeline (z.B. ein Merge gegen eine bestehende Datei), greift
erhöhter Review:

- **Validator** (`scripts/validate_contract.py`): jede bindende Reference muss
  `verifiziert` **und** wörtlich belegt (`source_quote`) sein — eine `unverifiziert`e
  oder ungrounded Reference ist hier ein **Fehler** (im Normalfall nur ein Hinweis).
  Zusätzlich ein gut sichtbarer `HOCHRISIKO`-Banner und die Empfehlung eines sichtbaren
  Hochrisiko-Disclaimers (`disclaimer_key`, empfohlen `process.disclaimer.high_risk_legal`).
- **PR-Body** (`src/tessera/pr.py`): eine prominente Hochrisiko-Reviewer-Warnung mit
  verschärfter Kardinalregel-/Grounding-Checkliste und dem Hinweis, dass dieser Prozess
  handmodellierter v0-Inhalt ist (nicht automatisch extrahiert).

«v1 ist risikoarm» bezieht sich also auf den **automatischen** Output; die schweren
Fälle bleiben menschlich kuratiert und werden hier nur strenger geprüft, nicht erzeugt.

## Eingangskontrolle (Gate)

`scripts/validate_contract.py` ist die deterministische Eingangskontrolle: Struktur,
DAG, Referenz-Integrität, statusabhängiges Grounding-Gate und Kardinalregel-Lint.
Eine Leistung wird **nur** ausgegeben, wenn der Validator Exit 0 liefert. Das
Ziel-Repo prüft zusätzlich via eigener CI (`validate:prozesse`) — doppeltes Gate.

## Label↔Wert-Gate (gegen «richtige Seite, falscher Wert»)

Der gefährlichste Output ist nicht der sichtbare Fehlschlag, sondern der
plausibel-aber-falsche Treffer: ein `Gebühr`-Label, dessen `source_quote` nur eine
Frist belegt, oder eine `Meldefrist`, deren Zitat gar keine Dauer nennt. Deshalb
prüft `src/tessera/binding.py` mechanisch, ob ein Zitat den **Werttyp** belegt, den
sein Label benennt (Frist/Dauer/Datum vs. Betrag/Gebühr):

- **Grounding-Gate** (`grounding.py`, Publish-Pfad mit Korpus): Ist ein Zitat zwar
  wörtlich auffindbar, belegt aber den falschen Werttyp → **Abstinenz**: `status`
  wird auf `unverifiziert` gesetzt, das Zitat verworfen, ein Flag erzeugt. Für
  Hochrisiko-Fälle wird daraus über den Validator ein harter Fehler.
- **Validator** (`validate_contract.py`, ohne Korpus): derselbe Abgleich als
  **Hinweis** für Reviewer — der Validator sieht keine Quelle und entscheidet die
  Mehrdeutigkeit nicht. Opt-in zum **Fehler** via `--strict-label-value` oder
  `TESSERA_STRICT_LABEL_VALUE` (die ENV-Variable erbt `tessera validate`/`pr`):
  sinnvoll für handgepflegte/gemergte Zieldateien, die nicht durch das
  Grounding-Gate laufen.

Die Heuristik fängt den sauber entscheidbaren Teil («das Zitat belegt **keinen**
Wert des richtigen Typs»). Ob eine *vorhandene* Zahl die *richtige* ist
(Einsprache- vs. Zahlungsfrist), bleibt menschliches Urteil und wird bewusst nicht
automatisiert.

## Re-Verifikation: Link-Rot & Beleg-Drift (`tessera verify`)

Gespeicherte URLs sind flüchtig (Quellseiten strukturieren um, Slugs ändern sich
binnen Tagen), und schon verifizierte Zitate verrutschen still bei Seitenedits.
`tessera verify` ist die laufende Hygiene dagegen — **propose-only**, schreibt nie
in `out/`, Report nach `reports/verify/<id>.md`:

- **Netzfrei** (`tessera verify`): die Label↔Wert-Befunde von oben.
- **Online** (`tessera verify --online`): jede `source_url` **tri-state** prüfen —
  `tot` (404/410) ≠ `blockiert` (403/Policy) ≠ `netzfehler`; und jedes verifizierte
  Zitat gegen die Live-Seite (identische Normalisierung wie beim Speichern). Eine
  erkannte JS-SPA wird als «ungeprüft — braucht Rendering» gemeldet, nicht als Drift.

**Tri-State ist der Kern:** Nur `tot` und echter Drift sind **Datenprobleme**
(Exit 1, harter Stopp). `blockiert`/`netzfehler`/SPA-`ungeprüft` sind
**Umgebungsbefunde** und lassen den Lauf bewusst nicht scheitern — sonst sähen
Netz-Policy oder fehlender Browser wie kaputte Daten aus.

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
