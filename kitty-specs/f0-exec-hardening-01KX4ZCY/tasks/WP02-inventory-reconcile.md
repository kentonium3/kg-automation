---
work_package_id: WP02
title: Reconcile architecture inventory to live config
dependencies: []
requirement_refs:
- FR-002
- FR-003
- FR-004
- NFR-001
- NFR-004
- NFR-005
tracker_refs:
- kentonium3/kg-automation#675
planning_base_branch: feat/f0-exec-hardening
merge_target_branch: feat/f0-exec-hardening
branch_strategy: Planning artifacts for this mission were generated on feat/f0-exec-hardening. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/f0-exec-hardening unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
- T009
- T010
agent: claude
history:
- at: '2026-07-10T03:00:00Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/
create_intent: []
execution_mode: code_change
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, load your assigned agent profile via
`/ad-hoc-profile-load curator-carla` (or the equivalent profile loader in your harness). The
profile carries the identity, governance scope, and boundaries you operate under during this
WP. Treat the profile as authoritative for tone, escalation rules, and Op lifecycle.

## Objective

Reconcile **`docs/design/architecture/data/service-inventory.json`** (authoritative) and its
narrative counterpart **`docs/design/architecture/service-inventory.md`** to the **real live
`openclaw.json` config** for all six Felix agents. The reconcile is a **full sweep** — not just
`model`/`skills` — because #699's partial reconcile left stale per-agent narrative fields.
**This WP edits docs only.** It makes **no** `openclaw.json` or runtime change; the live config
is already correct — it is the *docs* that are wrong.

## Context

**Read before starting (authoritative — the live ground truth is captured, do not re-probe
unless verifying):**
- `kitty-specs/f0-exec-hardening-01KX4ZCY/spec.md` (FR-002, FR-003, FR-004; NFR-001/004/005)
- `kitty-specs/f0-exec-hardening-01KX4ZCY/research.md` — **Decision 2** (the exact live
  per-agent model/skills table + the deeper stale fields + version drift).
- `kitty-specs/f0-exec-hardening-01KX4ZCY/data-model.md` (the reconcile-target field rules + invariants).
- `docs/design/architecture/data/service-inventory.json` (the file you edit — authoritative JSON).
- `docs/design/architecture/service-inventory.md` (narrative view — must agree with the JSON).
- `docs/design/architecture/change-control.md` (the `updated_by` provenance convention).

**Live ground truth to match (research.md Decision 2):** `main`=sonnet-4-6 (gog: gmail/drive);
capture=haiku `[vikunja_api,github]`; habits=haiku `[vikunja_api]`; tasker=haiku
`[task_intelligence,vikunja_api]`; escalation=sonnet-4-6 `[escalation,vikunja_api]`;
calendar=haiku `[]`. All exec `security=full`. gog is **main-only** post-#699.

**Invariants (data-model.md):** JSON is authoritative; narrative follows JSON; edited JSON MUST
pass `tooling/scripts/validate_architecture_data.py`; exactly one gog consumer post-#699
(`main`). The line ~2332 `#699` notes entry is **already correct** — mirror its framing; do not
touch `data-flows.json`/`service-dependencies.json` (already #699-correct).

## Subtasks

### T006 — Correct model drift (FR-003)

In the JSON, set **felix-admin-habits** and **felix-admin-tasker** `model` →
`anthropic/claude-haiku-4-5` (both currently `anthropic/claude-sonnet-4-6`). Update any
narrative mention in `service-inventory.md`. Leave escalation + main (`sonnet-4-6`) and capture
+ calendar (`haiku`) unchanged.

### T007 — Reconcile per-agent `skills` arrays (FR-002)

Set each agent's `skills` to the live Step-2 array (research Decision 2). Critically,
**`felix-admin-calendar.skills` → `[]`** (was the fictional `["calendar","gog"]`: `calendar`
is not a real OpenClaw skill and #699 removed `gog`). Verify capture `[vikunja_api,github]`,
habits `[vikunja_api]`, tasker `[task_intelligence,vikunja_api]`, escalation
`[escalation,vikunja_api]` match; correct any that don't.

### T008 — Correct stale per-agent narrative fields #699 missed (FR-002)

Reconcile the pre-#699 gog-path prose in these fields to the **post-#699 inline path** (capture
reaches the calendar via `route_calendar_event --create`; `felix-admin-calendar` invokes the
Felix calendar helper — google-api-python-client — **not** gog; `main` is **not** in the
calendar-create path, its gog use is gmail/drive only):
- **felix-admin-capture** `notes` — "calendar events … delegated to Felix main for `gog
  calendar create`".
- **`route_calendar_event` / `validate_calendar_event`** component `purpose` — "delegate to
  Felix main for `gog calendar create`".
- **felix-admin-calendar** `purpose` — "event creation via `gog`/Google Calendar … executes
  `gog calendar create`".
- **felix-admin-main** `purpose` — "main now routes calendar work to felix-admin-calendar via
  openclaw-agent dispatch". Preserve historical framing where useful, but the present-tense
  description must be post-#699.

### T009 — Version + main exception (FR-002, FR-004)

- Update the OpenClaw-gateway `version` `v2026.6.5` → **`2026.6.11`** (live: `OpenClaw
  2026.6.11 (e085fa1)`).
- Annotate **`main`** as the tracked Foundation-0 exception: the **only** current `gog`
  consumer (gmail/drive), retained until email/drive get controlled owners (#680); record exec
  posture `security: full` fleet-wide (no per-agent restriction deployed) rather than any
  allowlist-containment claim.

### T010 — Provenance, validator, semantic grep (NFR-001, NFR-004, NFR-005)

- Append this mission's provenance to the relevant `updated_by` field(s) using the existing
  convention (e.g. `+ f0-exec-hardening-01KX4ZCY (#675 — exec-hardening finding + live-config reconcile)`).
- Run `python3 tooling/scripts/validate_architecture_data.py` — MUST pass.
- Run the **NFR-005 semantic grep** and confirm no present-tense stale phrases remain:
  ```bash
  grep -nE '"calendar","gog"|delegate to Felix main for .gog calendar create|executes .gog calendar create|"anthropic/claude-sonnet-4-6"' \
    docs/design/architecture/data/service-inventory.json docs/design/architecture/service-inventory.md
  ```
  (Any `sonnet-4-6` hits must be only escalation/main; no calendar/gog present-tense hits.)
- Confirm `service-inventory.md` narrative agrees with the JSON (INV-1). **No `openclaw.json`
  or other-file change** (NFR-004).

## Definition of Done

- [ ] habits + tasker `model` = `anthropic/claude-haiku-4-5` in JSON + narrative (T006).
- [ ] calendar `skills` = `[]`; all per-agent skills match live Step-2 sets (T007).
- [ ] Stale per-agent narrative fields (capture/calendar/main/route) corrected to post-#699 inline path (T008).
- [ ] Gateway version → `2026.6.11`; main annotated as the sole-gog tracked exception (T009).
- [ ] `validate_architecture_data.py` passes; NFR-005 grep clean; narrative agrees with JSON; provenance appended (T010).
- [ ] **Only the two owned files are modified.** No `openclaw.json`/runtime change; `data-flows.json`/`service-dependencies.json` untouched.

## Branch Strategy

Planning base: `feat/f0-exec-hardening`. Final merge target: `feat/f0-exec-hardening`.
Execution worktrees are allocated per computed lane from `lanes.json` during
`/spec-kitty.implement`. Completed changes merge back into `feat/f0-exec-hardening`.

## Reviewer Guidance

Run the validator + the NFR-005 grep yourself. Confirm the six agents' model/skills match
research Decision 2 exactly, that calendar shows `[]` (not `["calendar","gog"]`), that the four
stale narrative fields now describe the inline post-#699 path, and that the JSON stayed
authoritative with the narrative agreeing. Confirm `data-flows.json`/`service-dependencies.json`
were not touched (they already reflect #699).
