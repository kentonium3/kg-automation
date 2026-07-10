---
work_package_id: WP04
title: Scan runner, alert render, timer & deploy
dependencies:
- WP02
- WP03
requirement_refs:
- C-002
- FR-005
- NFR-001
- NFR-002
tracker_refs: []
planning_base_branch: fix/felix-truthful-reporting
merge_target_branch: fix/felix-truthful-reporting
branch_strategy: Planning artifacts for this mission were generated on fix/felix-truthful-reporting. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-truthful-reporting unless the human explicitly redirects the landing branch.
subtasks:
- T015
- T016
- T017
- T018
- T019
- T020
phase: Phase 2 - Runner & deploy
assignee: ''
agent: "claude:sonnet:python-pedro:implementer"
agent_profile: "python-pedro"
shell_pid: "9700"
history:
- at: '2026-07-10T18:45:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/trust/
create_intent:
- scripts/trust/alert_render.py
- scripts/trust/state.py
- scripts/trust/run_trust_scan.py
- scripts/office2/felix-trust-scan.service
- scripts/office2/felix-trust-scan.timer
- scripts/deploy/deploy-truthful-reporting.py
- deploys/queued/truthful-reporting-detector.yaml
- tests/trust/test_alert_render.py
- tests/trust/test_state.py
- tests/trust/test_run_trust_scan.py
- tests/trust/test_trust_deploy.py
execution_mode: code_change
owned_files:
- scripts/trust/alert_render.py
- scripts/trust/state.py
- scripts/trust/run_trust_scan.py
- scripts/office2/felix-trust-scan.service
- scripts/office2/felix-trust-scan.timer
- scripts/deploy/deploy-truthful-reporting.py
- deploys/queued/truthful-reporting-detector.yaml
- tests/trust/test_alert_render.py
- tests/trust/test_state.py
- tests/trust/test_run_trust_scan.py
- tests/trust/test_trust_deploy.py
role: implementer
tags: []
---

# WP04 — Scan runner, alert render, timer & deploy

This work package wires WP02 (cron-drift detection) and WP03 (assertion
verification) into a single scan runner, renders findings into `#701` alert-bus
`Alert` objects and emits them, tracks seen-findings state for alert cadence,
ships the systemd user timer that runs the scan on a ≤15-minute cadence, and
provides the deploy manifest + entrypoint that installs it on office2. It is the
IC-05 concern from `plan.md`.

**DEPENDS ON WP02 + WP03.** WP02 owns `scripts/trust/__init__.py`,
`detect_cron_drift`, the approved-cron baseline loader (`load_baseline`), the
baseline hash (`baseline_hash`), and the live-cron enumeration wrapper. WP03
owns `verify_assertion` and the assertion-reader / JSONL iterator. This WP
**imports** those; it does **not** re-implement or re-create them, and it does
**not** create `scripts/trust/__init__.py`.

## ⚡ Do This First: Load Agent Profile

Before doing anything else, load your assigned agent profile via
`/ad-hoc-profile-load`. This applies your identity, governance scope,
boundaries, and initialization declaration for this session. Do not begin
implementation until the profile is loaded and you have emitted the
initialization declaration it requires.

## Branch Strategy

- Current branch at workflow start: `fix/felix-truthful-reporting`.
- Planning/base branch for this feature: `fix/felix-truthful-reporting`.
- Completed changes must merge into `fix/felix-truthful-reporting`.
- The concrete lane/worktree for this WP is resolved by
  `/spec-kitty.implement` — do not create branches or worktrees by hand.
- **DEPENDS ON WP02 + WP03**: implement from a base that already contains their
  merged code so `from scripts.trust import detect_cron_drift, load_baseline,
  baseline_hash, …` and `from scripts.trust import verify_assertion, …` resolve.
  If the base you are given does **not** contain those symbols, STOP and surface
  it — do not stub them locally.

## Objectives & Success Criteria

- **FR-005** — emit an alert via the unified alert bus (`#701`) for every covered
  divergence class (cron drift + assertion-artifact-missing), identifying the
  divergence, owning agent where known, and the missing corroboration.
- **NFR-001** — the detection/alerting path is fail-safe: a detector fault never
  breaks agent request handling (agents never call this inline; it is an
  out-of-band timer). A fault in one sub-scan must not abort the other.
- **NFR-002** — a divergence alert is emitted within one detection cycle of the
  divergence becoming observable; the cycle is **≤ 15 minutes** (the timer
  cadence).
- **SC-003** provable: an injected `unapproved_present` cron and an injected
  `artifact_missing` assertion each produce an alert within one cycle.
- **SC-005** provable: with the detector forced unavailable, `--json` reports
  `ok:false` / `errors[]`, **no** alert is emitted, and agents are unaffected.

## Context & Constraints

- **python3-only.** office2 has no `python` binary. Invoke everything as
  `python3 -m scripts.trust.<mod>`. A bare `python` in a unit or prompt is an
  exit-127 fault (memory: office2 is python3-only).
- **Reuse the `#701` bus — no parallel channel (C-002).** Import exactly:
  ```python
  from scripts.common.alert_bus import emit
  from scripts.common.alert_bus.model import Alert, Severity
  ```
  `emit(alert)` **never raises**; it returns an `AlertResult(ok=…)`. Do **not**
  build any other alerting mechanism, do not talk to ntfy directly, do not add a
  new topic. The `#706` ledger records every emitted alert for free.
- **`Alert` required fields**: `source`, `severity` (a `Severity` enum),
  `title`, `description` — all non-empty or the constructor raises `ValueError`
  at the call site. Optional: `action`, `details` (a `dict[str, str]` — stringify
  all values), `timestamp`.
- **Fail-safe everywhere.** Every load/enumerate/verify/emit is wrapped so a
  fault degrades to *no alert*, never to a crash loop or a broken agent.
- **Exit-code discipline (data-model.md "Fail-safe & exit-code discipline").**
  Two run modes:
  - **Timer mode** (systemd target, default): **always exit 0**; a scan fault is
    reported via `ok:false` + `errors[]` in the JSON/logs so systemd never marks
    the unit `failed` or enters a restart loop.
  - **Preflight / explicit mode** (`--once` / `--preflight` / deploy self-test):
    **may exit 2** when the scan itself could not run (e.g., unreadable baseline).
  - **Finding drift is NEVER a non-zero exit** in either mode — drift is expected
    signal, not a failure.
- **Deploy gotchas folded in (`#701`/`#699`/`#706`):** the deploy entrypoint must
  be `chmod +x` (felix-deployer runs it by path, a direct exec — no exec bit ⇒
  exit-126 `Permission denied`); a repo unit file does nothing until *installed +
  `daemon-reload`*; a failing manifest left in `deploys/queued/` fail-loops
  felix-deployer and alerts **every tick** — get the entrypoint right before
  merge.

## Subtasks & Detailed Guidance

### T015 — `scripts/trust/alert_render.py` (render + emit)

- **Purpose**: Map each `CronDriftFinding` (WP02) and `AssertionFinding` (WP03),
  plus the runner's `drift_resolved` event, into a `#701` `Alert` and `emit()` it.
- **Steps**:
  1. Define a render function per finding family, e.g.
     `render_cron_finding(finding) -> Alert` and
     `render_assertion_finding(finding) -> Alert`, plus
     `render_drift_resolved(name, first_seen, cleared_at) -> Alert`.
  2. Map severity + title + detail exactly per the data-model.md **Finding →
     Alert** table:
     | Finding | Severity | Title |
     |---|---|---|
     | `unapproved_present` | `error` | `Unrequested cron detected: <name>` |
     | `approved_missing` | `warn` | `Approved cron missing: <name>` |
     | `schedule_mismatch` | `warn` | `Approved cron schedule changed: <name>` |
     | `enabled_mismatch` | `warn` | `Approved cron disabled: <name>` |
     | `artifact_missing` | `error` | `Completion claim not grounded: <artifact_kind>` |
     | `unverifiable_kind` | `warn` | `Completion claim unverifiable: <artifact_kind>` |
     | `drift_resolved` | `info` | `Cron drift cleared: <name>` |
  3. Put the forensic fields into `Alert.details` (all values **stringified** —
     the bus requires `dict[str, str]`): cron findings carry `agent_id`,
     `cron_id`, `schedule`, `created_at`, and `first_seen`/`last_seen` from state;
     assertion findings carry `agent`, `artifact_id`, `claim`; `drift_resolved`
     carries `first_seen`, `cleared_at`.
  4. Provide an `emit_finding(finding_or_event) -> AlertResult` wrapper that
     builds the `Alert` and calls `emit()`. Set `source` to a stable value such
     as `"felix-trust-scan/cron"` or `"felix-trust-scan/assertion"`.
- **Files**: `scripts/trust/alert_render.py`.
- **Notes**: Redaction is the bus's job — pass title + a plain description; keep
  details redaction-consistent with `#701`/`#706` (no secrets in `details`).
  `emit()` never raises, but still guard the render step (a malformed finding
  must not crash the tick).

### T016 — `scripts/trust/state.py` (seen-findings state + cadence)

- **Purpose**: Track seen findings across ticks so alert cadence is correct:
  alert on first observation, re-alert every 24h while unresolved, emit
  `drift_resolved` (info) and drop the entry when a finding disappears.
- **Steps**:
  1. State file: a small JSON map `finding_fingerprint -> {first_seen,
     last_seen, last_alerted}` (ISO-8601 UTC strings). Home under
     `/data/services/trust/state/` (path is a module constant; injectable for
     tests).
  2. **Fingerprint** = a stable hash of the finding identity (kind + name +
     agent_id for cron; kind + agent + artifact_kind + artifact_id for
     assertion) **combined with `baseline_hash` from WP02** (`load_baseline` /
     `baseline_hash`) so a baseline update re-evaluates findings rather than
     letting stale seen-state suppress a now-legitimate or newly-illegitimate
     cron (data-model.md "Baseline-versioned fingerprints").
  3. Cadence function `reconcile(current_findings, now) ->
     (to_alert, resolved_events)`:
     - fingerprint not in state ⇒ **first observation** → include in `to_alert`,
       set `first_seen = last_seen = last_alerted = now`;
     - fingerprint in state and `now - last_alerted >= 24h` ⇒ **re-alert** →
       include in `to_alert`, update `last_alerted = now`; always update
       `last_seen = now`;
     - fingerprint in state but **absent** from `current_findings` ⇒ produce a
       `drift_resolved` event carrying `first_seen` + `cleared_at = now`, and
       drop the entry.
  4. **Atomic write**: write to a temp file in the same dir + `os.replace`
     (temp+rename). Never partially write the state file.
- **Files**: `scripts/trust/state.py`.
- **Notes**: Deterministic — take `now` as an injected parameter (do not call
  `datetime.now()` inside the reconcile logic) so tests can drive the 24h
  boundary. Missing/corrupt state file loads as empty (fail-safe), not a crash.

### T017 — `scripts/trust/run_trust_scan.py` (entrypoint, contract C2)

- **Purpose**: The single scan entrypoint (systemd target + CLI) driving both
  sub-scans, applying the seen-findings cadence, and emitting via `alert_render`.
- **Steps**:
  1. **Cron-drift sub-scan**: enumerate live crons via WP02's live-enumeration
     wrapper (fail-safe — a CLI/JSON error becomes an error in `errors[]`, NOT
     "no crons"), load the baseline via `load_baseline`, call
     `detect_cron_drift(live_jobs, baseline)`.
  2. **Assertion sub-scan**: iterate *new* assertions via WP03's reader +
     watermark (each verified once), call `verify_assertion(a)` per record,
     collect `AssertionFinding`s.
  3. Feed all findings through `state.reconcile(..., now)` to get `to_alert` +
     `resolved_events`; then `alert_render.emit_finding(...)` for each (unless
     `--dry-run`).
  4. **Flags**:
     - `--dry-run` — compute + print findings; **no emit**, **no** state/watermark
       mutation.
     - `--once` / `--preflight` — preflight mode (see exit codes).
     - `--json` — print the summary
       `{"ok": bool, "drift_findings": N, "assertion_findings": N,
       "alerts_emitted": N, "errors": []}` to stdout.
  5. **Exit codes** (per data-model.md + contract C2):
     - timer mode (default) → **always 0**; a fault sets `ok:false` and records
       `errors[]`;
     - preflight mode (`--once`/`--preflight`) → **may exit 2** on scan-inability
       (e.g., unreadable baseline);
     - drift/assertion **found** → **never** non-zero in either mode.
  6. **Fail-safe isolation**: wrap each sub-scan so an exception is caught into
     `errors[]` and does **not** abort the other sub-scan. The overall tick
     never raises.
- **Files**: `scripts/trust/run_trust_scan.py`.
- **Notes**: `main(argv)` returns the exit code; `if __name__ == "__main__":
  sys.exit(main())`. Advance the assertion watermark only on a non-dry-run,
  successful read (atomic write, delegated to WP03's reader where it owns that).

### T018 — `scripts/office2/felix-trust-scan.service` + `.timer` (systemd user units)

- **Purpose**: Run the scan in timer mode on a ≤15-minute cadence under the
  `claude` account.
- **Steps** (match the `felix-health-check.service` / `felix-doc-auditor.timer`
  conventions **exactly**):
  1. `felix-trust-scan.service` — `Type=oneshot`; `ExecStart=/usr/bin/python3 -m
     scripts.trust.run_trust_scan --json` (timer mode — no `--preflight`);
     `Environment=HOME=/home/claude`; `Environment=PYTHONPATH=/home/claude/kg-automation`;
     `WorkingDirectory=/home/claude/kg-automation`; and the `#701` bus env via
     `EnvironmentFile=-/home/claude/.config/felix/alert-bus/env` (leading `-` so
     startup is non-fatal if absent — the bus returns `NTFY_MISSING_TOPIC`).
  2. `felix-trust-scan.timer` — `[Timer]` with a ≤15-min cadence
     (`OnUnitActiveSec=15min` plus an `OnBootSec`/`OnCalendar` kick as the sibling
     timers do), `Persistent=true`, `[Install] WantedBy=timers.target`.
- **Files**: `scripts/office2/felix-trust-scan.service`,
  `scripts/office2/felix-trust-scan.timer`.
- **Notes**: Do **not** pass `--preflight` in the unit — timer mode must exit 0
  on faults so systemd never enters a restart loop. Keep the `Description` lines
  accurate.

### T019 — deploy manifest + entrypoint

- **Purpose**: Install the timer on office2 through the manifest discipline.
- **Steps**:
  1. `deploys/queued/truthful-reporting-detector.yaml` — **do NOT pre-number**
     (per `docs/runbooks/deploy/discipline.md`, felix-deployer assigns the
     applied `NNNN-` prefix; a pre-added number is at best cosmetic and at worst
     misleading). Manifest fields: `schema_version: v1`; `name`;
     `issue: kentonium3/kg-automation#683`; `tier: 3` (Tier-3 logic — installs a
     user timer, no Tier 0/1/2 action); `entrypoint:
     scripts/deploy/deploy-truthful-reporting.py`; `audited_surface: true`
     (systemd user units are an audited surface) with a note that rebaseline is
     **not required** (see below); `created_at`; `created_by`.
  2. `scripts/deploy/deploy-truthful-reporting.py` — mirror the structure of
     `scripts/deploy/deploy-felix-calendar-helper.py`: `#!/usr/bin/env python3`
     shebang, the `sys.path.insert(0, parents[2])` shim (felix-deployer invokes
     by path, not `-m`), a `main(argv)` dispatching `--dry-run` / `--apply`
     (anything else ⇒ exit 2), `_print_line`/`_print_recovery` helpers, and a
     `_run()` subprocess wrapper. The `--apply` path, in order:
     - **install** `felix-trust-scan.{service,timer}` into the user systemd dir
       (`~/.config/systemd/user/`);
     - `systemctl --user daemon-reload`, then `systemctl --user enable --now
       felix-trust-scan.timer`;
     - **self-test**: run `python3 -m scripts.trust.run_trust_scan --preflight
       --json` (preflight mode — may exit 2 on a hard fault) with `cwd` = the
       checkout; a non-zero self-test fails the deploy;
     - **prompt-sync (Codex finding 10)**: `systemctl --user start
       agent-prompt-sync.service` and **verify the deployed `AGENTS.md` content**
       (grep the synced prompt for the doctrine marker) *before* declaring
       success — do not wait for the 5-min prompt-sync timer;
     - report outcome via the `#701` bus (`from scripts.common.alert_bus import
       emit`).
     The `--dry-run` path prints each planned step (read-only; safe off-office2).
  3. `chmod +x scripts/deploy/deploy-truthful-reporting.py` **before** `git add`
     (mode `0755`) — felix-deployer execs it directly.
- **Files**: `deploys/queued/truthful-reporting-detector.yaml`,
  `scripts/deploy/deploy-truthful-reporting.py`.
- **Notes**: **Rebaseline is NOT required** (gap `#621`) — agent prompts are an
  *unmonitored* audited surface (`audit.sh` does not hash deployed `AGENTS.md`)
  and the detector/systemd code is not a hashed baseline. The merge commit
  records `Rebaseline: not required — agent prompts are an unmonitored audited
  surface (gap #621); detector code is not a hashed baseline`. Do not provision
  any secret here — reuse the `#701` topic env-file that already exists on office2.

### T020 — tests

- **Purpose**: Prove render/severity mapping, cadence, runner behavior + exit
  codes, and entrypoint logic — all deterministic, no office2 calls.
- **Steps**:
  1. `tests/trust/test_alert_render.py` — each finding kind (and
     `drift_resolved`) maps to the correct `Severity` + title; `emit` is called
     with a well-formed `Alert` (mock `scripts.common.alert_bus.emit`); all
     `details` values are strings.
  2. `tests/trust/test_state.py` — first-seen ⇒ alert; re-alert exactly at/after
     24h (injected `now`); disappearance ⇒ `drift_resolved` event + entry
     dropped; atomic write (temp+rename); baseline-hash change re-evaluates the
     fingerprint; missing/corrupt state loads empty.
  3. `tests/trust/test_run_trust_scan.py` — drift + assertion findings drive the
     right emits; `--dry-run` emits nothing and mutates no state; exit codes:
     timer-mode fault ⇒ exit **0** with `ok:false`, preflight scan-inability ⇒
     exit **2**, drift-found ⇒ exit **0**; a failure in one sub-scan is caught in
     `errors[]` and the other sub-scan still runs.
  4. `tests/trust/test_trust_deploy.py` — entrypoint `--dry-run` prints steps
     with no side effects; the `--apply` self-test / systemctl / prompt-sync
     logic drives the expected subprocess calls (mock `subprocess`/`systemctl`);
     usage error ⇒ exit 2.
- **Files**: `tests/trust/test_alert_render.py`, `tests/trust/test_state.py`,
  `tests/trust/test_run_trust_scan.py`, `tests/trust/test_trust_deploy.py`.
- **Notes**: **Mock the bus, `subprocess`, and `systemctl`** at the boundary. No
  test may call office2, ntfy, OpenClaw, or Vikunja. Import WP02/WP03 symbols
  from `scripts.trust` (do not redefine them in the tests).

## Test Strategy

Run:

```
python3 -m pytest tests/trust/test_alert_render.py tests/trust/test_state.py tests/trust/test_run_trust_scan.py tests/trust/test_trust_deploy.py -v --cov=scripts/trust --cov-branch
```

All tests are deterministic and hermetic. Mock `scripts.common.alert_bus.emit`,
`subprocess.run`, and any `systemctl` invocation. Drive time via an injected
`now` — never a real clock. Use `# pragma: no branch` only on genuinely
unreachable defensive branches guarded by an earlier short-circuit.

## Definition of Done

- [ ] `alert_render.py` renders every finding kind + `drift_resolved` to the
      correct `Severity` + title per the data-model table and `emit()`s via the
      `#701` bus (no parallel channel).
- [ ] `state.py` implements the seen-findings cadence (first-seen alert, 24h
      re-alert, `drift_resolved` on disappearance), baseline-hash-versioned
      fingerprints, and atomic (temp+rename) writes.
- [ ] `run_trust_scan.py` drives both sub-scans with fail-safe isolation, applies
      the cadence, honors `--dry-run`/`--once`/`--preflight`/`--json`, and obeys
      the exit-code discipline (timer=0 always; preflight may exit 2;
      drift-found never non-zero).
- [ ] `felix-trust-scan.service` + `.timer` installed-ready, matching the
      existing unit conventions, timer mode invocation, ≤15-min cadence.
- [ ] Deploy manifest (**not pre-numbered**) + entrypoint (`chmod +x`; installs
      units + `daemon-reload` + `enable --now`; runs preflight self-test;
      triggers `agent-prompt-sync.service` + verifies deployed `AGENTS.md`;
      reports via the `#701` bus).
- [ ] All four test modules pass under `--cov-branch`.
- [ ] Merge commit will record `Rebaseline: not required — <reason>`.

## Risks

- **Deploy gotchas.** Entrypoint must be `chmod +x` (else exit-126 at
  `entrypoint_dry_run`). A repo unit file is inert until *installed +
  `daemon-reload`ed*. A **failing manifest left in `deploys/queued/`
  fail-loops felix-deployer and alerts every tick** — the entrypoint must be
  correct and idempotent before merge.
- **Timer-mode exit-0 discipline.** If the unit runs with `--preflight` (or the
  runner exits non-zero on a transient fault in timer mode), systemd will mark
  the unit `failed` / enter a restart loop. Timer mode = `--json` only, always
  exit 0.
- **Parallel alert channel.** Do **not** introduce any alerting other than the
  `#701` bus (`emit`) — no direct ntfy, no new topic (C-002).
- **Secrets.** Provision nothing secret in this WP; reuse the existing `#701`
  topic env-file on office2.

## Reviewer Guidance

- Confirm **both** exit-code modes: timer mode always exits 0 (fault ⇒
  `ok:false`); preflight/`--once` may exit 2 on scan-inability; drift-found is
  never non-zero in either mode.
- Confirm **fail-safe isolation**: a failure in one sub-scan is caught into
  `errors[]` and the other sub-scan still runs; the tick never raises.
- Confirm **bus reuse**: alerts go only through `scripts.common.alert_bus.emit`
  with a valid `Alert` (required fields non-empty; `details` all strings); no
  parallel channel.
- Confirm the **entrypoint** installs the units, runs `daemon-reload` +
  `enable --now`, runs the preflight self-test, **and** triggers
  `agent-prompt-sync.service` + verifies deployed `AGENTS.md` before declaring
  success; it is `chmod +x`.
- Confirm the queued manifest is **not pre-numbered** and declares the right
  tier/guard.
- Confirm the **severity mapping** matches the data-model Finding → Alert table
  exactly.

## Activity Log

- 2026-07-10T19:43:36Z – claude:sonnet:python-pedro:implementer – shell_pid=9700 – Assigned agent via action command
