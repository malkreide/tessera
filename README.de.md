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

> Noch nicht funktionsfähig — das ist der vorgesehene Einstieg, sobald v1 gebaut ist.

```bash
# Pre-flight: bestehende Inventare + Scraping-Regeln prüfen (schreibt nach reports/)
tessera preflight

# Einen kuratierten Prozess extrahieren und einen Review-PR gegen die Maschinerie öffnen
tessera run --service hund-anmelden
```

## Konfiguration

Umgebungsvariablen (siehe `.env.example`, sobald angelegt):

| Variable | Zweck |
|---|---|
| `LLM_PROVIDER` / `LLM_API_KEY` | Modell für die strukturierte Extraktion |
| `GITHUB_TOKEN` | Schreibrecht auf das Ziel-Repo für die PR-Erstellung |
| `TARGET_REPO` | Default: `malkreide/maschinerie-zuerich` |

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
