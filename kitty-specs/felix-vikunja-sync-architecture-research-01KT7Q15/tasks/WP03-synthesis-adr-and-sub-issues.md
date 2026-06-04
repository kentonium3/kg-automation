---
work_package_id: WP03
title: Synthesis + ADR-0003 draft + follow-on sub-issue filing
dependencies:
- WP01
- WP02
requirement_refs:
- FR-006
- FR-007
- FR-009
- FR-012
- NFR-001
- NFR-004
- NFR-005
- NFR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
- T015
- T016
- T017
phase: Phase 3 — Synthesis + handoff
assignee: ''
agent: "claude:sonnet:implementer:implementer"
shell_pid: "89671"
history:
- timestamp: '2026-06-03T22:59:10Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/design/architecture/adr/
execution_mode: planning_artifact
owned_files:
- docs/research/felix-vikunja-sync-architecture/findings/rq-6-adr-scope.md
- docs/research/felix-vikunja-sync-architecture/findings.md
- docs/research/felix-vikunja-sync-architecture/recommendation.md
- docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md
tags: []
---

# Work Package Prompt: WP03 — Synthesis + ADR-0003 + Sub-Issue Filing

## Objective

Translate WP01 substrate + WP02 policy/mapping into operator-facing outputs that close the research mission:

- **RQ-6 (ADR-0003 scope)**: supersede-vs-extend decision with rationale (SC-001).
- **`findings.md`**: synthesis/index over all per-RQ files (operator-cold readable).
- **`recommendation.md`**: operator-facing architectural proposal (NFR-004).
- **`docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md`**: canonical ADR with polling-only interaction-model diagram (FR-009).
- **2–4 follow-on sub-issues** under Epic #507 with explicit "Depends on #N" declarations (FR-012, NFR-005).
- **Operator-review-pending** state per SC-007.

## Mission Context

- **Mission**: `felix-vikunja-sync-architecture-research-01KT7Q15`.
- **Source issue**: [#508](https://github.com/kentonium3/kg-automation/issues/508).
- **Parent epic**: [#507](https://github.com/kentonium3/kg-automation/issues/507).
- **Inputs**: WP01's `findings/rq-1-*.md`, `findings/rq-2-*.md`, `findings/rq-5-*.md`, `findings/probe-transcripts.md`; WP02's `findings/rq-3-*.md`, `findings/rq-4-*.md`, `findings/conflict-event-log.sketch.md`; rows in `research/source-register.csv` + `research/evidence-log.csv`.
- **Specification**: [spec.md](../spec.md).
- **Methodology**: [plan.md](../plan.md) § RQ-6.
- **Decision log**: [research.md](../research.md).
- **Format reference for ADR-0003**: [docs/design/architecture/adr/0001-google-workspace-via-gog.md](../../docs/design/architecture/adr/0001-google-workspace-via-gog.md).
- **Base ADR to supersede or extend**: [docs/design/architecture/adr/0002-felix-vikunja-task-model.md](../../docs/design/architecture/adr/0002-felix-vikunja-task-model.md).

## Branch Strategy

- **Planning / base branch**: `main`. **Merge target**: `main`.
- Same lane as WP01 + WP02 (`lane-planning`).

## Implementation Command

```bash
spec-kitty agent action implement WP03 --agent <your-name>
```

This WP **depends on WP01 and WP02** (both must be `approved`).

## Locked Inputs (from spec.md Constraints)

- **C-001 through C-008** — all locked policy + out-of-scope items.
- **C-008**: filed sub-issues land at `spec: brief`, **not** `spec: ready`. Operator formalization is a separate gate.
- **#516 cross-reference**: ADR-0003 references WP02's forward-compat analysis; does not pre-empt #516's framework decision.

## Shared Resources (Append-Only)

Continue appending to `kitty-specs/.../research/source-register.csv` (e.g., `adr-0001`, `adr-0002`, filed sub-issue numbers as they're created) and `evidence-log.csv`. Never modify WP01/WP02 rows.

## Subtasks

### T011 — RQ-6 ADR-0003 scope decision; write `findings/rq-6-adr-scope.md`

**Purpose**: Decide whether ADR-0003 supersedes ADR-0002 entirely or extends it (SC-001 requires explicit rationale).

**Steps** (plan.md § RQ-6):
1. Read [ADR-0002](../../docs/design/architecture/adr/0002-felix-vikunja-task-model.md) in full. Enumerate each architectural decision as a numbered list.
2. For each ADR-0002 decision, classify the proposed sync architecture's stance: `override` / `extend` / `preserve`.
3. Apply tally rule (plan.md § RQ-6): >50% override → supersede; mostly preserve+extend → extend; split → document both, pick one with rationale.
4. Write `findings/rq-6-adr-scope.md` with enumeration, per-decision verdict, and final supersede-vs-extend choice + rationale.

**Acceptance gate** (SC-001): the choice is explicit; the rationale cites specific ADR-0002 decisions.

**Evidence CSV population**: add `adr-0002` to source-register if not already. Append evidence-log row for the supersede-vs-extend verdict with citation = `adr-0002`.

**Files**: `findings/rq-6-adr-scope.md`.

### T012 — Write `findings.md` synthesis/index

**Purpose**: Single entry point operator reads when consuming the research output (per the "show me everything" view).

**Content** (drawing on all per-RQ files in `docs/research/felix-vikunja-sync-architecture/findings/`):
- **Summary** (one paragraph): what the research found at a glance.
- **Per-RQ section** (one paragraph each):
  - RQ verbatim from spec.md.
  - 2–3 sentence answer.
  - Link to the per-RQ file (`findings/rq-N-*.md`).
- **Links**: to `recommendation.md`, draft `adr-0003.md`, filed sub-issues (back-filled in T016).
- **Footer**: `Operator review pending on #508` with exact criterion (per SC-007).

**Constraint**: operator-cold readable (NFR-004) — operator reads `findings.md` without working notes and can orient.

**Files**: `findings.md` (in `docs/research/felix-vikunja-sync-architecture/`).

### T013 — Write `recommendation.md`

**Purpose**: Operator-facing architectural proposal. The document operator reads first when deciding accept/reject.

**Content checklist**:
- **Summary** (3–5 sentences): what's recommended, why, what changes from today.
- **Sync layers**: the three-layer model with Vikunja resources per layer + reconciliation cadence within the 5-min ceiling.
- **Polling cadence**: recommended range, not single value; rationale based on RQ-4 latency.
- **Conflict resolution**: Vikunja wins (locked); unsafe-class criteria from WP02; log-first + WhatsApp router.
- **Log shape summary**: one-paragraph overview + link to `conflict-event-log.sketch.md`.
- **Identifier choice**: which Vikunja field is the stable identifier per RQ-1 verdict.
- **What this changes**: explicit before/after for each Felix component named in WP01 RQ-2 inventory (without proposing implementation — that's follow-on missions).
- **What this defers**: open questions deferred to implementation missions per Deferred-to-implementation sections of each per-RQ file.

**Writing constraint**: operator-readable **cold** (NFR-004). Test by writing last and re-reading without working notes. If a section needs `findings/` context, inline it briefly — do not assume `findings/` has been read.

**Files**: `recommendation.md` (in `docs/research/felix-vikunja-sync-architecture/`).

### T014 — Draft `docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md`

**Purpose**: The canonical architectural record. Lives in the ADR tree, not `docs/research/`.

**Steps**:
1. Read [ADR-0001](../../docs/design/architecture/adr/0001-google-workspace-via-gog.md) for format and tone.
2. Front matter: declare `supersedes-vs-extends` per T011's verdict. If `supersedes`, name ADR-0002. If `extends`, name ADR-0002 and the specific decisions extended.
3. Sections:
   - **Status**: `Draft` (operator review on #508 promotes to `Accepted`).
   - **Context**: why this ADR exists — bi-directional sync need surfaced by #408 WP01 + Epic #507.
   - **Decision**: the architectural choices. Cross-reference `recommendation.md`. More terse than recommendation.md — this is the record.
   - **Consequences**: positive (what this enables), negative (what this costs), risks (what could go wrong).
   - **Alternatives considered**: webhooks (dropped per C-001); GitHub-issue conflict surfacing (dropped per C-003); implementing #516 framework now (deferred per C-006).
4. **Interaction-model diagram** (Mermaid per project convention): replace Epic #507's "webhooks + polling" with polling-only. Show Vikunja (canonical state), Felix touchpoints (grouped per WP01 RQ-2 owner_component), reconciliation cycle, conflict-event log sink, WhatsApp router as downstream consumer of unsafe-class events only.
5. Append a section linking to: spec.md, plan.md, all per-RQ files, recommendation.md, conflict-event-log.sketch.md, #507, #508, #516.

**Operator-cold test** (NFR-004): re-read by operator without working notes; architecture clear. If not, revise. Brevity good but not at cost of clarity.

**Files**: `docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md`.

### T015 — Decide on 2–4 follow-on mission scopes + dependencies

**Purpose**: Translate the recommendation into a roadmap of implementation missions. Each scoped for one mission's worth of work.

**Steps**:
1. Re-read `recommendation.md`. Identify natural sequencing boundaries (e.g., "Foundation: polling driver + reconciliation cycle", "Layer 1: status sync", "Layer 2: task sync", "Layer 3: project sync").
2. Default tilt: **fewer, larger missions** (plan-step default). 2–3 missions is sweet spot; only split to 4 if a hard sequencing dependency forces it.
3. For each mission, define:
   - Title.
   - Predecessor(s) by ordinal ("Depends on #N" — N back-filled in T016).
   - Scope: one paragraph naming layers / components / touchpoints touched.
   - Out of scope: what this mission deliberately defers.
   - Acceptance: what makes it "done".
4. Hold the drafts in working memory for T016.

**Files**: no new files; drafts in agent memory.

### T016 — File 2–4 sub-issues under Epic #507; back-fill cross-references

**Purpose**: Materialize the roadmap as GitHub sub-issues with explicit dependency declarations.

**Steps**:
1. **Pre-flight**: confirm `kg-felix-bot` token available (memory `project_kg_felix_bot_identity`). If unavailable, **surface as blocker and stop** — do not file under Kent's identity.
2. For each mission from T015, file via `gh issue create`:
   - Repo: `kentonium3/kg-automation`.
   - Title: clear, concise (≤70 chars).
   - Body: structured per `.github/ISSUE_TEMPLATE/feature.md` (or `infra.md` if infra-shaped). Required sections: Summary, **Observable symptom** (per Directive 8 — memory `feedback_operational_symptom_required`), Acceptance criteria, Out of scope, Dependencies (with "Depends on #N" for predecessors), References (cross-reference Epic #507, ADR-0003 draft, recommendation.md).
   - Labels: `area/task-intel`, `P1-feature` (or `P1-infra` if appropriate), `spec: brief` (NOT `spec: ready` per C-008).
3. After all filed, link to Epic #507 as sub-issues via `gh api graphql` `addSubIssue` mutation (memory `reference_github_subissues_via_graphql`). `gh issue` + REST do not expose parent/child.
4. Add each to Felix Roadmap project per memory `project_github_project_backlog`. Set domain field as appropriate (likely `area/task-intel`).
5. **Back-fill**: replace any `#N` placeholders in `findings.md` and `recommendation.md` with the actual filed issue numbers. Add filed-issue rows to source-register (`source_id = issue-<num>`).

**Validation** (NFR-005):
- [ ] All sub-issues linked to #507 (verify via `gh api graphql` query).
- [ ] All sub-issues use "Depends on #N" where applicable.
- [ ] No dependency cycles in filed sub-issues (visually inspect the DAG).
- [ ] All sub-issues have `spec: brief`.
- [ ] CSV rows added for filed issues.

**Files**: edits to `findings.md` + `recommendation.md`; GitHub issues created (off-repo).

### T017 — Final NFR / SC readiness check

**Purpose**: Quality gate before WP03 moves to `for_review`.

**Steps**:
1. **NFR-004**: re-read `recommendation.md` + draft `adr-0003.md` cold. If anything reads ambiguous or assumes working-notes context, revise.
2. **NFR-005**: verify filed sub-issues' dependency DAG has no cycles.
3. **SC-001**: confirm supersede-vs-extend choice is explicit with rationale in `findings/rq-6-adr-scope.md` and reflected in ADR front matter.
4. **SC-007 readiness**: confirm `findings.md` footer names exact next step (operator review on #508 with accept-or-reject decision recorded as a comment).
5. Add a section to `findings.md` titled **Mission status** with: artifacts produced (linked), sub-issues filed (linked), operator-review-pending, expected operator action.

**Validation**:
- [ ] NFR-004: operator-cold readability passes.
- [ ] NFR-005: no cycles in sub-issue DAG.
- [ ] SC-001: explicit supersede-or-extend rationale.
- [ ] SC-007: operator-review-pending documented.

**Files**: edits to `findings.md`.

## Definition of Done

- `findings/rq-6-adr-scope.md` exists with verdict + rationale.
- `findings.md` exists with synthesis/index + Mission status block.
- `recommendation.md` exists, operator-cold readable.
- `docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md` exists as Draft with polling-only Mermaid diagram.
- 2–4 sub-issues filed under #507, linked via GraphQL, with `spec: brief` labels and `Depends on #N` declarations.
- Cross-references back-filled in `findings.md` + `recommendation.md`.
- T017 quality gate passes.
- WP03 moves cleanly to `for_review`.

## Risks

- `kg-felix-bot` token unavailable → blocker; do not file under Kent's identity.
- Recommendation surfaces ADR-0002 tension requiring operator input → escalate; do not unilaterally re-open ADR-0002.
- Sub-issue body construction takes longer than expected → prioritize 2 clean issues over rushing 4. Minimum is 2 (FR-012).
- Roadmap scope drifts beyond 4 missions → file 4 + add count-overrun note in `findings.md`. Surface to operator.
- Recommendation contradicts WP01/WP02 substrate → stop; surface contradiction.

## Reviewer Guidance

- ADR-0003 reads operator-cold (spot-check: pick a section, read without context, "would operator understand?").
- Supersede-vs-extend choice has explicit rationale tied to specific ADR-0002 decisions.
- Mermaid interaction-model diagram reflects polling-only (no webhooks).
- Sub-issues exist on GitHub, linked to #507 (not just referenced), use "Depends on #N" where applicable.
- `findings.md` Mission status section concrete (names exact next operator criterion).
- Recommendation does not introduce architectural decisions not also in ADR-0003.

## Cross-references

- Spec: [spec.md](../spec.md) § FR-006, FR-007, FR-009, FR-012, NFR-001, NFR-004, NFR-005, NFR-007, SC-001, SC-005, SC-007, C-008.
- Plan: [plan.md](../plan.md) § RQ-6.
- Decision log: [research.md](../research.md).
- Inputs from WP01 + WP02: all per-RQ files + conflict-event-log.sketch.md + CSV rows.
- Format reference: ADR-0001.
- Base ADR: ADR-0002.
- Parent epic: [#507](https://github.com/kentonium3/kg-automation/issues/507).
- Cross-referenced spike: [#516](https://github.com/kentonium3/kg-automation/issues/516).

## Output Discipline

Operator-facing artifacts (`recommendation.md`, draft ADR-0003, `findings.md`) follow Felix output-discipline pattern strictly: succinct, structured, no boilerplate. ADR is the canonical record; brevity wins where clarity is preserved. Recommendation can be slightly longer (it's the explainer).

## Activity Log

- 2026-06-04T01:28:58Z – claude:sonnet:implementer:implementer – shell_pid=89671 – Started implementation via action command
