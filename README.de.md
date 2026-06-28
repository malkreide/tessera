# Tessera

![Status](https://img.shields.io/badge/status-early%20scaffold-orange)
![Version](https://img.shields.io/badge/version-0.0.1-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.11+-blue)

> Offene KI-Agenten, die Verwaltungsprozesse in modulare, maschinenlesbare Bausteine (*tesserae*) überführen — als Zulieferung für [Maschinerie Zürich](https://github.com/malkreide/maschinerie-zuerich).

[🇬🇧 English Version](README.md)

## Übersicht

Eine *Tessera* ist ein einzelnes Mosaiksteinchen. Dieses Projekt extrahiert die
**Prozess-Ebene** der öffentlichen Verwaltung — wie ein Verfahren tatsächlich
abläuft — und gibt sie als kleine, belegbare, maschinenlesbare Steinchen aus, die
sich in die Visualisierung [Maschinerie Zürich](https://github.com/malkreide/maschinerie-zuerich)
einfügen. Die Maschinerie zeigt *Strukturen* (wer ist zuständig); Tessera ergänzt
*Prozesse* (wie ein Verfahren abläuft).

**Status: nur Grundgerüst.** Es gibt noch keine funktionsfähige Pipeline. Das System
wird bewusst in Stufen gebaut (siehe *Roadmap*), und die Extraktions-Schicht ist
hinter einen Nutzen-Nachweis gehängt, der im Maschinerie-Repo liegt, nicht hier.

> **Keine amtliche Quelle.** Tessera ist ein unabhängiges Open-Source-Projekt. Der
> Output ist eine *inoffizielle* Verständnishilfe zu Verwaltungsprozessen.
> Verbindlich ist allein die verlinkte Originalseite der zuständigen Behörde. Eine
> Verbindung zur oder Billigung durch die Stadt Zürich ist nicht impliziert.

## Designprinzipien

- **«Link, don't assert».** Rechtlich bindende Werte (Fristen, Gebühren,
  Rekursfristen) werden nie als eigenständige autoritative Fakten republiziert —
  sie werden auf die exakte Originalquelle verlinkt. Nur die Prozess-*Struktur*
  (Akteure, Schritte, Reihenfolge, Abhängigkeiten) wird als Daten abgebildet.
- **Human-in-the-Loop.** Jede Extraktion wird als Pull Request gegen das
  Maschinerie-Repo publiziert und vor dem Merge von einem Menschen reviewt. Die
  Pipeline merged nie selbst.
- **Belegbarkeit statt Selbsteinschätzung.** Jedes extrahierte Element muss als
  wörtliche Stelle in der Quelle belegbar sein; nicht belegbare Elemente werden
  verworfen und geflaggt, nicht angezeigt. Kein Modell-Selbsteinschätzungs-Score
  als Publish-Schwelle.
- **Konsumieren statt neu entdecken.** Der Leistungskatalog wird aus bestehenden
  maschinenlesbaren Inventaren (eCH-0070, I14Y) bezogen, nicht von Grund auf
  gecrawlt.
- **Standard-ausgerichtet.** Schema-Feldnamen folgen eCH-0073 und dem EU Core
  Public Service Vocabulary (CPSV), wo das ohne Mehraufwand geht.

## Roadmap (gestuft)

| Stufe | Lebt in | Scope |
|---|---|---|
| **v0** | `maschinerie-zuerich` | 2–3 von Hand modellierte Prozesse als Nutzen-Nachweis (keine Pipeline) |
| **v1** | **`tessera`** | Extraktion der Prozess-*Struktur* für ~10 kuratierte Prozesse → PR in die Maschinerie |
| **v2** | `tessera` | Validierungs-Loop, Schema-Versionierung, Änderungs-Diff-Cron |
| **v3** | `tessera` | Optionale Module: PDF/Vision-Parsing, RAG-Gesetzesabgleich, BPMN/eCH-0096-Export |

**Die Baureihenfolge ist ein Gate:** v1 nicht starten, bevor v0 gemergt und im
Vercel-Preview der Maschinerie als nützlich bestätigt ist.

### Risiko-Haltung vs. schwere Rechtsfälle

«v1 ist risikoarm» beschreibt Tesseras **automatischen** Output, nicht die ganze
Maschinerie. v0 zeigt bereits einige der schwersten Rechtsfälle — Baubewilligung
(`baugesuch`), Sozialhilfe (`sozialhilfe`), Veranstaltungsbewilligung (`veranstaltung`)
— als **von Hand modellierte, menschlich reviewte** Prozesse. Das ist legitim (ein
Mensch hat sie modelliert und geprüft), aber sie tragen das höchste Reputationsrisiko:
eine falsche Frist/Gebühr, auf die sich jemand verlässt, ist realer Schaden. Beide
Aussagen passen zusammen — **gerade weil** diese Fälle menschlich kuratierter
v0-Inhalt sind, während Tesseras Pipeline sie in v1 bewusst von der Extraktion
**ausschliesst** (siehe `sources.yaml`).

Wo ein solcher Fall die Pipeline dennoch berührt (z.B. ein Merge gegen eine bestehende
Datei), gilt erhöhter Review — einmal definiert in `src/tessera/risk.py` und vom
Vertrags-Validator erzwungen:

- **Jede bindende Reference muss wörtlich belegt sein.** Bei einem Hochrisiko-Prozess
  ist eine `unverifiziert`e / ungrounded Reference ein harter **Fehler**, kein Hinweis
  — ein reputationskritischer Prozess darf kein unbelegtes Frist-/Gebühren-Label tragen.
- **Ein sichtbarer Hochrisiko-Disclaimer wird erwartet** (`disclaimer_key`), und der
  Draft-PR trägt eine prominente Hochrisiko-Reviewer-Checkliste.

## Voraussetzungen

- Python 3.11+
- Ein GitHub-Token mit Schreibrecht auf das **Ziel**-Repo (`maschinerie-zuerich`),
  um Pull Requests zu öffnen (richtest du selbst ein; nie committen)
- Ein LLM-Provider-Key, konfiguriert über Umgebungsvariable

## Installation

```bash
git clone https://github.com/malkreide/tessera.git
cd tessera
uv sync          # oder: python -m venv .venv && pip install -e ".[dev]"
```

## Verwendung / Quickstart

```bash
# Pre-flight (Pflicht vor jedem Crawl): Inventar-Abdeckung (I14Y, eCH-0070)
# und robots.txt/Nutzungsbedingungen prüfen — schreibt nach reports/
tessera preflight

# Einzelne Schritte (jeweils optional auf eine Leistung begrenzbar)
tessera crawl    --id hund-anmelden    # Quellseiten → Markdown-Snapshots
tessera extract  --id hund-anmelden    # LLM-Extraktion + Grounding-Gate → out/
tessera validate --id hund-anmelden    # Vertrags-Validator (muss Exit 0 liefern)
tessera pr       --id hund-anmelden    # Draft-PR-Bundle bauen / einreichen

# Oder alles in Reihenfolge
tessera run --id hund-anmelden

# Re-Verifikation (propose-only, schreibt nie in out/): Label↔Wert-Befunde;
# mit --online zusätzlich tri-state Link-Rot (tot/blockiert/netzfehler) + Drift
tessera verify  --id hund-anmelden --online
```

Ohne `GITHUB_TOKEN` wird kein PR eingereicht; das fertige Bundle (JSON +
PR-Body mit Reviewer-Checkliste) liegt dann in `out/outbox/<id>/`.

## Konfiguration

Umgebungsvariablen — Keys werden nie committet und nie geloggt:

| Variable | Zweck |
|---|---|
| `TESSERA_MODEL` | pydantic-ai-Modellstring; Default `anthropic:claude-opus-4-8` |
| `ANTHROPIC_API_KEY` | Key des LLM-Providers (bzw. der zum Modell passende Key) |
| `GITHUB_TOKEN` | Schreibrecht auf das Ziel-Repo für die PR-Erstellung (optional) |
| `TARGET_REPO` | Default: `malkreide/maschinerie-zuerich` |

### Secrets über `.env`

tessera liest Keys **ausschliesslich** aus der Prozess-Umgebung (`os.environ`) und
lädt eine `.env`-Datei **nicht** automatisch. Der `.env`-Weg bedeutet: Secrets
einmal in eine gitignorierte Datei schreiben und vor dem Lauf in die Shell laden.
Das ist besser, als jede Sitzung `$env:`/`export` neu zu tippen — eine einzige
Stelle, die du bei Rotation aktualisierst, nichts wird in die Konsole eingefügt
(also kein Key in Shell-History, Screenshots oder Chat), und `.env` / `.env.*` sind
gitignored, sodass ein Key nie committet werden kann (nur die nicht-geheime Vorlage
`.env.example` ist eingecheckt).

Einmalig einrichten:

```bash
cp .env.example .env      # danach .env oeffnen und Werte eintragen
```

Pro Shell laden, dann ausführen:

```bash
# macOS / Linux / WSL (bash, zsh)
set -a; source .env; set +a
tessera run --id hund-anmelden
```

```powershell
# Windows PowerShell — tessera hat keinen Auto-Loader, also .env selbst importieren.
# Diese Funktion ins Profil ($PROFILE) legen, dann ist sie wiederverwendbar:
function Import-DotEnv {
    param([string]$Path = ".env")
    if (-not (Test-Path $Path)) { Write-Warning "$Path nicht gefunden"; return }
    Get-Content $Path | Where-Object { $_ -match '^\s*[^#].+=' } | ForEach-Object {
        $name, $value = $_ -split '=', 2
        Set-Item -Path "Env:$($name.Trim())" -Value $value.Trim().Trim('"')
    }
}

Import-DotEnv
tessera run --id hund-anmelden
```

Hinweise:

- **Pro Shell laden.** Ein geladener Wert gilt nur für die aktuelle Sitzung; ein
  neues Fenster braucht den Lade-Schritt erneut.
- **Nach einer Key-Rotation** `.env` aktualisieren und neu laden (`Import-DotEnv` /
  erneut `source`) — beide überschreiben eine bereits gesetzte Variable, sodass ein
  alter, widerrufener Key in der Sitzung ersetzt wird. Ein Lauf mit dem alten Key
  scheitert mit `401 invalid x-api-key`.
- `.env` ist Klartext — über normale Dateiberechtigungen schützen und nie teilen.
  Für höhere Anforderungen einen Secret-Manager nutzen; für lokale Entwicklung ist
  `.env` der übliche, ausreichende Weg.
- Werte ohne Anführungszeichen schreiben (`ANTHROPIC_API_KEY=sk-ant-…`).

## Projektstruktur

```
tessera/
├── README.md / README.de.md   # diese Datei (EN Haupt-, DE Übersetzung)
├── CLAUDE.md                   # Hausregeln für Claude Code (pro Session verbindlich)
├── docs/
│   └── data-contract.md        # der Datenvertrag tessera ↔ Maschinerie
├── sources.example.yaml        # Vorlage für die kuratierte Prozessliste
├── pyproject.toml              # Projekt-Metadaten + vorgesehene Dependencies
├── reports/                    # committete Audit-Artefakte (Abdeckung, Compliance)
└── src/tessera/                # Pipeline-Code (in v1 via Claude Code gebaut)
```

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md).

## Lizenz

Code: MIT — siehe [LICENSE](LICENSE).
Extrahierte Daten referenzieren die offenen Daten und öffentlichen Seiten der Stadt
Zürich; verbindlich bleibt die verlinkte Originalquelle.

## Autor

malkreide · [github.com/malkreide](https://github.com/malkreide)
