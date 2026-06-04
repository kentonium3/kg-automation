---
work_package_id: WP01
title: 'Gathering substrate: independent RQs + evidence registration'
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-008
- NFR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 1 — Gathering substrate
assignee: ''
agent: "claude:sonnet:implementer:implementer"
shell_pid: "79945"
history:
- timestamp: '2026-06-03T22:59:10Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/research/felix-vikunja-sync-architecture/findings/
execution_mode: planning_artifact
owned_files:
- docs/research/felix-vikunja-sync-architecture/findings/rq-1-vikunja-api.md
- docs/research/felix-vikunja-sync-architecture/findings/rq-2-touchpoints.md
- docs/research/felix-vikunja-sync-architecture/findings/rq-5-pattern-fit.md
- docs/research/felix-vikunja-sync-architecture/findings/probe-transcripts.md
tags: []
---

# Work Package Prompt: WP01 — Gathering Substrate

## Objective

Produce sourced research findings for the three sub-questions with no inter-dependencies: **RQ-1 (Vikunja API surface)**, **RQ-2 (Felix touchpoint inventory)**, **RQ-5 (existing-pattern fit)**. Populate the mission's shared evidence CSVs and per-RQ deliverable files. Enforce NFR-001 (every load-bearing claim cites an evidence row) and NFR-006 (every API claim tagged observed-or-documented).

This WP produces the substrate that WP02 and WP03 read. Without it the rest of the mission cannot start.

## Mission Context (read this first)

- **Mission**: `felix-vikunja-sync-architecture-research-01KT7Q15` (id `01KT7Q15NKQFW1J276F4KN2JFG`).
- **Mission type**: `research`. No code lands. Outputs are markdown + CSV rows.
- **Source issue**: [kentonium3/kg-automation#508](https://github.com/kentonium3/kg-automation/issues/508).
- **Specification**: read [spec.md](../spec.md) in full before starting.
- **Methodology**: [plan.md](../plan.md) per-RQ sub-sections — your detailed playbook for T002, T003, T004.
- **Data model**: [data-model.md](../data-model.md) — entity attribute columns your findings must populate.
- **Decision log**: [research.md](../research.md) — locked decisions you should not re-litigate.
- **Deliverables path**: `docs/research/felix-vikunja-sync-architecture/` (set in `meta.json`).

## Branch Strategy

- **Planning / base branch**: `main`.
- **Merge target**: `main`.
- Execution worktree allocated automatically by `spec-kitty agent action implement WP01 --agent <name>`. Single-lane research mission — all three WPs share `lane-planning`.

## Implementation Command

```bash
spec-kitty agent action implement WP01 --agent <your-name>
```

This WP has **no dependencies**.

## Locked Inputs (from spec.md Constraints — do NOT re-open)

- **C-001**: polling-only. RQ-1's webhook sub-question closes; document the API surface for record only.
- **C-002**: Vikunja wins conflicts.
- **C-003**: silent steady-state; log-first; WhatsApp router for unsafe class only.
- **C-004**: ~5-min latency; idempotency first-class.
- **Live-probe scope**: read-only GET only. No POST/PUT/PATCH/DELETE. If you find a question that only a write probe can answer, surface as deferred-to-implementation in the relevant RQ file.

## Shared Resources (Append-Only)

These two CSVs live under `kitty-specs/felix-vikunja-sync-architecture-research-01KT7Q15/research/` and are **not in any WP's owned_files**. All WPs append rows. Never modify rows added by other WPs.

- `research/source-register.csv` — every source consulted (API endpoints, code paths, docs, memory entries).
- `research/evidence-log.csv` — every load-bearing finding with citation + confidence.

Conventions for this mission are documented in the CSV header comments. `source_type` values used here: `api_probe`, `code`, `doc`, `issue`, `memory`. `source_id` conventions: `vikunja-api-<endpoint>`, `code-<path>`, `adr-<num>`, `issue-<num>`, `mem-<memory-name>`, `doc-<path-or-name>`.

## Subtasks

### T001 — Scaffold deliverables path + per-RQ skeletons

**Purpose**: Create the directory structure and skeleton files so T002/T003/T004 have consistent landing pads.

**Steps**:
1. Create directory `docs/research/felix-vikunja-sync-architecture/findings/` (this is the first time anything lands here; the parent `docs/research/` is also new).
2. Create the four skeleton files this WP owns. Each starts with frontmatter:
   ```markdown
   ---
   rq_id: "RQ-1"   # or RQ-2 / RQ-5
   title: "Vikunja API surface"   # adjust per RQ
   depends_on: []   # or list per RQ
   wp: "WP01"
   ---
   # RQ-1 — Vikunja API surface
   ...sections per plan.md probe sequence...
   ```
3. `probe-transcripts.md` starts with one heading per RQ-1 probe in plan.md's probe sequence; body populates during T002.

**Validation**:
- [ ] Directory `docs/research/felix-vikunja-sync-architecture/findings/` exists.
- [ ] Four skeleton files present with frontmatter.
- [ ] Headings match plan.md's per-RQ probe-sequence structure.

**Files created**: 4 new files in `docs/research/felix-vikunja-sync-architecture/findings/`.

### T002 — Execute RQ-1 Vikunja API probes; populate evidence CSVs; write `findings/rq-1-vikunja-api.md`

**Purpose**: Capture Vikunja's API surface as it actually behaves on the live instance. Read-only.

**Live target**: `https://office2.tail0f5f56.ts.net/api/v1`. Auth: `vikunja-api` token (provisioned).

**Steps** (follow plan.md § RQ-1 probe sequence verbatim):
1. `GET /info` (or equivalent) — capture server version.
2. `GET /tasks/all?per_page=1` — capture task schema (every field with type).
3. `GET /projects` — capture project schema.
4. `GET /tasks/{id}` for a representative task — full task representation.
5. **Identifier probe**: enumerate candidate stable identifiers; populate `data-model.md` § Stable Identifier columns (candidate / stability_under_edit / stability_under_delete_recreate / cross_project_uniqueness / surfaced_in_ui / verdict). Cross-reference memory `reference_vikunja_id_vs_identifier`.
6. **Filter probe**: attempt at least three server-side `?filter=` queries documented in memory `reference_vikunja_filter_gotchas`. Confirm or refute the G6/G7 rejection class. Document failing queries verbatim with error responses.
7. **Batch probe**: check for `/tasks/bulk` or equivalent. Document presence/absence with evidence (404 / OPTIONS / docs URL).
8. **Subscribe/webhook probe**: confirm presence/absence of WebSocket/SSE/webhook config endpoints. Document for historical record (decision locked per C-001).

**Tagging**: every claim in `rq-1-vikunja-api.md` must be tagged either `observed (transcript row N)` linking to `probe-transcripts.md`, or `documented (URL)` per NFR-006.

**Raw transcripts**: for each probe, append a section to `probe-transcripts.md` with the HTTP request and full response. Redact only the token if it appears in headers.

**Evidence CSV population** (mandatory per FR-002, FR-003):
- For each endpoint probed, add a row to `research/source-register.csv` with `source_id = vikunja-api-<endpoint>` (e.g., `vikunja-api-tasks-all`), citation = "GET /tasks/all (Vikunja v<server-version>)", URL = full live-instance URL, accessed_date = today UTC, relevance = high, status = reviewed.
- For each load-bearing finding (e.g., "task schema includes `identifier` field of type string", "`?filter=` rejects on `done`-based filters"), append a row to `research/evidence-log.csv` with citation = source_id from register, confidence = high (directly observed in transcript), notes = caveats (e.g., "Vikunja v2026.x — re-verify on upgrade").

**Acceptance gate** (plan.md § RQ-1):
- [ ] Server version captured.
- [ ] Task + project schemas captured field-by-field with write-status where determinable.
- [ ] Stable-identifier candidates enumerated with full verdict matrix.
- [ ] Filter rejection class confirmed or status-updated with evidence.
- [ ] Batch + subscribe capabilities documented (presence/absence with evidence).
- [ ] Evidence-log rows added for every load-bearing claim.

**Stop conditions**:
- 401/403 on probe → document token-permission gap; do not rotate.
- Live instance unreachable → fall back to docs only; tag every claim `documented`. Flag unreachability as a research caveat.

**Files**: `findings/rq-1-vikunja-api.md`, `findings/probe-transcripts.md`; rows added to both CSVs.

### T003 — Execute RQ-2 touchpoint inventory; write `findings/rq-2-touchpoints.md`

**Purpose**: Enumerate every Felix code callsite that reads from or writes to Vikunja. **Exhaustive**, not representative (FR-004).

**Steps** (plan.md § RQ-2 probe sequence):
1. `git ls-files | xargs grep -l 'vikunja-api'` — every file referencing the API token.
2. Targeted greps for Vikunja API base URL variants (`office2.tail0f5f56.ts.net/api/v1`, `vikunja.local`, etc.).
3. Targeted greps for HTTP client imports calling into Vikunja (`requests.`, `httpx.`, `urllib`).
4. Directory-scoped enumeration over `scripts/habits/`, `scripts/openclaw/agents/felix-admin-*`, `scripts/tasker/`, `scripts/openclaw/observation/signals/`, and any directories surfaced by step 1.
5. For each callsite (one row per callsite, not per file), populate `data-model.md` § Touchpoint columns: `file_path`, `function_or_callsite`, `layer`, `http_verb`, `vikunja_endpoint`, `read_set`, `write_set`, `freshness_assumption`, `owner_component`, `runtime_trigger`.

**Reproducibility**: every grep command USED must appear verbatim in `findings/rq-2-touchpoints.md` in a code-fenced block so re-running them at a later commit gives an actionable delta (FR-004).

**Evidence CSV population**:
- For each file inventoried, add a row to `source-register.csv` with `source_id = code-<dashed-path>` (e.g., `code-scripts-habits-schedule-loader`), citation = "file_path (commit <SHA-short>)", URL empty or repo-url, accessed_date = today, relevance = high.
- For each load-bearing touchpoint finding (e.g., "schedule_loader.py:write_due_date writes Vikunja task.due_date with freshness assumption ≤ same-cron-tick"), append a row to `evidence-log.csv` with citation = source_id, confidence = high (directly read), notes = layer + owner_component.

**Acceptance gate** (plan.md § RQ-2):
- [ ] Every file from the broad grep is either inventoried or explicitly excluded with reason.
- [ ] Every callsite enumerated (multi-callsite files have multiple rows).
- [ ] Grep commands documented verbatim.
- [ ] Evidence-log rows added per touchpoint.

**Stop conditions**: if a touchpoint contradicts a load-bearing Epic #507 assumption, surface as a finding (add to evidence-log with notes flagging) and continue; do not unilaterally re-open the Epic.

**Files**: `findings/rq-2-touchpoints.md`; rows in both CSVs.

### T004 — Execute RQ-5 existing-pattern fit; write `findings/rq-5-pattern-fit.md`

**Purpose**: For each existing Felix pattern, determine fit for the sync architecture.

**Patterns to evaluate** (plan.md § RQ-5 source plan):
1. **Signal-driven monitoring pipeline (#59 / #490)** — read memory `feedback_signal_driven_doc_audit` + code under `scripts/openclaw/observation/signals/`.
2. **felix-doc-auditor driver pattern** — memory `reference_felix_doc_auditor_ops`; verify driver code path via grep; runbook at `docs/runbooks/doc-auditor-driver-ops.md`.
3. **schedule_loader.py + reconciliation flag** — read `scripts/habits/schedule_loader.py`.
4. **habits-history.jsonl pattern** — examine the JSONL ledger format used under `scripts/habits/`.

**Steps** (per pattern):
1. Identify canonical reference (memory + code).
2. Capture structural shape (driver / ledger / freshness pointer / signal extractor).
3. Map each shape dimension to a sync-architecture need (drift detection, reconciliation cycle, conflict-event emission, state cache).
4. Verdict: `use as-is` / `extend` / `replace` / `not applicable` with rationale.

**Evidence CSV population**:
- For each memory entry consulted: add row to `source-register.csv` with `source_id = mem-<memory-name>`, citation = full memory name, accessed_date = today, relevance per pattern (high if directly informs verdict).
- For each code reference: add row with `source_id = code-<path>`.
- For each pattern verdict, append evidence-log row citing both memory and code sources, confidence per source quality.

**Acceptance gate**: all four patterns analyzed; each has a clear verdict + rationale + evidence-log row.

**Stop conditions**: if no pattern fits even loosely, surface that the architecture needs a new pattern (becomes input to WP03's RQ-6).

**Files**: `findings/rq-5-pattern-fit.md`; rows in both CSVs.

### T005 — NFR-001 + NFR-006 enforcement; flag deferred sub-questions

**Purpose**: Quality gate for WP01 outputs before WP02 consumes them.

**Steps**:
1. Walk `findings/rq-1-vikunja-api.md` line by line. For every load-bearing claim:
   - Confirm it cites an evidence-log row (NFR-001). If unsourced, either source it or remove it.
   - Confirm the claim has `observed (transcript ref)` or `documented (URL)` tag (NFR-006).
2. Walk `findings/rq-2-touchpoints.md`. For every grep command:
   - Confirm it's pasted verbatim (FR-004).
   - Re-run one or two greps spot-check; output matches what's recorded.
3. Walk `findings/rq-5-pattern-fit.md`. Confirm every pattern verdict has rationale and an evidence-log row.
4. For each of the three RQ files, add a final section **Deferred to implementation** listing sub-questions surfaced but out-of-scope per C-006. Format as bulleted list with parking-lot rationale.

**Validation**:
- [ ] NFR-001: zero unsourced load-bearing claims across rq-1, rq-2, rq-5.
- [ ] NFR-006: every API claim tagged observed/documented.
- [ ] FR-004: every grep command in rq-2 is reproducible (spot-checked).
- [ ] Each RQ file has a Deferred-to-implementation section (may be empty, but heading exists).

**Files**: edits to the three per-RQ files; no new files.

## Definition of Done

- All four `findings/` files in `docs/research/felix-vikunja-sync-architecture/findings/` exist with sourced content.
- T002 produces RQ-1 findings with observed/documented tags and raw transcripts in `probe-transcripts.md`.
- T003 produces RQ-2 touchpoint inventory with reproducible greps.
- T004 produces RQ-5 fit assessments with verdicts + rationale.
- T005 quality gate passes (all checkboxes above).
- `source-register.csv` and `evidence-log.csv` have new rows added (count not strictly bounded; aim for completeness per the citation-discipline rubric).
- Worktree contains commits; `git rev-list --count <base>..HEAD` is non-zero.
- WP01 moves cleanly from `doing` to `for_review`.

## Risks

- Live Vikunja unreachable: fall back to docs only; flag as caveat.
- Token permission gap: document, do not rotate.
- Grep misses unusual import pattern: NFR-equivalent FR-004 reproducibility lets a future audit re-run with refined patterns. Acceptable.
- RQ-5 patterns more divergent than expected: deeper analysis is fine; don't block other RQs.

## Reviewer Guidance

A reviewer of WP01 should verify:
- Re-running the documented Vikunja-API probes reproduces every observed claim.
- Re-running the documented greps reproduces the touchpoint inventory.
- Every load-bearing claim cites an evidence-log row (spot-check 5).
- The observed-vs-documented tagging is consistent.
- The Deferred-to-implementation sections name what the deferred implementation mission needs to answer (no hand-waving).
- CSVs are append-only across this WP — no edits to rows from other WPs (none exist yet, but worth checking).

## Cross-references

- Spec: [spec.md](../spec.md) — DR/AR/QR/C constraints.
- Plan: [plan.md](../plan.md) — per-RQ source plans + probe sequences.
- Data model: [data-model.md](../data-model.md) — Touchpoint / Stable Identifier columns.
- Decision log: [research.md](../research.md) — locked decisions not to re-litigate.
- Deliverables path: `docs/research/felix-vikunja-sync-architecture/` (set in `meta.json`).

## Output Discipline

Findings follow the Felix output-discipline pattern (memory `reference_felix_output_discipline_pattern`): state the claim, cite the evidence-log row, move on. No boilerplate, no editorializing. Per-RQ files are reference documents; readers scan them.

## Activity Log

- 2026-06-03T23:49:01Z – claude:sonnet:implementer:implementer – shell_pid=65155 – Started implementation via action command
- 2026-06-04T00:02:21Z – claude:sonnet:implementer:implementer – shell_pid=65155 – Ready for review: RQ-1/2/5 findings sourced; CSVs populated; NFR-001/NFR-006/FR-004 enforced in T005
- 2026-06-04T00:03:11Z – claude:opus:reviewer:reviewer – shell_pid=69101 – Started review via action command
- 2026-06-04T00:50:08Z – claude:sonnet:implementer:implementer – shell_pid=79945 – Started implementation via action command
