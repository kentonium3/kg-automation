---
title: Signal-driven monitoring operations (felix-core-digest signal extraction + felix-heartbeat-gate)
doc_type: runbook
audience: agents_and_humans
status: approved
created: 2026-06-01
last_validated: 2026-06-01
last_updated: '2026-06-01'
updated_by: '#490'
version: v1.0
owners: [kgale]
---

# Signal-driven monitoring — operations runbook

Authoritative operator reference for the two-layer observation pipeline
introduced by mission [#490 — signal-driven-monitoring-haiku-gate](https://github.com/kentonium3/kg-automation/issues/490)
(spec: `kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/spec.md`).
Covers cutover, day-to-day health checks, troubleshooting, and rollback.

The operator-facing quickstart lives at
[`kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/quickstart.md`](<../../kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/quickstart.md>).
This runbook is the durable post-merge artifact — it complements the
quickstart with the cutover procedure that runs **once at deploy time**
and the rollback procedure that runs **only when needed**.

---

## Overview

Mission #490 replaces a single ~30-minute Sonnet heartbeat with a
two-layer architecture:

1. **Deterministic signal extraction** (`felix-core-digest`, every 15
   minutes). `tick.py` scans `/tmp/openclaw/openclaw-*.log` for named
   signals (defined declaratively in `scripts/openclaw/observation/signals/config.toml`),
   maintains per-signal rolling counters, and files GitHub issues via
   `kg-felix-bot` whenever a signal crosses its threshold AND no
   matching open issue exists in the dedup window. **No LLM is in this
   path** (NFR-003). Initial signal set: `whatsapp_creds_restore`,
   `web_watchdog_reconnect`, `agent_unhandled_error` (FR-006).

2. **Heartbeat routing gate** (`felix-heartbeat-gate`, every 30
   minutes). `run.py` reads the latest signal-extraction snapshot
   (`last-tick.json`) plus `HEARTBEAT.md`, asks `claude-haiku-4-5` to
   classify the situation, and routes one of three outcomes:
   - `HEARTBEAT_OK` — silent tick.
   - `LOG_AND_SKIP` — observable but no action this tick.
   - `ESCALATE_TO_SONNET` — invoke the existing Sonnet 4.6 main-agent
     path exactly once via `openclaw system event --mode now`.
   On API failure / timeout / malformed response, the gate falls back to
   the same `ESCALATE_TO_SONNET` invocation so observation is **never
   silently dropped** (FR-011); fallback is recorded in
   `last-gate-decision.json.fallback_invoked`.

The design call: **the things Felix should observe and act on are
nameable in advance.** We narrow coverage of unknown-unknown patterns in
exchange for accurate, low-cost monitoring of named signals. The gate
preserves novel-signal escalation as the safety net.

---

## Architecture

| Aspect | felix-core-digest (post-#490) | felix-heartbeat-gate (new #490) |
|---|---|---|
| Host | office2 (Ubuntu 24.04 LTS) | office2 (Ubuntu 24.04 LTS) |
| Run-as user | `claude` | `claude` |
| Schedule | `OnUnitActiveSec=15min`, `OnBootSec=3min`, `Persistent=true` | `OnUnitActiveSec=30min`, `OnBootSec=5min`, `Persistent=true` |
| Trigger | `felix-core-digest.timer` (user unit) → `felix-core-digest.service` (oneshot, two chained ExecStart) | `felix-heartbeat-gate.timer` (user unit) → `felix-heartbeat-gate.service` (oneshot) |
| Entrypoint 1 | `/usr/bin/python3 /home/claude/repos/kg-automation/scripts/openclaw/observation/summarize.py` (existing) | `/usr/bin/python3 /home/claude/repos/kg-automation/scripts/openclaw/heartbeat_gate/run.py` |
| Entrypoint 2 | `/usr/bin/python3 /home/claude/repos/kg-automation/scripts/openclaw/observation/tick.py` (new) | — |
| Model | none (deterministic) | `claude-haiku-4-5` (anthropic SDK, direct) |
| Session mode | stateless per tick | stateless per tick |
| GitHub identity | `kg-felix-bot` (via `gh` CLI, for `tick.py` filings) | n/a — no GitHub writes from the gate |
| API key | n/a for the digest layer | `/data/services/openclaw/secrets/anthropic` (0600, claude:claude) |
| State dir | `/data/services/openclaw/felix-core-digest-signals/` (state, last-tick.json, signals-ledger.jsonl) | `/data/services/openclaw/felix-heartbeat-gate/` (last-gate-decision.json, gate-ledger.jsonl) |
| Health signal | `/data/services/openclaw/felix-core-digest-signals/last-tick.json` | `/data/services/openclaw/felix-heartbeat-gate/last-gate-decision.json` |
| Audit ledger | `signals-ledger.jsonl` (one row per filing) | `gate-ledger.jsonl` (one row per tick) |

Source tree:

```
scripts/openclaw/
├── observation/
│   ├── summarize.py        ← existing (#F014) — agent-log digest
│   ├── tick.py             ← new (#490) — signal-extraction orchestrator
│   ├── filer.py            ← new (#490) — deterministic GitHub filer
│   ├── state.py            ← new (#490) — per-signal counter persistence
│   ├── config.py           ← new (#490) — config loader
│   └── signals/            ← new (#490) — signal-source implementations
│       ├── config.toml     ← declarative signal definitions (FR-005)
│       ├── creds_restore.py
│       ├── watchdog_reconnect.py
│       ├── unhandled_error.py
│       └── openclaw_log.py ← shared log-reader
└── heartbeat_gate/         ← new (#490)
    ├── run.py              ← entrypoint
    ├── gate.py             ← SDK wrapper (Anthropic call + schema validation)
    ├── context.py          ← per-tick context assembly
    ├── escalator.py        ← openclaw system event subprocess
    ├── ledger.py           ← gate-ledger.jsonl writer
    └── prompts/
        └── routing.prompt.md  ← cache-aware system prompt
```

Contracts:

- [`tick-signal.contract.md`](<../../kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md>) — schema for `last-tick.json`
- [`gate-decision.contract.md`](<../../kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/gate-decision.contract.md>) — schema for `last-gate-decision.json`
- [`signal-config.contract.md`](<../../kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/signal-config.contract.md>) — schema for `signals/config.toml`
- [`filer-invocation.contract.md`](<../../kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/filer-invocation.contract.md>) — `felix-file-issue.py` subprocess contract

---

## Cutover — first deployment

This procedure runs once, after the mission merges to `main`. It deploys
WP-01 / WP-02 / WP-03 code, creates the state directories, **disables
OpenClaw's internal heartbeat (Tier 2 — Restic confirmed below)**, and
enables the new gate timer.

**Architectural precedent**: this procedure is modeled on the
`felix-doc-auditor` cutover (`docs/runbooks/doc-auditor-driver-ops.md`).
Where the procedures diverge, the divergence is called out inline.

### Pre-cutover checklist (run BEFORE flipping the switch)

Verify all five conditions before proceeding to the cutover steps.

1. **WP code is on `main`**. The mission has merged via `/spec-kitty.merge`. On office2:

   ```bash
   ssh office2-claude 'cd ~/repos/kg-automation && git log -1 --oneline'
   ```

   Expected: latest commit on `main` referencing #490 / mission `signal-driven-monitoring-haiku-gate-01KT22PC`.

2. **Restic backup currency for `/data/services/openclaw/` (Tier 2 precondition)**. Per CLAUDE.md Tier 2 protocol, confirm a backup within the last 24 hours exists before modifying any state directory.

   ```bash
   ssh office2-claude 'tail -50 /data/services/backup/logs/backup.log | grep -E "snapshot|completed"'
   ```

   Expected: a `completed` line within the last 24 hours. If absent, trigger a fresh backup first:

   ```bash
   ssh office2-claude '/data/services/backup/scripts/backup.sh'
   ```

   Wait for completion (script exits 0) before continuing.

3. **`kg-felix-bot` identity active on office2**. The deterministic filer refuses to file under any other identity (C-001).

   ```bash
   ssh office2-claude 'gh auth status'
   ```

   Expected: `Logged in to github.com account kg-felix-bot`.

4. **Anthropic API key present**. The gate reads it at tick start.

   ```bash
   ssh office2-claude 'ls -l /data/services/openclaw/secrets/anthropic'
   ```

   Expected: file exists, mode `-rw-------` (0600), owner `claude:claude`.

5. **OpenClaw daily logs present**. `tick.py` reads from these.

   ```bash
   ssh office2-claude 'ls -1t /tmp/openclaw/openclaw-*.log | head -3'
   ```

   Expected: at least one recent `openclaw-YYYY-MM-DD.log` file dated today (UTC).

If any check fails, stop and resolve before proceeding.

### Cutover procedure

Run each command in order. One command per code block — copy-paste each into a separate terminal invocation, wait for completion, then run the next.

1. **Pull the latest code on office2** (if the spec-kitty merge hasn't already been pulled).

   ```bash
   ssh office2-claude 'cd ~/repos/kg-automation && git pull --ff-only'
   ```

2. **Create the state directories** (Tier 2 — Restic confirmed in pre-cutover step 2).

   ```bash
   ssh office2-claude 'mkdir -p /data/services/openclaw/felix-core-digest-signals/state /data/services/openclaw/felix-heartbeat-gate'
   ```

3. **Install/refresh the systemd unit files**. The in-repo source-of-truth lives under `scripts/office2/`. Deploy by copying into `~/.config/systemd/user/`.

   ```bash
   ssh office2-claude 'install -m 0644 ~/repos/kg-automation/scripts/office2/felix-core-digest.service ~/.config/systemd/user/felix-core-digest.service'
   ```

   ```bash
   ssh office2-claude 'install -m 0644 ~/repos/kg-automation/scripts/office2/felix-heartbeat-gate.service ~/.config/systemd/user/felix-heartbeat-gate.service'
   ```

   ```bash
   ssh office2-claude 'install -m 0644 ~/repos/kg-automation/scripts/office2/felix-heartbeat-gate.timer ~/.config/systemd/user/felix-heartbeat-gate.timer'
   ```

4. **Reload systemd to pick up the new + modified units**.

   ```bash
   ssh office2-claude 'systemctl --user daemon-reload'
   ```

5. **Verify the modified `felix-core-digest.service` parses correctly**.

   ```bash
   ssh office2-claude 'systemd-analyze --user verify felix-core-digest.service'
   ```

   Expected: no output (zero exit), or only warnings. Any error here aborts the cutover.

6. **Verify the new `felix-heartbeat-gate.service` parses correctly**.

   ```bash
   ssh office2-claude 'systemd-analyze --user verify felix-heartbeat-gate.service'
   ```

   Expected: no output (zero exit).

7. **DISABLE OpenClaw's internal heartbeat (Tier 2 — Restic confirmed in pre-cutover step 2)**. This is the load-bearing cutover step. Until this runs, OpenClaw will continue to fire its own Sonnet-tier heartbeat in addition to our new gate, double-charging.

   ```bash
   ssh office2-claude 'openclaw system heartbeat disable'
   ```

8. **VERIFY the disable took effect**. Read the heartbeat status:

   ```bash
   ssh office2-claude 'openclaw system heartbeat last'
   ```

   Expected: status indicates the scheduler is disabled / paused. No new heartbeat ticks will appear here once the disable propagates.

9. **Enable the new gate timer**.

   ```bash
   ssh office2-claude 'systemctl --user enable --now felix-heartbeat-gate.timer'
   ```

10. **Confirm `felix-core-digest.timer` is enabled** (it should already be — this is a no-op safety check).

    ```bash
    ssh office2-claude 'systemctl --user enable --now felix-core-digest.timer'
    ```

11. **Force a manual run of `felix-core-digest.service`** to populate the first `last-tick.json` immediately (don't wait 15 min).

    ```bash
    ssh office2-claude 'systemctl --user start --wait felix-core-digest.service'
    ```

12. **Force a manual run of `felix-heartbeat-gate.service`** to populate the first `last-gate-decision.json`.

    ```bash
    ssh office2-claude 'systemctl --user start --wait felix-heartbeat-gate.service'
    ```

### Post-cutover verification

Confirm each of the following before declaring cutover done.

1. **`last-tick.json` is fresh and clean**.

   ```bash
   ssh office2-claude 'cat /data/services/openclaw/felix-core-digest-signals/last-tick.json | jq "{exit_status, started_at_utc, errors, issues_filed}"'
   ```

   Expected: `exit_status == "success"`, `started_at_utc` within last few minutes, `errors == []`.

2. **`last-gate-decision.json` is fresh and clean**.

   ```bash
   ssh office2-claude 'cat /data/services/openclaw/felix-heartbeat-gate/last-gate-decision.json | jq "{outcome, started_at_utc, errors, fallback_invoked}"'
   ```

   Expected: `outcome` is one of `HEARTBEAT_OK` / `LOG_AND_SKIP` / `ESCALATE_TO_SONNET`, `started_at_utc` within last few minutes, `errors == []`, `fallback_invoked == false`.

3. **Both timers active**.

   ```bash
   ssh office2-claude 'systemctl --user list-timers --all | grep -E "felix-core-digest|felix-heartbeat-gate"'
   ```

   Expected: both timers present, `NEXT` column shows a future time.

4. **OpenClaw's internal heartbeat is NOT firing** (verifies step 7 stuck).

   ```bash
   ssh office2-claude 'openclaw system heartbeat last'
   ```

   Expected: no new heartbeat ticks from OpenClaw's scheduler since the disable. Re-check after 35 minutes (one gate cycle + buffer) — only the new gate's ticks should appear.

5. **First-week observation window opens**. Per the WP04 prompt's
   post-merge actions, monitor `last-tick.json` and `last-gate-decision.json`
   **daily for the first week**. Tune thresholds in
   `scripts/openclaw/observation/signals/config.toml` based on false-positive
   rate (config edits are Tier 3; redeploy via `git pull` on office2 — no
   restart needed, next cycle picks them up).

---

## Day-to-day operations

See the quickstart for the routine surface (30-second health check,
adding a signal, tuning thresholds, investigating a filed issue,
auditing gate decisions, cost & token math):
[`kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/quickstart.md`](<../../kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/quickstart.md>).

The quickstart is the operator-facing surface. This runbook covers the
events you don't expect to run more than once or twice per year
(cutover, rollback, threshold re-calibration after a regime change).

---

## Troubleshooting

### `felix-core-digest.service` failing with first ExecStart non-zero

**Symptom**: the chained ExecStart pattern is `summarize.py` (first), then `tick.py` (second). systemd `Type=oneshot` runs them sequentially and **stops at the first failure**. If `summarize.py` exits non-zero, `tick.py` does NOT run, and the unit fails as a whole.

**Distinguish the two failure modes**:

```bash
ssh office2-claude 'systemctl --user status felix-core-digest.service'
```

Look at the journal entries for the failing `ExecStart` PID. The path in the entry tells you which script failed (`summarize.py` vs `tick.py`).

**If `summarize.py` failed** — `last-tick.json` will NOT be updated this cycle (tick.py never ran). The downstream gate will see a stale `last-tick.json` and may escalate more aggressively until the next successful cycle. Fix `summarize.py` (likely an Obsidian-Sync / vault-path issue) and the next cycle resumes both passes.

**If `tick.py` failed** — `summarize.py` did succeed (digest written), but signal extraction did not. `last-tick.json` may be missing or stale; the gate's `last-gate-decision.json` will reflect a stale-input condition. Inspect:

```bash
ssh office2-claude 'systemctl --user status felix-core-digest.service --no-pager | tail -40'
```

Common `tick.py` failures: missing `/tmp/openclaw/openclaw-*.log` (OpenClaw didn't write today's log yet — wait one cycle), malformed `signals/config.toml` (last edit broke it — revert via `git checkout`), or state-directory permission issue (Tier 2 — was the state dir created in cutover step 2?).

### Gate ledger growing without escalations

**Symptom**: `gate-ledger.jsonl` is appending one row per 30 minutes, all with `outcome: HEARTBEAT_OK`.

**Diagnosis**: this is the **expected steady state**. The gate is doing its job — most ticks have no novel signal, and `HEARTBEAT_OK` is the routing decision that says "do nothing." The cost reduction (NFR-001 ≥80%) depends on this being common.

**Action**: none. Inspect token usage via the quickstart's cost & token section to confirm the gate is staying within Haiku budget.

### Gate always escalating (`outcome: ESCALATE_TO_SONNET` on every tick)

**Symptom**: every entry in `gate-ledger.jsonl` shows `ESCALATE_TO_SONNET`. Sonnet costs are not dropping.

**Diagnosis order**:

1. Check `fallback_invoked` on recent decisions:

   ```bash
   ssh office2-claude 'cat /data/services/openclaw/felix-heartbeat-gate/last-gate-decision.json | jq ".fallback_invoked"'
   ```

   - **`true` sustained** → gate side is broken (Anthropic API failure, timeout, or malformed response). Inspect `errors` field for the specific cause. Most likely: Anthropic API key issue. Re-verify with pre-cutover check 4.
   - **`false` and outcome is ESCALATE_TO_SONNET** → the gate is intentionally escalating. Either (a) `HEARTBEAT.md` always has a scheduled task that requires judgment (operator action — clear the contract file or rewrite tasks to be cheap-tier-friendly), or (b) `last-tick.json` is consistently showing novel patterns the gate can't classify with defined signals (operator action — add new signal definitions to `signals/config.toml` per the quickstart).

2. Check whether `last-tick.json` is fresh:

   ```bash
   ssh office2-claude 'jq ".started_at_utc" /data/services/openclaw/felix-core-digest-signals/last-tick.json'
   ```

   If older than 30 minutes, `felix-core-digest.service` is failing — see troubleshooting section above. The gate biases toward escalation on stale input.

### Two heartbeats running together (gate fires + OpenClaw heartbeat also fires)

**Symptom**: OpenClaw's own heartbeat is still firing alongside the new gate. Sonnet invocations doubled.

**Diagnosis**: the cutover's step 7 (`openclaw system heartbeat disable`) didn't stick, or someone re-enabled OpenClaw's heartbeat.

**Action**:

```bash
ssh office2-claude 'openclaw system heartbeat disable'
```

```bash
ssh office2-claude 'openclaw system heartbeat last'
```

Confirm no new ticks from OpenClaw's own scheduler.

### `kg-felix-bot` identity mismatch

**Symptom**: `tick.py` invokes `felix-file-issue.py` but issue creation fails with an authentication or identity error.

**Diagnosis**: `felix-file-issue.py` refuses to file when the active `gh` identity isn't `kg-felix-bot` (C-001).

**Action**:

```bash
ssh office2-claude 'gh auth status'
```

Expected: `Logged in to github.com account kg-felix-bot`. If shown as a different identity, the PAT has been rotated or replaced. Restore per the `kg-felix-bot-pat` entry in `docs/design/architecture/credentials-and-secrets.md`.

### Duplicate issues filed for the same signal

**Symptom**: two open GitHub issues for the same signal class (e.g., two `whatsapp_creds_restore` issues from the same threshold breach).

**Diagnosis order**:

1. Check `last_filed_issue_ref` in the per-signal state file:

   ```bash
   ssh office2-claude 'cat /data/services/openclaw/felix-core-digest-signals/state/whatsapp_creds_restore.json | jq ".last_filed_issue_ref"'
   ```

   - If `last_filed_issue_ref` points to a **closed** issue while a new one was filed: this is **correct**. Dedup is on open-only — once an issue closes, the next threshold breach is allowed to file a new one.
   - If `last_filed_issue_ref` points to an **open** issue and a duplicate was filed anyway: this is a **bug**. File a P2-bug citing the per-signal state file + the two duplicate issue numbers.

### `last-tick.json` missing entirely

**Symptom**: `last-tick.json` doesn't exist at the expected path.

**Diagnosis**: either `tick.py` has never successfully run (first cutover never completed step 11), or the state directory permissions are broken.

**Action**: verify the state directory exists and is writable by `claude`:

```bash
ssh office2-claude 'ls -ld /data/services/openclaw/felix-core-digest-signals'
```

If missing, run cutover step 2 again. If present but `tick.py` still fails to write, inspect the unit status (troubleshooting section above).

### `signals/config.toml` change isn't taking effect

**Symptom**: edited a threshold in `signals/config.toml`, pushed, deployed via `git pull` on office2, but the next cycle still uses the old threshold.

**Diagnosis**: `tick.py` reads the config file at the start of each tick (no daemon, no cache). If a change isn't taking effect, the file on office2 isn't actually updated.

**Action**:

```bash
ssh office2-claude 'cd ~/repos/kg-automation && git log -1 --oneline scripts/openclaw/observation/signals/config.toml'
```

Expected: most-recent commit matches the change you pushed. If not, the deploy didn't propagate; re-run the deploy.

---

## Rollback

If the new pipeline introduces a regression that can't be resolved
inline, roll back via the steps below. Each step reverses the
corresponding cutover step.

1. **Disable the new gate timer**. (Reverses cutover step 9.)

   ```bash
   ssh office2-claude 'systemctl --user disable --now felix-heartbeat-gate.timer'
   ```

2. **Re-enable OpenClaw's internal heartbeat**. (Reverses cutover step 7. Tier 2 — but rollback to a known-good prior state, no fresh backup required.)

   ```bash
   ssh office2-claude 'openclaw system heartbeat enable'
   ```

3. **Verify the OpenClaw heartbeat is firing**.

   ```bash
   ssh office2-claude 'openclaw system heartbeat last'
   ```

   Expected: new heartbeat ticks within 30 minutes.

4. *(Optional)* **Revert the modified `felix-core-digest.service`** if the chained `tick.py` ExecStart is causing collateral failures and `summarize.py`-only operation is preferred. The in-repo source-of-truth is the file under `scripts/office2/`; on office2:

   ```bash
   ssh office2-claude 'git -C ~/repos/kg-automation show HEAD~1:scripts/office2/felix-core-digest.service > ~/.config/systemd/user/felix-core-digest.service'
   ```

   (Adjust `HEAD~1` to the pre-#490 commit on `main` if more recent merges have landed.)

   ```bash
   ssh office2-claude 'systemctl --user daemon-reload'
   ```

5. *(Optional)* **Revert architecture JSON entries** if downstream consumers (governance pre-flight checklists, the doc-auditor, etc.) start choking on the new entries. Restore via `git revert` of the WP04 commit on `main`. Coordinate with the operator before doing this — most downstream consumers should be tolerant of additive changes.

After rollback, file a P1-bug citing the failure mode that triggered the
rollback, and **leave the state directories in place** so the next
forward attempt can re-use the persistent counters (FR-004).

---

## Cross-references

- **Mission spec**: [`kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/spec.md`](<../../kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/spec.md>)
- **Plan**: [`kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/plan.md`](<../../kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/plan.md>)
- **Quickstart**: [`kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/quickstart.md`](<../../kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/quickstart.md>)
- **Architectural precedent**: [`docs/runbooks/doc-auditor-driver-ops.md`](<./doc-auditor-driver-ops.md>) — same `kg-felix-bot` identity, same Anthropic key path, same scripts-first stateless-per-tick driver pattern
- **Source issue**: [#490](https://github.com/kentonium3/kg-automation/issues/490)
- **Architecture data**:
  - [`docs/design/architecture/data/service-inventory.json`](<../design/architecture/data/service-inventory.json>) — `felix-core-digest` (modified by #490) and `felix-heartbeat-gate` (new) entries
  - [`docs/design/architecture/data/credential-manifest.json`](<../design/architecture/data/credential-manifest.json>) — `anthropic` and `kg-felix-bot-pat` consumer lists updated to include new consumers
  - [`docs/design/architecture/data/data-flows.json`](<../design/architecture/data/data-flows.json>) — `signal-extraction-to-github` and `heartbeat-gate-to-main-agent` flow entries
- **Markdown views**:
  - [`docs/design/architecture/service-inventory.md`](<../design/architecture/service-inventory.md>) — Scheduled-Jobs table + per-service detail sections
  - [`docs/design/architecture/data-flows.md`](<../design/architecture/data-flows.md>) — narrative sections "Signal Extraction → GitHub" and "Heartbeat Gate → Main Agent"
  - [`docs/design/architecture/data-flows.view.md`](<../design/architecture/data-flows.view.md>) — Mermaid subgraph "Signal-Driven Monitoring (#490)"

---

## Post-rollout tuning (operator, NOT this WP's scope)

After cutover succeeds and the system has been observed for a full
week:

- **Threshold tuning**: false-positive rate guides edits to
  `signals/config.toml` (`cycle_threshold`, `rolling_threshold`,
  `dedup_window`). Config edits are Tier 3 — push, `git pull` on office2,
  next cycle picks up the new values.
- **Add new signals**: per the quickstart's "Add a new signal" section.
- **Token baseline**: capture a post-rollout 7-day baseline using
  `felix-doc-auditor`'s baseline procedure as the template; compute the
  NFR-001 cost reduction. File a follow-up issue if reduction is <80%.

This runbook is the durable record. Update it (with `updated_by` referencing the issue) when behavior or procedure changes.
