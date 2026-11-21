---
work_package_id: WP10
title: Live-data inventory and reversible repair
dependencies:
- WP01
- WP02
requirement_refs:
- FR-021
- FR-022
- NFR-005
- C-004
- SC-003
planning_base_branch: fix/felix-rrule-adaptation
merge_target_branch: fix/felix-rrule-adaptation
branch_strategy: Planning artifacts for this mission were generated on fix/felix-rrule-adaptation. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-rrule-adaptation unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-rrule-adaptation-01M7TKNX
base_commit: 5326880634f73f35a626efc5b2d55ce41217035c
created_at: '2026-11-19T23:20:03.189491+00:00'
subtasks:
- T046
- T047
- T048
- T049
- T050
phase: Phase 2 - Live data
history:
- at: '2026-11-19T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/vikunja/
create_intent:
- scripts/vikunja/rule_inventory.py
- scripts/vikunja/rule_repair.py
- tests/vikunja/test_rule_inventory.py
- tests/vikunja/test_rule_repair.py
- docs/runbooks/vikunja-task-repair.md
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/vikunja/rule_inventory.py
- scripts/vikunja/rule_repair.py
- tests/vikunja/test_rule_inventory.py
- tests/vikunja/test_rule_repair.py
- docs/runbooks/vikunja-task-repair.md
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP10 – Live-data inventory and reversible repair

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `spec-kitty agent tasks status` for a `review_ref`, and address every item before going back to review.

---

## Objectives & Success Criteria

Build the two helpers specified in `contracts/repair-and-inventory-cli.md`, plus a runbook. **This WP does not touch live data.** It is reviewable entirely from its diff: helpers, tests and runbook. Operating the helpers against live data is an operator step outside this WP (C-004), described in `quickstart.md` and the runbook.

1. **`rule_inventory`** (read-only, FR-021):
   - Compares a **read-only copy** of a snapshot DB (the rule columns only) with live v2 GETs.
   - Classifies each task `ok | progressed | ended | lost | removed | changed | unresolved`.
   - `lost` requires Felix-write attribution.
   - Cross-checks the sync `seed-ledger.jsonl`.
   - Records a `current_fingerprint` per task.
2. **`rule_repair`** (FR-022, NFR-005) supports `--dry-run`, `--apply`, `--resume`, `--restore` and `--emit-issue-markdown`, with:
   - a drift check;
   - a durable snapshot before the write;
   - an intent journal;
   - a clear-first rule write;
   - a readback;
   - an outcome journal entry for every attempt;
   - an ordered restore.
3. **Runbook** `docs/runbooks/vikunja-task-repair.md` covers when to use the helpers, the exact commands, UI exclusion during a run, how to post on #1111, and how to undo.

## Context & Constraints

- Read in full: `contracts/repair-and-inventory-cli.md`; `data-model.md` (Damage inventory entry, Live-write record, Repair restore algorithm, Invariant 5); research.md R-009; and post-plan-review.md findings 3, 4 and 6 plus re-review items 3, 4 and new-HIGH 2. **Those reviews define the edge cases. Implement every one, and test it.**
- **Snapshot DB.**
  - The pre-cutover snapshot is under `/data/services/vikunja/snapshots/20261030T081520Z/`. It is claude-owned, mode 700, and private.
  - The helper takes `--baseline-db PATH` and opens it as `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`.
  - It **refuses** the live DB path (`/data/services/vikunja/data/vikunja.db`) and any path under `/data/services/vikunja/data/`.
  - It reads `id, repeats, repeats_from_current_date` only. **Discover the snapshot's actual column names** with `PRAGMA table_info(tasks)`, both in the code and in a test using a synthetic sqlite file. Do not assume the column names. The release baseline (`scripts/deploy/vikunja_release/baseline.py:189`) used `repeats` and `repeats_from_current_date`.
- **Privacy.** The inventory's `--out` file is mode 600. The stdout summary and `--emit-issue-markdown` print **task ids and rule text only**, plus titles **only** for the habit task ids already public on #1111 (14, 15, 16, 18, 19, 20, 65, 75, 76, 77). No `@mentions` anywhere.
- **Attribution sources** (`--felix-logs`), all read-only and all on office2:
  - `/data/services/openclaw/state/habits/sweeper-ledger.jsonl` and `habits-history.jsonl`;
  - `/data/services/openclaw/state/escalation/*.jsonl`;
  - the intake reply log. Find its path in `scripts/intake/apply_reply.py`'s state constants.
  - A Felix write counts when it names the task id after 2026-10-30, and the task's live `updated` is within 120 s of it. This is a documented residual risk (post-plan-review.md re-review 2, item 4).
- The client comes from WP02 (`get_task_v2`, `patch_task` with the internal `_allow_null`, which this WP uses only on the restore path). The rule library comes from WP01.
- State dir: `/data/services/openclaw/state/vikunja-repair/<run_id>/`, overridable with `--state-dir`, which tests use.

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

```bash
spec-kitty agent action implement WP10 --agent claude --mission felix-rrule-adaptation-01M7TKNX
```

## Subtasks & Detailed Guidance

### Subtask T046 – `rule_inventory`

- **Steps**:
  1. Read the baseline rows: task id → `(rule_text, from_current)`. Rows with an empty rule are not candidates, unless they appear in the habit schedule, which acts as a second source (`--schedule-path`).
  2. For each candidate, call `get_task_v2(id)`. A 404 gives status `deleted`; add it to the status set and the docs.
  3. Classify, in this order (the order matters, per re-review new-HIGH 2):
     - (a) `ok`: same rule;
     - (b) `progressed`: same rule except a lower COUNT;
     - (c) `ended`: done, with the baseline rule having COUNT and now no rule, or having UNTIL and the rule kept;
     - (d) `lost`: no rule now, the baseline had one with no COUNT/UNTIL, and Felix attribution exists;
     - (e) `removed`: as (d) but with no attribution, **or** done with no rule where the baseline had COUNT/UNTIL but the end could not be confirmed;
     - (f) `changed`: a different rule;
     - (g) `unresolved`: no restore source.
  4. Seed-ledger cross-check: applied after (c).
  5. Write `--out` (mode 600) with full entries, including `current_fingerprint`. Stdout gets the summary JSON from the contract.

### Subtask T047 – `rule_repair --dry-run` / `--apply`

- Implement steps 1–5 of the contract exactly: drift check → snapshot + fsync → intent journal + fsync → clear-first rule write → readback → outcome journal.
- **Scope.** `--apply` acts on `lost` only. Other statuses need `--task-id N --accept-changed`. Refuse otherwise, with a message.
- **Stop conditions.** Stop the run on a snapshot or journal write failure, which happens before any Vikunja write. Also stop on `mismatch` or `unknown`, printing the restore command. A `skipped_drift` continues with the next task.
- `run_id` is a ULID. Check `scripts/` for an existing ULID helper first (the sweeper has `new_tick_id`).

### Subtask T048 – `--resume`, `--restore`, `--emit-issue-markdown`

- `--resume <run_id>`: for each intent without an outcome, do a fresh read, then record `ok`, `mismatch` or `unknown` (compare with the intent's `intended`) **before** anything else. Then continue with any remaining planned tasks.
- `--restore <snapshot.before.json>`: the ordered restore algorithm from data-model.md:
  1. Rule: clear-first, then set from canonical text, or clear only (with the flag) if the snapshot had none.
  2. Reminders, with `[]` for null.
  3. Due date, using `_allow_null={"due_date"}` when the snapshot had none.
  4. `done=false` only when the snapshot was open. **Refuse** a restore to `done=true` while a rule exists.
  5. A full readback, reporting every field that differs.

  Journal it the same way as `--apply`.
- `--emit-issue-markdown <run_id>`: a table with columns task id | before rule | after rule | readback | outcome | restore command, plus a header naming the run id, the time and the operator. The operator posts it with `gh issue comment 1111 --repo kentonium3/kg-automation --body-file <file>`. The helper itself has no GitHub access.

### Subtask T049 – Tests

- Use the WP01 factory, a synthetic sqlite snapshot built in `tmp_path`, and `mock_vikunja_urlopen`.
- **Inventory**:
  - each status, including the ordering cases: a COUNT series ended plus a seeded no-rule is `ended`, not `lost`; no attribution gives `removed`;
  - refusing the live DB path;
  - `PRAGMA` column discovery;
  - **zero write calls** (assert the request methods are only GET).
- **Repair**:
  - dry-run makes zero writes;
  - apply writes in the order snapshot file → intent line → PATCH `{"repeat":null}` → PATCH rule → GET → outcome line; assert the file and journal exist *before* the first PATCH by intercepting it;
  - drift gives `skipped_drift` with no write;
  - a readback mismatch stops the run and journals `mismatch`;
  - a timeout on PATCH journals `unknown`, and resume resolves it;
  - snapshot write failure causes no Vikunja call.
- **Restore**:
  - a different rule;
  - a decremented COUNT, where clear-first defeats the stale echo, shown by asserting the request sequence;
  - null reminders sent as `[]`;
  - a null due date;
  - an open snapshot against a done task gives `done=false`;
  - a done snapshot against a task with a rule is refused.
- **Emit**: the markdown contains no titles outside the allowed ids and no `@`.

```bash
python3 -m pytest -q tests/vikunja/test_rule_inventory.py tests/vikunja/test_rule_repair.py
```

```bash
make test
```

### Subtask T050 – Runbook

- `docs/runbooks/vikunja-task-repair.md` needs valid frontmatter (validate_docs). Read an existing runbook for its shape.
- Sections:
  - **Purpose.**
  - **Preconditions:** fixes deployed, the token re-issued, the rollout window closed.
  - **Read-only copy of the snapshot:** make a copy into a private scratch dir and never open the original. Use `cp --preserve=mode` as `claude`, and fall back to a Kent-run copy if permissions require it.
  - **Inventory command**, then **post the summary on #1111**.
  - **Dry-run**, posted on #1111 for visibility.
  - **Apply.**
  - **Emit and post.**
  - **Restore.**
  - **Resume after interruption.**
  - **UI exclusion:** don't edit the affected tasks during a run.
  - **Residual-risk note** (attribution).
- WP11 adds the INDEX and DEVELOPER_PORTAL links. This WP only creates the runbook.

## Risks & Mitigations

- **Touching the original snapshot or the live DB.** Path refusal plus `mode=ro`, both tested.
- **A journal gap on crash.** Intent-before-write plus resume, both tested.

## Review Guidance

- Walk the contract's step list against the code and confirm each step has a test.
- Confirm the inventory and dry-run make no writes (tests).
- Confirm no private titles leak into the issue markdown.

## Progress & Status

Use `spec-kitty agent tasks add-history WP10 --note "..."` and `spec-kitty agent tasks mark-status T0xx --status done`.
