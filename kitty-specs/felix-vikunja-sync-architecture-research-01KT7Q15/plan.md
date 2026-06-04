# Research Plan: Felix-Vikunja Sync Architecture Design

**Mission**: `felix-vikunja-sync-architecture-research-01KT7Q15`
**Branch**: `main` (planning_base = `main`, merge_target = `main`)
**Date**: 2026-06-03
**Spec**: [spec.md](spec.md)
**Source issue**: [kentonium3/kg-automation#508](https://github.com/kentonium3/kg-automation/issues/508)

## Branch Strategy (restated, mandatory)

- **Current branch at plan start**: `main`
- **Planning / base branch**: `main`
- **Final merge target**: `main`
- **`branch_matches_target`**: `true`
- Execution worktrees are allocated at `/spec-kitty.implement` time per the lane assignments from `finalize-tasks`.

## Summary

This is a `research` mission (Deep Research Kitty). It investigates how Felix should bi-directionally synchronize with Vikunja under operator constraints (automatic, silent, accurate, ~5-minute latency) and produces design artifacts — `findings.md`, `recommendation.md`, draft `adr-0003.md`, and 2–4 follow-on GitHub sub-issues — that close the design-gate for Epic #507's implementation arc. No code lands from this mission. Operator review on issue #508 is the canonical acceptance gate (SC-007).

## Research Context

**Research Question**: How should Felix bi-directionally synchronize with Vikunja so the operator constraints are met across all seven Epic #507 use cases without coupling to the broader observability framework still being scoped in #516?

**Research Type**: Case study with mixed-methods evidence collection.

**Domain**: Personal-AI-operating-system architecture (Felix), with Vikunja as the canonical task-state authority.

**Time Frame**: Single mission — three sequential WPs (single lane). No external deadlines beyond Kent's bandwidth.

**Resources Available**:
- Live Vikunja instance: `https://office2.tail0f5f56.ts.net/api/v1` (read-only access via `vikunja-api` token).
- Felix codebase: `/Users/kentgale/repos/kg-automation/`.
- Existing ADRs: `docs/design/architecture/adr/0001-google-workspace-via-gog.md`, `docs/design/architecture/adr/0002-felix-vikunja-task-model.md`.
- Operational memory: relevant entries enumerated in spec.md References + per-RQ Source Plans below.

**Key Background**:
- Epic [#507](https://github.com/kentonium3/kg-automation/issues/507) frames the bi-directional sync need and enumerates seven operator use cases (a–g).
- Issue [#516](https://github.com/kentonium3/kg-automation/issues/516) scopes the broader Felix observability/error-emission framework. The conflict-event log shape proposed by this research must be forward-compatible with #516's three possible framework outcomes (sender-only / router-only / both).
- Source incident: mission #408 WP01 task_id mis-binding bug.
- Operator decisions locked into spec.md Constraints (C-001 through C-008) — these will not be re-litigated during research.

## Methodology

### Research Design

**Approach**: Mixed methods. Three substrates:
1. **Live API probing** (read-only GETs against Vikunja) — RQ-1.
2. **Codebase analysis** (exhaustive grep over Felix scripts and helpers) — RQ-2.
3. **Document and memory review** (ADRs, Epic body, Issue #516 body, operational memory entries) — RQ-3, RQ-4, RQ-5, RQ-6.

**Phases** (mapped to research-kitty's state machine `scoping → methodology → gathering → synthesis → output → done`):

1. **Scoping** (completed) — spec.md is the artifact; primary question + sub-questions + scope locked.
2. **Methodology** (current) — this plan.md is the artifact; source plans + acceptance gates defined per sub-question.
3. **Gathering** (WP01 + part of WP02) — populate `kitty-specs/<mission>/research/source-register.csv` and `kitty-specs/<mission>/research/evidence-log.csv` with probe results, grep results, doc and memory citations.
4. **Analysis & Synthesis** (WP02 + WP03) — extract per-sub-question findings into the deliverables path; synthesize into `findings.md` and `recommendation.md`.
5. **Publication** (WP03) — draft `adr-0003.md`; file 2–4 follow-on missions as GitHub sub-issues under #507.
6. **Done** — gated by **operator review on #508** (SC-007), not by spec-kitty merge.

### Sub-Question Methodologies

Each sub-question gets a structured methodology with source plan, probe sequence, acceptance gate, and stop conditions.

#### RQ-1 — Vikunja API surface

- **Source plan**: live Vikunja instance (read-only GETs); Vikunja public docs URLs; memory entries `reference_vikunja_id_vs_identifier` and `reference_vikunja_filter_gotchas`.
- **Probe sequence**:
  1. `GET /info` (or version equivalent) — capture server version.
  2. `GET /tasks/all?per_page=1` — capture task schema.
  3. `GET /projects` — capture project schema.
  4. `GET /tasks/{id}` for a representative task — full task representation.
  5. Identifier probe — enumerate candidate stable identifiers; populate the dimensions from `data-model.md` § Stable Identifier.
  6. Filter probe — attempt at least three server-side `?filter=` queries documented in `reference_vikunja_filter_gotchas`; confirm or refute the G6/G7 rejection class on current Vikunja.
  7. Batch probe — check for `/tasks/bulk` or equivalent; document presence/absence.
  8. Subscribe/webhook probe — check for WebSocket/SSE/webhook config endpoints; document for historical record (decision is locked per C-001).
- **Acceptance gate**: server version captured; task and project schemas captured field-by-field with write-status where determinable; stable-identifier candidates enumerated with full verdict matrix; filter rejection class confirmed or status-updated; batch and subscribe capabilities documented (presence/absence with evidence).
- **Stop conditions**: 401/403 → document token-permission gap, do not propose rotation. Live instance unreachable → fall back to docs only and tag every claim `documented`. Flag unreachability as a research caveat.

#### RQ-2 — Felix touchpoint inventory

- **Source plan**: Felix codebase (`git ls-files`); `vikunja-api` token references as coarse identifier; targeted directory scoping per spec.md Sub-Questions.
- **Probe sequence**:
  1. `git ls-files | xargs grep -l 'vikunja-api'` — every file referencing the token.
  2. Targeted greps for Vikunja API base URL variants.
  3. Targeted greps for HTTP client imports calling into Vikunja.
  4. Directory-scoped enumeration over `scripts/habits/`, `scripts/openclaw/agents/felix-admin-{capture,escalation}/`, `scripts/tasker/`, `scripts/openclaw/observation/signals/`, plus any other directories surfaced by step 1.
  5. For each callsite (one row per callsite, not per file), populate `data-model.md` § Touchpoint columns.
- **Acceptance gate**: every file from the broad grep is either inventoried or explicitly excluded with reason; every callsite enumerated; multi-callsite files have multiple rows; grep commands documented verbatim and pasted into evidence-log.
- **Stop conditions**: if a touchpoint contradicts a load-bearing Epic #507 assumption, surface as a finding and continue; do not unilaterally re-open the Epic.

#### RQ-3 — Conflict policy + log shape

- **Source plan**: RQ-1 output (Vikunja write semantics); RQ-2 output (touchpoints that write); existing JSONL shapes (`habits-history.jsonl`, signal-extractor ledgers); Issue #516 body for the framework decision space; memory `feedback_idle_pings_acceptable_for_now` for noise-floor context.
- **Probe sequence**:
  1. Read existing JSONL shapes; identify common fields and conventions.
  2. For each RQ-2 touchpoint's write-set, identify what Vikunja state could conflict.
  3. Propose unsafe-to-auto-resolve criteria; each must be testable from conflict-event fields alone (see `data-model.md` § Unsafe-Class).
  4. Draft the conflict-event schema in the deliverables path (`contracts/conflict-event-log.sketch.md` if a contracts/ subdir; else inline in findings/rq-3).
  5. For each of #516's three framework outcomes (sender-only, router-only, both), write a forward-compat paragraph naming at least one load-bearing schema field (FR-010 / SC-006).
  6. Draft the WhatsApp ping format: succinct, one-line ideally (≤3 lines), conflict class + Vikunja entity ID + diff summary.
- **Acceptance gate**: unsafe-class criteria listed and testable from log fields alone; conflict-event schema documented with rationale; forward-compatibility analysis is explicit (one paragraph per #516 outcome); WhatsApp format passes the noise-floor calibration in NFR-003.
- **Stop conditions**: if Vikunja lacks a stable identifier sufficient for cross-cycle re-identification, escalate (conflict detection becomes unsound).

#### RQ-4 — Use-case → layer mapping

- **Source plan**: Epic #507 body (7 use cases enumerated a–g); RQ-1 output (Vikunja entities per layer); RQ-2 output (touchpoints per use case); RQ-5 output (pattern fit informs layer reuse).
- **Probe sequence**:
  1. Extract the 7 use cases verbatim from Epic #507.
  2. For each use case, populate `data-model.md` § Sync Layer columns: layer(s) touched, change shape, detection mechanism (which reconciliation step catches it), Felix-side action, worst-case latency.
- **Acceptance gate**: all 7 use cases in the table; every column populated; worst-case latency ≤ 5 min for each (NFR-002); any sub-5-min ceiling miss surfaced as a recommendation gap.
- **Stop conditions**: if a use case requires sub-1-min latency that polling cannot meet, escalate.

#### RQ-5 — Existing pattern fit

- **Source plan**: memory entries `reference_felix_doc_auditor_ops` + `feedback_signal_driven_doc_audit`; code under `scripts/openclaw/observation/signals/`, `scripts/doc_audit/`, `scripts/habits/schedule_loader.py`, `scripts/habits/*-history.jsonl`; runbook at `docs/runbooks/doc-auditor-driver-ops.md`.
- **Probe sequence**:
  1. For each pattern, read the canonical reference (memory + code).
  2. Capture the pattern's structural shape (driver / ledger / freshness pointer / signal extractor).
  3. Map each shape dimension to a sync-architecture need (drift detection, reconciliation cycle, conflict-event emission, state cache).
  4. Write fit assessment: `use as-is` / `extend` / `replace` / `not applicable` with rationale.
- **Acceptance gate**: all four patterns analyzed; each has a clear verdict with rationale.
- **Stop conditions**: if no pattern fits even loosely, surface that the architecture needs a new pattern (input to RQ-6).

#### RQ-6 — ADR-0003 scope

- **Source plan**: ADR-0002 body; RQ-1 through RQ-5 outputs.
- **Probe sequence**:
  1. Read ADR-0002 in full. Enumerate each architectural decision.
  2. For each ADR-0002 decision, classify the proposed sync architecture's stance: `override` / `extend` / `preserve`.
  3. Apply the tally rule: >50% override → supersede; mostly preserve+extend → extend; split → document both options and pick one with rationale.
  4. Draft ADR-0003 in format of ADR-0001; declare supersedes-vs-extends per the verdict; replace Epic #507's interaction-model diagram from "webhooks + polling" to polling-only.
- **Acceptance gate**: ADR-0002 decisions enumerated; ADR-0003 supersede-vs-extend choice explicit with rationale (SC-001); ADR-0003 operator-cold readable (NFR-004); interaction-model diagram updated (FR-009).
- **Stop conditions**: if no new architectural decisions are required beyond ADR-0002, surface to operator (ADR-0003 unnecessary — unlikely).

### Data Sources

**Primary**:
- Live Vikunja instance at `https://office2.tail0f5f56.ts.net/api/v1`.
- Felix codebase at `/Users/kentgale/repos/kg-automation/`.

**Secondary**:
- `docs/design/architecture/adr/0001-google-workspace-via-gog.md`, `docs/design/architecture/adr/0002-felix-vikunja-task-model.md`.
- GitHub issue bodies: [#507](https://github.com/kentonium3/kg-automation/issues/507), [#516](https://github.com/kentonium3/kg-automation/issues/516), [#508](https://github.com/kentonium3/kg-automation/issues/508).
- Vikunja public docs (URLs captured during probe session per NFR-equivalent NFR-006).

**Search Strategy**:
- **Keywords (codebase grep)**: `vikunja-api`, `office2.tail0f5f56.ts.net`, `vikunja.local`, `requests.get`/`requests.post`/`httpx`/`urllib` for Vikunja-context callsites.
- **Inclusion criteria**: any Felix-owned code (scripts, helpers, agents, signal extractors) that reads from or writes to Vikunja.
- **Exclusion criteria**: docs-only mentions (e.g., reference to vikunja in markdown), spec-kitty workflow files (`kitty-specs/`, `.kittify/`).

### Analysis Framework

- **Coding scheme**: per-sub-question structured templates from `data-model.md`. Findings are coded by sub-question (RQ-1 through RQ-6) and by layer (`status` / `task` / `project`) where applicable.
- **Synthesis method**: per-sub-question analysis + cross-sub-question synthesis in `findings.md`. The recommendation in `recommendation.md` is a coherent architectural proposal that satisfies all locked constraints (C-001 through C-008) and answers every sub-question.
- **Quality assessment**: per NFR-001 (every claim cited), NFR-006 (observed-vs-documented tagging), NFR-007 (alternatives considered). Confidence levels in `evidence-log.csv` row-per-row (high = directly observed; medium = synthesized; low = unverified memory).

## Data Management

### Evidence Tracking

- **File**: `kitty-specs/felix-vikunja-sync-architecture-research-01KT7Q15/research/evidence-log.csv`
- **Purpose**: Track every load-bearing finding with citation and confidence.
- **Columns**: per research-kitty's evidence-log template — `timestamp`, `source_type`, `citation`, `key_finding`, `confidence`, `notes`.
- **Source types used in this mission**: `api_probe` (Vikunja live HTTP), `code` (Felix codebase grep), `doc` (ADR, runbook, docs file), `issue` (GitHub issue body), `memory` (operational memory entry).
- **Agent guidance**:
  1. When a probe runs, grep returns, doc is read, or memory consulted, append a row.
  2. Citation: probe transcript ID for `api_probe`; repo-relative path + function/line for `code`; URL or repo path for `doc`/`issue`; memory name for `memory`.
  3. Confidence: `high` = directly observed and reproducible; `medium` = synthesized from multiple sources or single doc claim; `low` = memory claim not re-verified against current state.
  4. Notes: caveats, version constraints, alternative interpretations, deferred sub-questions.

### Source Registry

- **File**: `kitty-specs/felix-vikunja-sync-architecture-research-01KT7Q15/research/source-register.csv`
- **Purpose**: Master list of every source consulted.
- **Columns**: per research-kitty's source-register template — `source_id`, `citation`, `url`, `accessed_date`, `relevance`, `status`.
- **source_id convention**:
  - `vikunja-api-<endpoint>` for API endpoints (e.g., `vikunja-api-tasks-all`).
  - `code-<repo-relative-path>` for codebase files (e.g., `code-scripts-habits-schedule-loader`).
  - `adr-0001`, `adr-0002` for existing ADRs; `issue-507`, `issue-508`, `issue-516` for GitHub issues.
  - `mem-<memory-name>` for memory entries (e.g., `mem-reference-vikunja-filter-gotchas`).
- **Agent guidance**:
  1. Add source to register on first reference (don't wait until citation in findings).
  2. Maintain relevance ratings to prioritize review.
  3. Status updates: `pending` → `reviewed` (after extraction) → `archived` (if irrelevant after closer look).

## Research Deliverables Location

**Deliverables Path**: `docs/research/felix-vikunja-sync-architecture/`

Chosen rationale:
- Drops the noisy `01KT7Q15` mid8 suffix from the mission slug; the directory is project-permanent and doesn't need mission-instance identifiers.
- Drops the redundant trailing `-research-` token (the parent dir `docs/research/` already says it).
- Establishes the naming convention for future research missions in `docs/research/` (clean kebab-case domain identifier).

This path will:
- Be created during WP01 (or earlier if convenient — the directory itself is created lazily by the first agent to write into it).
- Contain `findings.md`, `recommendation.md`, optional sub-files (e.g., per-RQ files if WP-level ownership requires the split).
- The draft `adr-0003.md` lives at `docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md` (canonical ADR location), not under `docs/research/`.

## Project Structure

### Sprint Planning Artifacts (in `kitty-specs/`)

```
kitty-specs/felix-vikunja-sync-architecture-research-01KT7Q15/
├── spec.md              # Research question + DR/AR/QR + C-### constraints (locked)
├── plan.md              # This file — methodology
├── tasks.md             # Research WP layout (generated by /spec-kitty.tasks)
├── meta.json            # Mission metadata + deliverables_path setting
├── checklists/
│   └── requirements.md  # Spec quality checklist
├── research/
│   ├── evidence-log.csv      # Every finding with confidence + citation
│   ├── source-register.csv   # Every source consulted with relevance + status
│   └── (no methodology.md — methodology lives in this plan.md)
└── tasks/
    ├── WP01-*.md        # (generated by /spec-kitty.tasks)
    ├── WP02-*.md
    └── WP03-*.md
```

### Research Deliverables (in deliverables path)

```
docs/research/felix-vikunja-sync-architecture/
├── findings.md          # Synthesis across all sub-questions (RQ-1 to RQ-6)
├── recommendation.md    # Operator-readable architectural proposal
└── (per-WP working files as needed — see tasks.md for WP-level file ownership)
```

### Canonical ADR (outside both kitty-specs/ and docs/research/)

```
docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md
```

## Quality Gates

### Before Data Gathering (end of methodology phase)

- [ ] Research question clear and focused — codified in spec.md
- [ ] Methodology documented and reproducible — codified in this plan.md
- [ ] Data sources identified and accessible — listed above
- [ ] Analysis framework defined — listed above
- [ ] Evidence-tracking CSVs scaffolded in `kitty-specs/<mission>/research/`

### During Data Gathering (WP01 + WP02 partial)

- [ ] All sources documented in source-register.csv before being cited
- [ ] Evidence logged with proper citations + confidence levels
- [ ] No load-bearing claim makes it into per-RQ analysis without an evidence-log row
- [ ] Probe transcripts captured for every API probe

### Before Synthesis (end of WP02)

- [ ] All six sub-questions have evidence rows sufficient to answer them
- [ ] Findings coded by sub-question and layer where applicable
- [ ] Patterns identified across RQs
- [ ] Limitations documented per sub-question

### Before Publication (end of WP03)

- [ ] Research question answered in `findings.md`
- [ ] All claims cited to evidence-log rows
- [ ] Methodology clear and reproducible from this plan.md
- [ ] Recommendation in `recommendation.md` is operator-cold readable
- [ ] Draft `adr-0003.md` is operator-cold readable
- [ ] 2–4 follow-on missions filed as GitHub sub-issues under #507
- [ ] Bibliography (source-register) complete and ordered

### After Publication (operator-review gate)

- [ ] Operator reads `recommendation.md` + draft `adr-0003.md` cold
- [ ] Operator records `accept` or `reject + feedback` as a comment on #508
- [ ] If accepted: follow-on sub-issues are cleared for `spec: brief` → `spec: ready` flip

## Charter Check

| Item | Status | Notes |
|---|---|---|
| Charter loaded | Partial (compact mode) | Known governance-unresolved diagnostic (pytest/python in `available_tools`). |
| Section anchors loaded | Yes | |
| Governance resolved | **No (known issue)** | Scheduled as post-this-mission maintenance per memory `project_charter_tool_registry_mismatch`. Not a blocker — research mission requires no code-tool execution. |
| Branch strategy | Aligned | Plan and merge target both `main`. |
| Change-Risk Taxonomy tier | Tier 4 (auto-commit) for research artifacts; **no Tier 0/1/2 changes** in this mission. | No services deployed, no credentials touched, no network topology changes. |
| Output discipline | Applies | Memory `reference_felix_output_discipline_pattern`. |

## Known Constraints (this mission)

1. **Charter governance unresolved** (scheduled post-mission maintenance per memory).
2. **spec-kitty #1684** (lane-base ignores WP-level dependencies). Avoided by execution model: single lane (`lane-planning`) because all WPs are `planning_artifact`. Diagnostic at `docs/diagnostics/1684_lane-base-not-inferred-from-wp-deps.md`. Internal tracking [#492](https://github.com/kentonium3/kg-automation/issues/492).
3. **spec-kitty #588** (sparse-checkout staleness after merge). Post-merge `git status` verification per memory `reference_speckitty_issue_588`.
4. **spec-kitty #589** (review-lock blocks approve on lane-worktree reviews). `--force` after verifying `.spec-kitty/` only untracked per memory `reference_speckitty_issue_589`.
5. **Codex paused** (C-007). Review = Claude self-review or operator review.
6. **WhatsApp noise floor** (NFR-003). Hard NFR on recommendation.

## Implementation Lane Plan (preview for `/spec-kitty.tasks`)

This is a preview of WP layout to inform tasks generation. Not the WP plan itself.

- **One lane**: `lane-planning` (research-kitty's default lane for all `planning_artifact` WPs).
- **Expected WPs** (3, sized to phase boundaries):
  - **WP01 — Gathering substrate (independent RQs + evidence registration)**: probe Vikunja (RQ-1), inventory Felix touchpoints (RQ-2), assess existing patterns (RQ-5); populate source-register.csv and evidence-log.csv as findings emerge.
  - **WP02 — Dependent analysis (policy + mapping)**: from RQ-1 + RQ-2 + RQ-5 substrate, answer RQ-3 (conflict policy + log shape with #516 forward-compat) and RQ-4 (use-case → layer mapping with ≤5-min latency).
  - **WP03 — Synthesis + publication**: answer RQ-6 (ADR-0003 scope); write `findings.md` and `recommendation.md` in the deliverables path; draft `adr-0003.md`; file 2–4 sub-issues under #507.

## Branch Strategy (restated for the second time, mandatory per plan command)

- **Current branch**: `main`
- **Planning / base branch**: `main`
- **Final merge target**: `main`
- All artifacts described in this plan land on `main` via the spec-kitty merge at mission end.

## Next step

`/spec-kitty.tasks` to generate the WP files. This command does **not** generate them.
