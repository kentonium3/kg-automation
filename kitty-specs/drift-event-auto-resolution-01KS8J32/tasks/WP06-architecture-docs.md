---
work_package_id: WP06
title: Architecture docs + ops runbook
dependencies: []
requirement_refs:
- C-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-drift-event-auto-resolution-01KS8J32
base_commit: 3ca2785869415a756fbf1cc04190f8414c349b34
created_at: '2026-05-22T19:52:50.029336+00:00'
subtasks:
- T029
- T030
- T031
- T032
shell_pid: "3065"
history: []
authoritative_surface: docs/
execution_mode: code_change
mission_id: 01KS8J321F8KE7369R3DA02329
mission_slug: drift-event-auto-resolution-01KS8J32
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data-flows.md
- docs/design/architecture/data-flows.view.md
- docs/runbooks/doc-auditor-driver-ops.md
tags: []
agent: "agy:gemini-2.5-pro:spec-kitty-review:reviewer"
---

# WP06 — Architecture docs + ops runbook

## Objective

Update the JSON arch docs (service-inventory, data-flows) for the new `scripts/doc_audit/judgment/drift_interpretation.py` module + supporting files. Update markdown views to match. Add Moment 0 to the doc-auditor-driver-ops runbook. Implements C-007 (in-mission doc updates per Constitution Directive 5).

## Context

- **Spec**: C-007 (arch docs in-mission)
- **Plan**: Project Structure section enumerates the new files
- **Pattern source**: mission #309's WP08 / mission #371's WP05 did the same shape — refer to their commits for the JSON entry style
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T029 — service-inventory.json updates

**Purpose**: Register the new modules.

**Steps**:

1. Read existing `docs/design/architecture/data/service-inventory.json`. Find the existing `felix-doc-auditor-driver` entry.
2. Update `felix-doc-auditor-driver`:
   - `last_updated: "2026-05-22"`
   - `updated_by: "#362"`
   - Extend `judgment_moments` (or equivalent field) to include `drift_interpretation`. If the field doesn't exist yet, add it as a list including the existing moments (`tier_classification`, `cross_file_implication`, `debt_body_generation`) PLUS `drift_interpretation`.
   - Extend `depends_on` (if present) or add a `helpers` block listing the new modules.
3. Add new entries (or extend existing config_files block — match the mission #309/#371 pattern):
   - `drift_interpretation` — kind=judgment_module, path=`scripts/doc_audit/judgment/drift_interpretation.py`, invoked_by=felix-doc-auditor-driver, calls=`api.anthropic.com`, credentials=`["anthropic-api"]`, introduced_by=`"#362"`.
   - `drift_ledger` — kind=storage, path=`scripts/doc_audit/output/drift_ledger.py`, writes_to=`/data/services/security-monitor/logs/drift-events-ledger.jsonl`, introduced_by=`"#362"`.
   - `drift_to_proposed_edit` — kind=translator, path=`scripts/doc_audit/routing/drift_to_proposed_edit.py`, invoked_by=handle_drift_events, introduced_by=`"#362"`.
   - `cutover_362` — kind=one_shot_script, path=`scripts/doc_audit/helpers/cutover_362.py`, invoked_by=`operator`, introduced_by=`"#362"`.
4. Update `handle_drift_events` entry:
   - `last_updated: "2026-05-22"`
   - `updated_by: "#362"`
   - Add reference to the new config block `[drift_interpretation]`

**Files**: `docs/design/architecture/data/service-inventory.json` (modified).

**Validation**:
- [ ] `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` succeeds
- [ ] Every new entry has `introduced_by: "#362"` or `updated_by: "#362"`

---

### T030 — data-flows.json updates

**Purpose**: Register new LLM call path + ledger writes.

**Steps**:

1. Read existing `docs/design/architecture/data/data-flows.json`.
2. Add new flow entries:
   - `doc-audit-drift-interpretation-llm` — from `scripts/doc_audit/judgment/drift_interpretation.py`, to `api.anthropic.com`. Trigger: per drift event when `[drift_interpretation].enabled = true`. introduced_by="#362".
   - `doc-audit-drift-ledger-write` — from `scripts/doc_audit/output/drift_ledger.py`, to `/data/services/security-monitor/logs/drift-events-ledger.jsonl`. Trigger: per processed drift event. introduced_by="#362".
   - `doc-audit-cutover-gh-close` — from `scripts/doc_audit/helpers/cutover_362.py`, to `api.github.com`. Trigger: one-shot operator invocation. introduced_by="#362".
3. Update any existing flows referencing `handle_drift_events` to note v2 (since #362).

**Files**: `docs/design/architecture/data/data-flows.json` (modified).

**Validation**:
- [ ] JSON parses
- [ ] All 3 new flow entries have `introduced_by: "#362"`

---

### T031 — Markdown views match JSON

**Purpose**: Per Felix Constitution Directive 5 — JSON ↔ markdown parity.

**Steps**:

1. Identify which markdown views derive from service-inventory + data-flows. Candidates:
   - `docs/design/architecture/service-inventory.md`
   - `docs/design/architecture/data-flows.md`
   - `docs/design/architecture/data-flows.view.md` (Mermaid)
2. For each:
   - Add narrative entries for the 4 new modules (drift_interpretation, drift_ledger, drift_to_proposed_edit, cutover_362)
   - Update felix-doc-auditor-driver section to note Moment 0 layer + v2 since #362
   - If Mermaid is present: add nodes for the new modules + the ledger file + the new LLM call edge; redraw arrows accordingly
3. If `tooling/scripts/validate_docs.py` exists in the repo, run it; do NOT introduce new errors (pre-existing errors out of scope).

**Files**:
- `docs/design/architecture/service-inventory.md` (modified)
- `docs/design/architecture/data-flows.md` (modified)
- `docs/design/architecture/data-flows.view.md` (modified)

**Validation**:
- [ ] Every new JSON entry has a corresponding markdown narrative
- [ ] If Mermaid present: new nodes + edges visible
- [ ] No new validate_docs.py errors

---

### T032 — doc-auditor-driver-ops.md update

**Purpose**: Operator-facing runbook for the Moment 0 layer.

**Steps**:

1. Read existing `docs/runbooks/doc-auditor-driver-ops.md`. Identify the "judgment moments" or "tick lifecycle" section.
2. Add new section: **Moment 0 — drift interpretation**
   - Trigger: every mapped drift event when `[drift_interpretation].enabled = true`
   - LLM call: Haiku 4.5; cache-aware prompt
   - Three verdicts: PROPOSED_EDIT, JUDGMENT_REQUIRED, NO_CHANGE_NEEDED
   - Confidence threshold: 0.80 (below → demote to JUDGMENT_REQUIRED)
   - Retry policy: 30s/60s/120s; on exhaustion → fallback to pre-#362 issue filing
3. Add **Ledger queries** subsection:
   ```bash
   # Triage rate (NFR-001 metric)
   python3 -m scripts.doc_audit.output.drift_ledger triage-rate --days 7
   
   # Outcome breakdown
   python3 -m scripts.doc_audit.output.drift_ledger summary --days 7
   
   # Recent entries
   python3 -m scripts.doc_audit.output.drift_ledger tail
   ```
4. Add **Rollback** subsection:
   ```bash
   # Disable Moment 0 (cuts back to pre-#362 behavior)
   ssh office2-claude 'sed -i "s/^enabled = true$/enabled = false/" ~/kg-automation/scripts/doc_audit/config.toml'
   ```
5. Update frontmatter: `last_validated: 2026-05-22`, `updated_by: "#362"`, bump version.
6. Cross-reference the mission quickstart (`kitty-specs/drift-event-auto-resolution-01KS8J32/quickstart.md`).

**Files**: `docs/runbooks/doc-auditor-driver-ops.md` (modified, ~80 line delta).

**Validation**:
- [ ] Frontmatter `updated_by: "#362"`
- [ ] Every CLI example matches the actual `--help` output of the deployed helpers
- [ ] No broken markdown links

---

## Branch Strategy

Planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Test Strategy

Doc-only WP. Validation via:
- JSON parse (`python3 -c "import json; json.load(...)"`)
- Markdown ↔ JSON cross-check (manual + project's validator if available)
- Reviewer walks the runbook end-to-end

## Definition of Done

- [ ] All 4 subtasks complete.
- [ ] JSON files parse and have `updated_by: "#362"` on touched entries.
- [ ] Markdown views match JSON sources.
- [ ] Runbook covers Moment 0 + ledger queries + rollback.
- [ ] Cross-references resolve (no broken links).

## Risks

- **JSON ↔ markdown drift**: easy to update one and forget the other. Manual review + validator catches most.
- **Mermaid diagram complexity**: the data-flows.view.md may become unwieldy with new nodes; if it does, consider splitting into two diagrams (a follow-on PR, not in scope here).
- **task-detection cron drift** (existing pre-condition discovered during #310 spec-readiness): out of scope here; mention in a comment if encountered.

## Reviewer Guidance

1. Cross-check every new JSON entry has a markdown counterpart.
2. Verify the runbook covers Moment 0 + ledger CLI + rollback.
3. Run `--help` on `drift_interpretation`, `drift_ledger`, and `cutover_362`; compare against runbook examples.
4. Confirm `updated_by: "#362"` on all touched entries.

## Implementation Command

```bash
spec-kitty agent action implement WP06 --mission drift-event-auto-resolution-01KS8J32 --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-22T19:52:52Z – claude:opus:python-implementer:implementer – shell_pid=729 – Assigned agent via action command
- 2026-05-22T20:02:51Z – claude:opus:python-implementer:implementer – shell_pid=729 – Ready for review: architecture docs + ops runbook updated
- 2026-05-22T20:03:43Z – agy:gemini-2.5-pro:spec-kitty-review:reviewer – shell_pid=3065 – Started review via action command
- 2026-05-22T20:05:58Z – agy:gemini-2.5-pro:spec-kitty-review:reviewer – shell_pid=3065 – Review passed: All JSON architecture registry entries for Moment 0 modules and data flows were successfully added with proper metadata, and are fully synced with their Markdown narrative and Mermaid visual counterparts. The operations runbook was comprehensively updated with Moment 0 execution details, CLI ledger queries, and configuration-driven rollback instructions. Document validation checks succeeded with zero errors introduced.
