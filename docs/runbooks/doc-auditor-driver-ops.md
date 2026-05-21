---
title: felix-doc-auditor driver operations
doc_type: runbook
audience: agents_and_humans
status: draft
created: 2026-05-21
last_validated: 2026-05-21
last_updated: '2026-05-21'
updated_by: '#343-refactor-doc-auditor-to-scripts-first-driver'
owners: [kgale]
---

# felix-doc-auditor driver — operations runbook

Authoritative operator reference for the scripts-first `felix-doc-auditor`
driver introduced by mission [#343 — refactor-doc-auditor-to-scripts-first-driver](https://github.com/kentonium3/kg-automation/issues/343).
Replaces the conceptual coverage in the (now-deleted) `AGENTS.md` +
runtime `SKILL.md`. The pre-#343 runbook
[`doc-auditor-ops.md`](<./doc-auditor-ops.md>) remains in place for the
historical openclaw-agent architecture but is no longer the operational
surface.

> **Status note**: this runbook describes the **post-cutover state**. The
> cutover playbook lives at
> [`docs/design/architecture/baselines/cutover-log.md`](<../design/architecture/baselines/cutover-log.md>);
> until that playbook is executed on office2 the production service is still
> the pre-#343 openclaw-agent. Plan accordingly.

---

## Overview

`felix-doc-auditor` post-#343 is a Python driver that runs hourly as a
systemd user-timer-launched oneshot on office2. Each tick is a fresh
process that:

1. Reads signals from configured signal sources in
   `scripts/doc_audit/signals/` (commit-marker, drift-event, weekly-cron,
   decision-label) and the GitHub queue.
2. Calls the Anthropic API directly via the `anthropic-python` SDK at
   exactly three judgment moments — **tier classification**,
   **debt-body generation**, and **cross-file implication detection**.
3. Mutates GitHub state via the `gh` CLI (issues, labels, comments,
   commits as `kg-felix-bot`).
4. Writes a structured tick signal to `last-tick.json` and a prose entry
   to the daily activity log.
5. Exits.

Persistent state lives on GitHub (labels, issues) and in two files on
office2 (`last-tick.json` for the most-recent-tick snapshot; the activity
log for prose history). Between ticks the driver holds nothing in
memory.

**Mission context**: [`kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/spec.md`](<../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/spec.md>)
and the `kitty-specs/.../plan.md` next to it.

---

## Architecture

| Aspect | Value |
|---|---|
| Host | office2 (Ubuntu 24.04 LTS) |
| Run-as user | `claude` |
| Schedule | `OnCalendar=hourly`, `Persistent=true` |
| Trigger | `felix-doc-auditor.timer` (user unit) → `felix-doc-auditor.service` (oneshot) |
| Entrypoint | `/usr/bin/python3 /home/claude/kg-automation/scripts/doc_audit/run.py` |
| Model | `claude-haiku-4-5` (anthropic SDK, direct) |
| Session mode | **stateless** (no openclaw session, no persistent process) |
| GitHub identity | `kg-felix-bot` (classic PAT at `/home/claude/.config/gh/hosts.yml`) |
| API key | `/data/services/openclaw/secrets/anthropic` (0600 claude:claude) |
| Tick signal | `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json` |
| Activity log | `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md` |

Source tree:

```
scripts/doc_audit/
├── run.py                          ← entrypoint
├── config.py / config.toml         ← loader + default config (signal sources, paths, model)
├── data_model.py                   ← typed records
├── prompts/
│   ├── tier_classification.prompt.md
│   ├── debt_body_generation.prompt.md
│   └── cross_file_implication.prompt.md
├── signals/                        ← signal source implementations (drift_event.py, gh_issue.py, ...)
├── judgment/                       ← LLM-call wrappers
├── routing/                        ← routing/orchestration helpers
├── output/                         ← edit-write + comment emit
├── helpers/                        ← shared utilities
└── baselines/                      ← measure-tokens.py + baseline artifacts
```

Contracts (cross-references):

- [`contracts/driver-invocation.contract.md`](<../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/driver-invocation.contract.md>) — CLI surface
- [`contracts/tick-signal.contract.md`](<../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/tick-signal.contract.md>) — shape of `last-tick.json`
- [`contracts/signal-source.contract.md`](<../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/signal-source.contract.md>) — adapter interface
- [`contracts/judgment-prompts.contract.md`](<../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/judgment-prompts.contract.md>) — LLM-call boundaries

---

## Health checks

### 30-second check

```bash
ssh office2-claude 'cat /data/services/openclaw/felix-doc-auditor-driver/last-tick.json | jq'
```

What to look for:

- `status: "success"`
- `timestamp_utc` within the last ~60 minutes (≤ 2 hours after a missed
  tick recovery)
- `exit_code: 0`
- `errors: []`

Expected shape (see [`tick-signal.contract.md`](<../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/tick-signal.contract.md>)):

```json
{
  "status": "success",
  "exit_code": 0,
  "timestamp_utc": "2026-05-21T16:00:00Z",
  "duration_seconds": 7.3,
  "tick": { "signals_seen": 0, "signals_processed": 0, "audits_filed": 0 },
  "judgment": {
    "tier_classification_calls": 0,
    "debt_body_generation_calls": 0,
    "cross_file_implication_calls": 0,
    "input_tokens": 0,
    "cache_hit_input_tokens": 0,
    "output_tokens": 0
  },
  "errors": []
}
```

If `timestamp_utc` is older than 2 hours OR `status != "success"`, jump
to [Troubleshooting](#troubleshooting).

### Force a manual tick

```bash
ssh office2-claude 'systemctl --user start --wait felix-doc-auditor.service'
```

`--wait` blocks until the oneshot completes. Then re-run the 30-second
check.

### Dry-run preview

```bash
ssh office2-claude 'python3 /home/claude/kg-automation/scripts/doc_audit/run.py --dry-run'
```

Prints what the next tick **would** do (signals it would consume, audits
it would file, decisions it would action) without filing issues,
committing, or labeling. Use this to investigate an unexpected backlog
before forcing a real tick.

### Journal grep for tick history

Each tick emits a single `SUMMARY:` line to the systemd journal,
mirroring the high-level shape of `last-tick.json`:

```
SUMMARY: status=success audits=2 debt=1 tier_a=1 drift=0 dur=7.3s tokens=in:6420(cache:4180)/out:540
```

Recent ticks:

```bash
ssh office2-claude 'journalctl --user -u felix-doc-auditor --since "24 hours ago" --no-pager | grep "^SUMMARY:"'
```

Full prose for a single tick (debugging only):

```bash
ssh office2-claude 'journalctl --user -u felix-doc-auditor --since "2 hours ago" --no-pager'
```

---

## Configuration

### Default location

`scripts/doc_audit/config.toml` (in-repo). Deployed to
`/home/claude/kg-automation/scripts/doc_audit/config.toml` via the deploy
script. Holds:

- Adapter list (which signal sources are enabled)
- Anthropic model (default `claude-haiku-4-5`)
- API-key path (default `/data/services/openclaw/secrets/anthropic`)
- Cursor file paths (per-adapter)
- Activity log directory
- `last-tick.json` path

### Override path

For testing or one-off runs, pass `--config <path>`:

```bash
ssh office2-claude 'python3 /home/claude/kg-automation/scripts/doc_audit/run.py --config /tmp/my-test-config.toml --dry-run'
```

Production always uses the default. Do **not** edit the deployed
`config.toml` directly — change in-repo and re-deploy via the deploy
script (see [Deployment](<./deployment.md>)).

---

## Prompt artifact inspection

The three judgment prompts are checked-in markdown files. Reviewing them
tells you everything the LLM sees:

```bash
ssh office2-claude 'less /home/claude/kg-automation/scripts/doc_audit/prompts/tier_classification.prompt.md'
ssh office2-claude 'less /home/claude/kg-automation/scripts/doc_audit/prompts/debt_body_generation.prompt.md'
ssh office2-claude 'less /home/claude/kg-automation/scripts/doc_audit/prompts/cross_file_implication.prompt.md'
```

Each file contains:

- **Cached boilerplate**: the rule recap + output schema. With prompt
  caching enabled, this is billed at ~10% of standard input on cache
  hits within a single tick.
- **Variable inputs**: what gets injected per call (diff hunk, candidate
  doc list, etc.).
- **Expected response schema**: what the driver's response parser
  validates against.

To see the invocation surface (which prompt is built when):

```bash
ssh office2-claude 'less /home/claude/kg-automation/scripts/doc_audit/judgment/tier_classification.py'
```

Editing prompts: change in-repo, re-deploy, force a tick, watch
`last-tick.json` + `SUMMARY:` for token-usage shifts. Boilerplate
changes invalidate the prompt cache for the first post-deploy tick.

---

## Backlog recovery

When the GitHub queue is unexpectedly deep (e.g., post-outage, post-cron-gap):

```bash
# 1. Confirm signals exist
ssh office2-claude 'gh issue list --label "Doc audit:" --state open --limit 20 --json number,title'

# 2. Force a tick — the driver processes the FULL queue per tick (per spec Q3=B)
ssh office2-claude 'systemctl --user start --wait felix-doc-auditor.service'

# 3. Verify drain
ssh office2-claude 'gh issue list --label "Doc audit:" --state open'

# 4. Check tick result for partial-success or errors
ssh office2-claude 'cat /data/services/openclaw/felix-doc-auditor-driver/last-tick.json | jq ".status, .errors"'
```

Partial success is expected when one item in the queue fails (e.g., a
malformed audit issue). `last-tick.json` records the failure, the
healthy items still drain, and the next hourly tick retries the failed
item. If the queue still doesn't drain after two ticks, see
[Troubleshooting → Stuck audit](#troubleshooting).

---

## Stuck lock recovery

Pre-#343 the operator had to manually clear stuck `status:in-progress`
locks. Post-#343 the driver recovers them automatically per spec FR-014:
on each tick the driver enumerates issues carrying `status:in-progress`,
checks whether the holder is the current driver process (it never is —
the driver is stateless), and clears the orphaned lock.

If a lock persists across two consecutive ticks:

```bash
# Confirm the auditor saw it
ssh office2-claude 'cat /data/services/openclaw/felix-doc-auditor-driver/last-tick.json | jq ".errors"'

# If confirmed orphan, clear manually
gh issue edit <number> --repo kentonium3/kg-automation --remove-label "status:in-progress"
```

Note: an issue with a referenced `audit-pending-approval` issue and no
decision label is the **expected** Level-1 wait state, not a stuck lock.
The driver's stale-lock detection follows the SKILL.md §8.7 rules
inherited from the pre-#343 implementation.

---

## Pending-approval workflow

The driver still surfaces Tier-B proposed edits as
`audit-pending-approval` issues. The operator decides asynchronously by
applying ONE of:

| Decision label | Driver action on next tick |
|---|---|
| `audit-approve` | Apply edits, commit as `kg-felix-bot`, close both audit + pending-approval. |
| `audit-reject` | Demote proposals to docs-debt issues, close both. |
| `audit-skip` | Close both with a skip note (no edits, no debt). |

**Actor verification**: the driver refuses to process a decision label
applied by `kg-felix-bot` itself (the bot's own identity). This is the
inherited §8.6 safeguard — preserved post-#343 inside
`scripts/doc_audit/run.py` (see the `_get_decision_actor` function and
its caller in the pending-approval execution path). If a decision is
being silently ignored, this is the first thing to check:

```bash
# Inspect who applied the label
gh issue view <number> --repo kentonium3/kg-automation --json events --jq '.events[] | select(.label.name == "audit-approve")'
```

If the actor is `kg-felix-bot`, remove the label and re-apply as your
operator identity (`kentonium3`).

---

## Cost / token usage

Each tick records token usage in `last-tick.json` under `judgment`:

```json
"judgment": {
  "tier_classification_calls": 3,
  "debt_body_generation_calls": 1,
  "cross_file_implication_calls": 0,
  "input_tokens": 6420,
  "cache_hit_input_tokens": 4180,
  "output_tokens": 540
}
```

For monthly cost estimation:
`(input_tokens + output_tokens) × 24 ticks/day × 30 days`. With prompt
caching, `cache_hit_input_tokens` is billed at 10% of the standard
input rate.

**Baselines**:

- Pre-rework: [`docs/design/architecture/baselines/felix-doc-auditor-pre-rework.json`](<../design/architecture/baselines/felix-doc-auditor-pre-rework.json>)
- Post-rework: [`docs/design/architecture/baselines/felix-doc-auditor-post-rework.json`](<../design/architecture/baselines/felix-doc-auditor-post-rework.json>)
- Methodology: [`docs/design/architecture/baselines/README.md`](<../design/architecture/baselines/README.md>)

Reduction target: ≥80% versus the pre-rework baseline (spec NFR-001).
The post-rework baseline is finalised on the first 14 days of
production ticks following cutover.

---

## Troubleshooting

### Tick failure

`status != "success"` or non-empty `errors` in `last-tick.json`.

```bash
# Read the structured error list
ssh office2-claude 'cat /data/services/openclaw/felix-doc-auditor-driver/last-tick.json | jq ".errors"'

# Read the full prose journal for the most recent tick
ssh office2-claude 'journalctl --user -u felix-doc-auditor --since "2 hours ago" --no-pager'
```

Common failure classes:

- `AnthropicRateLimitError` / 5xx → next tick retries automatically.
  Spec NFR-002 requires the driver to maintain ≥95% success rate
  across rolling 24h; one transient API failure is normal.
- `GhCliError` → check `gh auth status` on office2, ensure
  `kg-felix-bot` PAT hasn't been revoked.
- `ConfigLoadError` → the deployed `config.toml` is malformed.
  Restore via `git checkout` + redeploy.
- `JudgmentResponseParseError` → the LLM returned something the response
  parser can't handle. Re-run with `--dry-run` to see the raw response.
  If reproducible, file a P2-bug — do **not** edit the prompt blindly.

### Stale signal

`timestamp_utc` in `last-tick.json` older than 2 hours.

```bash
# Is the timer enabled and active?
ssh office2-claude 'systemctl --user list-timers felix-doc-auditor.timer --no-pager'
ssh office2-claude 'systemctl --user status felix-doc-auditor.service'

# Is the timer actually firing?
ssh office2-claude 'journalctl --user -u felix-doc-auditor.timer --since "24 hours ago" --no-pager'
```

If the timer is dead, restart it:

```bash
ssh office2-claude 'systemctl --user daemon-reload && systemctl --user restart felix-doc-auditor.timer'
```

If the timer is alive but the service never finishes, force a tick with
`--wait` and watch the journal in another terminal.

### Cost spike

`input_tokens` or `output_tokens` in recent ticks far higher than the
post-rework baseline.

Likely causes:

1. **Cache invalidation**: a prompt boilerplate change invalidated the
   cache. Expected for the first tick after any prompt change. Should
   recover on the next tick.
2. **Queue size spike**: more audits in the queue → more
   tier-classification calls. Check `tick.signals_processed` in
   `last-tick.json`. This is correct behaviour.
3. **Loop bug**: a single audit is re-classified repeatedly. Inspect
   `judgment.tier_classification_calls` against the queue size and
   `last-tick.json` activity log — if calls ≫ queue size, file a P2-bug.

Re-baseline annually (see [Re-baselining cadence](#re-baselining-cadence)).

### API outage

`errors` mentions Anthropic `5xx` or rate-limit. The driver retries
automatically next tick. If the outage persists multiple hours, the
`SUMMARY:` line will show `status=partial` or `status=failure` ticks —
the #327 alerting consumer is the long-term route to operator
attention. Until #327 lands, manual journal grep is the safety net.

---

## Re-baselining cadence

Recapture the post-rework baseline annually, or after any of the
following:

- Prompt boilerplate change ≥ 10% (measured by character count)
- Adapter change (signal source added/removed)
- Model upgrade (e.g., `claude-haiku-4-5` → `claude-haiku-5`)
- Sustained queue-size shift (e.g., post-merge cron rate change)

Procedure:

```bash
# 1. Capture token usage from the last 14 days of ticks
ssh office2-claude 'python3 /home/claude/kg-automation/scripts/doc_audit/baselines/measure-tokens.py --window 14d --out /tmp/baseline.json'

# 2. Pull back to repo
scp office2-claude:/tmp/baseline.json docs/design/architecture/baselines/felix-doc-auditor-post-rework-$(date +%Y-%m-%d).json
```

See [`baselines/README.md`](<../design/architecture/baselines/README.md>)
for the full methodology and retention policy.

---

## What changed vs the old openclaw-agent auditor

| Aspect | Pre-#343 | Post-#343 |
|---|---|---|
| Entrypoint | `openclaw agent --agent felix-doc-auditor ...` | `python3 scripts/doc_audit/run.py` |
| Process model | openclaw gateway dispatches an LLM session | Stateless Python oneshot per tick |
| State between ticks | Persistent openclaw session (accumulated until context overflow per [#342](https://github.com/kentonium3/kg-automation/issues/342)) | None — GitHub + last-tick.json + activity log only |
| Procedure source | `AGENTS.md` + `SKILL.md` (~57 KB) interpreted by LLM | Python code in `scripts/doc_audit/` |
| LLM model | claude-haiku-4-5 via openclaw gateway | claude-haiku-4-5 via anthropic SDK directly |
| LLM calls per tick | 1 huge call interpreting the full procedure | 0-N small calls per judgment moment |
| Per-tick cost | ~20 K input tokens regardless of work done | ~1-2 K input per judgment moment, only when judgment is required |
| Health signal | Free-text in journal + activity log | Structured `last-tick.json` + journal `SUMMARY:` line |
| Failure visibility | Silent (per [#342](https://github.com/kentonium3/kg-automation/issues/342), 52+ hours undetected) | Structured signal; ≥95% NFR-002 floor; [#327](https://github.com/kentonium3/kg-automation/issues/327) alerting consumes the signal |
| Workspace files | `/data/services/openclaw/felix-doc-auditor/` (deleted at cutover) | None — the driver has no workspace |
| Stale-lock recovery | Manual operator action | Automatic per tick (FR-014) |
| Pending-approval flow | Unchanged (operator label → next tick reads + actions) | Unchanged |
| Identity | `kg-felix-bot` | `kg-felix-bot` (unchanged) |

---

## Cross-references

- **Mission spec**: [`kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/spec.md`](<../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/spec.md>)
- **Plan**: [`kitty-specs/.../plan.md`](<../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/plan.md>)
- **Research decisions**: [`kitty-specs/.../research.md`](<../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/research.md>)
- **Quickstart (developer-facing)**: [`kitty-specs/.../quickstart.md`](<../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/quickstart.md>)
- **Tick-signal contract**: [`contracts/tick-signal.contract.md`](<../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/tick-signal.contract.md>)
- **Signal-source contract**: [`contracts/signal-source.contract.md`](<../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/signal-source.contract.md>)
- **Judgment-prompt contract**: [`contracts/judgment-prompts.contract.md`](<../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/judgment-prompts.contract.md>)
- **Driver-invocation contract**: [`contracts/driver-invocation.contract.md`](<../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/driver-invocation.contract.md>)
- **Baselines**: [`docs/design/architecture/baselines/`](<../design/architecture/baselines/>)
- **Cutover playbook**: [`docs/design/architecture/baselines/cutover-log.md`](<../design/architecture/baselines/cutover-log.md>)
- **Pre-#343 runbook (historical)**: [`docs/runbooks/doc-auditor-ops.md`](<./doc-auditor-ops.md>)
- **Inherited SKILL.md (informative, not loaded at runtime)**: [`scripts/openclaw/skills/doc-audit/SKILL.md`](<../../scripts/openclaw/skills/doc-audit/SKILL.md>)
- **Future alerting consumer**: [#327](https://github.com/kentonium3/kg-automation/issues/327)
- **Identity**: [`docs/constitution/AGENT-REGISTRY.md#service-accounts`](<../constitution/AGENT-REGISTRY.md#service-accounts>); [`kg-felix-bot-pat`](<../design/architecture/data/credential-manifest.json>) in credential-manifest.json
