# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- High-risk legal-case policy (`src/tessera/risk.py` as single source of truth):
  `baugesuch`, `sozialhilfe`, `veranstaltung` are reputation-critical and remain
  excluded from automated v1 extraction. Heightened review where they touch the
  pipeline: the contract validator turns an `unverifiziert`/ungrounded reference
  into a hard **error** (not a warning) for these ids, prints a `HOCHRISIKO`
  banner, and recommends a visible high-risk `disclaimer_key`; the draft PR body
  carries a prominent high-risk reviewer checklist. New stdlib tests
  (`tests/test_risk.py`) and fixtures (`examples/baugesuch.json`,
  `examples/invalid-high-risk-ungrounded.json`) wired into CI. Governance docs
  (README EN/DE, `docs/v1-pipeline.md`, `CLAUDE.md`) reconcile the "v1 is
  low-risk" story with v0 already shipping hand-authored heavy cases.
- Lossless field-wise merge against existing hand-curated target files
  (`src/tessera/merge.py`): existing non-empty i18n locales (`de/en/fr/it/ls`)
  and `description` blocks are never emptied; extraction only fills gaps and adds
  new structure, merged by business key (`step_id`/`reference_id`/`actor.id`).
  Non-mergeable cases are skipped, not impoverished. The draft PR carries a
  reviewer warning listing preserved/added fields, so tessera PRs pass the target
  repo's `check:regression` guard without `ALLOW_PROZESS_SHRINK`. Covered by
  `tests/test_merge.py` (in CI).
- v1 core pipeline (`src/tessera/`, plain loop, no orchestration framework):
  `preflight` (I14Y public API + eCH-0070 inventory -> `reports/coverage.md`;
  robots.txt/ToU -> `reports/scraping-compliance.md`, hard crawl gate on
  disallow), `crawl` (Crawl4AI -> Markdown snapshots, documented Trafilatura
  fallback), `extract` (pydantic-ai, strict structure-only schema, provider/
  model/key from ENV only), `grounding` (status-aware gate: unverifiable
  reference -> `unverifiziert` + flag, unverifiable step -> dropped + DAG
  rewiring + flag), `pr` (one draft PR per service against `TARGET_REPO`;
  without `GITHUB_TOKEN` the bundle lands in `out/outbox/`). Every output must
  pass `scripts/validate_contract.py` (exit 0) before a PR is built.
- Curated source list `sources.yaml` (hund-anmelden, umzug-melden); URLs
  manually verified 2026-06-11.
- stdlib tests for the grounding gate (`tests/test_grounding.py`) wired into CI.
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
- v1: first extraction runs + draft PRs into Maschinerie (pipeline is built;
  needs a session with `ANTHROPIC_API_KEY` / `GITHUB_TOKEN` set by the maintainer),
  then widen the curated set (~10 processes).

## [0.0.1] - 2026-06-09

### Added
- Repository scaffold
- House rules for Claude Code (`CLAUDE.md`)
- Data contract draft (`docs/data-contract.md`)
- Curated-sources template (`sources.example.yaml`)
- Project metadata and intended dependencies (`pyproject.toml`)

> No functional pipeline yet. The extraction layer (v1) is gated behind the v0
> proof-of-value step in the `maschinerie-zuerich` repo.
