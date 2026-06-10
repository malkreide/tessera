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
