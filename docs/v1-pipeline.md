# v1 — Plan ab hier: von der gebauten Mechanik zur Definition of Done

> **Stand: 2026-06-28.** Die Pipeline-Mechanik ist vollstaendig gebaut, getestet
> und in CI; die Haertung (key-/netzfreier Integrationstest + Link-Rot-Cron) ist
> gemergt. Dieses Dokument enthaelt **nur noch, was von hier an zu tun ist**: die
> offenen Gates, die exakten Schritte pro Leistung bis zur Definition of Done und
> den Ausblick danach. Die ausfuehrliche History bereits erledigter Phasen steht
> im Git-Verlauf und im `CHANGELOG.md`.

## Was schon steht (Kontext — nicht mehr zu tun)

- **CLI / Mechanik:** `tessera preflight | crawl | extract | validate | verify |
  pr | run` (`src/tessera/`, schlichte Schleife, kein Orchestrierungs-Framework).
- **Gates im Code:** Grounding-Gate (`grounding.py`), Label↔Wert-Gate
  (`binding.py`), feldweiser Merge gegen Handdaten (`merge.py`),
  Hochrisiko-Registry (`risk.py`), tri-state Re-Verifikation (`verify.py`,
  `reach.py`) — alle mit stdlib-Tests in CI (`.github/workflows/contract-check.yml`).
- **Datenvertrag** auf das kanonische v0-Schema in `maschinerie-zuerich`
  abgeglichen (alle live kanonischen JSONs bestehen `scripts/validate_contract.py`).
- **Pre-Flight-Reports** aus echten Abrufen vorhanden:
  `reports/coverage.md`, `reports/scraping-compliance.md` (hund-anmelden,
  umzug-melden, fundsache — alle robots-erlaubt).
- **Haertung gemergt:** `tests/test_pipeline_integration.py` (Strecke
  extract→to_contract→ground→validate, key-/netzfrei) und
  `.github/workflows/link-rot.yml` (woechentliche Beleg-Hygiene).

## Zwei nicht verhandelbare Gates (vor jedem Echtlauf)

1. **Baureihenfolge:** kein echter Extraktions-/PR-Lauf, bevor v0 im Maschinerie-
   Repo gemergt **und** im Vercel-Preview als nuetzlich bestaetigt ist.
2. **Credentials-Grenze:** Keys/Tokens setzt ausschliesslich der Maintainer im
   ENV; nie in Code/Commit/Log.

---

## Phase A — Freigabe & Umgebung (Maintainer)

Alles in Phase A ist Voraussetzung fuer die Echtlaeufe und liegt beim Maintainer
(Credentials-Grenze). Ohne A.1 → **Stopp**, kein echter Lauf.

### A.1 — v0-Baureihenfolge-Gate bestaetigen
- **Aktion:** Link zum gemergten v0-PR + Vercel-Preview bereitstellen; als kurze
  Notiz in `reports/` festhalten (z.B. `reports/v0-freigabe.md`).
- **Erwartetes Resultat:** dokumentierte Freigabe. Ohne sie kein Echtlauf.
- **Prompt (Maintainer):** «v0 ist gemergt: <PR-Link>, Preview nuetzlich
  bestaetigt: <Vercel-Link>. Freigabe fuer tessera-Echtlaeufe erteilt.»

### A.2 — Keys & Netz-Policy bereitstellen
- **LLM-/PR-Keys (ENV, nie im Code):**
  ```
  TESSERA_MODEL=anthropic:claude-opus-4-8     # pydantic-ai-Modellstring (Default)
  ANTHROPIC_API_KEY=…                         # setzt der Maintainer
  GITHUB_TOKEN=…                              # nur fuer den Cross-Repo-Draft-PR
  TARGET_REPO=malkreide/maschinerie-zuerich   # Default
  ```
  Ohne `GITHUB_TOKEN` landet das fertige PR-Bundle in `out/outbox/<id>/`.
- **Netz-Policy (ausgehend HTTPS):**
  ```
  i14y.admin.ch          # Pre-Flight-Katalog (ohne Auth)
  www.stadt-zuerich.ch   www.zh.ch   www.amicus.ch   skos.ch
  www.fedlex.admin.ch    www.zhlaw.ch
  pypi.org   files.pythonhosted.org
  ```
- **Test-Setting:** `tessera verify --id hund-anmelden --online` gegen eine
  vorhandene Datei zeigt `ok`/`blockiert` statt `netzfehler` (Erreichbarkeit ohne
  Keys). Key-Praesenz prueft der Extract-Schritt selbst (`extract._require_key`).

### A.3 — Runtime-Deps installieren + Smoke-Test
- **Aktion:** venv anlegen, `pip install -e .` (zieht `crawl4ai`, `pydantic`,
  `pydantic-ai`, `httpx`, `pyyaml`, `openpyxl`); optional `playwright install chromium`.
- **Test-Setting:**
  ```bash
  python -m venv .venv && . .venv/bin/activate
  pip install -e .
  tessera --help                 # preflight|crawl|extract|validate|verify|pr|run
  python -c "import tessera.crawl, tessera.extract, tessera.verify"   # Import-Smoke
  python tests/run_checks.py && python tests/test_grounding.py \
    && python tests/test_pipeline_integration.py && python tests/test_binding.py \
    && python tests/test_verify.py && python tests/test_merge.py \
    && python tests/test_risk.py        # stdlib-Suite gruen
  ```
- **Erwartetes Resultat:** alles gruen. Ist Chromium n/v: nur der SSR-Pfad laeuft
  (httpx + Trafilatura) — ehrlich dokumentieren, nicht faken.

---

## Phase B — Echtlaeufe pro Leistung (bis zur Definition of Done)

Schlichte Schleife je Leistung: `preflight → crawl → extract → validate → verify
→ pr`, mit menschlichem Review an den markierten Stellen. **Pilot:**
`hund-anmelden` (rein kommunal, risikoarm, SSR-Quelle stadt-zuerich.ch, klar
belegbare Frist/Abgabe). **Dann:** `umzug-melden` (zh.ch SSR, eUmzug beachten)
und `fundsache` (VBZ Fundbuero, `actors[]` → Actor-Abgleich beim Merge).

Cardinal Rule durchgehend: keine bindende Zahl in einem Label — Fristen/Gebuehren
nur als `references` (Label ohne Zahl + Deep-Link + woertliche `source_quote`).

### B.1 — Pre-Flight (Gate je Leistung)
- **Aktion:** `tessera preflight --id <id>`.
- **Erwartetes Resultat:** `reports/coverage.md`, `reports/scraping-compliance.md`
  und `reports/raw/preflight-gate.json` mit `allowed: true`.
- **Test-Setting:**
  ```bash
  tessera preflight --id hund-anmelden
  python -c "import json;g=json.load(open('reports/raw/preflight-gate.json'));\
print({k:v['allowed'] for k,v in g.items()})"   # True erwartet
  ```
- **Stop-Bedingung:** `DISALLOW` (robots) oder ToU-Verbot → nicht crawlen,
  flaggen, Maintainer fragen.
- **Frische:** Das Gate verfaellt nach 7 Tagen (`preflight.MAX_GATE_AGE_DAYS`) —
  robots.txt kann sich aendern. Ein aelteres, fehlendes oder ungueltiges
  `checked_at` verweigert den Crawl; zuerst `tessera preflight` erneut ausfuehren.

### B.2 — Crawl (Snapshots)
- **Aktion:** `tessera crawl --id <id>`.
- **Erwartetes Resultat:** `reports/raw/<id>/NN-*.md` + `meta.json` mit pro URL
  `http_status`, `state` (`ok`), `spa_suspected` (stadt-zuerich.ch/zh.ch sind
  SSR → `false`), `chars > 0`.
- **Test-Setting:**
  ```bash
  tessera crawl --id hund-anmelden
  python -c "import json;m=json.load(open('reports/raw/hund-anmelden/meta.json'));\
[print(x['url'],x['state'],x['spa_suspected'],x['chars']) for x in m]"
  ```
- **Ehrliche Degradation:** wird eine Quelle als SPA erkannt und kein Browser ist
  da, App-Shell behalten + in `meta.json` vermerken; Crawl in einer Chromium-
  Umgebung wiederholen — keinen Inhalt faken.

### B.3 — Extract + Grounding
- **Vorbedingung:** `ANTHROPIC_API_KEY` gesetzt; brauchbare Snapshots.
- **Aktion:** `tessera extract --id <id>` (deterministisch wo akzeptiert;
  Review-/Repair-Pass an, Opt-out `TESSERA_REVIEW=0`).
- **Erwartetes Resultat:** `out/<id>.json` (struktur-only, kardinalregel-konform)
  + `out/<id>.flags.json`. Soweit belegbar zusätzlich Step-`type` und `documents`
  (speisen Ziel-Indikatoren wie Medienbruch/Online-Schritt/benötigte Unterlagen);
  `documents` durchlaufen dasselbe Grounding-Gate wie Schritte. Nicht belegte
  References → `unverifiziert`; Label↔Wert-Mismatch → Abstinenz-Flag. Das
  Grounding-Gate verwirft jedes nicht woertlich belegte Element. Zwei Schaerfen:
  **per-URL-Grounding** (das Zitat einer Reference muss auf der Seite ihrer
  `source_url` stehen, nicht bloss irgendwo im Korpus — sonst Abstinenz mit
  Flag, das die tatsaechliche Fundseite nennt) und **Mindest-Spezifitaet**
  (Zitate unter `grounding.MIN_QUOTE_CHARS` = 25 normalisierten Zeichen belegen
  nichts → Abstinenz bzw. Verwurf mit Flag).
- **Test-Setting:**
  ```bash
  tessera extract --id hund-anmelden
  cat out/hund-anmelden.flags.json
  python scripts/validate_contract.py out/hund-anmelden.json   # Exit 0
  ```
- **Review (Mensch):** Schritte/Reihenfolge gegen die Originalseite; Geflaggtes
  bleibt offen, nicht von Hand „reparieren".

### B.4 — Validate (Eingangs-Gate)
- **Aktion:** `python scripts/validate_contract.py out/<id>.json`; optional
  `--strict-label-value` fuer gemergte/handnahe Dateien.
- **Erwartetes Resultat:** Exit 0 = Publikations-Voraussetzung. Hinweise
  (i18n-ausstehend, Label↔Wert) bewusst ok.
  ```bash
  python scripts/validate_contract.py out/hund-anmelden.json; echo "exit=$?"
  TESSERA_STRICT_LABEL_VALUE=1 python scripts/validate_contract.py out/hund-anmelden.json
  ```

### B.5 — Re-Verifikation (online, vor dem PR)
- **Aktion:** `tessera verify --id <id> --online` (propose-only, schreibt nie in
  `out/`; Report nach `reports/verify/<id>.md`).
- **Tri-State (Kern):** nur **`tot`** (404/410) und echter **Drift** sind
  Datenprobleme (Exit 1, Stopp). `blockiert`/`netzfehler`/SPA-`ungeprueft` sind
  **Umgebungsbefunde** und lassen den Lauf bewusst nicht scheitern.
  ```bash
  tessera verify --id hund-anmelden --online; echo "exit=$?"   # 0 erwartet
  ```
- **Bei `tot`:** neue offizielle URL vorschlagen (nicht still ersetzen). **Bei
  Drift:** altes vs. aktuelles Zitat zeigen.

### B.6 — Draft-PR emittieren
- **Vorbedingung:** `GITHUB_TOKEN`; Validator Exit 0.
- **Aktion:** `tessera pr --id <id>`. (Ohne Token: Bundle in `out/outbox/<id>/`.)
- **Feldweiser Merge:** existiert die Zieldatei
  (`stadt-zuerich-next/data/prozesse/zh/<id>.json`), wird ueber fachliche
  Schluessel (`step_id`/`reference_id`/`actor.id`) gemergt — bestehende i18n-/
  `description`-Bloecke bleiben erhalten, die Extraktion fuellt nur Luecken. Nicht
  sauber mergebar → Datei ueberspringen statt verarmen (kein PR). Der PR-Body
  traegt die Merge-Warnung mit erhaltenen/ergaenzten Feldern; so besteht der PR
  den Ziel-Guard `check:regression` ohne `ALLOW_PROZESS_SHRINK`. Zwei Schaerfen:
  **Label-Guard** — `step_id`/`reference_id` sind LLM-vergeben, keine stabilen
  fachlichen Schluessel; sind die Labels eines ID-Paars semantisch fremd
  (Aehnlichkeit < `merge.LABEL_SIMILARITY_MIN` = 0.5), wird das Paar NICHT
  gemerged, sondern als `suspect_pairs` im PR geflaggt (bestehend bleibt
  unangetastet). **Provenienz-Ausnahme** — `retrieved_at` (Prozess und je
  gepairte Reference) gewinnt immer aus der Extraktion (frisches Crawl-Datum),
  protokolliert als `refreshed`.
- **Erwartetes Resultat:** Draft-PR (`draft: true`, Branch
  `tessera/<id>-<datum>`) mit Reviewer-Checkliste; Ziel-CI `validate:prozesse`,
  `check:regression`, `check:links` gruen.
- **Regel:** tessera merged **nie** und pusht **nie** nach `main` (hier wie im Ziel-Repo).

### Hochrisiko (erhoehter Review)
`baugesuch`, `sozialhilfe`, `veranstaltung` (Registry `src/tessera/risk.py`)
tragen das hoechste Reputationsrisiko. Ab v2 ist als **bewusste Ausnahme** genau
EIN Fall — `veranstaltung` — in `sources.yaml` fuer die automatische Extraktion
freigeschaltet, mit maximalem Gate: nur als **Draft-PR**, Merge ausschliesslich
durch einen Menschen. `baugesuch` und `sozialhilfe` bleiben ausgeschlossen.
Unabhaengig von der Freischaltung greift fuer alle drei der erhoehte Gate, wo
immer sie die Pipeline beruehren: jede bindende Reference muss `verifiziert`
**und** woertlich belegt sein (sonst Validator-**Fehler**), plus sichtbarer
Hochrisiko-Disclaimer (`Prozesse.disclaimerHochrisiko`) und verschaerfte
PR-Checkliste.

---

## Definition of Done (v1)

- [ ] `reports/coverage.md` + `reports/scraping-compliance.md` aus echten Abrufen ✅ (vorhanden)
- [ ] 2–3 Leistungen extrahiert, jede besteht `validate_contract.py` (Exit 0)
- [ ] jeder rechtlich relevante Wert ist belegter Link (`source_quote`), keine Zahl im Label
- [ ] ein Draft-PR pro Leistung gegen `maschinerie-zuerich`, mit Reviewer-Checkliste
- [ ] kein Merge / kein main-Push; keine Keys in Code/Commits/Logs; neue Deps bestaetigt

---

## Phase C — Kuratiertes Set erweitern (~10 Leistungen)
- **Aktion:** `sources.yaml` um gepruefte, risikoarme, kommunale Leistungen (SSR-
  Quellen bevorzugt) ergaenzen; Kandidaten-URLs vorab auf HTTP 200 pruefen
  (tri-state, Subagent-Fan-out moeglich); je Leistung Phase B.
- **Akzeptanz:** wie B (Validator Exit 0, `verify` sauber, Ziel-CI gruen).
  **`baugesuch` und `sozialhilfe` bleiben ausgeschlossen** (`risk.py`);
  `veranstaltung` ist die einzige freigeschaltete Hochrisiko-Ausnahme (Draft-PR,
  Merge nur durch Menschen).
- **Vorgehen:** Auswahl begruenden, mit dem Crawl auf Maintainer-Freigabe warten.

## Phase D — v2-Ausblick (nur bei Bedarf, nach Rueckfrage)
Bewusst **nicht** in v1 (`CLAUDE.md`):
1. **Struktur-Artikel-Fetcher fuer Recht** (Erlass + §/Art-Nummer/Anker,
   Akoma-Ntoso/PDF) statt Bag-of-Words.
2. **Tabellarische Bindewerte** (Gebuehren-Widgets) mit explizitem Feld→Label-
   Mapping, sonst Abstinenz — ggf. Datenvertrag erweitern.
3. **Discovery-Agent / RAG-Gesetzesabgleich / BPMN-Export** — nur bei belegtem Nutzen.

---

## Stop-Bedingungen (sofort fragen)
- robots.txt/ToU verbietet eine Quelle
- Schema-Konflikt mit dem kanonischen Vertrag
- eine Reference laesst sich nicht woertlich belegen
- `crawl4ai`/Chromium nicht installierbar

## Test-Setting (Uebersicht)

| Ebene | Wann | Werkzeug | Erfolgskriterium |
|---|---|---|---|
| Unit (stdlib, key-frei) | jeder Commit / CI | `tests/*.py`, `run_checks.py` | alle gruen |
| Integration (key-frei) | jeder Commit / CI | `test_pipeline_integration.py` | Gate-Verhalten korrekt |
| Vertrags-Gate | vor jedem PR | `validate_contract.py` (Exit 0) | gueltig |
| Beleg-Hygiene | vor PR + woechentlich (`link-rot.yml`) | `tessera verify --online` | keine tot/Drift |
| Aenderungs-Diff (v2) | woechentlich (`change-diff.yml`) | `tessera diff` vs. `reports/fingerprints/<id>.json` | keine inhaltliche Aenderung |
| Ziel-Repo-CI | im Draft-PR | `validate:prozesse`, `check:regression`, `check:links` | gruen |
| Mensch | vor Merge | Reviewer-Checkliste im PR-Body | freigegeben |

### v2 Aenderungs-Diff (re-crawlen + diffen)

`tessera fingerprint` schreibt nach einem Lauf eine committete Baseline
(`reports/fingerprints/<id>.json`): je Quell-URL ein SHA-256 ueber den
**normalisierten** Seitentext (`grounding.normalize`). `tessera diff` re-crawlt
die Live-Seiten und vergleicht: rein kosmetische Aenderungen (Whitespace,
Typografie) loesen NICHTS aus, nur inhaltliche. `tessera diff --json` gibt eine
maschinenlesbare Zusammenfassung aus (menschliche Zeilen dann nach stderr).

Der woechentliche `change-diff.yml`-Cron faehrt `tessera diff --json` ueber alle
Leistungen mit Baseline und **oeffnet/aktualisiert daraus EIN rollendes
GitHub-Issue** (Label `source-change`), statt nur einen roten Job zu
hinterlassen — so bleibt die Aenderung sichtbar und nachverfolgbar. Sind beim
naechsten Lauf keine Befunde mehr offen, schliesst sich das Issue selbst. Nur
inhaltliche Aenderung oder toter Link erzeugen einen Befund; Block/Netzfehler/SPA
und neu/entfernt sind Hinweise (kein Issue). Ergaenzt `verify`: jenes prueft
Drift einzelner zitierter Belege, dieses jede Seitenaenderung (auch noch nicht
zitierte, z.B. ein neuer Schritt).

### Schema-Versionierung

`SCHEMA_VERSION` liegt zentral in `src/tessera/contract.py` (eine Wahrheitsquelle)
und wird von `schema.to_contract` (Ausgabe) und `validate_contract.py` (Pruefung)
gemeinsam genutzt. Der Validator behandelt eine **abweichende** (aber SemVer-
gueltige) `schema_version` als **Hinweis**, nicht als Fehler — eine kanonische
Datei aus dem Ziel-Repo darf einer anderen Contract-Generation angehoeren, ohne
faelschlich abgelehnt zu werden (Gate-Paritaet). Ein nicht-SemVer-Wert bleibt ein
Fehler. Bump-Prozess (wenn das Ziel-Repo die Version anhebt): `SCHEMA_VERSION`
nachziehen, betroffene Felder in `schema.py`/`validate_contract.py` anpassen,
Fixtures/Doku abgleichen; bei Unsicherheit ueber die kanonische Bedeutung stoppen
und fragen (Cross-Repo-Grenze).

**Leitprinzipien (gelten fuer jeden Schritt):** propose-don't-write, Default =
Abstinenz bei bindenden Werten, Tri-State (Umgebung ≠ Daten), kleine Commits +
frueher Draft-PR, bei Unsicherheit ueber Schema/Quelle/Recht stoppen und fragen.
