---
work_package_id: WP06
title: Migrate credential-health + final SC gate
dependencies:
- WP01
- WP02
- WP03
- WP04
- WP05
requirement_refs:
- FR-001
- FR-003
- NFR-002
tracker_refs: []
planning_base_branch: fix/860-retire-vikunja-felix-bot
merge_target_branch: fix/860-retire-vikunja-felix-bot
branch_strategy: Planning artifacts for this mission were generated on fix/860-retire-vikunja-felix-bot. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/860-retire-vikunja-felix-bot unless the human explicitly redirects the landing branch.
base_branch: fix/860-retire-vikunja-felix-bot
base_commit: 99db76c0f6102a6b0d86972b5b3ffccafba79626
created_at: '2026-07-23T21:04:52Z'
subtasks:
- T022
- T023
- T024
phase: Phase 2 - Gate
assignee: ''
agent: "claude:sonnet-5:python-pedro:implementer"
agent_profile: python-pedro
role: implementer
shell_pid: "85351"
shell_pid_created_at: "1784847680.091815"
history:
- at: '2026-07-23T21:04:52Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/security/credential_health_check/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/security/credential_health_check/vikunja_writer.py
- tests/security/test_vikunja_writer.py
tags: []
---

# Work Package Prompt: WP06 — Migrate credential-health + final SC gate

## ⚡ Do This First: Load Agent Profile

Load your assigned agent profile via `/ad-hoc-profile-load` before anything else; adopt its
identity/governance/boundaries for this work package.

## Branch Strategy

- **Planning/base branch**: `fix/860-retire-vikunja-felix-bot`
- **Final merge target**: `fix/860-retire-vikunja-felix-bot`
- **Base may differ later**: `/spec-kitty.implement` populates `base_branch` on worktree creation.
- **If human instructions contradict these fields**: stop and resolve the landing branch.

**Depends on WP01–WP05** (the final gate needs every migration landed). Implement command:
`spec-kitty agent action implement WP06 --agent <name>`.

---

## Objectives & Success Criteria

Migrate the last raw consumer (credential-health Vikunja writer) onto `VikunjaClient`, then run the
mission's acceptance gate proving the consolidation is complete and behavior-preserving.

**Success criteria**:

- [ ] `scripts/security/credential_health_check/vikunja_writer.py` uses `VikunjaClient`; no raw
      urllib / hand-loaded token remains.
- [ ] `pytest tests/security/test_vikunja_writer.py` passes.
- [ ] **SC-001**: repo grep shows no **runtime** consumer hand-loading a token or issuing raw HTTP to
      Vikunja (only admin/one-shot + docs may remain).
- [ ] **SC-002**: the full Vikunja/inbox/habits/escalation/enrichment/trust/sync test surface passes.
- [ ] **SC-004**: `VikunjaClient.DEFAULT_TOKEN_PATH` is unchanged (felix-bot) — zero identity change.

## Context & Constraints

- `scripts/security/credential_health_check/vikunja_writer.py` is a small raw-urllib writer;
  migrate it onto the client like the other consumers, preserving its write/error behavior.
- The final gate is verification across the whole mission — it depends on WP02–WP05 being merged, so
  this WP runs last.

**Reference**: `spec.md` (Success Criteria SC-001..SC-004), `plan.md` (IC-03).

## Subtasks & Detailed Guidance

### Subtask T022 — Migrate `credential_health_check/vikunja_writer.py`

- **Steps**:
  1. Replace the urllib writer internals with `VikunjaClient` calls; preserve its write semantics and
     error handling (credential-health alerting depends on the outcome).
  2. Extend `tests/security/test_vikunja_writer.py` with parity assertions.
- **Parallel?**: No.

### Subtask T023 — SC-001 grep gate + full suite

- **Steps**:
  1. Run the SC-001 greps and confirm no runtime raw path remains:
     ```
     grep -rnE "secrets/vikunja-api([^-]|$)" scripts/
     grep -rnE "urllib.request|urlopen" scripts/sync scripts/escalation scripts/enrichment \
       scripts/habits scripts/security/credential_health_check
     ```
     Expect only admin/one-shot scripts (`provision_felix_bot`, `validate_felix_bot`,
     `swap_vikunja_secrets`, `reconcile_projects`, `create_saved_filters`, `migrate_tasks`) and docs
     to remain. If any runtime consumer still hand-loads a token or issues raw HTTP, it is a gap —
     report it (it likely belongs to an earlier WP).
  2. Run the full affected suite: `pytest tests/sync tests/escalation tests/enrichment tests/habits
     tests/security tests/common/test_vikunja_client.py tests/inbox tests/trust tests/vikunja` — all
     green (SC-002).
- **Parallel?**: No — depends on T022 + WP02–WP05.

### Subtask T024 — SC-004 default-token assertion + behavior-preserving confirmation

- **Steps**:
  1. Confirm `VikunjaClient.DEFAULT_TOKEN_PATH` still resolves to the felix-bot `vikunja-api` file
     (the WP01 assertion still holds) — zero identity change this phase.
  2. Summarize the behavior-preserving evidence (every consumer's parity test green) in the WP's
     completion notes for the merge record.
- **Parallel?**: No.

## Definition of Done

- Credential-health writer migrated; `tests/security/test_vikunja_writer.py` green.
- SC-001 grep clean (only admin/one-shot + docs remain); SC-002 full suite green; SC-004 default
  token unchanged.
- No identity/token change; no abstract port introduced anywhere in the mission.

## Risks

- **False-clean grep**: ensure the grep covers `sync/http.py`+`fetch.py` and that the WP05
  dead-`_read_token()` removal landed — otherwise the gate reads clean while a gap remains.
- **Cross-WP integration**: this is the first point every migration is together; watch for shared-
  client contract mismatches surfaced only in the full suite.

## Reviewer Guidance

- Confirm the writer migration; run the SC-001 greps yourself; confirm the full suite is green and
  the default token is unchanged. This is the mission acceptance gate — be thorough.

## Activity Log

- 2026-07-23T23:01:37Z – claude:sonnet-5:python-pedro:implementer – shell_pid=85351 – Assigned agent via action command
- 2026-07-23T23:09:47Z – claude:sonnet-5:python-pedro:implementer – shell_pid=85351 – Ready for review — vikunja_writer migrated (create_task_in_project, 15s timeout + VikunjaWriteError contract preserved). SC-001: zero raw urllib in 5 runtime domains, only admin/one-shot+docs+constants remain (all migrated modules import client). SC-002: 3153 passed 0 failed. SC-004: DEFAULT_TOKEN_PATH unchanged (felix-bot). flake8 exit 0. Commit f8dfbfbc lane-f (integrates all WP01-05).
