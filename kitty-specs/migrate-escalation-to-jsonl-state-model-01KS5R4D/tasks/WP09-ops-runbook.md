---
work_package_id: WP09
title: Operations runbook + soak monitoring
dependencies:
- WP07
requirement_refs:
- FR-011
- NFR-002
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-21T17:45:30+00:00'
subtasks:
- T027
- T028
- T029
agent: "codex:gpt-5:spec-kitty-review:reviewer"
shell_pid: "22804"
history:
- at: '2026-05-21T17:45:30+00:00'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: docs/runbooks/
execution_mode: code_change
mission_id: 01KS5R4D79WQQWY2MCHZVCT85G
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
owned_files:
- docs/runbooks/escalation-ops.md
- kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/quickstart.md
- kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/SOAK.md
tags: []
---

# WP09 — Operations runbook + soak monitoring

## Objective

Rewrite the escalation operations runbook for the new JSONL-based flow. Pin quickstart.md to deployed reality (paths, commands, exit code semantics). Add the SOAK.md template that captures the 3-day post-cutover monitoring data. Implements FR-011 (3-day soak), NFR-002 (95% gate), SC-006 (soak completion gate).

## Context

- **Mission spec**: FR-011 (3-day soak observed), NFR-002 (≥95% tick success), SC-006 (soak gate)
- **Plan**: research D11 (comment-write parity during soak)
- **Quickstart already drafted**: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/quickstart.md` (planning-phase output) — needs verification + pinning post-implementation.
- **Existing runbook**: `docs/runbooks/escalation-ops.md` (if exists) — describes v1 ops. Needs full rewrite.
- **Habits Phase 5 precedent**: cutover runbook + soak — read `docs/runbooks/habits-ops.md` for the pattern (per project history file `f6558765` and related).
- **Dependency**: WP07 — the runbook references the new SKILL.md / AGENTS.md surface.
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T027 — Rewrite `docs/runbooks/escalation-ops.md`

**Purpose**: Single-source ops doc for the new flow. A new operator reading this end-to-end can execute the full lifecycle.

**Steps**:

1. Check if `docs/runbooks/escalation-ops.md` exists. If not, create it. If yes, read it first and identify what to preserve vs. replace.
2. New structure:
   ```markdown
   ---
   id: escalation-ops
   doc_type: runbook
   title: Escalation Operations
   status: approved
   level: 2
   owners: [kent]
   last_validated: '2026-05-21'
   updated_by: '#309'
   version: '2.0.0'
   ---

   # Escalation Operations

   ## Overview
   <2-3 paragraph description of the escalation subsystem post-#309>

   ## Daily operation (steady state)
   - Tick cadence: <when>, <what triggers it>
   - Where state lives: JSONL files per project
   - How to query current state for a task: derive_state CLI
   - How to read recent ticks: journalctl + parse stdout structure

   ## Cutover procedure
   Cross-reference quickstart.md. Don't duplicate — link.

   ## Verification & monitoring
   - Tick success rate query
   - JSONL growth check
   - Open hard-fail bug query
   - Spurious re-alert check (manual via WhatsApp history)

   ## Rollback procedure
   Cross-reference quickstart.md § Rollback.

   ## Maintenance
   - When to rotate the JSONL files (if ever — likely never at projected scale)
   - How to inspect a malformed record manually
   - How to manually repair a JSONL file (operator_repair source)

   ## Cross-references
   - mission #309 (this mission)
   - quickstart.md (cutover playbook)
   - SKILL.md / AGENTS.md (in scripts/openclaw/)
   - Phase 2 library docs
   ```
3. Each section: concrete commands, no hand-waving. If a command requires sudo, mark it as "Kent runs via `ssh office2-kgale`" (per CLAUDE.md).
4. Frontmatter compliant with project standards (`docs/design/standards.md` if present).

**Files**:
- `docs/runbooks/escalation-ops.md` (rewritten — target ~200-260 lines)

**Validation**:
- [ ] A fresh reader can execute steady-state ops without consulting any other file (except via explicit links).
- [ ] No commands reference v1 comment-parsing.
- [ ] Frontmatter has `updated_by: '#309'`.
- [ ] All command examples use the post-#309 CLIs.

---

### T028 — Verify quickstart.md matches deployed reality

**Purpose**: The planning-phase quickstart was drafted before implementation. Now that the actual paths, exit codes, and CLI flags are known, pin every detail.

**Steps**:

1. Re-read `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/quickstart.md` with the WP01-WP07 implementations in hand.
2. For each command in quickstart.md:
   - Verify the exact CLI flags match contracts/cli.md (which itself was finalized in WP01-WP06 implementations).
   - Verify the exact paths match the runtime constants in `scripts/escalation/*` modules.
   - Verify exit codes match `record_completion`, `reconcile_completions`, `backfill_jsonl_from_comments` actual behavior.
3. Update any drifted commands. Common drift cases:
   - Path constants changed during implementation.
   - Exit codes reshuffled for clarity.
   - Flag names renamed.
4. Add a "Last verified against" footer with the commit SHA of the WP07 merge (or the most recent helper-touching commit at quickstart-update time).

**Files**:
- `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/quickstart.md` (modified — pinned to deployed reality)

**Validation**:
- [ ] Every CLI command in quickstart matches `python3 -m scripts.escalation.<helper> --help` output.
- [ ] Every path matches the corresponding module constant.
- [ ] Exit code references match the actual `sys.exit(...)` values in the helpers.

---

### T029 — Add SOAK.md template + soak-monitoring checklist

**Purpose**: A pre-filled template operators populate during the 3-day soak. Captures the 95% gate data + spurious-re-alert audit + hard-fail count.

**Steps**:

1. Create `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/SOAK.md`:
   ```markdown
   # Phase 6 Soak Window

   **Cutover date**: __YYYY-MM-DD__
   **Soak end date**: __YYYY-MM-DD__ (cutover + 3 calendar days)
   **Mission**: #309

   ## Daily check-in

   Run these queries once per day during soak. Record values below.

   ### Day 1
   - Date: __YYYY-MM-DD__
   - Ticks fired (journalctl): __N__
   - Ticks completed exit 0: __N__
   - Tick success rate: __% (target: ≥95%)__
   - New `escalation` JSONL records: __N__
   - Open hard-fail bugs: __N__ (zero is ideal; non-zero requires triage but does NOT block soak)
   - Spurious re-alert reports from Kent: __0__ (any other value = STOP and rollback)
   - Notes: __free-form__

   ### Day 2
   <same template>

   ### Day 3
   <same template>

   ## Soak completion gate (NFR-002, SC-006)

   - [ ] All 3 daily check-ins completed
   - [ ] Aggregate tick success rate ≥95%
   - [ ] Zero spurious re-alerts across the 3-day window
   - [ ] Hard-fail bugs (if any) are triaged or accepted (not blocking)

   If all four checked: declare Phase 6 complete. File follow-on issue for v1 comment-write removal.

   ## Useful queries

   ```bash
   # Tick success rate (single day)
   ssh office2-claude
   journalctl --user --machine=office2-claude@ -u escalation.service \
     --since "today 00:00" --until "tomorrow 00:00" --output=cat \
     | grep -cE "Started|Finished" # interpret as fired vs successful

   # New JSONL records (single day)
   ssh office2-claude
   for f in /data/services/openclaw/state/escalation/project-*-escalation-history.jsonl; do
     awk -v today=$(date -I) -F'"' '$0 ~ today { print }' "$f" | wc -l
   done | paste -sd+ | bc

   # Open hard-fail bugs
   gh issue list --repo kentonium3/kg-automation \
     --label P2-bug --search "Escalation hard-fail" --state open --json number,title,createdAt
   ```
   ```
2. Frontmatter NOT included (this is a mission-scoped artifact, not a runbook).

**Files**:
- `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/SOAK.md` (new, ~80 lines)

**Validation**:
- [ ] File exists with the 3-day template.
- [ ] Every query block uses real commands that would work on office2 today.

---

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Execution worktree allocated per `lanes.json` after `finalize_tasks`.

## Test Strategy

Doc-only WP. Validation via manual review + a "fresh reader" walkthrough — can a new operator execute the cutover + soak end-to-end using only these files?

## Definition of Done

- [ ] T027-T029 subtasks complete with all validations green.
- [ ] `docs/runbooks/escalation-ops.md` rewritten with v2 procedures.
- [ ] `quickstart.md` pinned to deployed CLI/paths/exit codes.
- [ ] `SOAK.md` template ready for operator use during the 3-day soak.

## Risks

- **Doc drift between runbook and quickstart**: T028 + T027 must converge. The reviewer should diff them for any contradictory instructions.
- **CLI-flag drift mid-implementation**: WP01-WP06 may have changed flag names. T028 catches this — but ONLY if the reviewer actually runs each `--help`.
- **Soak gate ambiguity**: NFR-002's "≥95% of escalation ticks complete with a successful structured signal" — make sure SOAK.md's daily check-in operationalizes this clearly.

## Reviewer Guidance

1. Read `docs/runbooks/escalation-ops.md` end-to-end as if you're a new operator. Can you execute steady-state ops without confusion?
2. Diff quickstart.md against actual helper `--help` outputs. Any drift = WP09 fails.
3. Read SOAK.md. Can a non-author populate it day-by-day without ambiguity?
4. Verify cross-references are accurate (no broken markdown links).

## Implementation Command

```bash
spec-kitty agent action implement WP09 --mission migrate-escalation-to-jsonl-state-model-01KS5R4D --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-21T22:06:14Z – claude:opus:python-implementer:implementer – shell_pid=20835 – Started implementation via action command
- 2026-05-21T22:16:48Z – claude:opus:python-implementer:implementer – shell_pid=20835 – Re-scoped per Kent: lane keeps docs/runbooks/ only; kitty-specs SOAK.md moved to docs/runbooks/escalation-soak-window.md; quickstart.md edits deferred to chore commit on main
- 2026-05-21T22:16:55Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=22804 – Started review via action command
