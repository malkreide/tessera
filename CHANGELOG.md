# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Machine-readable draft of the data contract as JSON Schema (`docs/process.schema.json`),
  explicitly non-canonical (canonical schema lives in `maschinerie-zuerich`).
- Dependency-free contract validator (`scripts/validate_contract.py`): structure,
  DAG integrity, reference integrity, grounding gate (`source_quote`), and a
  cardinal-rule lint (a binding value in a step label fails the check).
- Synthetic example fixtures (`examples/`): one valid process and one that
  intentionally violates the cardinal rule.
- v1 groundwork (offline, no new deps): curated `sources.yaml` (risk-light start
  set hund-anmelden + umzug-melden), pre-flight report templates
  (`reports/coverage.md`, `reports/scraping-compliance.md`), and the pipeline
  architecture (`docs/v1-pipeline.md`).

### Changed
- Aligned the draft contract, JSON Schema, and validator to the canonical v0
  schema in `maschinerie-zuerich`: Leichte-Sprache locale key `leichte_sprache`
  → `ls`; `depends_on` now accepts `{step_id, condition?}` (condition is i18n) for
  conditional edges; `retrieved_at` accepts a day-precision date in addition to a
  full timestamp; `preconditions` is now a list of i18n objects.
- Added the canonical additive fields so the validator and JSON Schema accept real
  canonical process files 1:1: process `$schema`/`city`/`description`/`actors`/
  `legal_basis`/`sources`/`reife`/`meta`; step `type`/`description`/`documents`/
  `source_id`/`loops_back_to`; reference `status`. The grounding gate is now
  status-aware (`verifiziert` requires a quote; `unverifiziert` may omit it).
  Verified: all 8 live canonical process JSONs pass both the validator and the
  JSON Schema. New fixtures `extensions-showcase.json` and
  `invalid-grounding-verifiziert.json`.

### Planned
- v1: structure-only extraction for ~10 curated processes, with PR into Maschinerie

## [0.0.1] - 2026-06-09

### Added
- Repository scaffold
- House rules for Claude Code (`CLAUDE.md`)
- Data contract draft (`docs/data-contract.md`)
- Curated-sources template (`sources.example.yaml`)
- Project metadata and intended dependencies (`pyproject.toml`)

> No functional pipeline yet. The extraction layer (v1) is gated behind the v0
> proof-of-value step in the `maschinerie-zuerich` repo.
