---
id: cutover-log-felix-doc-auditor-driver
doc_type: runbook
title: "Cutover Playbook: felix-doc-auditor → felix-doc-auditor-driver (Scripts-First)"
status: approved
level: howto
owners: [kent, felix-doc-auditor]
last_validated: 2026-05-21
version: 0.1
---

# Cutover Playbook: felix-doc-auditor → felix-doc-auditor-driver

> **Status when this file was written**: pre-cutover. Mission
> `refactor-doc-auditor-to-scripts-first-driver-01KS2XNX` (#343) had completed
> WP01–WP08; WP09 produced this playbook in lieu of executing the deploy.
> The live deploy + verification + post-rework measurement are deferred to
> the post-merge operator (Kent, or a follow-on Claude Code session driving
> this playbook step-by-step).

This playbook is a single-page operator runbook. It is intended to be
executed verbatim — every command is copy-pasteable, every decision branch
is enumerated, every placeholder is marked `<...>` for the operator to
fill in inline at execution time. The document records the actual cutover
once executed: pre-cutover state, deploy output, verification results,
measurement values, and the NFR-001 acceptance gate determination.

The cutover is **Tier 2** (application/state — replaces a systemd unit,
deletes a workspace directory, deregisters an OpenClaw agent). Follow
the Tier-2 protocol: confirm Restic backup within 24 hours before
proceeding. This is **fail-forward** per spec C-007 — no automatic
rollback; recovery is the manual restore at the end of this doc.

## Table of contents

1. [Pre-flight checklist (T040)](<#1-pre-flight-checklist-t040>)
2. [Cutover execution sequence (T041)](<#2-cutover-execution-sequence-t041>)
3. [First-tick verification (T042)](<#3-first-tick-verification-t042>)
4. [Post-rework measurement procedure (T043)](<#4-post-rework-measurement-procedure-t043>)
5. [Post-rework baseline JSON population (T044)](<#5-post-rework-baseline-json-population-t044>)
6. [NFR-001 acceptance gate (T045)](<#6-nfr-001-acceptance-gate-t045>)
7. [Known hazard: spec-kitty merge `git mv` invariant violation (#1039)](<#7-known-hazard-spec-kitty-merge-git-mv-invariant-violation-1039>)
8. [Rollback note (C-007: fail-forward; manual restore last-resort)](<#8-rollback-note-c-007-fail-forward-manual-restore-last-resort>)

## Provenance

| Field | Value |
|---|---|
| Mission | refactor-doc-auditor-to-scripts-first-driver-01KS2XNX |
| Mission issue | #343 |
| Spec C-references | C-004 (queue-drained), C-007 (fail-forward), FR-010 (retire old agent), NFR-001 (≥80% reduction) |
| Deploy script | `scripts/office2/deploy/felix-doc-auditor-driver.sh` |
| Driver entry point | `/home/claude/kg-automation/scripts/doc_audit/run.py` |
| systemd unit | `~/.config/systemd/user/felix-doc-auditor.service` |
| systemd timer | `~/.config/systemd/user/felix-doc-auditor.timer` (OnCalendar=hourly) |
| Tick signal | `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json` |
| Activity log | `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md` |
| Legacy workspace (to be deleted) | `/data/services/openclaw/felix-doc-auditor/` |
| Pre-rework baseline | `docs/design/architecture/baselines/felix-doc-auditor-pre-rework.json` |
| Post-rework baseline | `docs/design/architecture/baselines/felix-doc-auditor-post-rework.json` |

## Cutover execution record

> Operator: fill these out inline as you progress through the playbook.
> Replace each `<...>` placeholder with the actual value at execution time.

- **Pre-cutover state recorded on**: `<DATE-UTC>`
- **Mission merge to main commit SHA**: `<SHA>`
- **Deploy started (UTC)**: `<TIMESTAMP>`
- **Deploy ended (UTC)**: `<TIMESTAMP>`
- **Deploy exit code**: `<0 or non-zero>`
- **First verification tick (UTC)**: `<TIMESTAMP>`
- **First verification tick result**: `<success / failure>`
- **Measurement window start (UTC)**: `<TIMESTAMP>`
- **Measurement window end (UTC)**: `<TIMESTAMP>`
- **NFR-001 acceptance gate determination**: `<PASS / FAIL>`
- **NFR-001 weighted_average_reduction_pct**: `<X.X%>`

---

## 1. Pre-flight checklist (T040)

**Goal**: confirm the system is in a deploy-safe state. Tier-2 protocol
plus spec C-004 (queue-drained) plus deploy-script preconditions.

### 1.1 Queue state — spec C-004

Per spec C-004 the queue must be **drained or near-drained**. Fully empty
is NOT required; the acceptable states are documented below.

#### 1.1.1 Open audits with `status:in-progress`

```bash
gh issue list --repo kentonium3/kg-automation --label "Doc audit:,status:in-progress" --state open --json number,title,labels
```

Acceptable outcomes:

- **Fully drained** (0 in-progress) — ideal, proceed.
- **Near-drained** (1–2 in-progress, each with a matching `audit-pending-approval` issue per 1.1.2) — acceptable; these are Level-1 wait states, not stuck locks. Document the audit numbers below.
- **Stuck-lock orphans** (in-progress with NO matching pending-approval) — NOT acceptable. Clear the orphan label first (`gh issue edit <N> --remove-label "status:in-progress"`), let the next tick re-pick up the audit, re-check after one timer fire.

Record below:

- **In-progress audit count at pre-flight**: `<N>`
- **In-progress audit issues**: `<list of #N or "none">`
- **Justification (if not zero)**: `<text — e.g. "audit #350 has matching pending-approval #351 — known Level-1 wait state, proceeding">`

#### 1.1.2 Open pending-approvals

```bash
gh issue list --repo kentonium3/kg-automation --label "audit-pending-approval" --state open --json number,title,labels
```

Acceptable outcomes:

- Empty list — ideal.
- Non-empty AND every issue has one of the three decision labels (`audit-approve`, `audit-reject`, `audit-skip`) — safe; the new driver will pick them up on its first tick post-deploy.
- Non-empty AND any issue is undecided (no decision label) — pause cutover; have Kent triage before continuing.

Record below:

- **Pending-approval count at pre-flight**: `<N>`
- **Undecided pending-approvals (must be zero to proceed)**: `<N>`

#### 1.1.3 Drift events processed in last 24h

```bash
ssh office2-claude 'tail -50 /data/services/openclaw/felix-doc-auditor/drift-events.jsonl 2>/dev/null | wc -l'
```

(Best-effort reference; the legacy workspace will be deleted by the deploy. Record the value for diagnostic continuity in case the cutover needs to be debugged against the prior tick rate.)

- **Drift events touched in last 24h (legacy workspace)**: `<N>`

#### 1.1.4 Last successful tick under the legacy agent

```bash
ssh office2-claude 'grep -E "^- \*\*[0-9]" /home/kgale/second-brain/agents/logs/doc-auditor-$(date -u +%Y-%m-%d).md 2>/dev/null | tail -3'
```

(If today's log doesn't exist yet, fall back to yesterday: `--date "yesterday"`.)

- **Last successful tick timestamp (legacy)**: `<UTC timestamp>`

### 1.2 Tier-2 backup + connectivity

#### 1.2.1 Restic backup within last 24 hours

```bash
ssh office2-claude 'tail -20 /data/services/backup/logs/backup-*.log 2>/dev/null | grep -E "SUCCESS|FAIL" | tail -5'
```

Required: the most recent `SUCCESS` line is within the last 24 hours. If older, trigger a fresh snapshot before proceeding:

```bash
ssh office2-claude 'systemctl --user start --wait restic-backup.service'
```

Then re-check.

- **Most recent Restic SUCCESS timestamp**: `<UTC timestamp>`
- **Backup confirmed within 24 h**: `<YES / NO>`

#### 1.2.2 openclaw-gateway health

```bash
ssh office2-claude 'systemctl --user is-active openclaw-gateway.service'
```

Expected output: `active`. If not, troubleshoot openclaw-gateway before proceeding — the deploy's step 5 (`openclaw agents list`) will fail and abort.

- **openclaw-gateway.service status**: `<active / inactive / failed>`

#### 1.2.3 gh CLI authenticated as kg-felix-bot

```bash
ssh office2-claude 'gh auth status'
```

Expected: `Logged in to github.com as kg-felix-bot`. The deploy's step 1 will fail otherwise.

- **gh CLI user on office2**: `<kg-felix-bot / OTHER>`

#### 1.2.4 Anthropic secret readable

```bash
ssh office2-claude 'test -r /home/claude/.openclaw/secrets/anthropic && echo READABLE || echo MISSING'
```

Expected: `READABLE`. (The deploy's step 1 pre-flight will also verify this.)

- **Anthropic secret readable on office2**: `<READABLE / MISSING>`

### 1.3 Mission merged to main

```bash
git -C /Users/kentgale/repos/kg-automation log origin/main --oneline -1 | grep -i "refactor-doc-auditor-to-scripts-first-driver" || echo "NOT MERGED YET"
```

This playbook is only valid AFTER the mission has been merged to main. If the merge has not happened (or has been blocked by spec-kitty merge bug #1039), see section 7 first.

- **Merge commit on main**: `<SHA>`
- **Merge commit message**: `<text>`

### 1.4 Pre-flight summary

All boxes must be checked before proceeding to section 2:

- [ ] In-progress audit count is zero OR each entry has a matching pending-approval (1.1.1)
- [ ] No undecided pending-approvals (1.1.2)
- [ ] Restic backup confirmed within 24 h (1.2.1)
- [ ] openclaw-gateway.service is `active` (1.2.2)
- [ ] gh CLI authenticated as kg-felix-bot on office2 (1.2.3)
- [ ] Anthropic secret readable on office2 (1.2.4)
- [ ] Mission merged to main (1.3)

If any box is unchecked: STOP. Address the gap. Do not proceed.

---

## 2. Cutover execution sequence (T041)

**Goal**: run the deploy script in `--apply --backup-confirmed` mode. The
script implements the 8-step sequence documented in
`scripts/office2/deploy/felix-doc-auditor-driver.sh`. Each step is
idempotent (steps 3–7 detect existing state and skip cleanly).

### 2.1 (Optional but recommended) Dry-run preview

```bash
ssh office2-claude 'bash /home/claude/kg-automation/scripts/office2/deploy/felix-doc-auditor-driver.sh --dry-run'
```

Expected output mirrors `scripts/office2/deploy/felix-doc-auditor-driver.dry-run.expected.txt`. Compare by eye for any surprises (e.g., unexpected `STEP FAILED:` lines, missing dependencies). The dry-run does NOT modify state; it is purely informational.

- **Dry-run completed**: `<YES / NO>`
- **Dry-run exit code**: `<0 or non-zero>`
- **Dry-run surprises**: `<none / list>`

### 2.2 Execute the deploy

```bash
ssh office2-claude 'bash /home/claude/kg-automation/scripts/office2/deploy/felix-doc-auditor-driver.sh --apply --backup-confirmed' 2>&1 | tee /tmp/felix-doc-auditor-driver-deploy-$(date -u +%Y%m%dT%H%M%SZ).log
```

The `tee` to `/tmp/` captures the full output for the cutover record. After completion, copy the log file into this document (or attach to the mission issue) for durable audit trail.

- **Deploy started (UTC)**: `<TIMESTAMP>`
- **Deploy ended (UTC)**: `<TIMESTAMP>`
- **Deploy exit code**: `<0 or non-zero>`
- **Deploy log path on Mac**: `<scp the file off and record local path>`

### 2.3 Verify each of the 8 deploy steps printed as completed

The deploy script emits `==> Step N/8: <title>` for each step. Confirm each appeared and (in apply mode) was followed by `[APPLY] $ <command>` lines without `STEP FAILED:` markers.

| Step | Title | Apply-mode outcome to verify |
|---|---|---|
| 1 | Pre-flight checks | hostname=office2, openclaw-gateway active, secret readable, gh as kg-felix-bot, repo present |
| 2 | Pull driver code (`git pull --rebase` at `/home/claude/kg-automation`) | Pull succeeded; new `scripts/doc_audit/run.py` present |
| 3 | Create driver state directory `/data/services/openclaw/felix-doc-auditor-driver` | dir exists, mode 0755, owner claude:claude |
| 4 | Install systemd unit + timer to `~/.config/systemd/user/` | service + timer files copied; `daemon-reload` ran |
| 5 | Retire openclaw agent registration `felix-doc-auditor` | `openclaw agents delete felix-doc-auditor --force` ran; post-check confirms absence |
| 6 | Delete legacy workspace `/data/services/openclaw/felix-doc-auditor` | dir removed |
| 7 | Verify `felix-doc-auditor.timer` is enabled | timer active; next-fire time printed |
| 8 | Done; print follow-up | follow-up verification command printed |

Sanity-spot-check on office2 after the deploy:

```bash
ssh office2-claude 'systemctl --user is-active felix-doc-auditor.timer && systemctl --user list-timers felix-doc-auditor.timer --no-pager'
ssh office2-claude 'test -f /data/services/openclaw/felix-doc-auditor-driver && echo state_dir_exists || (ls -ld /data/services/openclaw/felix-doc-auditor-driver && echo OK_dir)'
ssh office2-claude 'test ! -d /data/services/openclaw/felix-doc-auditor && echo legacy_workspace_gone || echo LEGACY_STILL_PRESENT'
ssh office2-claude 'openclaw agents list | grep -E "^- felix-doc-auditor\b" && echo STILL_REGISTERED || echo deregistered_ok'
```

Validation checklist for section 2:

- [ ] Deploy script exits 0
- [ ] All 8 step headers printed
- [ ] No `STEP FAILED:` lines in the captured log
- [ ] `felix-doc-auditor.timer` active and enabled
- [ ] `/data/services/openclaw/felix-doc-auditor-driver/` state dir exists, owned by claude:claude
- [ ] Legacy workspace `/data/services/openclaw/felix-doc-auditor/` no longer exists
- [ ] `openclaw agents list` does NOT include `felix-doc-auditor`

If any box is unchecked: STOP. Do not advance to section 3. The deploy is idempotent — re-run from the failed step after addressing the root cause. If a destructive step (5 or 6) completed but a later step failed, see section 8 (rollback).

---

## 3. First-tick verification (T042)

**Goal**: force a verification tick before the next hourly cron fire to catch any deploy-time integration error early.

### 3.1 Trigger the verification tick

```bash
ssh office2-claude 'systemctl --user start --wait felix-doc-auditor.service'
```

`--wait` blocks until the oneshot unit exits. Capture the local wall-clock start time below.

- **Verification tick triggered at (UTC)**: `<TIMESTAMP>`
- **`start --wait` exit code on the operator's side**: `<0 or non-zero>` (note: this reflects the systemctl invocation, not the driver itself — check 3.2 next)

### 3.2 Inspect the tick signal

```bash
ssh office2-claude 'cat /data/services/openclaw/felix-doc-auditor-driver/last-tick.json | jq'
```

Required values:

- `status` = `"success"`
- `exit_code` = 0
- `timestamp_utc` is within the last minute
- `errors` = `[]`
- `judgment` block populated (or zero for an empty tick — both acceptable)

Record below:

- **last-tick.json `status`**: `<success / partial / failure>`
- **last-tick.json `exit_code`**: `<0 / 1 / 2>`
- **last-tick.json `timestamp_utc`**: `<value>`
- **last-tick.json `tick.signals_seen`**: `<N>`
- **last-tick.json `tick.signals_processed`**: `<N>`
- **last-tick.json `errors`**: `<array>`
- **last-tick.json `judgment.input_tokens`**: `<N>`
- **last-tick.json `judgment.cache_hit_input_tokens`**: `<N>`
- **last-tick.json `judgment.output_tokens`**: `<N>`

### 3.3 Inspect the systemd journal

```bash
ssh office2-claude 'journalctl --user -u felix-doc-auditor --since "2 minutes ago" --no-pager'
```

Required: the final stdout line is the deterministic `SUMMARY:` line (per tick-signal contract):

```
SUMMARY: status=success audits=N debt=N tier_a=N drift=N dur=Ns tokens=in:N(cache:N)/out:N
```

There must be NO exception tracebacks. The unit should exit `code=exited, status=0/SUCCESS`.

- **Journal SUMMARY line**: `<paste the line>`
- **Exceptions or tracebacks present**: `<NO / YES — describe>`
- **Unit final state**: `<inactive (success) / failed>`

### 3.4 Inspect the activity log

```bash
ssh office2-claude 'tail -20 /home/kgale/second-brain/agents/logs/doc-auditor-$(date -u +%Y-%m-%d).md 2>/dev/null || tail -20 /home/kgale/second-brain/agents/logs/doc-auditor-$(date -u -d "yesterday" +%Y-%m-%d).md'
```

Required: a new entry corresponding to the verification tick's timestamp. The new driver's activity-log format mirrors the legacy agent's format (timestamp header + per-audit lines) so existing readers remain compatible.

- **New activity-log entry timestamp**: `<value>`
- **New entry matches the verification tick**: `<YES / NO>`

### 3.5 First-tick decision branch

| All four checks pass | Any check fails |
|---|---|
| Proceed to section 4 (post-rework measurement) | STOP. Do not advance. Investigate the first-tick failure root cause. |

If section 3 fails: the deploy completed but the driver is non-functional. Likely root causes: missing Python dependency (`anthropic` SDK version mismatch), incorrect file ownership on the state dir (claude can't write the artifact), missing kg-felix-bot gh-cli auth on the unit's environment, `/home/claude/.openclaw/secrets/anthropic` not readable by the driver process. Triage via the journal stderr; patch forward (commit a fix to `scripts/doc_audit/run.py`, redeploy via section 2, re-verify via section 3).

Validation checklist for section 3:

- [ ] Tick signal: `status=success`, `exit_code=0`
- [ ] `timestamp_utc` is within last minute
- [ ] `errors` is `[]`
- [ ] Journal SUMMARY line present
- [ ] Unit exited 0 (no failed state)
- [ ] Activity log entry written
- [ ] No exceptions in journal

---

## 4. Post-rework measurement procedure (T043)

**Goal**: capture 3+ representative ticks under the new driver and feed
them to `scripts/doc_audit/baselines/measure-tokens.py` for the NFR-001
comparison. Ideal mix: at least one empty, one debt-only, one tier-A
apply. Natural variation across ~24h normally covers this; if not, fall
back to the synthetic-audit option in 4.4.

### 4.1 Snapshot ticks as they happen

`last-tick.json` is overwritten by every tick (current-state, not append-only). To preserve a measurement window, snapshot each tick into a per-tick directory immediately after it fires.

#### 4.1.1 One-time setup (on office2)

```bash
ssh office2-claude 'mkdir -p /tmp/post-rework-ticks'
```

#### 4.1.2 Per-tick snapshot (run after each natural tick fires)

```bash
ssh office2-claude 'cp /data/services/openclaw/felix-doc-auditor-driver/last-tick.json /tmp/post-rework-ticks/tick-$(date -u +%Y%m%dT%H%M%SZ).json'
```

Alternatively, set up a watcher (cron-style script that snapshots every time the artifact's mtime changes) for a few days. A simple inotify polling approach:

```bash
ssh office2-claude 'nohup bash -c "
prev=\"\"
while true; do
  curr=\$(stat -c %Y /data/services/openclaw/felix-doc-auditor-driver/last-tick.json 2>/dev/null)
  if [ -n \"\$curr\" ] && [ \"\$curr\" != \"\$prev\" ]; then
    cp /data/services/openclaw/felix-doc-auditor-driver/last-tick.json /tmp/post-rework-ticks/tick-\$(date -u +%Y%m%dT%H%M%SZ).json
    prev=\"\$curr\"
  fi
  sleep 60
done
" > /tmp/post-rework-watcher.log 2>&1 &'
```

Stop the watcher after measurement window closes:

```bash
ssh office2-claude 'pkill -f /tmp/post-rework-watcher.log'
```

(If a more robust watcher is desired, file a follow-up issue; the cron-snapshot approach is sufficient for a one-off baseline.)

### 4.2 Verify outcome coverage during the window

Watch the systemd journal to confirm the mix of outcomes is reasonable:

```bash
ssh office2-claude 'journalctl --user -u felix-doc-auditor --since "24 hours ago" --no-pager | grep ^SUMMARY:'
```

A line like `SUMMARY: status=success audits=0 debt=0 tier_a=0 drift=0 dur=...` = empty outcome. `debt=N tier_a=0` with `audits=N` = debt_only. `tier_a=N` = tier_a_apply.

- **Empty ticks observed in window**: `<N>`
- **Debt-only ticks observed in window**: `<N>`
- **Tier-A apply ticks observed in window**: `<N>`

### 4.3 Run measure-tokens.py against the snapshots

The script `scripts/doc_audit/baselines/measure-tokens.py` was authored against the OpenClaw session JSONL surface for pre-rework measurement. For post-rework, the operator has two options:

#### 4.3.1 Option A — measure-tokens.py adapter mode (if implemented in WP07)

If the script already supports `--source post-rework --tick-dir <path>`, run it directly:

```bash
ssh office2-claude 'python3 /home/claude/kg-automation/scripts/doc_audit/baselines/measure-tokens.py --source post-rework --tick-dir /tmp/post-rework-ticks --output /tmp/post-rework-measurements.json'
scp office2-claude:/tmp/post-rework-measurements.json /Users/kentgale/repos/kg-automation/tmp/
```

#### 4.3.2 Option B — manual aggregation from snapshots (fallback)

If the script doesn't yet have a `--source post-rework` mode (verify with `--help` first), aggregate the `last-tick.json` snapshots directly with `jq`:

```bash
ssh office2-claude 'jq -s "
  {
    by_outcome: (
      group_by(
        if (.tick.tier_a_commits | length) > 0 then \"tier_a_apply\"
        elif (.tick.debt_filed | length) > 0 then \"debt_only\"
        else \"empty\" end
      ) | map({
        outcome: (
          if (.[0].tick.tier_a_commits | length) > 0 then \"tier_a_apply\"
          elif (.[0].tick.debt_filed | length) > 0 then \"debt_only\"
          else \"empty\" end
        ),
        sample_count: length,
        average_input_tokens: (map(.judgment.input_tokens) | add / length),
        average_cache_hit_input_tokens: (map(.judgment.cache_hit_input_tokens) | add / length),
        average_output_tokens: (map(.judgment.output_tokens) | add / length),
        average_duration_seconds: (map(.duration_seconds) | add / length),
        samples: .
      })
    )
  }
" /tmp/post-rework-ticks/*.json' > /Users/kentgale/repos/kg-automation/tmp/post-rework-measurements.json
```

(The script-adapter path in 4.3.1 is preferred when available — it ensures methodology consistency with the pre-rework measurement. The jq fallback is for the rare case where the script isn't yet adapted.)

### 4.4 If natural variation doesn't yield all 3 outcomes within 24h

File a synthetic audit issue against a doc whose `last_validated` is stale by ≥30 days to force a `tier_a_apply` outcome. Acceptable; document the synthetic origin in the post-rework JSON's sample note.

```bash
gh issue create --repo kentonium3/kg-automation --title "Doc audit: <doc-path> (synthetic for post-rework measurement)" --label "Doc audit:,priority:Tier-A" --body "Synthetic audit to drive a tier_a_apply outcome under the new driver. Documented in cutover-log.md section 4.4."
```

Wait for the next hourly tick to pick it up.

- **Synthetic audit filed**: `<YES / NO — issue # if YES>`

### 4.5 Recorded measurements

Once `measure-tokens.py` (or the jq fallback) has emitted the per-outcome aggregation, copy each value into `docs/design/architecture/baselines/felix-doc-auditor-post-rework.json` per section 5. Below is a compact summary table for inline reference during the gate determination in section 6.

| Outcome | sample_count | avg input | avg cache_hit input | avg output | avg duration_s |
|---|---|---|---|---|---|
| empty | `<N>` | `<N>` | `<N>` | `<N>` | `<N>` |
| debt_only | `<N>` | `<N>` | `<N>` | `<N>` | `<N>` |
| tier_a_apply | `<N>` | `<N>` | `<N>` | `<N>` | `<N>` |

Validation checklist for section 4:

- [ ] ≥3 ticks measured total
- [ ] At least 1 outcome represented (empty is most common)
- [ ] Token counts are in plausible range (input ≪ pre-rework baseline)
- [ ] Cache-hit ratio is non-zero for non-empty outcomes (see sanity check in section 5)

---

## 5. Post-rework baseline JSON population (T044)

**Goal**: replace the placeholder values in
`docs/design/architecture/baselines/felix-doc-auditor-post-rework.json`
with the measured values from section 4. The schema skeleton already
matches the pre-rework JSON shape; populate it in-place.

### 5.1 Replace top-level placeholders

- `status`: `"not_yet_executed"` → `"measured"` (or `"failed_nfr_001"` if section 6 determines a FAIL with patch-forward pending)
- `captured_at`: `null` → `"<ISO-8601 UTC timestamp of when measurement closed>"`
- `subject.git_sha`: `null` → `"<sha of HEAD at measurement time>"`
- `measurement_window.tick_count`: `null` → `<total ticks measured>`
- `measurement_window.earliest_tick_utc`: `null` → `"<earliest snapshot timestamp>"`
- `measurement_window.latest_tick_utc`: `null` → `"<latest snapshot timestamp>"`
- `measurement_window.spans_hours`: `null` → `<integer hours>`

### 5.2 Populate per-outcome measurements

For each outcome (`empty`, `debt_only`, `tier_a_apply`) in `measurements[]`, replace the `null` values with the aggregated numbers from section 4. Populate the `samples` array with the per-tick records (`tick_id`, `timestamp_utc`, `input_tokens`, `cache_hit_input_tokens`, `output_tokens`, `duration_seconds`).

Example populated outcome (for reference):

```json
{
  "outcome": "empty",
  "description": "Tick exits cleanly with no signals to process...",
  "sample_count": 18,
  "average_input_tokens": 7200,
  "average_cache_hit_input_tokens": 4500,
  "average_output_tokens": 95,
  "average_duration_seconds": 4.2,
  "average_llm_calls": 1.0,
  "samples": [
    {
      "tick_id": "tick-20260523T010005Z",
      "timestamp_utc": "2026-05-23T01:00:05Z",
      "input_tokens": 6900,
      "cache_hit_input_tokens": 4400,
      "output_tokens": 88,
      "duration_seconds": 3.9
    }
  ]
}
```

### 5.3 Compute the comparison block

Per-outcome reduction formula (per spec NFR-001):

```
effective_post_input = post_input_tokens - (post_cache_hit_input_tokens * 0.9)
reduction_pct = ((pre_input_tokens_billable - effective_post_input) / pre_input_tokens_billable) * 100
```

Notes:

- Pre-rework had NO prompt caching (OpenClaw-agent path). `pre_cache_hit_input_tokens` is always 0 in this comparison; only `post_cache_hit_input_tokens` contributes to the discount.
- The 0.9 factor reflects Anthropic's ~10% billing rate for cache hits (cache hits cost ~10% of standard input rate, so the "saved" portion is the remaining 90%).
- For the `empty` outcome the pre baseline used `average_total_input_tokens_billable: 523131.4` (includes cache_read + cache_write under the OpenClaw session-jsonl methodology).
- For `debt_only`: pre value 1,456,874.2.
- For `tier_a_apply`: pre value 1,170,917.0.

Populate `comparison_with_pre_rework.per_outcome[]`:

```json
{
  "outcome": "empty",
  "pre_input_tokens_billable": 523131.4,
  "post_input_tokens": <from measurement>,
  "post_cache_hit_input_tokens": <from measurement>,
  "effective_post_input_tokens": <computed>,
  "reduction_pct": <computed>
}
```

Compute `weighted_average_reduction_pct` using the observed mix in the post-rework window (NOT the pre-rework mix). Hold per-outcome reductions as the primary comparator for NFR-001 acceptance — the weighted average is supplementary.

### 5.4 Cache sanity check (BEFORE declaring victory in section 6)

This check is load-bearing per spec NFR-001 — prompt caching is supposed to provide most of the reduction. If caching is broken, the NFR may still appear to pass on prompt-size-shrinkage alone, but the durability of the savings is questionable.

- **Check 1**: For non-empty ticks, `cache_hit_input_tokens / input_tokens ≥ 0.5` within a tick should hold (the cached boilerplate is invariant; a non-first call within the 5-minute TTL hits the cache). If `cache_hit_input_tokens = 0` across ALL measured non-empty ticks: **CACHING IS BROKEN**. Record in `open_caveats[]` and investigate before closing the mission. Likely causes:
  - Misplaced `cache_control: ephemeral` marker in the prompt template
  - Anthropic SDK version doesn't support cache_control on the selected model
  - Cached prompt blocks are too small (Anthropic enforces a minimum block size for cacheability)
- **Check 2**: Across the full window (including empty ticks), the global ratio will be lower (empty ticks may not call the LLM at all). Use the per-tick ratio as the diagnostic, not the global average.

Record sanity-check outcome below:

- **Non-empty per-tick cache_hit / input ratio (median)**: `<value>`
- **Caching status**: `<healthy / broken / no_data>`

### 5.5 Add open_caveats

Append any anomalies observed during the measurement:

- Mix bias (e.g., all-empty window because queue was blocked)
- Undersampled outcomes
- Synthetic audit origin for tier_a_apply (if 4.4 was used)
- Cache health concerns from 5.4
- Any failed/partial ticks excluded from the per-outcome averages

### 5.6 Commit the populated file

The post-merge operator commits the populated JSON in a follow-up commit to `main` (NOT to the mission branch — the mission is already merged):

```bash
cd /Users/kentgale/repos/kg-automation
git add docs/design/architecture/baselines/felix-doc-auditor-post-rework.json docs/design/architecture/baselines/cutover-log.md
git commit -m "docs(felix-doc-auditor): record post-rework measurement + NFR-001 gate result [doc-audit]"
git push origin main
```

Validation checklist for section 5:

- [ ] All top-level placeholders replaced
- [ ] All per-outcome `null` values replaced with measured values
- [ ] `comparison_with_pre_rework` per_outcome reduction_pct computed for each outcome
- [ ] `weighted_average_reduction_pct` computed
- [ ] Cache sanity check performed (5.4)
- [ ] `open_caveats` reflects any anomalies
- [ ] File JSON-validates (e.g. `python3 -c "import json; json.load(open('docs/design/architecture/baselines/felix-doc-auditor-post-rework.json'))"`)

---

## 6. NFR-001 acceptance gate (T045)

**Goal**: explicit pass/fail determination on ≥80% reduction. This is the
single gate the whole rework is graded against. Record the determination
here so the audit trail is unambiguous.

### 6.1 Criteria

- **PASS**: `comparison_with_pre_rework.weighted_average_reduction_pct ≥ 80.0`
  AND per-outcome reductions are each ≥80% for at least the `empty` outcome
  (the highest-volume case; sets the floor for cost).
- **FAIL**: any of the above is not satisfied.

If `weighted_average_reduction_pct ≥ 80` but per-outcome `empty` reduction
is < 80%, the gate is FAIL — the cost on the dominant outcome must drop
even if other outcomes overcompensate. (Rationale: NFR-001's goal is to
make the high-frequency idle case cheap. Carrying the empty outcome on
the others would tighten future operating costs.)

### 6.2 Gate determination

- **weighted_average_reduction_pct**: `<X.X%>`
- **per-outcome empty reduction_pct**: `<X.X%>`
- **per-outcome debt_only reduction_pct**: `<X.X%>`
- **per-outcome tier_a_apply reduction_pct**: `<X.X%>`
- **Determination**: `<PASS / FAIL>`
- **Date of determination (UTC)**: `<TIMESTAMP>`

### 6.3 Per-outcome breakdown table (final record)

> Operator: replace placeholders below with measured values.

| Outcome | Pre input (billable) | Post input | Post cache hit | Effective post input | Reduction |
|---|---|---|---|---|---|
| empty | 523131.4 | `<N>` | `<N>` | `<N>` | `<X.X%>` |
| debt_only | 1456874.2 | `<N>` | `<N>` | `<N>` | `<X.X%>` |
| tier_a_apply | 1170917.0 | `<N>` | `<N>` | `<N>` | `<X.X%>` |

### 6.4 On PASS

- Update this file's `## Cutover execution record` block at top — set `NFR-001 acceptance gate determination: PASS` and `NFR-001 weighted_average_reduction_pct: <X.X%>`.
- Update `docs/design/architecture/baselines/felix-doc-auditor-post-rework.json` `status` to `"measured"`.
- Proceed to WP10 (architecture doc updates — `service-inventory.json`, `topology.json`, `data-flows.json` reflect the new driver instead of the OpenClaw agent).
- The mission is releasable.

### 6.5 On FAIL — investigation paths

Likely root causes, in priority order:

1. **Prompt caching not working** (`cache_hit_input_tokens = 0` across non-empty ticks).
   - Inspect prompt construction in `scripts/doc_audit/judgment/*.py` — confirm the boilerplate-system-message block has a `cache_control: { type: "ephemeral" }` marker and is sized above Anthropic's minimum cacheable threshold.
   - Confirm the Anthropic SDK version on office2 supports `cache_control` on the selected model (`anthropic/claude-haiku-4-5`). Check `/home/claude/kg-automation/.venv/lib/python*/site-packages/anthropic` version.
   - Run a minimal-reproducer script that makes 2 back-to-back calls with the same cached block, log `usage.cache_read_input_tokens`. If 0 on the second call, caching is broken.
2. **Per-judgment input larger than expected** (prompts contain too much context).
   - Inspect the prompt templates in `scripts/doc_audit/prompts/`. Are they pulling in full files when a summary would suffice? Are they re-including the doc body when it's already in the cached preamble?
   - Trim aggressively. The judgment LLM should see: the small variable context (issue title, audit metadata, recent diff hunks) + the cached preamble (system rules, persona). It should NOT see the entire doc body unless absolutely necessary.
3. **Output tokens larger than expected** (LLM responses verbose).
   - Inspect the prompt's output schema. Are response fields free-form text where a structured enum would do? Are rationale fields longer than necessary?
   - Constrain via JSON schema validators (already in place per WP04 cycle-2 fix — verify they're rejecting verbose output).
4. **Anomalous samples skewing the average** (e.g., one tick had a runaway debt generation).
   - Inspect per-tick samples in the JSON. If one sample dominates the average, drop it (with note in `open_caveats`) and recompute.

After investigation:

- File a follow-up issue in #343's tree OR plan a patch-forward fix within this mission.
- Do NOT close the mission until NFR-001 passes. The post-rework.json `status` stays `"failed_nfr_001"` and the cutover-log records the FAIL determination with the investigation path documented inline.
- Re-measure after patching forward; re-evaluate the gate.

Validation checklist for section 6:

- [ ] Gate determination recorded (PASS or FAIL)
- [ ] Per-outcome breakdown table populated
- [ ] On PASS: mission status reflects "releasable"; post-rework.json `status` set to `"measured"`
- [ ] On FAIL: investigation path documented; mission stays open

---

## 7. Known hazard: spec-kitty merge `git mv` invariant violation (#1039)

This mission includes `git mv` of two files in WP01:

- `scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py` → `scripts/doc_audit/helpers/handle_drift_events.py`
- `scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py` → `scripts/doc_audit/helpers/handle_audit_routing.py`

Per the diagnostic at
`docs/diagnostics/1039_merge-resume-fails-after-invariant-violation.md`,
this triggers a known spec-kitty bug (filed upstream as
`Priivacy-ai/spec-kitty#1039`, spec-kitty 3.1.8). The squash commit
lands on `main` cleanly, but the post-merge "working-tree invariant"
check trips because the renamed source path reappears in the primary
checkout's working tree, auto-staged as `A` (added). Retrying
`spec-kitty merge` then fails with `Squash commit into main failed:
Not currently on any branch.`

The work itself reaches `main` correctly. Only the bookkeeping
(mission_number assignment, lane branch deletion, worktree removal,
auto-close hook) is stranded.

### 7.1 Symptom recognition

After running `spec-kitty merge --mission refactor-doc-auditor-to-scripts-first-driver-01KS2XNX`, the operator sees one of:

**Symptom A** — invariant violation on first attempt:

```text
Error: Post-merge working-tree invariant violated. The following paths diverge
from HEAD unexpectedly:
  A  scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py
  A  scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py
```

**Symptom B** — resume fails after manual cleanup:

```text
Error: Squash commit into main failed: Not currently on any branch.
```

Either symptom triggers section 7.2 recovery.

### 7.2 Manual recovery sequence (inline — no need to flip to a different doc)

Execute on the Mac, in the primary checkout (`/Users/kentgale/repos/kg-automation`), NOT in a worktree.

```bash
cd /Users/kentgale/repos/kg-automation
```

**Step 7.2.1** — Confirm the merge commit IS on main:

```bash
git log origin/main --oneline -5
```

You should see a commit like `<sha> feat(kitty/mission-refactor-doc-auditor-to-scripts-first-driver-01KS2XNX): squash merge of mission` near the top. If yes: the work is on main; only bookkeeping needs cleanup. If no: this is a different failure mode; do NOT proceed; investigate.

**Step 7.2.2** — Clean the stale staged additions from the working tree:

```bash
git restore --staged scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py
git restore --staged scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py
rm -f scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py
rm -f scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py
git status
```

`git status` should now report `working tree clean` (or only the changes you intentionally want to keep).

**Step 7.2.3** — Try `spec-kitty merge` resume first. It MAY succeed for follow-on bookkeeping; if it fails with `Not currently on any branch`, fall through to 7.2.4:

```bash
spec-kitty merge --mission refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
```

If it succeeded: skip 7.2.4–7.2.6; proceed to 7.2.7.

**Step 7.2.4** — Cherry-pick the orphaned `mission_number` assignment commit onto `main`:

```bash
# Find the commit — it'll be on the mission branch, not main:
git log kitty/mission-refactor-doc-auditor-to-scripts-first-driver-01KS2XNX --oneline | grep "assign mission_number" | head -1
# Cherry-pick it:
git cherry-pick <sha-from-above>
```

**Step 7.2.5** — Remove the lane worktree:

```bash
git worktree remove .worktrees/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX-lane-a
```

If this fails with "worktree contains modified or untracked files", check the worktree first; the lane should be clean post-merge. If not, investigate before forcing.

**Step 7.2.6** — Delete the leftover branches:

```bash
git branch -D kitty/mission-refactor-doc-auditor-to-scripts-first-driver-01KS2XNX-lane-a
git branch -D kitty/mission-refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
```

**Step 7.2.7** — Manually close issue #343 (the auto-close hook didn't fire if the bookkeeping was stranded):

```bash
gh issue close 343 --repo kentonium3/kg-automation --comment "Closes via mission refactor-doc-auditor-to-scripts-first-driver-01KS2XNX. Merge commit: <sha>. Spec-kitty post-merge bookkeeping was stranded by upstream bug #1039 (git mv invariant violation); recovery applied per docs/design/architecture/baselines/cutover-log.md section 7."
```

**Step 7.2.8** — Push the cherry-picked commit + any post-rework measurement commits to origin:

```bash
git push origin main
```

### 7.3 Record the recovery in this playbook

- **Bug #1039 symptom encountered**: `<YES (A) / YES (B) / NO>`
- **Recovery sequence executed**: `<YES / NO>`
- **Manual cherry-pick SHA for mission_number commit**: `<sha or N/A>`
- **Manual #343 close timestamp (UTC)**: `<TIMESTAMP or N/A>`

---

## 8. Rollback note (C-007: fail-forward; manual restore last-resort)

**Per spec C-007: this cutover is fail-forward. There is no automatic
rollback.** If the first-tick verification in section 3 fails, the
default response is to patch the driver and redeploy via the same deploy
script — NOT to revert.

The manual-restore steps below are documented for completeness but
should only be used if the new driver is catastrophically broken AND
patching forward is not feasible within the operator's recovery
window. Treat manual restore as a last resort — it leaves the system in
a known-but-deprecated state and adds technical debt.

### 8.1 What was destroyed by the deploy

The deploy script (steps 5–6) does two destructive things:

1. **Step 5**: Deregisters `felix-doc-auditor` from openclaw (`openclaw agents delete felix-doc-auditor --force`). The openclaw registration metadata is gone; its representation lived in openclaw-gateway's state, not the repo. Recovery requires re-running the legacy registration command from `docs/runbooks/openclaw-agent-setup.md`.
2. **Step 6**: Deletes the legacy workspace directory `/data/services/openclaw/felix-doc-auditor/` (after Tier-2 backup-confirmed gate). The workspace files (IDENTITY.md, SOUL.md, AGENTS.md, helper scripts) are removed from the filesystem. They still exist in git history (last living version on `main` before the mission's deploy commit).

Both are recoverable from git history + the operator's most recent Restic backup.

### 8.2 Manual restore sequence (last resort)

**Step 8.2.1** — Stop the new driver to prevent it from picking up new work during restore:

```bash
ssh office2-claude 'systemctl --user stop felix-doc-auditor.timer'
ssh office2-claude 'systemctl --user disable felix-doc-auditor.timer'
```

**Step 8.2.2** — Restore the legacy workspace from git history.

Identify the last commit on `main` that contained the legacy workspace:

```bash
git -C /Users/kentgale/repos/kg-automation log --oneline -- scripts/openclaw/agents/felix-doc-auditor/ | head -5
```

Pick the SHA from BEFORE the mission's squash merge. Then on office2, recreate the workspace dir from that tree:

```bash
ssh office2-claude '
  mkdir -p /data/services/openclaw/felix-doc-auditor
  cd /home/claude/kg-automation
  # Checkout the legacy workspace files from the pre-cutover commit:
  git checkout <pre-cutover-sha> -- scripts/openclaw/agents/felix-doc-auditor/
  cp -r scripts/openclaw/agents/felix-doc-auditor/* /data/services/openclaw/felix-doc-auditor/
  chown -R claude:claude /data/services/openclaw/felix-doc-auditor
  # Restore HEAD to main (we only wanted the files, not the branch state):
  git checkout main -- scripts/openclaw/agents/felix-doc-auditor/ 2>/dev/null || true
'
```

(Note: if `scripts/openclaw/agents/felix-doc-auditor/` was deleted by the mission's merge commit, the `git checkout main` step will fail silently — that's fine; we only need the files to land in `/data/services/openclaw/felix-doc-auditor/`.)

**Step 8.2.3** — Re-register the agent with openclaw.

Per `docs/runbooks/openclaw-agent-setup.md`:

```bash
ssh office2-claude '
  # Inspect the AGENTS.md / openclaw.json fragment for the agent name + persona:
  cat /data/services/openclaw/felix-doc-auditor/AGENTS.md | head -30
  # Re-register:
  openclaw agents add --name felix-doc-auditor --workspace /data/services/openclaw/felix-doc-auditor
  openclaw agents list | grep felix-doc-auditor
'
```

(If `openclaw agents add` has different argument shape than shown, consult `openclaw agents add --help` on office2 and `docs/runbooks/openclaw-agent-setup.md`.)

**Step 8.2.4** — Restart openclaw to pick up the re-registered agent:

```bash
ssh office2-claude 'systemctl --user restart openclaw-gateway.service'
ssh office2-claude 'systemctl --user is-active openclaw-gateway.service'
```

**Step 8.2.5** — If office2 has a cron entry that fires the legacy agent (check `crontab -u claude -l` or the openclaw scheduler config), confirm it's still in place. The legacy agent ran via openclaw's internal scheduler, NOT via systemd — so once it's re-registered, openclaw should start ticking it again on its next scheduled fire.

**Step 8.2.6** — Verify a legacy tick succeeds:

```bash
ssh office2-claude 'tail -50 /home/claude/.openclaw/agents/felix-doc-auditor/sessions/*.jsonl | tail -10'
```

Look for new assistant turns matching the agent's normal tick pattern. If the agent is alive: rollback succeeded.

**Step 8.2.7** — Restore from Restic backup as a parallel safety net (if git-restore alone is insufficient):

```bash
ssh office2-claude '
  # Browse most recent snapshot:
  restic snapshots --tag felix-doc-auditor-workspace | tail -3
  # Restore to a staging dir, inspect, then promote:
  restic restore <snapshot-id> --target /tmp/restic-restore --include /data/services/openclaw/felix-doc-auditor
  ls /tmp/restic-restore/data/services/openclaw/felix-doc-auditor
  # If correct shape, promote:
  cp -r /tmp/restic-restore/data/services/openclaw/felix-doc-auditor/* /data/services/openclaw/felix-doc-auditor/
'
```

(Verify the Restic invocation against `docs/runbooks/restic-restore.md` if available — argument shape varies.)

### 8.3 Record the rollback (if performed)

- **Rollback executed**: `<YES / NO — REASON IF NO>`
- **Date (UTC)**: `<TIMESTAMP>`
- **Pre-cutover SHA used for git-restore**: `<sha>`
- **Restic snapshot ID used (if any)**: `<id or N/A>`
- **Legacy agent tick confirmed succeeding after restore**: `<YES / NO>`
- **Mission status after rollback**: `<rolled-back / patched-forward instead>`

### 8.4 Post-rollback follow-ups

- File a P1-bug describing the cutover failure root cause.
- Park the mission's `kitty/mission-...` branch (if still alive) for future re-deployment after the root cause is fixed.
- Update `docs/design/felix-capability-roadmap.md` to reflect the rollback (the capability area regresses to its pre-mission state until a follow-up mission lands).

---

## Appendix A: file ownership

- **Owner of this playbook**: this WP09 author + post-merge operator (Kent).
- **Mutable sections** (operator fills in during execution): all `<...>` placeholders, all checklist boxes, all section-end validation lists, the `## Cutover execution record` block, the per-outcome breakdown table in section 6.3.
- **Immutable sections** (do not edit during execution — these are the playbook itself): all command blocks, all reduction formulas, all schema descriptions.

If the playbook needs structural changes (commands wrong, steps misordered), file a follow-up issue and patch this file via a follow-on commit. Do NOT silently rewrite the playbook during execution — the audit trail depends on the playbook being stable across the execution window.

## Appendix B: when this playbook completes

The playbook is "complete" when:

- Section 6 records `PASS` (or `FAIL` with patch-forward path active).
- `docs/design/architecture/baselines/felix-doc-auditor-post-rework.json` is populated with measured values and committed to `main`.
- WP10 (architecture doc updates) is approved and merged (covers `service-inventory.json`, `topology.json`, `data-flows.json`, runbook updates).
- Issue #343 is closed with the merge commit SHA recorded.

At that point, the mission `refactor-doc-auditor-to-scripts-first-driver-01KS2XNX` is fully released and this cutover-log is frozen as the historical record.

## Appendix C: data population is deferred to execution time

This file was authored during WP09 implementation **before** the mission
was merged to main. Per Kent's WP09 scope adjustment, the live cutover
(deploy, verification, measurement, gate determination) is **deferred to
the post-merge operator**. Every `<...>` placeholder in this file marks
a value that the operator fills in inline at execution time. The
playbook itself is committed alongside the schema skeleton at
`docs/design/architecture/baselines/felix-doc-auditor-post-rework.json`
so the post-merge operator has the full operational recipe with no need
to context-switch to other docs (except the inline-referenced #1039
diagnostic — which is referenced in section 7 rather than copy-pasted to
avoid duplication).

---

## Cutover Execution Log — 2026-05-21

**Executed by**: Kent + Claude orchestrator
**Start**: 2026-05-21T15:38 ET
**Complete**: 2026-05-21T12:18 EDT (16:18 UTC, verification tick succeeded)

### Pre-flight (T040)

- ✅ Merge commit `f6558765` confirmed on `origin/main`
- ✅ 0 open `Doc audit:` issues (queue fully drained)
- ⚠️ 2 stale pending-approvals (#302, #318) from 2026-05-19 — closed with `audit-skip` before deploy per recommendation
- ✅ openclaw-gateway active
- ✅ gh auth as kg-felix-bot
- ✅ Anthropic secret readable (`/data/services/openclaw/secrets/anthropic`, 109 bytes, 0640)
- ✅ Restic backup completed today (65M repo)
- ⚠️ Drift events backlog: 10 events from 2026-05-16 to 2026-05-21, cursor=0 (old auditor never advanced) — proceeded; new driver processed all 10 in one tick

### Deploy execution (T041)

`bash /home/claude/kg-automation/scripts/office2/deploy/felix-doc-auditor-driver.sh --apply --backup-confirmed`

- ✅ Step 1: Pre-flight checks
- ✅ Step 2: Driver code pulled (git pull --rebase)
- ✅ Step 3: State dir created at `/data/services/openclaw/felix-doc-auditor-driver/`
- ✅ Step 4: systemd unit + timer installed; `daemon-reload`
- ✅ Step 5: openclaw agent `felix-doc-auditor` deregistered via `openclaw agents delete --force`
- ✅ Step 6: Legacy workspace at `/data/services/openclaw/felix-doc-auditor/` removed
- ✅ Step 7: Timer verified enabled (next fire 17:00 UTC)
- ✅ Step 8: Deploy complete

### Fix-forward operations applied during cutover (NOT in deploy script — filed as follow-ups)

1. **`anthropic` SDK install** — `python3 -m pip` not available on office2 (Debian externally-managed). Created venv at `/data/services/openclaw/felix-doc-auditor-driver/venv/` via `uv venv` + `uv pip install anthropic`. Updated systemd ExecStart to point at venv python. **Follow-up: see deploy-script enhancement issue.**
2. **Config path mismatch** — `config.toml` defaults expected `signal-to-doc-map.json`, `doc-domain-map.json`, `prompts/` at state-dir paths; deploy didn't copy them. Symlinked from repo. **Follow-up: see #361.**

### First-tick verification (T042)

Three tick attempts (cutover artifacts):

| Attempt | Time (UTC) | Status | Error | Notes |
|---|---|---|---|---|
| 1 | 16:14:57 | exit 1 | `ModuleNotFoundError: No module named 'anthropic'` | Fixed via venv install |
| 2 | 16:16:43 | partial (exit 2) | `FileNotFoundError: signal-to-doc-map.json at state dir` | Fixed via symlinks; meanwhile processed #302 #318 PAs cleanly |
| 3 | 16:18:00 | **success (exit 0)** | none | Verification tick — drained all 10 drift events |

Final tick signal (16:18:00 UTC) at `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json`:

```json
{
  "schema_version": "1.0",
  "status": "success",
  "exit_code": 0,
  "duration_seconds": 15.0,
  "tick": {
    "signals_seen": 0,
    "drift_events_consumed": 10,
    "pending_approvals_applied": [302, 318]
  },
  "errors": []
}
```

### Drift event outcomes (T043 partial)

10 drift events from cursor=0 to cursor=10 processed:
- 10 `[doc-audit]` issues filed (#351 through #360) — `P3-candidate` + `area/felix-core` labels per signal-to-doc-map.json
- Cursor advanced 0 → 10
- 0 unmapped events (all matched mappings in signal-to-doc-map.json)

These 10 issues await operator triage. Per the current architecture, they are NOT auto-processed by the driver because they don't carry the `Doc audit:` label (that's applied by the GH Actions workflow on commit). This gap is filed as a follow-on (#362).

### Pending-approval outcomes (T041 side-effect)

- #302 (audit #298) — closed with audit-skip
- #318 (audit #303) — closed with audit-skip
- Originating audits #298 and #303 — both closed

### NFR-001 post-rework measurement (T043-T045) — DEFERRED

Cannot run the full per-outcome measurement at this moment because:
- Empty tick: will measure naturally at 17:00 UTC (next scheduled fire)
- debt_only tick: requires Kent to label some [doc-audit] issues with `Doc audit:` OR for a fresh commit-triggered audit issue to land
- tier_a_apply tick: same

Post-rework JSON skeleton at `docs/design/architecture/baselines/felix-doc-auditor-post-rework.json` remains with `status: not_yet_executed` and `measurements: []`. To be populated as natural ticks accumulate over the 7-day soak window.

### Follow-on issues filed

- **#361** (P2-bug) — config defaults / deploy-time file population (the symlink band-aid)
- **#362** (P1-feature) — drift-event processing should auto-resolve where possible (the triage-burden gap)
- **#348** (P2-bug) — missing-file half-handling (from WP06 cycle 5 deferral, filed during WP06 arbiter)
- **#349** (P2-debt) — residual stale architecture view files (from WP10 arbiter)

### NFR-001 acceptance gate status

**Pending — to be evaluated during 7-day soak**. Post-rework measurement will be populated from natural ticks. Preliminary signal from this cutover: 3rd tick consumed 10 drift events in 15s wall-clock with 0 LLM tokens used (deterministic processing per spec). The pre-rework baseline showed 523K+ input tokens per EMPTY tick. Once a typical empty-queue tick is measured, the reduction is expected to massively exceed the 80% threshold.

### Rollback status

Not exercised. Fail-forward posture maintained. Two fix-forward operations applied (venv install, config symlinks). All work content from squash commit `f6558765` is preserved on main.
