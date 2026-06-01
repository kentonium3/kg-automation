---
title: felix-doc-auditor driver operations
doc_type: runbook
audience: agents_and_humans
status: approved
created: 2026-05-21
last_validated: 2026-05-31
last_updated: '2026-05-31'
updated_by: '#400 (initial); 2026-05-31 suspension reflected'
version: v1.4
owners: [kgale]
---

# felix-doc-auditor driver — operations runbook

> ⏸ **SUSPENDED INDEFINITELY — 2026-05-26**. The post-#343 driver is implemented
> and tested. Two-layer suspension is in place: `felix-doc-auditor.timer` is
> `disabled`, AND `[drift_interpretation].enabled = false` +
> `[audit_interpretation].enabled = false` in
> `scripts/doc_audit/config.toml` (commit `d46a9ead`). The GitHub Actions
> workflows `Doc Audit Trigger` and `Doc Audit Weekly` are also
> `disabled_manually`. The cutover playbook HAS executed; the production
> service IS the post-#343 driver — just not currently scheduled.
> Re-enablement requires the cost-control work tracked under
> [#137](https://github.com/kentonium3/kg-automation/issues/137) to land
> plus an explicit operator decision. This runbook is retained as the
> authoritative reference for when re-enablement occurs.

Authoritative operator reference for the scripts-first `felix-doc-auditor`
driver introduced by mission [#343 — refactor-doc-auditor-to-scripts-first-driver](https://github.com/kentonium3/kg-automation/issues/343).
Replaces the conceptual coverage in the (now-deleted) `AGENTS.md` +
runtime `SKILL.md`. The pre-#343 runbook
[`doc-auditor-ops.md`](<./doc-auditor-ops.md>) remains in place for the
historical openclaw-agent architecture but is no longer the operational
surface.

---

## Overview

`felix-doc-auditor` post-#343 is a Python driver that runs hourly as a
systemd user-timer-launched oneshot on office2. Each tick is a fresh
process that:

1. Reads signals from configured signal sources in
   `scripts/doc_audit/signals/` (commit-marker, drift-event, weekly-cron,
   decision-label) and the GitHub queue.
2. Calls the Anthropic API directly via the `anthropic-python` SDK at
   judgment moments. **Post-#400 the surface is five moments**:
   **Moment 0 has TWO surfaces** — **drift interpretation** (per mapped
   drift event; classifies PROPOSED_EDIT / JUDGMENT_REQUIRED /
   NO_CHANGE_NEEDED before any GitHub issue is filed; #362) and
   **audit interpretation** (per in-scope doc within a commit-derived
   `Doc audit:` issue; same three-verdict vocabulary; #400). Both run
   only when their respective `[*_interpretation].enabled` flag is
   true. **Moment 1 — tier classification** consumes PROPOSED_EDIT
   verdicts from either Moment 0 surface. Moments 2 and 3 —
   **debt-body generation** and **cross-file implication detection**
   (unchanged from #343).
3. Mutates GitHub state via the `gh` CLI (issues, labels, comments,
   commits as `kg-felix-bot`).
4. Writes a structured tick signal to `last-tick.json` and a prose entry
   to the daily activity log. Per-drift-event outcomes additionally
   land in the append-only audit ledger at
   `/data/services/security-monitor/logs/drift-events-ledger.jsonl`
   (one row per event). Post-#400, per-doc commit-audit outcomes land
   in a separate ledger at
   `/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl`
   (one row per (audit_issue, doc_path)). Both ledgers back the NFR-001
   operator-triage-rate metric for their respective signal class.
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
to [Troubleshooting](<#troubleshooting>).

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

## Moment 0 — drift interpretation (#362, cron-path corrected by #391)

Introduced by mission [#362 — drift-event-auto-resolution](https://github.com/kentonium3/kg-automation/issues/362).
Cutover playbook lives in the mission quickstart:
[`kitty-specs/drift-event-auto-resolution-01KS8J32/quickstart.md`](<../../kitty-specs/drift-event-auto-resolution-01KS8J32/quickstart.md>).

**Mission #391 correction**: the cron-path Moment 0 invocation site is
**`scripts/doc_audit/signals/drift_event.py::DriftEventSignalSource.commit()`**,
which delegates to the shared helper
**`scripts/doc_audit/routing/drift_moment0.py::route_drift_event()`**.
Earlier drafts of this runbook (v1.1) misnamed
`scripts/doc_audit/helpers/handle_drift_events.py::process_events()` as
the cron entry point. That module is the **library/CLI surface for
operator replay only** — `python3 -m doc_audit.helpers.handle_drift_events`
is for manual re-runs and one-off invocations. The cron service does NOT
use this entry point. Both surfaces delegate to the same
`routing/drift_moment0.py::route_drift_event()` helper so behavior is
identical bit-for-bit, regardless of how a drift event entered the
pipeline. Mission spec:
[`kitty-specs/moment0-integration-fix-01KS8XRM/spec.md`](<../../kitty-specs/moment0-integration-fix-01KS8XRM/spec.md>).

**Trigger**: every mapped drift event when `[drift_interpretation].enabled = true`
in `scripts/doc_audit/config.toml`. When `enabled = false`, the pipeline
behaves identically to the pre-#362 deterministic-only driver
(FR-013) — drift events file `[doc-audit]` issues unconditionally for
operator triage.

**LLM call**: Haiku 4.5 (`claude-haiku-4-5-20251001`) via the shared
`JudgmentClient`. Cache-aware prompt — stable system portion (≥80% of
tokens) marked `cache_control: ephemeral`, dynamic
`DriftInterpretationContext` (event metadata + diff + mapping rationale
+ current contents of each `doc_target`) in the user portion. Matches
the existing `tier_classification.py` pattern (C-005).

**Three verdicts**:

| Verdict | Behavior |
|---|---|
| `PROPOSED_EDIT` | A specific edit to a specific doc path with `current_value` + `proposed_value` |
| `JUDGMENT_REQUIRED` | The LLM cannot determine the edit; surfaces a specific question for the operator |
| `NO_CHANGE_NEEDED` | The drift doesn't imply a doc change (e.g., field not tracked in any target doc) |

**Confidence threshold**: `0.80` (configurable via
`[drift_interpretation].confidence_threshold`). PROPOSED_EDIT or
NO_CHANGE_NEEDED returned at confidence < 0.80 are demoted at the
helper boundary to JUDGMENT_REQUIRED, with the proposed edit / rationale
folded into the issue body. PROPOSED_EDIT at confidence ≥ 0.80 is
translated to a `ProposedEdit` (`change_type='drift_derived'`) and
routed through the existing `tier_classification` surface (Moment 1);
that classifier's conservative rules ultimately decide Tier A / Tier B /
judgment.

**Retry policy**: 30s / 60s / 120s exponential backoff on Anthropic API
errors, malformed JSON, or schema violations (FR-008). On exhaustion,
the system falls back to the pre-#362 `[doc-audit]` issue-filing path
with retry diagnostics in the issue body (FR-009).

**Defense-in-depth**: even if the LLM returns a valid PROPOSED_EDIT on
a guardrailed doc path (per SKILL.md §4.3), `tier_classification` will
short-circuit to `judgment`. The Moment 0 verdict is never a direct
auto-commit authority — it only feeds the existing Moment 1 surface.

### Ledger queries

Every processed drift event lands one row in
`/data/services/security-monitor/logs/drift-events-ledger.jsonl` (data-model
E3 — `event_id`, `verdict`, `confidence`, `outcome ∈ {auto_committed,
pr_filed, issue_filed, auto_closed, retry_exhausted}`, `doc_paths`,
`retry_count`, `latency_ms`, etc.). Read-only CLI subcommands:

```bash
# Triage rate (NFR-001 metric)
python3 -m scripts.doc_audit.output.drift_ledger triage-rate --days 7
```

```bash
# Outcome breakdown
python3 -m scripts.doc_audit.output.drift_ledger summary --days 7
```

```bash
# Recent entries
python3 -m scripts.doc_audit.output.drift_ledger tail
```

`triage-rate` computes `count(verdict=JUDGMENT_REQUIRED) / count(*)`
over the trailing N-day window — the success criterion is ≤30%
sustained over 7 days post-deploy. `summary` prints verdict counts +
outcome breakdown. `tail` shows the last 10 ledger entries as
pretty-printed JSON. Flags: `--ledger-path` (override the default
path), `--days N` (window for summary/triage-rate, default 7).

All three subcommands tail from end-of-file forward, so the cost is
bounded by window size, not by ledger growth.

### Rollback

The Moment 0 layer is gated by a single config flag — flipping it
reverts to pre-#362 deterministic-only behavior on the next tick
(≤60 seconds per NFR-007). No code revert required for the common
case:

```bash
# Disable Moment 0 (cuts back to pre-#362 behavior)
ssh office2-claude 'sed -i "s/^enabled = true$/enabled = false/" ~/kg-automation/scripts/doc_audit/config.toml'
```

Verify:

```bash
ssh office2-claude 'grep -A1 "\[drift_interpretation\]" ~/kg-automation/scripts/doc_audit/config.toml'
```

Force a tick to confirm the new pipeline is skipped:

```bash
ssh office2-claude 'systemctl --user start --wait felix-doc-auditor.service'
```

```bash
ssh office2-claude 'journalctl --user -u felix-doc-auditor.service --since "1 minute ago" --no-pager | grep -i "drift_interpretation"'
```

Expected log entries indicate the pipeline skipped Moment 0 and used
the pre-#362 deterministic-only path. The ledger file is preserved —
events already auto-resolved (Tier A commits, Tier B PRs, auto-closed
events) remain in their final state. Re-enabling later is just
flipping the flag back to `true` and waiting for the next tick.

For a code-level revert (rare; the config flag is the primary lever),
see the mission quickstart §7 Rollback procedure.

---

## Moment 0 — commit-derived audit interpretation (#400)

Introduced by mission [#400 — audit-interpretation-moment0](https://github.com/kentonium3/issues/400).
Mission spec at
[`kitty-specs/audit-interpretation-moment0-01KSBGBS/spec.md`](<../../kitty-specs/audit-interpretation-moment0-01KSBGBS/spec.md>).
Applies the #362/#391 Moment 0 architecture to commit-derived
`Doc audit:` issues. Structural twin of the drift Moment 0 section
above — same JudgmentClient, same cache-aware prompt pattern, same
defense-in-depth schema validation, same ≥0.80 confidence threshold.

**Trigger**: every `Doc audit:` issue's no-proposals path when
`[audit_interpretation].enabled = true` in
`scripts/doc_audit/config.toml`. Specifically: `handle_audit_routing.py`
first runs the existing deterministic pattern-matching path; if it
returns zero auto-applyable proposals, the no-proposals branch invokes
`audit_interpretation.interpret_audit(client, context)`. When
`[audit_interpretation].enabled = false`, the no-proposals branch
falls back to the pre-#400 behavior (release the `status:in-progress`
lock + post a "no automatable edits detected" comment for operator
triage). The deterministic-proposals path (when proposals IS non-empty)
is unaffected.

**LLM call**: Haiku 4.5 (`claude-haiku-4-5-20251001`) via the shared
`JudgmentClient`. Cache-aware prompt — stable system portion (≥80% of
tokens) marked `cache_control: ephemeral`, dynamic
`AuditInterpretationContext` (audit metadata + commit SHA + diff +
in-scope doc paths + per-doc current contents) in the user portion.
**One LLM call PER in-scope doc** (per spec D2 — per-doc verdicts
preserve granularity: an audit can be "partially clean").

**Three verdicts**:

| Verdict | Behavior |
|---|---|
| `PROPOSED_EDIT` | A specific edit to a specific in-scope doc path with `current_value` + `proposed_value` |
| `JUDGMENT_REQUIRED` | The LLM cannot determine the edit; surfaces a specific question for the operator |
| `NO_CHANGE_NEEDED` | The commit doesn't imply a change to this doc |

**Confidence threshold**: `0.80` (configurable via
`[audit_interpretation].confidence_threshold`). PROPOSED_EDIT or
NO_CHANGE_NEEDED returned at confidence < 0.80 are demoted at the
helper boundary to JUDGMENT_REQUIRED, with the proposed edit /
rationale folded into the consolidated comment. PROPOSED_EDIT at
confidence ≥ 0.80 is translated to a `ProposedEdit` and routed through
the existing `tier_classification` surface (Moment 1) — that
classifier's conservative rules ultimately decide Tier A / Tier B /
judgment. PROPOSED_EDIT proposing an edit to a path NOT in the audit's
in-scope list is a semantic violation → demoted to JUDGMENT_REQUIRED.

**Per-doc isolation + retry policy**: 30s / 60s / 120s exponential
backoff per doc on Anthropic API errors, malformed JSON, or schema
violations. **Retry exhaustion on doc N does NOT prevent docs N±1
from being evaluated** — the helper emits a synthetic JUDGMENT_REQUIRED
verdict (`confidence=0.0`, `rationale="LLM retry exhausted"`) for the
failed doc and continues. Catastrophic per-audit failures (e.g., the
audit body's in-scope doc list is malformed) fall back to the pre-#400
no-proposals path (lock release + "no automatable edits" comment).

**Consolidated comment for JUDGMENT_REQUIRED**: per spec research D3,
all JUDGMENT_REQUIRED verdicts for a single audit are folded into ONE
comment listing each doc + its specific question (avoids comment
noise; operator reads one comment to see all questions).

**Auto-close rule (FR-008)**: when ALL in-scope docs return
NO_CHANGE_NEEDED at confidence ≥0.80, the audit issue is auto-closed
with a summary comment listing the docs as "clean per LLM check". If
ANY doc is JUDGMENT_REQUIRED (after demotion), the audit stays open
(FR-009).

**Weekly audits**: skip Moment 0 entirely (no triggering SHA → empty
diff). Existing weekly behavior preserved (spec C-006).

**Defense-in-depth**: even if the LLM returns a valid PROPOSED_EDIT on
a guardrailed doc path, `tier_classification` will short-circuit to
`judgment`. The audit Moment 0 verdict is never a direct auto-commit
authority — it only feeds the existing Moment 1 surface.

### Ledger queries

Every processed in-scope doc lands one row in
`/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl`
(schema mirrors `drift_ledger` with two adaptations per spec D1/E3:
`audit_issue:int` replaces `event_id`/`baseline`/`mapping_id`, and
`judgment_required_posted` replaces drift's `issue_filed` since audit
appends a comment to the EXISTING audit issue rather than creating a
new one). Read-only CLI subcommands:

```bash
# Triage rate (NFR-001 metric)
python3 -m scripts.doc_audit.output.audit_ledger triage-rate --days 7
```

```bash
# Outcome breakdown
python3 -m scripts.doc_audit.output.audit_ledger summary --days 7
```

```bash
# Recent entries
python3 -m scripts.doc_audit.output.audit_ledger tail
```

Flags: `--ledger-path` (override the default path), `--days N`
(window for summary/triage-rate, default 7). All three subcommands
tail from end-of-file forward, so the cost is bounded by window size,
not by ledger growth.

### Rollback

Same lever pattern as drift Moment 0: a single config flag flip
reverts to the pre-#400 no-proposals path (lock release + "no
automatable edits" comment) on the next tick (≤60 seconds). No code
revert required:

```bash
ssh office2-claude 'sed -i "s/^enabled = true$/enabled = false/" ~/kg-automation/scripts/doc_audit/config.toml'
```

Note: this also flips the drift `[drift_interpretation]` block if both
are `enabled = true` (the `sed` matches both). To rollback ONLY the
audit Moment 0 path, edit the file directly to flip only the
`[audit_interpretation]` block's `enabled` flag.

Verify:

```bash
ssh office2-claude 'grep -A6 "\[audit_interpretation\]" ~/kg-automation/scripts/doc_audit/config.toml'
```

Force a tick to confirm the new pipeline is skipped:

```bash
ssh office2-claude 'systemctl --user start --wait felix-doc-auditor.service'
```

```bash
ssh office2-claude 'gh issue view <recent-doc-audit-issue> --comments'
```

Expected: the audit issue receives the pre-#400 "no automatable edits
detected" comment from `handle_audit_routing.py` (today-merged
behavior) and the `status:in-progress` lock is released. The ledger
file is preserved — entries already written (Tier A commits, Tier B
pending-approval issues, auto-closed audits) remain in their final
state.

For a code-level revert (rare; the config flag is the primary lever),
see the mission spec at
[`kitty-specs/audit-interpretation-moment0-01KSBGBS/spec.md`](<../../kitty-specs/audit-interpretation-moment0-01KSBGBS/spec.md>).

### Cutover replay for stuck audits (one-time, post-#400 deploy)

After #400 deploys, the 11 currently-stuck audits filed before WP02
landed are eligible for re-processing through the new Moment 0 path.
At WP02 merge time these were: #350, #363, #364, #365, #373, #377,
#395, #396, #397, #398, #399. Each one currently sits with a generic
14-item triage checklist and no actionable LLM analysis — once #400
ships, the next driver tick will re-evaluate each one's in-scope docs
through `audit_interpretation`.

To trigger:

1. Pull on office2:

   ```bash
   ssh office2-claude 'cd ~/kg-automation && git pull origin main'
   ```

2. Verify config:

   ```bash
   ssh office2-claude 'grep -A6 audit_interpretation ~/kg-automation/scripts/doc_audit/config.toml'
   ```

   Expected: `enabled = true` and the
   `/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl`
   ledger path is present.

3. Trigger a manual tick:

   ```bash
   ssh office2-claude 'systemctl --user start felix-doc-auditor.service'
   ```

4. The driver picks up each `doc-audit`-labeled audit, runs the
   deterministic-pattern path (no proposals expected for these
   already-triaged audits), then falls through to the NEW
   `audit_interpretation` path. Each in-scope doc receives one LLM
   call.

5. Verify outcomes by querying the audit ledger:

   ```bash
   ssh office2-claude 'cat /data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl | jq -c "{audit_issue, doc_path, verdict, outcome}"'
   ```

6. Expected mix:

   - Some audits auto-close (all in-scope docs return NO_CHANGE_NEEDED
     at confidence ≥0.80)
   - Some get JUDGMENT_REQUIRED consolidated comments (one comment per
     audit listing all per-doc questions)
   - Some get Tier A auto-commits or Tier B pending-approval issues
     (PROPOSED_EDIT at confidence ≥0.80 routed through
     `tier_classification`)

7. (Optional) Query the triage-rate after the tick completes:

   ```bash
   ssh office2-claude 'python3 -m scripts.doc_audit.output.audit_ledger triage-rate --days 1'
   ```

   Per NFR-001 the 7-day rolling target is ≤30%. The cutover replay is
   a one-time event with a non-representative mix; use the 7-day
   rolling window for the steady-state metric.

This is a one-time post-deploy operation. After the cutover tick
completes, subsequent commit-derived audits flow through the Moment 0
path naturally per the trigger described above. No sentinel marker or
helper script is needed — the existing audits are processed by the
same code path as new audits.

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
[Troubleshooting → Stuck audit](<#troubleshooting>).

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

Re-baseline annually (see [Re-baselining cadence](<#re-baselining-cadence>)).

### API outage

`errors` mentions Anthropic `5xx` or rate-limit. The driver retries
automatically next tick. If the outage persists multiple hours, the
`SUMMARY:` line will show `status=partial` or `status=failure` ticks —
the #327 alerting consumer is the long-term route to operator
attention. Until #327 lands, manual journal grep is the safety net.

### Debug capture for drift_interpretation

`DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` (exact match) enables raw-response logging
at each `_RetrySchemaError` raise site in `scripts/doc_audit/judgment/drift_interpretation.py`.
Off by default — enable only for diagnostic capture, never in steady-state production.
See [`../diagnostics/drift-interpretation-payload-shape.md`](<../diagnostics/drift-interpretation-payload-shape.md>)
for the captured-payload analysis (mission #404 follow-up).

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
- **Moment 0 mission spec (#362)**: [`kitty-specs/drift-event-auto-resolution-01KS8J32/spec.md`](<../../kitty-specs/drift-event-auto-resolution-01KS8J32/spec.md>)
- **Moment 0 mission plan (#362)**: [`kitty-specs/drift-event-auto-resolution-01KS8J32/plan.md`](<../../kitty-specs/drift-event-auto-resolution-01KS8J32/plan.md>)
- **Moment 0 data model (#362)**: [`kitty-specs/drift-event-auto-resolution-01KS8J32/data-model.md`](<../../kitty-specs/drift-event-auto-resolution-01KS8J32/data-model.md>)
- **Moment 0 CLI contract (#362)**: [`kitty-specs/drift-event-auto-resolution-01KS8J32/contracts/cli.md`](<../../kitty-specs/drift-event-auto-resolution-01KS8J32/contracts/cli.md>)
- **Moment 0 ledger schema (#362)**: [`kitty-specs/drift-event-auto-resolution-01KS8J32/contracts/ledger-schema.md`](<../../kitty-specs/drift-event-auto-resolution-01KS8J32/contracts/ledger-schema.md>)
- **Moment 0 cutover quickstart (#362)**: [`kitty-specs/drift-event-auto-resolution-01KS8J32/quickstart.md`](<../../kitty-specs/drift-event-auto-resolution-01KS8J32/quickstart.md>)
- **Moment 0 integration-fix mission spec (#391)**: [`kitty-specs/moment0-integration-fix-01KS8XRM/spec.md`](<../../kitty-specs/moment0-integration-fix-01KS8XRM/spec.md>) — corrects the cron-path invocation site to `signals/drift_event.py` + `routing/drift_moment0.py`; adds `cleanup_391.py` for the 13 broken-pipeline artifact issues (#378-#390)
- **Audit Moment 0 mission spec (#400)**: [`kitty-specs/audit-interpretation-moment0-01KSBGBS/spec.md`](<../../kitty-specs/audit-interpretation-moment0-01KSBGBS/spec.md>) — applies the #362/#391 Moment 0 architecture to commit-derived `Doc audit:` issues; structural twin of `drift_interpretation` adapted for per-doc verdicts within a single audit
- **Audit Moment 0 mission plan (#400)**: [`kitty-specs/audit-interpretation-moment0-01KSBGBS/plan.md`](<../../kitty-specs/audit-interpretation-moment0-01KSBGBS/plan.md>)
- **Audit Moment 0 data model (#400)**: [`kitty-specs/audit-interpretation-moment0-01KSBGBS/data-model.md`](<../../kitty-specs/audit-interpretation-moment0-01KSBGBS/data-model.md>)
