# Tessera

![Status](https://img.shields.io/badge/status-early%20scaffold-orange)
![Version](https://img.shields.io/badge/version-0.0.1-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.11+-blue)

> Open AI agents that turn public-sector processes into modular, machine-readable building blocks (*tesserae*) — feeding [Maschinerie Zürich](https://github.com/malkreide/maschinerie-zuerich).

[🇩🇪 Deutsche Version](README.de.md)

## Overview

A *tessera* is a single tile in a mosaic. This project extracts the **process layer**
of public administration — how a procedure actually flows — and emits it as small,
verifiable, machine-readable tiles that snap into the [Maschinerie Zürich](https://github.com/malkreide/maschinerie-zuerich)
visualization. The Maschinerie shows *structures* (who is responsible); Tessera adds
*processes* (how a procedure runs).

**Status: scaffold only.** There is no functional pipeline yet. The system is built
in deliberate stages (see *Roadmap*), and the extraction layer is gated behind a
proof-of-value step that lives in the Maschinerie repo, not here.

> **Not an official source.** Tessera is an independent open-source project. Its
> output is an *unofficial* aid to understanding administrative processes. The
> binding source is always the linked original page of the responsible authority.
> No affiliation with, or endorsement by, the City of Zurich is implied.

## Design principles

- **Link, don't assert.** Legally binding values (deadlines, fees, appeal periods)
  are never republished as standalone authoritative facts — they are linked to the
  exact official source. Only process *structure* (actors, steps, order,
  dependencies) is represented as data.
- **Human-in-the-loop.** Every extraction is published as a pull request against the
  Maschinerie repo and reviewed by a human before merge. The pipeline never merges.
- **Grounding over self-confidence.** Every extracted item must be traceable to a
  verbatim span in the source; unverifiable items are dropped and flagged, not
  shown. No model self-confidence score gates publication.
- **Consume, don't rediscover.** The service catalogue is taken from existing
  machine-readable inventories (eCH-0070, I14Y), not crawled from scratch.
- **Standards-aligned.** Schema field names follow eCH-0073 and the EU Core Public
  Service Vocabulary (CPSV) where this is cheap.

## Roadmap (staged)

| Stage | Lives in | Scope |
|---|---|---|
| **v0** | `maschinerie-zuerich` | 2–3 hand-authored processes to prove the frontend value (no pipeline) |
| **v1** | **`tessera`** | Extraction of process *structure* for ~10 curated processes → PR into Maschinerie |
| **v2** | `tessera` | Validation loop, schema versioning, change-diff cron |
| **v3** | `tessera` | Optional modules: PDF/vision parsing, RAG legal cross-check, BPMN/eCH-0096 export |

**Build order is a gate:** do not start v1 until v0 is merged and confirmed useful in
the Maschinerie's Vercel preview.

## Prerequisites

- Python 3.11+
- A GitHub token with write access to the **target** repo (`maschinerie-zuerich`),
  for opening pull requests (set up by you; never committed)
- An LLM provider key, configured via environment variable

## Installation

```bash
git clone https://github.com/malkreide/tessera.git
cd tessera
uv sync          # or: python -m venv .venv && pip install -e ".[dev]"
```

## Usage / Quickstart

> Not yet functional — this is the intended entry point once v1 is built.

```bash
# Pre-flight: check existing inventories + scraping rules (writes to reports/)
tessera preflight

# Extract one curated process and open a review PR against the Maschinerie repo
tessera run --service hund-anmelden
```

## Configuration

Environment variables (see `.env.example` once created):

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` / `LLM_API_KEY` | Model used for structured extraction |
| `GITHUB_TOKEN` | Write access to the target repo for PR creation |
| `TARGET_REPO` | Default: `malkreide/maschinerie-zuerich` |

## Project Structure

```
tessera/
├── README.md / README.de.md   # this file (EN main, DE translation)
├── CLAUDE.md                   # house rules for Claude Code (binding per session)
├── docs/
│   └── data-contract.md        # the tessera ↔ Maschinerie schema contract
├── sources.example.yaml        # template for the curated process list
├── pyproject.toml              # project metadata + intended dependencies
├── reports/                    # committed audit artifacts (coverage, compliance)
└── src/tessera/                # pipeline code (built in v1 via Claude Code)
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

Code: MIT — see [LICENSE](LICENSE).
Extracted data references the City of Zurich's open data and public pages; the
binding source remains the linked original.

## Author

malkreide · [github.com/malkreide](https://github.com/malkreide)
