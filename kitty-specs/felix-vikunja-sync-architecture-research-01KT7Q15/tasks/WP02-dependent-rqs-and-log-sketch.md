---
work_package_id: WP02
title: Dependent RQs (RQ-3, RQ-4) + conflict-event log sketch
dependencies:
- WP01
requirement_refs:
- FR-010
- FR-011
- NFR-002
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts were generated on main; completed changes must merge back into main.
subtasks:
- T006
- T007
- T008
- T009
- T010
phase: Phase 2 — Policy + use-case mapping
assignee: ''
agent: ''
history:
- timestamp: '2026-06-03T22:59:10Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/research/felix-vikunja-sync-architecture/findings/
execution_mode: planning_artifact
owned_files:
- docs/research/felix-vikunja-sync-architecture/findings/rq-3-conflict-policy.md
- docs/research/felix-vikunja-sync-architecture/findings/rq-4-use-case-mapping.md
- docs/research/felix-vikunja-sync-architecture/findings/conflict-event-log.sketch.md
tags: []
---

# Work Package Prompt: WP02 — Dependent RQs + Conflict-Event Log Sketch

## Objective

Convert WP01's substrate findings into the policy + mapping artifacts that drive the architectural recommendation:

- **RQ-3 (conflict policy)** — unsafe-class criteria + WhatsApp ping format.
- **FR-010 + SC-006**: conflict-event log shape with forward-compatibility analysis against each of #516's three possible framework outcomes (sender-only / router-only / both).
- **RQ-4 (use-case → layer mapping)** — Epic #507's seven use cases mapped to layers with worst-case latency under the 5-min ceiling.
- **NFR-002 enforcement**: ≤5-min for every use case.
- **NFR-003 enforcement**: WhatsApp volume guard ≤ 1/day steady-state with documented mechanism.

## Mission Context

- **Mission**: `felix-vikunja-sync-architecture-research-01KT7Q15`.
- **Source issue**: [#508](https://github.com/kentonium3/kg-automation/issues/508).
- **Inputs from WP01** (must be `done`/`approved` before WP02 claims): `findings/rq-1-vikunja-api.md`, `findings/rq-2-touchpoints.md`, `findings/rq-5-pattern-fit.md`, `findings/probe-transcripts.md`; rows in `research/source-register.csv` + `research/evidence-log.csv`.
- **Specification**: [spec.md](../spec.md).
- **Methodology**: [plan.md](../plan.md) § RQ-3, § RQ-4.
- **Data model**: [data-model.md](../data-model.md) — Conflict Event, Unsafe-Class, Reconciliation Cycle, Sync Layer columns.
- **Decision log**: [research.md](../research.md).
- **Cross-reference**: Issue [#516](https://github.com/kentonium3/kg-automation/issues/516) body — your forward-compatibility analysis must explicitly address this decision space.

## Branch Strategy

- **Planning / base branch**: `main`. **Merge target**: `main`.
- Same lane as WP01 (`lane-planning`); worktree reuses WP01's lane workspace per spec-kitty's lane-reuse semantics for dependent WPs.

## Implementation Command

```bash
spec-kitty agent action implement WP02 --agent <your-name>
```

This WP **depends on WP01**.

## Locked Inputs (from spec.md Constraints)

- **C-001**: polling-only.
- **C-002**: Vikunja wins conflicts. WP02 documents the policy; does not re-litigate direction.
- **C-003**: silent steady-state; log-first; WhatsApp router for unsafe class only.
- **C-004**: ~5-min latency; idempotency first-class.
- **C-006**: out-of-scope to implement the broader #516 framework. You only **sketch** a log shape + analyze its forward compatibility.

## Shared Resources (Append-Only)

Continue appending to the mission's shared CSVs at `kitty-specs/felix-vikunja-sync-architecture-research-01KT7Q15/research/`:
- `source-register.csv` — add rows for any new sources WP02 consults (e.g., `issue-516`, additional memory entries).
- `evidence-log.csv` — add rows for every WP02 load-bearing finding.

Never modify rows added by WP01.

## Subtasks

### T006 — Execute RQ-3 conflict-policy analysis; write `findings/rq-3-conflict-policy.md`

**Purpose**: Document conflict detection + resolution + unsafe-class criteria + WhatsApp surfacing.

**Steps** (plan.md § RQ-3 probe sequence):
1. Read WP01's `findings/rq-1-vikunja-api.md` (Vikunja write semantics) and `findings/rq-2-touchpoints.md` (which touchpoints write what).
2. For each touchpoint's write-set, identify what Vikunja state can conflict (operator edit between Felix-read and Felix-write).
3. Propose **unsafe-to-auto-resolve criteria**. Each criterion MUST:
   - Be testable from conflict-event fields alone (no out-of-band lookup) per `data-model.md` § Unsafe-Class.
   - Have a clear true/false answer.
   - Have at least one worked example drawn from WP01's RQ-2 inventory; cite the evidence-log row for that touchpoint.
4. Starting list from `data-model.md` (evaluate inclusion for each): `kent_edit_after_felix_write`, `operator_authored_field`, `downstream_behavior_depends`, `manual_override_signal`. Add others discovered from touchpoint analysis.
5. Document the detection mechanism (when Felix runs the diff, what fields compared).
6. Document WhatsApp ping format: succinct, one-line ideally (≤3 lines), `conflict_class + Vikunja entity ID + diff_summary`.

**Evidence CSV population**:
- Add memory `feedback_idle_pings_acceptable_for_now` to source-register if not already.
- Add #516 body to source-register (`source_id = issue-516`).
- For each unsafe-class criterion, append an evidence-log row citing the WP01 touchpoint that motivates it.

**Acceptance gate** (plan.md § RQ-3): criteria testable from log fields alone; WhatsApp format passes noise-floor calibration (see T010); cross-refs to WP01 outputs explicit (no implicit "see findings").

**Files**: `findings/rq-3-conflict-policy.md`; CSV rows.

### T007 — Draft `findings/conflict-event-log.sketch.md`

**Purpose**: The conflict-event log shape per FR-010. This is the **only contract sketch** this mission produces.

**Steps**:
1. Read `data-model.md` § Conflict Event for required dimensions.
2. Draft schema fields with type, description, rationale. Include `schema_version`.
3. Show **one worked example per `conflict_class`** value (initially: `auto_resolved`, `unsafe_to_auto_resolve`). Use realistic data from WP01's touchpoint inventory.
4. Specify persistence options (JSONL, SQLite, other) with trade-offs. Recommend a default + rationale; leave room for implementation-mission revision.
5. Specify the `event_id` derivation rule (e.g., `sha256(layer + vikunja_entity_id + ts_observed_utc + canonical(diff))`) — must be deterministic so replays produce the same ID (idempotency anchor).

**Cross-reference**: cite `data-model.md` § Conflict Event in evidence-log when introducing the schema.

**Files**: `findings/conflict-event-log.sketch.md`.

### T008 — #516-framework forward-compatibility analysis (SC-006)

**Purpose**: For each of #516's three possible framework outcomes, write a forward-compat paragraph proving the log shape from T007 fits cleanly.

**Steps**:
1. Re-read [#516 body](https://github.com/kentonium3/kg-automation/issues/516) § "Recommend (a/b/c)" — the three outcomes. Internalize what each implies for sender vs router responsibilities.
2. Write three paragraphs (one per outcome):
   - **Sender-contract-only**: how the log shape satisfies the sender contract; what (if anything) it requires of consumers.
   - **Router-contract-only**: how the log shape works if there's no sender contract but a unified router; what the producer side looks like.
   - **Both**: integration story; how the log shape provides the bridge.
3. Each paragraph names at least one specific schema field as load-bearing for that outcome.

**Acceptance gate** (SC-006): all three outcomes have an explicit paragraph; each names at least one load-bearing field.

**Landing**: append as final section to `conflict-event-log.sketch.md` (`## Forward compatibility with #516`). Cross-link from `rq-3-conflict-policy.md`.

**Files**: edits to `conflict-event-log.sketch.md`; cross-link in `rq-3-conflict-policy.md`.

### T009 — Execute RQ-4 use-case → layer mapping; write `findings/rq-4-use-case-mapping.md`

**Purpose**: Map each of Epic #507's seven operator use cases (a–g) to layers with detection, action, and worst-case latency.

**Steps** (plan.md § RQ-4 probe sequence):
1. Extract Epic #507's seven use cases verbatim from the issue body. Preserve a–g labels.
2. For each use case populate `data-model.md` § Sync Layer columns:
   - **Layer(s) touched**: `status` / `task` / `project` (one or more).
   - **Change shape**: state-change / content-change / structural-change.
   - **Detection mechanism**: which reconciliation-cycle step (`fetch` / `diff` / `classify`) catches it.
   - **Felix-side action**: cache invalidate / state advance / no-op / user alert / etc.
   - **Worst-case latency**: under proposed polling cadence.
3. If any use case requires sub-1-min latency, escalate per plan.md § RQ-4 stop conditions.

**Evidence CSV population**:
- Add Epic #507 body row to source-register (`source_id = issue-507`) if not already.
- For each use case mapping, append evidence-log row citing #507 + relevant WP01 touchpoint(s).

**Acceptance gate** (plan.md § RQ-4): all 7 use cases in table; every column populated; every worst-case-latency ≤ 5 min (NFR-002); any miss surfaced.

**Files**: `findings/rq-4-use-case-mapping.md`.

### T010 — NFR-002 + NFR-003 enforcement; volume estimate

**Purpose**: Quality gate for WP02 before WP03 consumes outputs.

**Steps**:
1. Walk the RQ-4 table; confirm every worst-case-latency ≤ 5 min (NFR-002). If any exceed, document the gap in `rq-4-use-case-mapping.md` Notes section. Do NOT silently shrink latency — surface tension.
2. For NFR-003:
   - For each unsafe-class criterion × use cases that can trip it, estimate realistic steady-state frequency. Be conservative-toward-noisier.
   - Multiply: criteria × use cases × frequency → expected unsafe-class events per day.
   - If estimate > 1/day, define a guard mechanism (rate limit, batching, threshold tightening) and re-estimate. Iterate until ≤ 1/day.
   - Document estimate, math, guard mechanism, final volume in `rq-3-conflict-policy.md` § Volume Estimate. Append final-volume evidence-log row.

**Validation**:
- [ ] NFR-002: every use case ≤ 5 min, or gap documented.
- [ ] NFR-003: estimated unsafe-class WhatsApp pings ≤ 1/day with documented guard.
- [ ] Evidence-log captures the volume estimate.

**Files**: edits to `rq-3-conflict-policy.md` and `rq-4-use-case-mapping.md`.

## Definition of Done

- `findings/rq-3-conflict-policy.md` exists with conflict policy + unsafe-class criteria + WhatsApp format + volume estimate.
- `findings/rq-4-use-case-mapping.md` exists with the 7-use-case table fully populated.
- `findings/conflict-event-log.sketch.md` exists with schema, worked examples per conflict_class, persistence options, three #516 forward-compat paragraphs.
- T010 quality gate passes.
- CSV rows added (no edits to WP01's rows).
- Worktree has commits; `git rev-list --count <base>..HEAD` is non-zero.
- WP02 moves cleanly to `for_review`.

## Risks

- Vikunja lacks stable identifier (WP01 RQ-1 verdict) sufficient for cross-cycle re-identification → escalate (conflict detection unsound).
- Use case requires sub-1-min latency → escalate.
- Volume estimate exceeds noise floor even with guards → tighten criteria; document tension.
- #516 framework decision drifts mid-mission → this WP only depends on the *decision space* (three outcomes), not any particular landing.

## Reviewer Guidance

- Unsafe-class criteria testable from log fields alone? Each has a worked example?
- Log shape `event_id` derivation idempotency-sound (replays = same ID; semantically different = different IDs)?
- Each of three #516 forward-compat paragraphs names at least one load-bearing field?
- All 7 use cases present in RQ-4 with all columns populated?
- Volume-estimate math shown? Guard mechanism concrete (a number or rule, not a hand-wave)?

## Cross-references

- Spec: [spec.md](../spec.md) — FR-001 to NFR-007, C-### constraints.
- Plan: [plan.md](../plan.md) — § RQ-3, § RQ-4 source plans + acceptance gates.
- Data model: [data-model.md](../data-model.md) — § Conflict Event, § Unsafe-Class, § Sync Layer, § Reconciliation Cycle.
- Inputs from WP01: all per-RQ-1/2/5 files + probe-transcripts + CSV rows.

## Output Discipline

Per the Felix output-discipline pattern. T010's volume estimate must show its math — hand-waving the noise-floor calibration defeats the purpose.
