---
work_package_id: WP02
title: Escalation enumeration helper + prompt rewrite
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- FR-003
tracker_refs: []
planning_base_branch: fix/deterministic-cron-hardening
merge_target_branch: fix/deterministic-cron-hardening
branch_strategy: Planning artifacts for this mission were generated on fix/deterministic-cron-hardening. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/deterministic-cron-hardening unless the human explicitly redirects the landing branch.
subtasks:
- T005
- T006
- T007
- T008
agent: "claude:opus:reviewer-renata:reviewer"
shell_pid: "2826"
history:
- '2026-07-12: authored by /spec-kitty.tasks'
agent_profile: python-pedro
authoritative_surface: scripts/escalation/enumerate_candidates.py
create_intent:
- scripts/escalation/enumerate_candidates.py
- tests/escalation/test_enumerate_candidates.py
execution_mode: code_change
owned_files:
- scripts/escalation/enumerate_candidates.py
- tests/escalation/test_enumerate_candidates.py
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
- scripts/openclaw/skills/escalation/SKILL.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Load your profile before anything else: `/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity + boundaries, then proceed.

## Objective

Replace the escalation agent's improvised Vikunja fetch + inline python3 with a deterministic **pre-candidate** enumeration helper, and rewrite the standing orders so the agent calls it and gates alerts on `derive_state`. This fixes the failing `escalation-daily` run (FR-001/002/003).

**Critical framing (post-plan review H7)**: the helper output is **pre-candidates** — the date/priority/project slice of §1 only. Snooze/dismiss/level lifecycle stays in `derive_state`. The agent MUST call `derive_state` per pre-candidate and alert ONLY when `next_eligible_level != null`. Do not name or document the helper output as the final alert set.

## Context

- **Depends on WP01** — reads `scripts.common.vikunja_scope.get_escalation_excluded_project_ids()`.
- Authoritative contracts: `contracts/enumerate_candidates.md` + `contracts/post-plan-review-resolutions.md` (H7/H8/H9).
- §1 criteria source: `scripts/openclaw/skills/escalation/SKILL.md` §1.
- Vikunja access: `scripts.common.vikunja_client.VikunjaClient` — stateless, `get(path, *, params)`, **leading-slash** paths, **no** pagination helper (you paginate). The all-tasks endpoint is **`/tasks/all`** (the agent's improvised `/projects/-4/tasks` was the bug). Vikunja caps `per_page` at 50.
- The agent's downstream flow (`reconcile_completions`, `derive_state`, `record_completion`) is UNCHANGED — you are replacing only the Step-2 enumeration.

### Subtask T005 — `scripts/escalation/enumerate_candidates.py`

**Purpose**: deterministic pre-candidate enumeration.

**Behavior**:
1. Instantiate `VikunjaClient()`. Paginate `get("/tasks/all", params={"page": n, "per_page": 50})` starting at page 1, **stopping on an empty batch** (never on `len < 100`).
2. Filter client-side (pure function, tested separately from I/O) per §1 date/priority/project slice:
   - `done == false`
   - `priority >= 2`
   - `project_id NOT IN get_escalation_excluded_project_ids()`
   - `due_date < today` OR (`due_date == today` AND `priority >= 3`)
3. **Due-date normalization (H8)**: reject (exclude) `null`, empty string, sentinel `0001-01-01T00:00:00Z`, and unparseable values; parse as an aware datetime; convert to **America/New_York**; compare **local calendar dates**.
4. Emit a JSON array on stdout, sorted by (`due_date`, `task_id`): each item `{task_id, project_id, title, due_date, priority, reason}` where `reason ∈ {"overdue", "due_today_high_priority"}`. Empty → `[]`.

**CLI**: `--date YYYY-MM-DD` (default today ET), `--base-url`, `--token-path` (local testing). Structure: a pure `filter_candidates(tasks, today, excluded_ids)` + an I/O `main()` that paginates and prints — so tests exercise the filter without network.

**Exit codes (H9)**: `0` success (incl. empty); `1` Vikunja unreachable/HTTP error (print nothing to stdout; stderr carries the error); `3` usage error.

### Subtask T006 — `tests/escalation/test_enumerate_candidates.py`

Fake `VikunjaClient`, no network. Cover:
- Overdue qualifies (`reason=overdue`); due-today+priority≥3 qualifies (`reason=due_today_high_priority`); due-today+priority<3 does NOT.
- `priority < 2` excluded; scope-excluded project ids excluded — and **swapping the scope config changes the result** (monkeypatch `get_escalation_excluded_project_ids`).
- `done=true` excluded; null / empty / sentinel / malformed due excluded.
- Due-date boundary: a task at 23:00 UTC vs 01:00 UTC on the date border classified by ET local date; one DST-transition case.
- Pagination: a >50-task, multi-page fixture aggregated; stop on empty page.
- Vikunja error path → exit 1, empty stdout.
- Output sorted deterministically.

### Subtask T007 — Rewrite `felix-admin-escalation/AGENTS.md` Step 2  ⚠️ AUDITED SURFACE

**Purpose**: the agent calls the helper (FR-003) and gates on `derive_state`.

**Rewrite the "Tick workflow" Step 2 (Candidate enumeration)** to:
- Invoke `cd /home/claude/kg-automation && python3 -m scripts.escalation.enumerate_candidates` and parse the stdout JSON pre-candidate array. Do NOT read the vikunja_api skill / build queries / write inline python3 for enumeration anymore.
- **Failure propagation (H9)**: if the helper exits non-zero, the agent MUST surface a truthful failure AND let the run register as failed (do not swallow it into a healthy IDLE) — so `openclaw-cron-state` sees `status=error`. State the required behavior explicitly.
- Keep Step 3 (`derive_state` per candidate) and make explicit that an alert is sent ONLY when `next_eligible_level != null` (pre-candidates are not the final set).
- Preserve every other section (identity line, output discipline, host=gateway, truthful-reporting, record_completion flow) byte-for-byte. This file is an audited surface — the deploy rebaselines it; keep edits surgical.
- Respect the AGENTS.md ~12k effective-char budget — run the fleet prompt-guard tests if they exist after editing.

### Subtask T008 — Update escalation `SKILL.md` §1

Reflect that enumeration is performed by `enumerate_candidates.py` (the deterministic mechanism), that its output is **pre-candidates** (date/priority/project), and that snooze/dismiss/level eligibility is applied by `derive_state` (§2). Keep §1's qualification criteria wording as the source of truth the helper implements; do not change the criteria themselves (C-002).

## Branch Strategy

Planning base + merge target: **`fix/deterministic-cron-hardening`**. Run in this WP's lane worktree; merge back to the mission branch.

## Test strategy

`pytest tests/escalation/test_enumerate_candidates.py -q`. If a fleet AGENTS.md guard-test exists, run it after T007.

## Definition of Done

- [ ] `enumerate_candidates.py` paginates `/tasks/all`, filters per §1 with config-sourced exclusions, prints sorted JSON, correct exit codes.
- [ ] Tests green incl. due-date boundary/DST, pagination, error→exit 1, config-swap.
- [ ] AGENTS.md Step 2 calls the helper, gates on `derive_state.next_eligible_level != null`, and propagates helper failure as a failed run; all other sections unchanged.
- [ ] SKILL.md §1 documents the helper + pre-candidate framing; criteria unchanged.

## Risks / reviewer guidance

- Reviewer verifies the filter is a **pure function** tested without network, and that due-date parsing follows H8 exactly (reject sentinel/null/malformed; ET local-date compare).
- Verify `/tasks/all` (not `/projects/...`) and per_page=50 stop-on-empty (grep the memory gotcha).
- Verify AGENTS.md edit is surgical + audited-surface-safe (no unrelated churn) and the failure-propagation wording is unambiguous.
- Verify the helper reads exclusions from `vikunja_scope` (WP01), not a hardcoded list.

## Activity Log

- 2026-07-12T04:05:14Z – claude:sonnet:python-pedro:implementer – shell_pid=91777 – Assigned agent via action command
- 2026-07-12T04:15:19Z – claude:sonnet:python-pedro:implementer – shell_pid=91777 – WP02 impl complete: enumerate_candidates (/tasks/all + §1 filter + H8 due-parse + H9 failure-prop) + surgical AGENTS.md/SKILL.md; 40 tests, full suite 4903 pass
- 2026-07-12T04:15:28Z – claude:opus:reviewer-renata:reviewer – shell_pid=2826 – Started review via action command
