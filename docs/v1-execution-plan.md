# v1-Ausführungs- & Entwicklungsplan

> **Zweck.** Dieses Dokument führt tessera vom Stand «Mechanik vollständig im Code,
> getestet» zur **Definition of Done** aus `docs/v1-pipeline.md` (echte Pre-Flight-
> Reports, 2–3 echte Extraktionen, je ein Draft-PR gegen `maschinerie-zuerich`) und
> skizziert die Härtung danach.
>
> **Lesart.** Jeder Schritt hat: **Ziel**, **Vorbedingung**, **Aktion**,
> **Erwartetes Resultat**, **Test-Setting** (wie man Erfolg deterministisch prüft)
> und **Prompt** (copy-paste für eine Claude-Code-Session). Prompts an den
> *Maintainer* (Keys, Freigaben) sind als solche markiert — die fasst der Agent
> nicht an (Credentials-Grenze, `CLAUDE.md`).
>
> **Zwei nicht verhandelbare Gates** (aus `CLAUDE.md`):
> 1. **Baureihenfolge:** kein echter Extraktions-/PR-Lauf, bevor v0 im Maschinerie-
>    Repo gemergt **und** im Vercel-Preview als nützlich bestätigt ist.
> 2. **Credentials-Grenze:** Keys/Tokens setzt ausschliesslich der Maintainer im ENV;
>    nie in Code/Commit/Log.

---

## Übersicht der Phasen

| Phase | Inhalt | Gate/Keys nötig | Ergebnis |
|---|---|---|---|
| 0 | Freigabe & Umgebung | v0-Gate, Maintainer-Keys | lauffähige, freigegebene Umgebung |
| 1 | Pre-Flight real | Netz-Policy | echte `coverage.md` + `scraping-compliance.md` + Gate-File |
| 2 | Crawl (1. Leistung) | Netz, opt. Chromium | Snapshots + `meta.json` |
| 3 | Extract + Ground | `ANTHROPIC_API_KEY` | `out/<id>.json` + Flags |
| 4 | Validate (inkl. strict) | — | Exit 0 |
| 5 | Verify (online) | Netz | `reports/verify/<id>.md`, keine Datenprobleme |
| 6 | Draft-PR emittieren | `GITHUB_TOKEN` | Draft-PR in Maschinerie, CI grün |
| 7 | 2. Leistung + Wiederholung | wie 2–6 | DoD erreicht (2–3 Leistungen) |
| 8 | Härtung: Golden-Test + Link-Rot-Cron | — | Integrationsnetz + laufende Hygiene |
| 9 | Set erweitern (~10) | wie 2–6 | breitere Abdeckung |
| 10 | v2-Ausblick | — | priorisierter Backlog |

**Empfohlene Pilot-Leistung:** `hund-anmelden` (rein kommunal, risikoarm, SSR-Quelle
stadt-zuerich.ch, klar belegbare Frist/Abgabe). Zweite: `umzug-melden`.

---

## Phase 0 — Freigabe & Umgebung

### Schritt 0.1 — Baureihenfolge-Gate bestätigen
- **Ziel:** belegen, dass v0 im Maschinerie-Repo gemergt und als nützlich bestätigt ist.
- **Vorbedingung:** Zugriff/Info zum Maschinerie-Repo (separat).
- **Aktion (Maintainer):** Link zum gemergten v0-PR + Vercel-Preview bereitstellen; in
  diesem Repo als kurze Notiz festhalten.
- **Erwartetes Resultat:** dokumentierte Freigabe (z.B. ein Satz + Link in
  `reports/README.md` oder einem `reports/v0-freigabe.md`).
- **Test-Setting:** menschliche Bestätigung; keine Automatik. Ohne diese Freigabe →
  **Stopp**, kein echter Lauf.
- **Prompt (Maintainer):** «v0 ist gemergt: <PR-Link>, Preview nützlich bestätigt:
  <Vercel-Link>. Freigabe für tessera-Echtläufe erteilt.»

### Schritt 0.2 — Datenvertrag gegen kanonisches Schema abgleichen
- **Ziel:** sicherstellen, dass das tessera-Ausgabeformat exakt dem kanonischen
  v0-Schema in `maschinerie-zuerich` entspricht (Cardinal: bei Abweichung stoppen,
  nicht raten).
- **Vorbedingung:** Lesezugriff auf das kanonische Schema + echte Prozess-JSONs im
  Maschinerie-Repo.
- **Aktion:** kanonische `*.json` herunterladen und gegen `scripts/validate_contract.py`
  laufen lassen; Abweichungen in `docs/data-contract.md` dokumentieren.
- **Erwartetes Resultat:** alle kanonischen Dateien bestehen den Validator 1:1
  (Stand Repo: «alle 8 live kanonischen JSONs bestehen»); jede Abweichung ist notiert.
- **Test-Setting:**
  ```bash
  python scripts/validate_contract.py /pfad/zu/maschinerie/.../*.json
  # Exit 0 erwartet; Abweichung => docs/data-contract.md ergänzen + Rückfrage
  ```
- **Prompt (Claude Code):**
  > Lies das kanonische Prozess-Schema und alle Prozess-JSONs aus dem Maschinerie-Repo
  > (Pfad: `stadt-zuerich-next/data/prozesse/zh/`). Validiere sie mit
  > `scripts/validate_contract.py`. Wenn alle Exit 0 liefern, bestätige das. Wenn nicht,
  > liste jede Abweichung auf, ändere NICHTS am Schema, sondern dokumentiere sie in
  > `docs/data-contract.md` und stoppe für Rückfrage.

### Schritt 0.3 — Runtime-Deps installieren + Smoke-Test
- **Ziel:** lauffähige Umgebung; bestätigte Dependencies (CLAUDE.md: neue Deps nur
  nach Rückfrage).
- **Vorbedingung:** Schritt 0.1 erteilt; Python 3.11+.
- **Aktion:** venv anlegen, `pip install -e .` (zieht `crawl4ai`, `pydantic`,
  `pydantic-ai`, `httpx`, `pyyaml`, `openpyxl`); optional `playwright install chromium`.
- **Erwartetes Resultat:** `tessera --help` läuft; Import-Smoke ohne Fehler; Chromium
  optional (sonst SSR-only, dokumentiert).
- **Test-Setting:**
  ```bash
  python -m venv .venv && . .venv/bin/activate
  pip install -e .
  tessera --help                 # zeigt preflight|crawl|extract|validate|verify|pr|run
  python -c "import tessera.crawl, tessera.extract, tessera.verify"   # Import-Smoke
  python tests/run_checks.py && python tests/test_grounding.py \
    && python tests/test_binding.py && python tests/test_verify.py \
    && python tests/test_merge.py && python tests/test_risk.py        # stdlib-Suite grün
  ```
- **Prompt (Claude Code):**
  > Lege ein venv an und installiere das Projekt editierbar (`pip install -e .`).
  > Führe danach `tessera --help` und einen Import-Smoke-Test aus, dann die komplette
  > stdlib-Testsuite. Berichte, ob Chromium für `crawl4ai` verfügbar ist; wenn nicht,
  > halte fest, dass nur der SSR-Pfad läuft. Installiere keine zusätzlichen, nicht in
  > `pyproject.toml` gelisteten Pakete ohne Rückfrage.

### Schritt 0.4 — Secrets & Netz-Policy bereitstellen
- **Ziel:** key-fähige, netz-fähige Session (ohne Keys im Code).
- **Aktion (Maintainer):** im ENV setzen: `ANTHROPIC_API_KEY`, `GITHUB_TOKEN` (Scope:
  PRs im Ziel-Repo), `TARGET_REPO=malkreide/maschinerie-zuerich`, optional
  `TESSERA_MODEL`; ausgehende HTTPS-Policy gemäss `docs/v1-pipeline.md` freischalten
  (i14y.admin.ch, stadt-zuerich.ch, zh.ch, …).
- **Erwartetes Resultat:** `env | grep -E 'ANTHROPIC|GITHUB'` zeigt gesetzte Keys
  (nur lokal, nie loggen); Quelldomains erreichbar.
- **Test-Setting:** `tessera verify --id hund-anmelden --online` gegen eine bereits
  vorhandene Datei zeigt `ok`/`blockiert` statt `netzfehler` (prüft Erreichbarkeit
  ohne Keys). Key-Präsenz prüft der Extract-Schritt selbst (`extract._require_key`).
- **Prompt (Maintainer):** «Keys sind im ENV gesetzt (ANTHROPIC_API_KEY, GITHUB_TOKEN,
  TARGET_REPO); Netz-Policy für die Quelldomains ist offen.»

---

## Phase 1 — Pre-Flight (real)

### Schritt 1.1 — `tessera preflight` ausführen
- **Ziel:** Katalog-Abdeckung + Rechtsflächen-Check aus echten Abrufen.
- **Vorbedingung:** Netz-Policy (i14y.admin.ch, eCH-XLSX-Quelle, Quelldomains).
- **Aktion:** `tessera preflight --id hund-anmelden --id umzug-melden`.
- **Erwartetes Resultat:** `reports/coverage.md` (I14Y- + eCH-Treffer pro Leistung),
  `reports/scraping-compliance.md` (robots-Verdikt je URL), `reports/raw/preflight-gate.json`
  mit `allowed: true` für beide Leistungen.
- **Test-Setting:**
  ```bash
  tessera preflight --id hund-anmelden --id umzug-melden
  python -c "import json;g=json.load(open('reports/raw/preflight-gate.json'));\
print({k:v['allowed'] for k,v in g.items()})"   # beide True erwartet
  ```
- **Prompt (Claude Code):**
  > Führe `tessera preflight` für `hund-anmelden` und `umzug-melden` aus. Zeige mir die
  > robots-Verdikte und die Katalog-Treffer aus `reports/`. Wenn eine URL `DISALLOW`
  > liefert, crawle sie NICHT, flagge sie und stoppe für Rückfrage.

### Schritt 1.2 — Compliance-Review (Mensch)
- **Ziel:** robots.txt/ToU bewusst akzeptieren.
- **Aktion:** `reports/scraping-compliance.md` lesen; ToU der Quelldomains kurz prüfen.
- **Erwartetes Resultat:** dokumentierte Freigabe oder Stopp.
- **Test-Setting:** menschliche Sichtung; **Stop-Bedingung** bei Disallow/ToU-Verbot.

---

## Phase 2 — Crawl (Pilot: hund-anmelden)

### Schritt 2.1 — Snapshots erzeugen
- **Ziel:** sauberer Markdown-Belegkorpus, SSR-first, ehrliche Degradation.
- **Vorbedingung:** Pre-Flight `allowed`.
- **Aktion:** `tessera crawl --id hund-anmelden`.
- **Erwartetes Resultat:** `reports/raw/hund-anmelden/NN-*.md` + `meta.json` mit pro URL:
  `http_status`, `state` (`ok`), `spa_suspected: false` (stadt-zuerich.ch ist SSR),
  `extractor: "httpx+trafilatura"`, `chars > 0`.
- **Test-Setting:**
  ```bash
  tessera crawl --id hund-anmelden
  python -c "import json;m=json.load(open('reports/raw/hund-anmelden/meta.json'));\
[print(x['url'],x['state'],x['spa_suspected'],x['chars']) for x in m]"
  # Erwartung: state==ok, spa_suspected==False, chars deutlich > 0
  ```
- **Prompt (Claude Code):**
  > Crawle `hund-anmelden`. Prüfe `meta.json`: erwartet `state==ok` und
  > `spa_suspected==false` für stadt-zuerich.ch. Falls eine Quelle als SPA erkannt
  > wird und kein Browser verfügbar ist, melde das ehrlich (App-Shell) und schlage vor,
  > den Crawl in einer Umgebung mit Chromium zu wiederholen — fake keinen Inhalt.

---

## Phase 3 — Extract + Grounding

### Schritt 3.1 — Extraktion mit Grounding-Gate
- **Ziel:** struktur-only-JSON, jede Reference/jeder Schritt verbatim belegt.
- **Vorbedingung:** `ANTHROPIC_API_KEY` gesetzt; brauchbare Snapshots.
- **Aktion:** `tessera extract --id hund-anmelden`.
- **Erwartetes Resultat:** `out/hund-anmelden.json` (Kardinalregel-konform: keine Zahl
  im Label) + `out/hund-anmelden.flags.json`. Erwartete Flags-Kategorien: nicht belegte
  References → `unverifiziert`; Label↔Wert-Mismatch → Abstinenz-Flag.
- **Test-Setting:**
  ```bash
  tessera extract --id hund-anmelden
  cat out/hund-anmelden.flags.json     # Flags menschlich sichten
  python scripts/validate_contract.py out/hund-anmelden.json   # Exit 0
  ```
- **Prompt (Claude Code):**
  > Extrahiere `hund-anmelden`. Zeige mir alle Grounding-Flags und erkläre pro Flag, ob
  > es eine fehlende Belegstelle oder ein Label↔Wert-Mismatch ist. Ändere die Ausgabe
  > nicht von Hand — wenn eine wichtige Reference unbelegt bleibt, lass sie
  > `unverifiziert` und markiere sie im späteren PR als offen.

### Schritt 3.2 — Inhaltlicher Review (Mensch)
- **Ziel:** Schritte/Reihenfolge entsprechen der offiziellen Darstellung; Fristen/Abgaben
  korrekt verlinkt.
- **Test-Setting:** Reviewer-Checkliste aus dem späteren PR-Body; Abgleich mit der
  Originalseite.

---

## Phase 4 — Validate

### Schritt 4.1 — Vertrags-Validator (optional strikt)
- **Ziel:** deterministisches Eingangs-Gate; Exit 0 = Publikations-Voraussetzung.
- **Aktion:** `python scripts/validate_contract.py out/hund-anmelden.json`; optional
  `--strict-label-value` (für gemergte/handnahe Dateien).
- **Erwartetes Resultat:** Exit 0; Hinweise (i18n-ausstehend, Label↔Wert) bewusst ok.
- **Test-Setting:**
  ```bash
  python scripts/validate_contract.py out/hund-anmelden.json; echo "exit=$?"
  TESSERA_STRICT_LABEL_VALUE=1 python scripts/validate_contract.py out/hund-anmelden.json
  # strikt: deckt versteckte Label↔Wert-Mismatches als Fehler auf
  ```
- **Prompt (Claude Code):**
  > Validiere `out/hund-anmelden.json` normal und mit `--strict-label-value`. Wenn der
  > strikte Lauf Fehler zeigt, die der normale nur als Hinweis hatte, erkläre sie und
  > schlage vor, die betroffene Reference auf `unverifiziert` zu setzen statt einen
  > falschen Wert zu publizieren.

---

## Phase 5 — Re-Verifikation (online)

### Schritt 5.1 — Link-Rot + Drift vor dem PR
- **Ziel:** Belege gegen die Live-Seite bestätigen; tote Links früh fangen.
- **Aktion:** `tessera verify --id hund-anmelden --online`.
- **Erwartetes Resultat:** `reports/verify/hund-anmelden.md`; **keine** Datenprobleme
  (`tot`/Drift). `blockiert`/`netzfehler`/SPA-`ungeprüft` sind Umgebungsbefunde (Exit 0).
- **Test-Setting:**
  ```bash
  tessera verify --id hund-anmelden --online; echo "exit=$?"   # 0 erwartet
  # exit=1 nur bei tot/Drift -> Quelle re-discovern bzw. Zitat neu belegen
  ```
- **Prompt (Claude Code):**
  > Führe `tessera verify --id hund-anmelden --online` aus. Bei `tot` (404/410): schlage
  > eine neue offizielle URL vor (nicht still ersetzen). Bei Drift: zeige altes vs.
  > aktuelles Zitat. Unterscheide klar Datenprobleme von Umgebungsbefunden.

---

## Phase 6 — Draft-PR emittieren

### Schritt 6.1 — `tessera pr`
- **Ziel:** ein Draft-PR pro Leistung gegen `TARGET_REPO`, feldweiser Merge gegen
  bestehende Handdaten, nie main-Push.
- **Vorbedingung:** `GITHUB_TOKEN`; Validator Exit 0.
- **Aktion:** `tessera pr --id hund-anmelden`. (Ohne Token: Bundle in `out/outbox/`.)
- **Erwartetes Resultat:** Draft-PR im Maschinerie-Repo mit Reviewer-Checkliste; bei
  bestehender Zieldatei Merge-Warnung (erhaltene/ergänzte Felder); lokales Bundle in
  `out/outbox/hund-anmelden/`.
- **Test-Setting:** PR ist `draft: true`, Branch `tessera/hund-anmelden-<datum>`; im
  Ziel-Repo werden `validate:prozesse`, `check:regression`, `check:links` grün (Ziel-CI).
  Ohne Token-Lauf: `out/outbox/hund-anmelden/{hund-anmelden.json,PR_BODY.md}` existieren.
- **Prompt (Claude Code):**
  > Erzeuge den Draft-PR für `hund-anmelden` gegen `TARGET_REPO`. Wenn die Zieldatei
  > existiert, merge feldweise (keine Übersetzungs-Regression) und hänge die
  > Merge-Warnung an. Verifiziere danach, dass die Ziel-Repo-CI (`validate:prozesse`,
  > `check:regression`, `check:links`) grün ist. Merge NICHT und pushe NICHT nach main.

### Schritt 6.2 — Review & Merge (Mensch)
- **Ziel:** menschliche Freigabe; tessera merged nie.
- **Test-Setting:** Maintainer reviewt PR + Checkliste, merged manuell.

---

## Phase 7 — Zweite Leistung + DoD-Abschluss
- **Aktion:** Schritte 2–6 für `umzug-melden` wiederholen (Quelle: zh.ch SSR;
  achte auf eUmzug-Verweise).
- **Erwartetes Resultat:** **Definition of Done erreicht** — 2 (–3) Leistungen
  extrahiert, validiert, je ein Draft-PR; echte Pre-Flight-Reports; keine Keys im Code.
- **Test-Setting:** DoD-Checkliste in `docs/v1-pipeline.md` abhaken; beide PRs offen/gemergt.
- **Prompt (Claude Code):**
  > Wiederhole den gesamten Ablauf (preflight→crawl→extract→validate→verify→pr) für
  > `umzug-melden`. Hake danach die Definition-of-Done-Liste in `docs/v1-pipeline.md`
  > anhand der tatsächlichen Artefakte ab und fasse den Stand zusammen.

---

## Phase 8 — Härtung (Code-Deliverables vor Skalierung)

### Schritt 8.1 — Golden-/Integrationstest (key-frei) — ✅ erledigt
> Umgesetzt in `tests/test_pipeline_integration.py`, in `contract-check.yml`
> verdrahtet (reine stdlib; der `to_contract`-Pfad wird zusaetzlich geprueft, wenn
> `pydantic` vorhanden ist, sonst sauber uebersprungen).

- **Ziel:** `extract→ground→to_contract→validate` ohne Netz/Keys testen (Vertrauen vor
  Skalierung), indem der LLM-Schritt durch eine fixierte XProcess-Antwort ersetzt wird.
- **Aktion (Entwicklung):** Test-Fixture = (Mini-Korpus-Markdown + gemockte
  `XProcess`-Ausgabe); `extract.extract_process` über einen injizierbaren Agenten/Stub
  umgehen; Resultat durch `grounding.apply_gate` + Validator schicken.
- **Erwartetes Resultat:** neuer `tests/test_pipeline_integration.py` (stdlib, in CI):
  belegte Schritte/Refs bleiben, unbelegte werden verworfen/`unverifiziert`,
  Label↔Wert-Mismatch → Abstinenz, Endergebnis besteht den Validator.
- **Test-Setting:** in `.github/workflows/contract-check.yml` aufnehmen; läuft ohne Deps.
- **Prompt (Claude Code):**
  > Baue `tests/test_pipeline_integration.py`: ein kleiner Markdown-Korpus + eine fest
  > verdrahtete `XProcess`-Antwort (kein echter LLM-Call), durch `to_contract`,
  > `grounding.apply_gate` und den Validator. Decke ab: belegter Schritt bleibt,
  > unbelegter wird verworfen mit Rewiring, Label↔Wert-Mismatch führt zu Abstinenz.
  > Verdrahte den Test in die CI. Kleiner Commit, Draft-PR.

### Schritt 8.2 — Link-Rot-Cron (laufende Hygiene) — ✅ erledigt
> Umgesetzt in `.github/workflows/link-rot.yml` (woechentlich + manueller
> Dispatch): `tessera verify --online` ueber `out/*.json`; Exit 1 nur bei
> Datenproblemen (tot/Drift), Umgebungsbefunde nur Log; schlanke Installation
> ohne Crawl4AI/Playwright; No-op solange nichts publiziert ist. Online-Dry-Run
> gegen eine bekannte Datei bestaetigt: Tri-State + Drift korrekt.

- **Ziel:** gespeicherte Belege regelmässig gegen die Live-Quellen prüfen.
- **Aktion (Entwicklung):** GitHub-Action `link-rot.yml` (zeitgesteuert) ruft
  `tessera verify --online` über die publizierten Leistungen; Exit 1 nur bei
  Datenproblemen (tot/Drift), Umgebungsbefunde nur als Log.
- **Erwartetes Resultat:** Workflow-Datei + dokumentierter Lauf; rotes CI = echter
  Befund, kein Umgebungsrauschen.
- **Test-Setting:** Workflow-Dry-Run gegen eine bekannte Datei; tri-state korrekt.
- **Prompt (Claude Code):**
  > Lege `.github/workflows/link-rot.yml` an, das wöchentlich `tessera verify --online`
  > für die publizierten Leistungen ausführt. Der Job darf nur bei echten Datenproblemen
  > (tot/Drift) fehlschlagen; Block/Netzfehler nur loggen. Beachte: braucht Netz-Policy;
  > dokumentiere das im Workflow-Kommentar.

---

## Phase 9 — Kuratiertes Set erweitern (~10 Leistungen)
- **Ziel:** Abdeckung verbreitern (weiterhin risikoarm, SSR-Quellen bevorzugt).
- **Aktion:** `sources.yaml` um geprüfte Leistungen ergänzen (URLs vorab auf HTTP 200
  prüfen, Subagent-Fan-out möglich); Phasen 1–6 je Leistung.
- **Erwartetes Resultat:** ~10 Leistungen mit je einem Draft-PR; `coverage.md` aktuell.
- **Test-Setting:** pro Leistung dieselbe Akzeptanz (Validator Exit 0, `verify` sauber,
  Ziel-CI grün). **Hochrisiko-IDs bleiben ausgeschlossen** (`risk.py`).
- **Prompt (Claude Code):**
  > Schlage 5–8 weitere risikoarme, kommunale Leistungen mit SSR-Quellen vor. Prüfe
  > jede Kandidaten-URL vorab auf HTTP 200 (tri-state) und nimm nur erreichbare auf.
  > Keine Hochrisiko-Fälle. Ergänze `sources.yaml` und begründe die Auswahl; warte mit
  > dem Crawl auf meine Freigabe.

---

## Phase 10 — v2-Ausblick (nur bei Bedarf, nach Rückfrage)
Priorisierter Backlog, bewusst **nicht** in v1 (`CLAUDE.md`):
1. **Struktur-Artikel-Fetcher für Recht** (Eingang Erlass + §/Art-Nummer/Anker,
   Akoma-Ntoso/PDF) statt Bag-of-Words — adressiert das «grep-Roulette» auf grossen
   Gesetzeskorpora.
2. **Tabellarische Bindewerte** (Gebühren-Widgets) mit explizitem Feld→Label-Mapping,
   sonst Abstinenz — ggf. Datenvertrag erweitern.
3. **Discovery-Agent / RAG-Gesetzesabgleich / BPMN-Export** — nur wenn der Nutzen belegt ist.

---

## Globales Test-Setting (Zusammenfassung)

| Ebene | Wann | Werkzeug | Erfolgskriterium |
|---|---|---|---|
| Unit (stdlib, key-frei) | jeder Commit / CI | `tests/*.py`, `run_checks.py` | alle grün |
| Integration (key-frei) | jeder Commit / CI (Phase 8.1) | `test_pipeline_integration.py` | Gate-Verhalten korrekt |
| Vertrags-Gate | vor jedem PR | `validate_contract.py` (Exit 0) | gültig |
| Beleg-Hygiene | vor PR + zeitgesteuert | `tessera verify --online` | keine tot/Drift |
| Ziel-Repo-CI | im Draft-PR | `validate:prozesse`, `check:regression`, `check:links` | grün |
| Mensch | vor Merge | Reviewer-Checkliste im PR-Body | freigegeben |

**Leitprinzipien (aus der Retrospektive, gelten für jeden Schritt):** propose-don't-write,
Default = Abstinenz bei bindenden Werten, Tri-State (Umgebung ≠ Daten), kleine Commits +
früher Draft-PR, bei Unsicherheit über Schema/Quelle/Recht stoppen und fragen.
