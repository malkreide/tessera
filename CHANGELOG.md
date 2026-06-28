# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Curated `parkplatz` (Anwohnerparkkarte) into the v1 set (`sources.yaml`): four
  citizen-facing pages (Parkbewilligungen overview, Anwohnerparkkarte, the
  private-person application form, and the AGB/legal page for fees + appeal), all
  robots-allowed and HTTP 200 (verified 2026-06-28); pre-flight reports
  regenerated. Parking fee and appeal deadline are references only (label without
  the number + deep-link + verbatim quote). The canonical target file carries
  `actors[]` (`halter`, `dav`, `stapo`, `statthalter`), so actor reconciliation
  applies on merge. `parkplatz` is **not** a high-risk id (the appeal step
  notwithstanding), unlike `baugesuch`/`sozialhilfe`.
- Key-/network-free pipeline integration test (`tests/test_pipeline_integration.py`,
  wired into `contract-check.yml`): exercises the `extract -> to_contract ->
  grounding.apply_gate -> validate_contract` leg with a hard-wired extraction
  answer (no LLM call), asserting that a source-backed step survives, an invented
  (ungrounded) step is dropped with transitive DAG rewiring, a verbatim-but-wrong-
  value-type reference is downgraded to abstinence, an unverifiable reference
  becomes `unverifiziert`, and the gated result passes the contract validator.
  Pure stdlib so it runs in CI without dependencies; when `pydantic` is present it
  additionally verifies that `to_contract` produces exactly the fixture (otherwise
  that one leg self-skips, logged — never silently passes).
- `.github/workflows/link-rot.yml` (scheduled weekly + manual dispatch): ongoing
  evidence hygiene — runs `tessera verify --online` over the published outputs
  (`out/*.json`). Tri-state holds: only a dead link (404/410) or real quote drift
  fails the job; a 403/policy block, network error, or JS-SPA is an environment
  finding and only logged. Lean install (`httpx`, `pyyaml`, `pydantic`) — no
  Crawl4AI/Playwright/pydantic-ai. No-op (exit 0) while no service is published;
  needs the outbound HTTPS net policy for the source domains (documented inline).
- Curated `fundsache` (Fundbüro) into the v1 set (`sources.yaml`): five
  citizen-facing VBZ Fundbüro pages, all robots-allowed and HTTP 200 (verified
  2026-06-28); pre-flight reports regenerated for all three services. Fees,
  deadlines, and finder's-reward are expected as references only (label without
  the number + deep-link + verbatim quote). The canonical target file carries
  `actors[]` (`person`, `fundbuero`), so actor reconciliation applies on merge.
- Label↔value gate against the "right page, wrong value" failure mode
  (`src/tessera/binding.py`, single source of truth for binding-value detection):
  a reference whose label names a binding value type (deadline/duration vs.
  fee/amount) must carry a `source_quote` that actually substantiates that type.
  Enforced as **abstinence** in the grounding gate (verbatim-but-wrong-type →
  downgraded to `unverifiziert`, quote dropped, flagged; a hard error for
  high-risk ids via the validator), and surfaced as a reviewer **hint** in the
  contract validator (which has no corpus) — opt-in promotable to a hard **error**
  via `--strict-label-value` or `TESSERA_STRICT_LABEL_VALUE` (the env var is
  inherited by `tessera validate`/`pr`), useful for hand-curated/merged target
  files that never pass through the grounding gate. The cardinal-rule lint now imports
  its `BINDING_VALUE` regex from `binding.py` (unchanged behaviour). Covered by
  `tests/test_binding.py` and a new grounding test (in CI).
- `tessera verify` — re-verification of existing outputs (propose-only, never
  writes to `out/`; report to `reports/verify/<id>.md`). Offline: label↔value
  findings. `--online`: **tri-state** reachability per `source_url`
  (`tot` 404/410 ≠ `blockiert` 403/policy ≠ `netzfehler`) and verbatim **drift**
  of each verified quote against the live page (identical normalization as on
  save; a detected JS-SPA shell is reported as "ungeprüft — needs rendering", not
  drift). Only dead links and real drift are data problems (exit 1); environment
  findings never fail the run. Tri-state classification lives in
  `src/tessera/reach.py`; the HTTP fetch is injectable so the offline path is
  tested without httpx (`tests/test_verify.py`, in CI).
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
- LLM sampling: `temperature=0` is no longer sent to Anthropic models that
  reject sampling parameters (Opus 4.7/4.8, Fable, Mythos) — `src/tessera/extract.py`.
  pydantic-ai / the Anthropic SDK discard a set `temperature` on those models
  (warning, or a `400`), so the determinism it was meant to give silently
  evaporated. For these models reproducibility now rides on the prompt (and
  `effort`), not on sampling; `temperature=0` never guaranteed bit-identical
  outputs anyway. Older models and non-Anthropic providers still get
  `temperature=0` (gated by `_supports_sampling`).
- Extraction accuracy: the LLM step (`src/tessera/extract.py`) now runs in
  **two passes** — a draft plus a review/repair pass that checks the draft against
  the *same* corpus: it adds source-backed steps that were missed (recall),
  corrects wrong `depends_on` edges, and drops guessed elements. The review never
  invents evidence — the downstream grounding gate (`grounding.py`) still discards
  any element that is not verbatim-grounded, so recall rises without raising the
  hallucination risk. The pass is on by default; opt out with `TESSERA_REVIEW=0`.
- Crawl fetch order reversed to SSR-first (`src/tessera/crawl.py`): try httpx +
  Trafilatura first (most source pages are server-rendered and reachable via the
  proxy), auto-detect a real JS-SPA (app-shell markers / suspiciously little
  text) and only then fall back to a headless browser (Crawl4AI) — and only for
  that one URL. If the browser is unavailable in the environment, the app-shell
  is kept and the degradation is recorded honestly in `meta.json` (never faked).
  Snapshot metadata gains tri-state `state` and `spa_suspected`.
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

### Fixed
- Draft-PR creation is now idempotent across re-runs (`src/tessera/pr.py`): the
  branch name is day-stamped (`tessera/<id>-<date>`), so a second run the same day
  used to crash with `422` on `POST /git/refs` ("reference already exists"). Now an
  existing branch is reset to base (`PATCH /git/refs/heads/...`, force) instead of
  aborting, and if a PR for that branch already exists the existing draft PR is
  reported rather than failing on the duplicate. Re-running a service updates its
  draft PR instead of erroring.
- Actor reconciliation now transliterates umlauts/ß before matching
  (`src/tessera/merge.py`): the LLM emits the original spelling (`"Fundbüro"`)
  while canonical `actors[].id`s are ASCII (`fundbuero`). Stripping non-alphanumerics
  dropped the `ü` (`fundbro`) and the match failed, so a known actor was wrongly
  flagged and `tessera pr` correctly refused the PR. `ü→ue`/`ä→ae`/`ö→oe`/`ß→ss`
  is deterministic CH-German equivalence (not fuzzy matching). Covered by
  `tests/test_merge.py` (real `fundsache` case: step actor `"Fundbüro"` → `fundbuero`).
- Grounding-gate normalization no longer drops *valid* verbatim quotes over
  invisible HTML→Markdown artifacts: zero-width characters (zero-width
  space/joiner, word-joiner U+2060, ZWNBSP/BOM U+FEFF — none of which `\s`
  matches) are stripped, and the ellipsis character `…` is unified with `...`.
  Previously a fee/deadline reference could be wrongly flagged `unverifiziert`
  just because the source carried an invisible separator the quote did not
  (`src/tessera/grounding.py`, covered by `tests/test_grounding.py`).
- Actor parity to match the target repo's `validate:prozesse`: when a process
  carries `actors[]`, every `steps[].actor` must be an `actors[].id`. The
  contract validator now treats a mismatch as an **error** (was a warning) —
  closing a gate-parity gap where a merged file passed locally but the target CI
  rejected it (PR #155). The field-wise merge (`src/tessera/merge.py`) now
  reconciles free-text extraction actors against the target's `actors[]`:
  exact, gender-neutral normalized matches are remapped to the id (e.g.
  `"Halter:in"` → `halter`); anything unresolved is **flagged, not guessed**
  (no invented `actors[]` entry with a guessed `type`) and surfaced in the PR
  body. `tessera pr` re-validates the actually-submitted (merged) file before
  opening a PR and refuses if the contract validator fails.

### Docs
- README (en/de): a "Secrets via `.env`" section under Configuration — how to set
  up `.env` from `.env.example` and load it per shell (bash `set -a; source` and a
  PowerShell `Import-DotEnv` function), why it beats re-typing `$env:`/`export`
  (single source on rotation, nothing in shell history/screenshots, gitignored),
  and the key caveats (load per shell, reload after rotation or hit
  `401 invalid x-api-key`, plaintext file). Notes that tessera reads `os.environ`
  only and does not auto-load `.env`.

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
