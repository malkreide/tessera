# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Diff excerpts for source changes** (`src/tessera/diff.py`,
  `change-diff.yml`; review package 6b, maintainer-approved full-text
  baselines): `tessera fingerprint` now also commits the line-wise normalised
  page text per URL (`reports/fingerprints/<id>/NN-slug.txt`, provenance
  README added) alongside the hash. When `tessera diff` detects a content
  change it emits a capped unified-diff excerpt baseline vs. live
  (`MAX_EXCERPT_LINES` = 20, long lines truncated) — in the CLI output, in
  `--json` (`excerpts` map), and rendered as a ```diff block in the rolling
  `source-change` issue, which now shows *what* changed instead of only which
  URL. The change hash is still computed over the whole-text normalisation,
  so existing hash-only baselines stay valid — they simply yield no excerpt
  until the next `fingerprint` run adds the texts; stale text files of
  removed URLs are pruned. The issue body falls back to excerpt-less
  rendering above ~60k chars (GitHub limit). Covered by four new cases in
  `tests/test_diff.py`.
- **Injection screening** on the crawled corpus (`src/tessera/screening.py`,
  wired in `cli.cmd_extract`): the corpus is untrusted LLM input, and the
  grounding gate fundamentally cannot defend against prompt injection —
  injected page text is verbatim in the corpus and passes the gate (it proves
  provenance, not legitimacy). A small, deliberately high-precision heuristic
  now flags instruction-shaped patterns («ignore previous instructions»,
  «du bist jetzt …», «system prompt», output steering, «as a language
  model», the meta term «prompt injection») per source URL, with a context
  snippet. Policy: **flag, no gate** — a hit never blocks or discards
  anything (false positives must not cost data); findings land in the flags
  file and PR body, and any injection flag unlocks an extra reviewer
  checklist item («flagged passages did not steer the extraction»). Benign
  administrative phrasing («Den Anweisungen der Polizei ist Folge zu
  leisten») stays clean. Covered by `tests/test_screening.py` (stdlib, in
  `contract-check.yml`).
- Enabled the first high-risk case for automated extraction as a **deliberate
  exception**: `veranstaltung` (event permit on public ground) is now curated into
  `sources.yaml` (three stadt-zuerich.ch pages, HTTP 200 verified 2026-07-03; first
  URL = canonical `source_url`). Maximal gate: output only as a **draft PR**, merged
  by a human alone. `baugesuch` and `sozialhilfe` stay excluded. All three remain in
  `HIGH_RISK_IDS` (`src/tessera/risk.py`) — enablement is controlled solely by
  `sources.yaml`, so the heightened validator gate (ungrounded binding reference =
  error) fires regardless. `schema.to_contract` now emits the high-risk disclaimer
  key for high-risk ids; `HIGH_RISK_DISCLAIMER_KEY` is aligned to the canonical
  `Prozesse.disclaimerHochrisiko` carried by the hand-modelled target file. The
  fingerprint baseline for `veranstaltung` is seeded on the first `tessera run`
  (SSR-markdown, not reproducible offline); until then `tessera diff` reports
  `no_baseline` and skips it. Policy docs updated (`risk.py`, `CLAUDE.md`,
  `README*.md`, `docs/v1-pipeline.md`).
- v2 change-diff now files a GitHub issue instead of just going red: the weekly
  `change-diff.yml` runs `tessera diff --json` and an `actions/github-script` step
  opens/updates **one rolling issue** (label `source-change`) listing the changed
  pages / dead links per service, and auto-closes it when the next run is clean.
  `tessera diff --json` prints a machine-readable summary to stdout (human lines to
  stderr) via `diff.report_to_dict`; covered by `tests/test_diff.py`.
- Schema versioning: `SCHEMA_VERSION` is now a single source of truth in
  `src/tessera/contract.py`, shared by `schema.to_contract` (output) and the
  contract validator (check). A **differing** but SemVer-valid `schema_version` is
  a hint, not an error (a canonical file may belong to another contract
  generation — gate parity); a non-SemVer value stays a hard error. Bump procedure
  documented in `contract.py` and `docs/v1-pipeline.md`. Covered by
  `tests/test_contract_fields.py`.
- Curated `kita-platz` (Betreuungsgutschein / subsidised childcare) into the v1
  set (`sources.yaml`): three citizen-facing pages (costs & subsidies, finding a
  place, FAQ), all robots-allowed and HTTP 200 (verified 2026-06-28); pre-flight
  reports regenerated. **Income-dependent → sensitive**: structure-only stays
  mandatory (no personal data; income thresholds / subsidy amounts only as
  references — label without the number + deep-link + verbatim quote). Canonical
  target file carries `actors[]` (`eltern`, `kita`, `schulamt`, `sozialdept`,
  `bezirksrat`), so actor reconciliation applies on merge. Not a high-risk id per
  the registry (unlike `sozialhilfe`), but flagged for extra cardinal-rule care on
  review. This exhausts the risk-light v1 set (`hund-anmelden`, `umzug-melden`,
  `fundsache`, `parkplatz`, `kita-platz`).
- v2 change-detection: `tessera fingerprint` + `tessera diff` and the weekly
  `change-diff.yml` cron (`src/tessera/diff.py`). Fingerprint writes a committed
  baseline `reports/fingerprints/<id>.json` — per source URL a SHA-256 over the
  **normalized** page text (`grounding.normalize`), so cosmetic changes
  (whitespace/typography/markdown) do **not** trigger, only content changes. Diff
  re-crawls the live pages (same SSR path as crawl) and reports per URL:
  `geaendert` / `tot` / env (`blockiert`/`netzfehler`) / `neu` / `entfernt` /
  unchanged. Exit 1 on a dead link always; with `--fail-on-change` also on a
  content change (so the cron goes red and the maintainer re-extracts). Complements
  `tessera verify`: verify drifts the individual *cited quotes*, diff catches *any*
  page change (incl. a not-yet-cited new step). Fetch is injectable → tested
  without httpx (`tests/test_diff.py`, in CI). Seeded baselines committed for the
  current services (hund-anmelden, umzug-melden, fundsache, parkplatz).
- Richer grounded extraction to feed the target dashboard's indicators
  (digitalization & user-orientation) and reduce "unknown" cells: the extractor
  now also produces the additive canonical step fields **`type`**
  (start/input/prozess/entscheidung/loop/warten/ende, only when unambiguous) and
  **`documents`** (required papers per step). Documents are factual claims, so
  they pass the **same grounding gate** as steps — each carries an internal
  verbatim `source_quote` (stripped before output); an unverifiable document is
  dropped and flagged, never guessed (`src/tessera/schema.py`,
  `src/tessera/grounding.py`; `apply_gate` takes an optional `doc_quotes` map and
  stays backward compatible). Extraction instructions now also nudge consistent
  actor labels (so actor handoffs/media breaks are derivable) and filling
  `preconditions`/`ls` where source-backed. Covered by `tests/test_grounding.py`.
- Allowed the canonical additive top-level field `bewertung` in the contract
  validator (`scripts/validate_contract.py`). It lives in hand-maintained target
  files in `maschinerie-zuerich` and is preserved verbatim by the loss-free merge;
  tessera never generates it. Without it on the allowlist, a merged `parkplatz`
  state failed the contract validator (`Unbekanntes Feld: bewertung`) and no PR was
  opened, even though the target CI accepts the file — a gate-parity gap. tessera
  treats `bewertung`'s internal shape as opaque (validated canonically in the
  target repo). New stdlib test `tests/test_contract_fields.py` (wired into
  `contract-check.yml`): asserts `bewertung` is accepted and that a genuine foreign
  field is still rejected.
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
- **GitHub Actions pinned to commit SHAs** (closes the maintainer TODO from
  review package 5): all `uses:` lines in `contract-check.yml`,
  `link-rot.yml` and `change-diff.yml` now reference immutable commit SHAs
  (with the release tag as a comment) instead of movable major tags —
  a hijacked tag can no longer inject code into the workflows. SHAs were
  resolved by the maintainer against the latest releases, so this is also a
  major bump (checkout v4→v7.0.0, setup-python v5→v6.3.0, github-script
  v7→v9.0.0, upload-artifact v4→v7.0.1); `contract-check` validates
  checkout/setup-python on this very PR, the two cron-only actions should be
  smoke-tested once via `workflow_dispatch`. New `.github/dependabot.yml`
  (github-actions ecosystem, monthly) keeps the pins from freezing stale.
- Ops/compliance hardening (review package 5):
  * **Crawl backoff implemented** (`crawl._ssr_fetch`): transient failures
    (connection/timeout, 5xx) are retried up to 3 attempts with 2s/4s
    exponential backoff — the politeness that
    `reports/scraping-compliance.md` promised but the code never had.
    Definitive answers (2xx/4xx) are never retried; the tri-state finding
    stays honest after the last attempt.
  * **Dependencies bounded and CI-pinned**: `pyproject.toml` now carries
    tested lower bounds + next-major caps (PyPI-verified 2026-07-04);
    the slim installs in `link-rot.yml`/`change-diff.yml` are pinned to
    exact versions so weekly crons don't silently pick up new releases.
    `trafilatura` moved from the `crawl-fallback` extra into core
    dependencies — since the SSR-first rework it is a runtime requirement
    of the crawl path, not a fallback. NOTE: pinning the GitHub Actions
    (`checkout`/`setup-python`/`github-script`/`upload-artifact`) to commit
    SHAs still needs the maintainer (tag→SHA resolution requires GitHub
    access outside this repo).
  * **eCH-0070 XLSX size guard** (`preflight.MAX_XLSX_BYTES` = 20 MiB):
    the externally downloaded workbook is not parsed if oversized
    (zip-bomb / wrong artefact behind the link) — reported as a coverage
    finding instead.
  * **Per-reference provenance**: `cmd_extract` now stamps each reference
    with the retrieval date of **its own** source page (from `meta.json`)
    instead of the newest date of the whole run.
  * **Token scope documented** (`.env.example`, `docs/v1-pipeline.md` A.2):
    fine-grained PAT, target repo only, exactly Contents + Pull requests
    read/write, with expiry.
  * Hygiene: removed the accidentally committed
    `tests/__pycache__/*.pyc` from the index (ignore rule already existed).
- Cardinal-rule lint gains a **strict tier for high-risk cases**
  (`src/tessera/binding.py` `BINDING_VALUE_STRICT`, applied in
  `scripts/validate_contract.py`): the narrow lint (digit + unit) stays
  unchanged and is always an error, but spelled-out deadlines («innert
  vierzehn Tagen»), date forms («31. März», ISO dates) and hour/minute
  durations previously slipped through rendered labels entirely. For
  high-risk ids (`risk.HIGH_RISK_IDS`) a strict-only hit is now a validator
  **error**; for all other services it is a hint (the broad patterns can
  match harmless phrasing — abstinence strictness belongs where the damage
  is greatest). The strict pattern is the union of the existing lint and the
  label↔value gate's time/money/date patterns — no new regex surface.
  New fixture `examples/invalid-high-risk-word-number.json` proves the check
  fires; covered by new cases in `tests/test_binding.py` and
  `tests/test_risk.py`.
- PR body reworked as reviewer UI and hardened as a security surface
  (`src/tessera/pr.py`): (1) a **reference table** (Label | Deep-Link |
  verbatim quote | status) puts the reviewer's most expensive check — does the
  quote really appear on the linked page? — one click away instead of buried
  in the JSON blob; (2) all **Leichte-Sprache (`ls`) texts** are listed in one
  section for content review (they are the only LLM free text without a
  mechanical gate); (3) **markdown neutralisation**: LLM/source text (title,
  labels, quotes, flags) is never interpolated raw — `_md`/`_md_code` escape
  markdown control characters and defuse @-mentions (U+2060 word joiner), so
  extracted text cannot fake checklist state, ping people, or instruct review
  bots; (4) a **body-size guard** replaces the embedded JSON block with a
  pointer once the body would exceed `MAX_BODY_CHARS` (GitHub caps PR bodies
  at 65 536 chars — previously a large process meant a hard 422); the JSON
  fence is now 4 backticks so a ``` inside a quote cannot break out; (5) the
  **branch force-reset is guarded**: an existing `tessera/<id>-<date>` branch
  is only reset if its head commit matches the tessera commit pattern —
  human follow-up commits on that branch abort the PR step instead of being
  silently overwritten. `pr.py`'s module imports are stdlib-only now (httpx
  lazy, config type-checking-only), so the body builder is covered by
  dependency-free CI tests (`tests/test_pr_body.py`, 9 cases, added to
  `contract-check.yml`).
- Field-wise merge hardened with a **label guard** for LLM-assigned keys
  (`src/tessera/merge.py`): `step_id`/`reference_id` are assigned by the LLM
  and are NOT stable business keys against an independently maintained target
  file — the same numeric id can denote a semantically different step. Before
  pairing two entries of the same id, their `label.de` are compared
  (`_label_similarity`: max of difflib character ratio and token overlap
  relative to the shorter label, umlaut-transliterated; threshold
  `LABEL_SIMILARITY_MIN = 0.5`). Below the threshold the pair is **not
  merged**: the existing entry stays untouched, the extraction's version is
  discarded, and the pair is flagged in `MergeReport.suspect_pairs` (rendered
  as its own «Offen» block in the PR body) — never fill gaps in the wrong
  step. A longer wording of the same step («Hund anmelden» vs. «Hund online
  oder am Schalter anmelden») and umlaut vs. ae/oe/ue spellings are not
  suspicious. `actors[]` keep semantic ids and need no guard.
- Merge **provenance exception**: `retrieved_at` (process level and per
  cleanly paired reference) now always takes the extraction's fresh crawl
  date instead of being «protected» as an existing non-blank value — an old
  retrieval date is wrong provenance for re-extracted content. Refreshes are
  recorded in `MergeReport.refreshed` and listed in the PR merge warning; if
  the extraction carries no `retrieved_at`, the existing one stays. Covered
  by six new cases in `tests/test_merge.py`.
- Grounding gate hardened with **per-URL grounding** for references
  (`src/tessera/grounding.py`, wired in `cli.cmd_extract` via a third
  `crawl.load_corpus` return value): when `corpus_by_url` is passed, a
  reference's `source_quote` must be found verbatim on the page of **its own
  `source_url`** — not merely anywhere in the concatenated corpus. Previously a
  deep link could point at a page that does not contain the quote (the drift
  check in `tessera verify --online` would only catch that after the fact).
  Quotes found on a *different* crawled page are downgraded to `unverifiziert`
  with a flag naming the page they actually appear on (easy reviewer fix); a
  `source_url` that matches no crawled snapshot is flagged as unverifiable.
  URL matching is conservative (whitespace/trailing-slash only, no fuzzing).
  Steps and documents carry no URL and keep grounding against the full corpus.
  Callers without `corpus_by_url` keep the old behaviour.
- Grounding gate now enforces a **minimum quote specificity**
  (`MIN_QUOTE_CHARS = 25` normalised characters): a one-word `source_quote`
  is a coincidental substring hit, not evidence. Too-short quotes downgrade a
  reference / drop a step or document with a dedicated flag («Zitat zu
  unspezifisch»). The extraction prompt already demands full sentences, so
  legitimate quotes are unaffected.
- Crawl gate now enforces **pre-flight freshness** (`src/tessera/preflight.py`):
  `require_allowed` rejects a gate entry whose `checked_at` is missing, invalid,
  in the future, or older than `MAX_GATE_AGE_DAYS = 7` — robots.txt and terms
  of use can change, so a stale «allowed» is no clearance (the docstring
  promised freshness; now the code enforces it). `preflight`'s module-level
  imports are stdlib-only now (httpx/openpyxl are lazy, the config import is
  type-checking-only, `ROOT` is computed locally like in `verify.py`/`diff.py`),
  so the gate logic is covered by dependency-free CI tests
  (`tests/test_preflight_gate.py`, added to `contract-check.yml`).
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
