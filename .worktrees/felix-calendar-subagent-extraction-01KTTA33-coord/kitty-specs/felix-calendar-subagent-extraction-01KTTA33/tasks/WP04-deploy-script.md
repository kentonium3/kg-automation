---
work_package_id: WP04
title: Deploy script (strict-order-of-operations Bash wrapper)
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-004
- FR-008
- FR-009
- FR-010
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T018
- T019
- T020
- T021
- T022
- T023
- T024
phase: Phase 2 - Deploy Substrate
history:
- at: '2026-06-11T03:26:12Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/deploy/
execution_mode: code_change
owned_files:
- scripts/deploy/deploy-felix-admin-calendar.sh
tags: []
agent_profile: implementer-ivan
role: implementer
agent: claude
---

# Work Package Prompt: WP04 – Deploy script (strict-order-of-operations Bash wrapper)

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, run `/ad-hoc-profile-load <agent_profile>` using the `agent_profile` value in this WP's frontmatter. The profile establishes your identity, governance scope, boundaries, and initialization — it is required for this work package. Do not proceed to the Objective section without loading the profile.

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual execution workspace is resolved later**: `/spec-kitty.implement` selects the lane worktree and records the lane branch in `base_branch`.

## Objectives & Success Criteria

Build `scripts/deploy/deploy-felix-admin-calendar.sh` per the strict-order-of-operations safe-deploy pattern (DIR-005, DIR-006, DIR-008). After this WP:

- The script is syntactically valid Bash (`bash -n` passes) and shellcheck-clean.
- The script implements all 6 stages from plan.md § Deploy substrate: pre-flight → agent-prompt-sync → openclaw.json edit → service restart → post-flight (journal watch) → rebaseline reminder.
- The script is idempotent for the openclaw.json edit step (skips if felix-admin-calendar already registered).
- Rollback instructions are documented in the script header.
- Naming: `scripts/deploy/deploy-felix-admin-calendar.sh` (per plan.md naming convention).

**Requirements covered**: FR-002 (verified post-deploy), FR-004 (openclaw.json registration), FR-008 (regression coverage via journal watch), FR-009, FR-010 (rebaseline command printed), NFR-002 (journal grep).

## Context & Constraints

- Reference deploy scripts: `scripts/deploy/deploy-NNN.sh`, `scripts/deploy/deploy-fNNN.sh`. Pick a recent one as a stylistic template (e.g., `deploy-f026.sh` if it follows the modern pattern).
- Canonical strict-order pattern: DIR-005 (pre-flight → copy artifacts → verify artifacts → edit config → post-flight smoke test). For this mission, "copy artifacts" is actually "trigger agent-prompt-sync" since #567 owns the file sync.
- openclaw.json edit contract: `kitty-specs/felix-calendar-subagent-extraction-01KTTA33/contracts/openclaw-json-entry.md`.
- Smoke runbook (printed at end): `docs/runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md` (delivered by WP07).
- Rebaseline command: from `docs/runbooks/security-baseline-ops.md` and CLAUDE.md — `ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'`.
- Office2 user: `ssh office2-claude` ONLY. Never `ssh office2-kgale` (per CLAUDE.md).
- CLI flag-shape discipline (per `feedback_verify_cli_flag_shape`): verify novel flag shapes (`systemctl --user`, `journalctl --user -u`, `jq` `+=`) via `<cmd> --help` BEFORE using them. Cite verification in script comments where load-bearing.

## Subtasks & Detailed Guidance

### Subtask T018 – Pre-flight block

- **Purpose**: Catch deploy-time prerequisites before touching production state.
- **Steps**:
  1. Header: `#!/usr/bin/env bash`, `set -euo pipefail`, `IFS=$'\n\t'`. Date and authorship comment block referencing #579 and this mission.
  2. Variables: `MISSION_SLUG`, `OFFICE2_USER=claude`, `OFFICE2_HOST=office2-claude` (the SSH alias), `OPENCLAW_JSON=$HOME/.openclaw/openclaw.json` (remote), `TS=$(date -u +%Y%m%dT%H%M%SZ)`.
  3. Pre-flight checks:
     - Verify local artifact presence: each of `scripts/openclaw/agents/felix-admin-calendar/{IDENTITY,SOUL,AGENTS,TOOLS,USER}.md` exists.
     - Run pytest: `pytest scripts/openclaw/agents/tests/ -v` → fail-fast if RED. This asserts NFR-001 and NFR-004 locally before pushing anything.
     - SSH reachability: `ssh "$OFFICE2_HOST" 'date'` returns within 10s.
     - Restic backup hygiene (advisory, not gate): `ssh "$OFFICE2_HOST" 'ls -1 /data/services/backup/logs/' | sort | tail -3` — print most recent backup log filenames so operator can confirm hygiene. No automated assertion (Tier 3 doesn't gate on backup age).
- **Files**: `scripts/deploy/deploy-felix-admin-calendar.sh`
- **Parallel?**: No — blocks T019+.

### Subtask T019 – Agent prompt sync

- **Purpose**: Force-sync the new agent files to office2 instead of waiting up to 5 min for the timer.
- **Steps**:
  1. Trigger sync: `ssh "$OFFICE2_HOST" 'systemctl --user start agent-prompt-sync.service'`
  2. Wait briefly (~10s) then verify post-sync:
     - `ssh "$OFFICE2_HOST" 'wc -c /data/services/openclaw/calendar-agent/AGENTS.md'` returns a non-zero size matching local `wc -c scripts/openclaw/agents/felix-admin-calendar/AGENTS.md` (or close enough to confirm sync — exact byte-match optional).
     - Similar verification for main: `ssh "$OFFICE2_HOST" 'wc -c /data/services/openclaw/data/AGENTS.md'` matches local main file.
  3. If sync verification fails, exit with rollback instruction (no openclaw.json mutation has happened yet — safe to abort).
- **Files**: `scripts/deploy/deploy-felix-admin-calendar.sh` (appending to)
- **Parallel?**: No.

### Subtask T020 – openclaw.json edit

- **Purpose**: Register felix-admin-calendar in the OpenClaw runtime config with idempotency.
- **Steps**:
  1. Pre-edit IDEMPOTENCY CHECK: `ssh "$OFFICE2_HOST" "jq '.agents.list[] | select(.id == \"felix-admin-calendar\")' $OPENCLAW_JSON"` — if it returns a non-empty result, the entry is already there. Log "felix-admin-calendar already registered; skipping openclaw.json edit" and continue.
  2. Otherwise:
     - Backup: `ssh "$OFFICE2_HOST" "cp $OPENCLAW_JSON ${OPENCLAW_JSON}.bak-${TS}"`
     - Mutate: per `contracts/openclaw-json-entry.md` — use jq to add the entry. Capture output to a temp file, validate parse, atomic mv.
     - Validate post-mutation: jq parse + entry-present check.
  3. On any failure during 2: print rollback (`cp $OPENCLAW_JSON.bak-${TS} $OPENCLAW_JSON`).
- **Files**: `scripts/deploy/deploy-felix-admin-calendar.sh`
- **Parallel?**: No.

### Subtask T021 – Service restart

- **Purpose**: Force OpenClaw to reload its agent registry.
- **Steps**:
  1. `ssh "$OFFICE2_HOST" 'systemctl --user restart openclaw-gateway.service'`
  2. Wait 5s.
  3. `ssh "$OFFICE2_HOST" 'systemctl --user is-active openclaw-gateway.service'` → expect `active`. If not, halt with rollback instructions (restore openclaw.json, restart again).
- **Files**: `scripts/deploy/deploy-felix-admin-calendar.sh`
- **Parallel?**: No.

### Subtask T022 – Journal watch (NFR-002)

- **Purpose**: Verify the truncation warning is gone — the canonical proof that the bug is fixed.
- **Steps**:
  1. Capture deploy start time at script entry: `DEPLOY_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)`.
  2. After service restart, sleep 10s for bootstrap to complete.
  3. `ssh "$OFFICE2_HOST" "journalctl --user -u openclaw-gateway.service --since '$DEPLOY_START' | grep 'truncating in injected context' || true"` — capture output.
  4. Filter for `agent:main:*` sessions: `grep 'agent:main:'` on the matches.
  5. If any match: print the matching lines and exit non-zero (deploy failed NFR-002 verification). Rollback instructions printed.
  6. If zero matches: print "NFR-002 verified: no truncation warnings observed on main agent bootstrap." and continue.
- **Files**: `scripts/deploy/deploy-felix-admin-calendar.sh`
- **Parallel?**: No.

### Subtask T023 – Post-flight reporting

- **Purpose**: Hand off to the operator with clear next steps.
- **Steps**:
  1. Print smoke runbook path: `docs/runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md`. The script should print "Operator: run the smoke checklist now."
  2. Print rebaseline command verbatim (do not run it — operator-driven per spec):
     ```
     ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
     ```
  3. Print rebaseline verification command:
     ```
     ssh office2-claude 'ls /data/services/security-monitor/baselines/ | wc -l && tail -5 /data/services/security-monitor/logs/audit-$(date +%Y-%m-%d).log'
     ```
  4. Remind operator that the merge commit footer must include `Rebaseline: completed at <ts>`.
- **Files**: `scripts/deploy/deploy-felix-admin-calendar.sh`
- **Parallel?**: No.

### Subtask T024 – Rollback documentation + exit codes

- **Purpose**: When something goes wrong, the operator has a clear path back.
- **Steps**:
  1. Top-of-file comment block (~30 lines) documents:
     - What the script does in 1 sentence
     - Order of operations
     - Exit codes: 0 = success; 1 = pre-flight failure; 2 = sync failure; 3 = openclaw.json edit failure; 4 = service restart failure; 5 = NFR-002 verification failure
     - Rollback for each failure stage (no-op for stages before openclaw.json edit; restore from `.bak-${TS}` for stages 3+; restart service)
  2. Every failure path in the script prints "ROLLBACK:" followed by the relevant restore command.
- **Files**: `scripts/deploy/deploy-felix-admin-calendar.sh`
- **Parallel?**: No.

## Test Strategy

- `bash -n scripts/deploy/deploy-felix-admin-calendar.sh` parses without errors.
- `shellcheck scripts/deploy/deploy-felix-admin-calendar.sh` passes (or warnings explicitly justified).
- Dry-run mode (optional): if you can structure pre-flight to support a `--dry-run` flag that performs read-only checks and skips mutations, do so. This is not strictly required but useful for operator confidence.
- The script's RUNTIME verification is what plan.md § Testing Strategy describes; this WP authors the script, not runs it. Running happens post-merge by Kent.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| CLI flag shape mismatch (per `feedback_verify_cli_flag_shape`, first incident `--max-results` → `--max`) | Verify novel flags by `<cmd> --help` before encoding; cite verification in adjacent code comment |
| Idempotency check fails to detect existing entry → duplicate registration | T020 step 1 uses `jq '... | select(.id == ...)'` which returns empty on absence and the entry on presence — robust shape |
| openclaw.json edit corrupts schema | Backup + post-edit validation; rollback step printed if validation fails |
| `agent-prompt-sync.service` unit doesn't exist on office2 | T019 first SSH should `systemctl --user list-unit-files | grep agent-prompt-sync` BEFORE the start; fail-fast with explanatory message |
| Sleep timing too short (10s) for service restart | If `is-active` check fails first attempt, retry once after another 5s |
| Journal grep produces false positives for non-main sessions | T022 step 4 filters explicitly for `agent:main:*` sessionKey pattern |

## Review Guidance

- `bash -n` clean? `shellcheck` clean (or justified)?
- Header comment includes exit-code table?
- All 6 stages present and ordered correctly per DIR-005?
- jq entry value matches `contracts/openclaw-json-entry.md` byte-for-byte?
- Idempotency check present and correctly shaped?
- Rebaseline command printed VERBATIM (no edits to the canonical command per CLAUDE.md)?
- No `ssh office2-kgale` anywhere?

## Activity Log

> **CRITICAL**: Activity log entries MUST be in chronological order (oldest first, newest last).

- 2026-06-11T03:26:12Z -- system -- Prompt created.
