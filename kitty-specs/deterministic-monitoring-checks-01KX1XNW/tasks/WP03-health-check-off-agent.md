---
work_package_id: WP03
title: Health-check off the Sonnet agent (systemd timer + wrapper + ntfy)
dependencies: []
requirement_refs:
- C-006
- FR-009
- FR-010
- NFR-002
tracker_refs: []
planning_base_branch: feat/deterministic-monitoring-checks
merge_target_branch: feat/deterministic-monitoring-checks
branch_strategy: Planning artifacts for this mission were generated on feat/deterministic-monitoring-checks. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/deterministic-monitoring-checks unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
- T015
agent: claude
history: []
agent_profile: python-pedro
authoritative_surface: scripts/office2/felix_health_check/
create_intent:
- scripts/office2/felix_health_check/__init__.py
- scripts/office2/felix_health_check/run.py
- scripts/office2/felix_health_check/tests/test_run.py
- scripts/office2/felix-health-check.service
- scripts/office2/felix-health-check.timer
- scripts/office2/deploy/felix-health-check.sh
execution_mode: code_change
owned_files:
- scripts/office2/felix_health_check/**
- scripts/office2/felix-health-check.service
- scripts/office2/felix-health-check.timer
- scripts/office2/deploy/felix-health-check.sh
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

`/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity + discipline
before reading further.

## Objective

Move the twice-daily health-check off the Sonnet `main` agent onto a new
`felix-health-check` **systemd user timer** + a non-agent Python wrapper that runs the
existing bash check via `subprocess`, classifies its output deterministically, stamps a
signal file, and pushes an **ntfy** alert on failure. Create **no** Sonnet session.

## Context (read these)

- Contract: `contracts/health-check-runner.contract.md` — precedence, delivery, test
  matrix, invariants. **Authoritative.**
- **Precedent to mirror closely** (read before writing):
  - `scripts/office2/credential-health-check.service` + `.timer` + `scripts/office2/
    deploy/credential-health-check.sh` — the systemd-timer deterministic-check pattern.
  - `scripts/office2/security-monitor/audit.sh:243-255` — the canonical ntfy send
    (curl POST with `Title`/`Priority`/`Tags`, `NTFY_TOPIC`, non-fatal-on-failure + log).
- The check being wrapped (reused unchanged, FR-010): `/home/claude/helper-scripts/
  health-check.sh` on office2. Current cron payload: `ALL_HEALTHY` → nothing;
  `FAILURES_DETECTED` → alert. Cadence 11:00 + 23:00.
- Decision: alerts go to **ntfy** (Kent confirmed 2026-07-08), not WhatsApp.

## Subtasks

### T011 — Health-check wrapper (`scripts/office2/felix_health_check/run.py`)
- Package `scripts/office2/felix_health_check/` (`__init__.py` + `run.py`), runnable
  `python3 -m scripts.office2.felix_health_check.run` (C-006).
- Run `bash /home/claude/helper-scripts/health-check.sh` via **`subprocess.run`
  (NOT `exec`)**, capturing stdout, stderr, returncode (bounded timeout).
- **Preflight**: script missing/non-executable → `status="SCRIPT_MISSING"` → ntfy alert.
- **Classify with failure-wins precedence** (Codex #9): `FAILURES_DETECTED` in
  stdout/stderr → `FAILURES_DETECTED` (wins even if `ALL_HEALTHY` also present); else
  `ALL_HEALTHY` present AND returncode 0 → `ALL_HEALTHY`; else → `UNKNOWN`.
- Stamp `/data/services/openclaw/felix-health-check/last-run.json`
  (`{status, ran_at_utc, exit_code, delivery}`) — atomic write.
- Deliver: `ALL_HEALTHY` → no push (silent). `FAILURES_DETECTED`/`UNKNOWN`/
  `SCRIPT_MISSING` → ntfy push (Title `Felix Health Check — office2`, Priority `high`),
  body = raw output truncated to ~4 KB with a `(truncated)` marker. ntfy-send failure
  is **logged** (journal) and recorded in the signal file `delivery` field — non-fatal.
  Read `NTFY_TOPIC` from the same config source the security-monitor uses (do NOT
  hard-code a topic; do NOT commit a real topic value).
- Exit 0 on any completed run (a health failure is data). Non-zero only if the wrapper
  itself cannot run.

### T012 — `felix-health-check.service` `[P]`
- Model on `scripts/office2/credential-health-check.service`. `Type=oneshot`;
  `ExecStart` runs the wrapper via the repo checkout + `python3 -m` (match the
  credential-health-check invocation form, incl. `WorkingDirectory` + `PYTHONPATH` if
  that precedent sets it). `Description=felix-health-check — twice-daily system health
  check (off-agent)`.

### T013 — `felix-health-check.timer` `[P]`
- Model on `credential-health-check.timer`. Two `OnCalendar` lines: `*-*-* 11:00:00`
  and `*-*-* 23:00:00` (matches the removed crons' `0 11` / `0 23`). `Persistent=true`
  optional per precedent. `[Install] WantedBy=timers.target`.

### T014 — Deploy script `scripts/office2/deploy/felix-health-check.sh`
- Model on `scripts/office2/deploy/credential-health-check.sh`: copy the wrapper +
  unit files into place, `systemctl --user daemon-reload`, **preflight** that
  `/home/claude/helper-scripts/health-check.sh` exists+executable (fail loud if not),
  enable+start the timer, print verification hints. Do NOT remove the openclaw crons
  here — that is WP04's manifest/quickstart step (ordering, Codex #6).

### T015 — Wrapper test matrix (`scripts/office2/felix_health_check/tests/`)
- Co-locate tests under the package to avoid the deep-`__init__` pytest collision
  (see repo lesson). Cover the contract matrix: stdout-only `ALL_HEALTHY`; stdout-only
  `FAILURES_DETECTED`; **both tokens** (failure wins); token in stderr only; non-zero
  exit + `ALL_HEALTHY` → `UNKNOWN`; missing script → `SCRIPT_MISSING` + alert; oversized
  output → truncation; ntfy send failure → non-fatal + logged/recorded. Stub the
  subprocess + the ntfy curl (no real network, no real script).

## Branch Strategy

Base + merge target `feat/deterministic-monitoring-checks`; worktrees per `lanes.json`.
No dependency — runs in parallel with WP01/WP02 (disjoint files).

## Definition of Done

- [ ] Wrapper implemented per contract (subprocess, precedence, signal file, ntfy w/
      truncation, missing-script + ntfy-failure surfaced, exit-0 semantics).
- [ ] `.service` + `.timer` mirror the credential-health-check precedent; timer fires
      11:00 + 23:00.
- [ ] Deploy script installs units + wrapper, preflights the check script, enables timer.
- [ ] Test matrix green (`python3 -m pytest scripts/office2/felix_health_check/tests/`),
      no real network/script touched.
- [ ] No `main`/agent invocation anywhere in the path; no real ntfy topic committed.

## Risks / reviewer guidance

- Codex #1: verify it is `subprocess`, not `exec`, and that a missing script AND an
  ntfy failure BOTH surface (not swallowed).
- Codex #9: verify failure-wins precedence with a both-token test.
- Confirm the invocation form + `PYTHONPATH`/`WorkingDirectory` match the
  credential-health-check precedent exactly (office2 python3-only; module-import form).
- Reviewer: the openclaw cron removal is intentionally NOT here (it's WP04 + the strict
  deploy order) — do not add it.
