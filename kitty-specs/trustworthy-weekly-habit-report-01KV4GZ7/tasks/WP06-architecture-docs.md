---
work_package_id: "WP06"
title: "Architecture documentation update"
subtasks: ["T022", "T023", "T024", "T025"]
dependencies: ["WP02"]
planning_base_branch: "main"
merge_target_branch: "main"
branch_strategy: "lane-from-coord"
owned_files:
  - "docs/design/architecture/data/service-inventory.json"
  - "docs/design/architecture/data/data-flows.json"
  - "docs/design/architecture/data/signal-to-doc-map.json"
  - "docs/design/architecture/services.md"
authoritative_surface: "docs/design/architecture/data/service-inventory.json"
execution_mode: "code_change"
agent_profile: "curator-carla"
role: "documenter"
agent: "claude"
requirement_refs: ["FR-011", "SC-006"]
history:
  - at: "2026-06-15T02:33:00Z"
    actor: "spec-kitty agent mission tasks"
    event: "WP created from /spec-kitty.tasks"
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, load your assigned agent profile via `/ad-hoc-profile-load curator-carla`. This WP is documentation-shaped (machine-readable JSON + narrative markdown), so the curator profile is more appropriate than the default implementer.

## Objective

Update the kg-automation architecture documentation to accurately describe the new canonical-read path. The current files state or imply that the weekly habit report queries Vikunja `done_at` history — which is the bug. Post-WP02, the report reads from `habits-history.jsonl`; the architecture docs must reflect that, or future contributors will reverse the fix.

## Context

Per kg-automation CLAUDE.md "Architecture Documentation" standing requirement: "Any feature that changes deployed services, credentials, data flows, or network topology must update the relevant files in `docs/design/architecture/` and `docs/design/architecture/data/`." Per Felix Constitution Directive 5, machine-readable JSON is authoritative; narrative markdown provides context.

This WP is the documentation closeout for the mission. It lands as the LAST of the parallel post-WP02 WPs (alongside WP03 + WP04 + WP05) and ensures `service-inventory.json` says what's true after the fix.

Read before starting:

- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/spec.md` (FR-011, SC-006)
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/plan.md` (IC-06)
- `docs/design/architecture/data/service-inventory.json` — current state
- `docs/design/architecture/data/data-flows.json` — current state
- `docs/design/architecture/data/signal-to-doc-map.json` — entry filter rules
- `docs/design/architecture/change-control.md` — the update protocol

## Subtasks

### T022 — [P] Update `service-inventory.json` felix-admin-habits weekly-tick description

The felix-admin-habits agent's `purpose` field currently contains language like:

> "the weekly Sunday-22:00 cron tick is also deterministic-helper-backed — the agent invokes scripts/habits/query_active_habits_weekly.py which queries Vikunja directly via the new shared scripts/common/vikunja_client.py for `done_at` history (NOT the sync cache, which holds current state only)"

That sentence is the bug-documented-as-design — it claims the weekly tick reads Vikunja `done_at` for history, which we now know is the bug. Rewrite it.

New sentence (target wording — adjust to match surrounding prose tone):

> "the weekly Monday-06:00 cron tick is deterministic-helper-backed — the agent invokes `scripts/habits/query_active_habits_weekly.py`, which queries the canonical `/data/services/openclaw/state/habits-history.jsonl` for completion history via the `scripts/habits/history.py` domain wrapper (built on `scripts/common/state_log.py`). Vikunja is queried for current-state task list + classification only; `done_at` history is NOT consulted because `repeat_after` recurrence resets that field on each cycle."

Update any other prose in this entry that references the prior cron schedule (`Sunday 22:00`) or the prior data source (Vikunja `done_at`).

After editing: `jq . docs/design/architecture/data/service-inventory.json > /dev/null` parses cleanly.

### T023 — [P] Update `data-flows.json` weekly-tick flow entry

Search for any data-flow entry referencing the weekly tick:

```bash
grep -nE "(weekly|query_active_habits_weekly|habits-weekly|01KTKSFT)" docs/design/architecture/data/data-flows.json
```

Likely candidates: entries with `from: "felix-admin-habits agent"` for the weekly flow, or entries referencing the prior mission slug `vikunja-client-and-habits-weekly-report-01KTKSFT`.

For each affected flow entry:
- Update the `description` to reflect the canonical-read path (read from `habits-history.jsonl` via the wrapper, not Vikunja `done_at`).
- Update the `source` or `from`/`to` shape if it explicitly names Vikunja as the completion-history source — point it at `habits-history.jsonl`.
- Update any prose that asserts the prior schedule (Sunday 22:00) — refer to "weekly tick" abstractly or use the new schedule (Monday 06:00) consistently.

After editing: `jq . docs/design/architecture/data/data-flows.json > /dev/null` parses cleanly.

### T024 — [P] Update `signal-to-doc-map.json` if applicable

Per kg-automation CLAUDE.md, signal-to-doc-map.json is consulted during specify/plan for architecture-impact lookups. Check whether the felix-admin-habits weekly tick has an entry here:

```bash
grep -nE "(felix-admin-habits|query_active_habits_weekly|weekly_report)" docs/design/architecture/data/signal-to-doc-map.json
```

Cases:
- **If an entry exists**: review its `doc_targets` and update any reference to the old data path. If the entry is generic (e.g., "service-modified" pointing at service-inventory.json), no edit may be needed — the change is already reflected via T022.
- **If no entry exists**: no action. Signal-to-doc-map is reactive to specific signal types; this mission may not introduce a new signal type.

Document the decision (edited / no edit needed) in the WP completion summary.

After editing (if applicable): `jq . docs/design/architecture/data/signal-to-doc-map.json > /dev/null` parses cleanly.

### T025 — [P] Update narrative architecture counterpart

Check whether `docs/design/architecture/services.md` (or whatever narrative companion exists for service-inventory.json) carries the same description as T022's edit:

```bash
grep -nE "(felix-admin-habits|done_at|query_active_habits_weekly)" docs/design/architecture/services.md
ls docs/design/architecture/*.md
```

If the narrative counterpart describes the felix-admin-habits weekly tick with the old data path, mirror T022's edit in prose form. If the narrative is silent on the weekly tick's data path, no edit needed.

If the narrative is silent BUT the JSON change is significant enough to warrant mentioning, add a brief paragraph — that's a judgment call within the curator profile's scope.

## Branch strategy

- Planning base branch: `main`
- Merge target branch: `main`
- This WP lands on its computed lane worktree.
- Depends on WP02 (description must reflect post-WP02 reality; updating ahead of code lands lying docs).

## Test strategy

This WP edits documentation; no pytest target. Validation steps:

```bash
# All JSON files parse cleanly
for f in docs/design/architecture/data/service-inventory.json \
         docs/design/architecture/data/data-flows.json \
         docs/design/architecture/data/signal-to-doc-map.json; do
  jq . "$f" > /dev/null && echo "$f: OK" || echo "$f: PARSE ERROR"
done

# Old bug-as-design language is gone
grep -nE "(done_at history|done_at)" docs/design/architecture/data/service-inventory.json
# Expected: no matches (or only references that explicitly say "NOT done_at" as a guardrail)

# New canonical-read language is present
grep -nE "(habits-history\.jsonl|state_log|scripts/habits/history\.py)" docs/design/architecture/data/service-inventory.json
# Expected: matches
```

## Definition of Done

- [ ] `service-inventory.json` felix-admin-habits weekly-tick description accurately states the canonical-read path.
- [ ] `data-flows.json` weekly-tick flow entries (all of them) updated to reference `habits-history.jsonl` as completion-history source.
- [ ] `signal-to-doc-map.json` reviewed; updated if applicable; no-op recorded if not.
- [ ] Narrative counterpart (`services.md` or equivalent) reviewed; updated if applicable.
- [ ] All edited JSON files parse cleanly with `jq`.
- [ ] Old "queries Vikunja for done_at history" language no longer appears in any architecture doc (except as a deliberate guardrail "NOT done_at" reference).
- [ ] Cron-schedule references aligned with the new Monday 06:00 ET schedule (or abstractly stated).

## Risks

- **Drift between JSON and narrative**: Felix Constitution Directive 5 says when they conflict, JSON wins. Make the JSON edits authoritative; mirror in narrative for context.
- **Forgotten doc surfaces**: the signal-to-doc-map exists precisely to make this kind of update discoverable. Trust the grep, but also browse `docs/design/architecture/` for any obvious adjacent surface (e.g., a `runbook` mentioning the cron schedule).
- **Schema drift in JSON files**: be careful to preserve the surrounding structure when editing string fields. JSON is whitespace-sensitive in some serializers; if the file uses 2-space indentation, keep it.
- **Stale reference to old mission slug**: `vikunja-client-and-habits-weekly-report-01KTKSFT` may appear in architecture doc cross-references. Leave those references alone (they're historical pointers to the prior mission); only update the operational descriptions.

## Reviewer guidance

Reviewers verify:

1. All four file types reviewed (service-inventory.json, data-flows.json, signal-to-doc-map.json, services.md narrative).
2. JSON files parse cleanly.
3. The edits are minimal and targeted — no scope creep into unrelated parts of the architecture docs.
4. Cross-references to the prior mission slug are preserved (they're history).
5. The new wording is consistent across all surfaces.

If the reviewer thinks the change-control protocol (`docs/design/architecture/change-control.md`) requires additional steps (e.g., updating a changelog), check it and follow.

## Implementation command

```bash
spec-kitty agent action implement WP06 --agent claude
```
