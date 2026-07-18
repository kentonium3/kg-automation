---
title: Task-Intake Validation Loop Operations
doc_type: runbook
audience: agents_and_humans
status: approved
level: 2
owners: [kent]
last_validated: '2026-07-17'
updated_by: 'task-intake-validation-loop-01KXS06W (#749; folds in #750)'
version: '1.0.0'
---

# Task-Intake Validation Loop Operations

## Overview

The **task-intake validation loop** enforces the #714 Tier-1 intake standard:
every task that leaves the Vikunja **Inbox** into a working project must carry a
**working project (≠ Inbox) + a friction label (`f:1-3`) + an Eisenhower quadrant
(`q:*`)**. Nothing enforced this before #749, so the friction/Eisenhower taxonomy
the #714 reset created decayed into inconsistency and Inbox became a permanent
dumping ground.

The loop **rides the existing inbox-processing crons** (see
[`inbox-ops.md`](<./inbox-ops.md>)) — there is no separate schedule. After each
inbox tick's `route_and_finalize`, `felix-admin-capture` runs
`scripts/intake/scan_inbox.py`, which scans the Inbox for **not-done,
Tier-1-incomplete** tasks and emits **one batched WhatsApp digest** numbering them
with their missing fields. Kent replies in **compact shorthand**; the **main** DM
agent correlates the reply to the right digest and runs
`scripts/intake/apply_reply.py`, which applies the project + labels + applicable
Tier-2 through the **kent** Vikunja token.

The design source of truth for the standard is
[`docs/design/vikunja-configuration-design.md`](<../design/vikunja-configuration-design.md>)
§Required Fields. The machine-readable records are the `inbox-processing` service
in [`service-inventory.json`](<../design/architecture/data/service-inventory.json>)
(`intake_validation_loop`, `config_files[*]`, `state_files[*]`) and the
`intake-validation-loop` flow in
[`data-flows.json`](<../design/architecture/data/data-flows.json>).

**Deterministic per Directive 6.** Scan, shorthand parse, token resolution, and
apply are 100% deterministic helpers — **no LLM** on that path. The LLM is a
narrow fallback the main agent invokes **only** for a token the parser cannot
resolve against the seam/alias table, constrained to proposing a canonical name
that the helper re-resolves through the #748 seam (never a raw id or free-form
value).

### #750 closure

felix-bot **403s** when it tries to attach a kent-owned label. The loop's apply
step writes **only** through the kent token (`vikunja-api-kent`, the #715
two-token model); felix-bot is used **read-only** for the scan. There is no
felix-bot-label-attach path in the loop — that closes #750 (SC-008).

## Architecture at a glance

| Item | Value |
|---|---|
| Host | office2 (Ubuntu 24.04 LTS) |
| Cadence | Rides the inbox crons — `inbox-7am` / `inbox-noon` / `inbox-5pm` / `inbox-10pm` ET (no separate schedule) |
| Scan helper | `scripts/intake/scan_inbox.py` (invoked by `felix-admin-capture` after `route_and_finalize`) |
| Apply helper | `scripts/intake/apply_reply.py` (invoked by the `main` DM agent on Kent's reply) |
| Grammar module | `scripts/intake/shorthand.py` (alias table; shared by apply) |
| Read token | `vikunja-api` (felix-bot) — scan only |
| Write token | `/data/services/openclaw/secrets/vikunja-api-kent` (kent) — apply only |
| Id resolution | `scripts/common/vikunja_refs.py` (#748 seam; **no hardcoded ids**) |
| State dir | `/data/services/openclaw/state/intake/` |
| Correlation record | `digests/intake-<digest_id>.json` (immutable per digest; 48h retention) |
| Latest pointer | `latest.json` |
| Tick artifact | `intake-tick-<ET-date>.json` (+ stable `intake-tick-latest.json`) |
| Apply ledger | `intake-apply-<ET-date>.jsonl` (append-only) |
| LLM calls | zero on the deterministic path (narrow unresolved-token fallback only) |
| Runs as | `claude` user |

## State-directory layout

State lives under `/data/services/openclaw/state/intake/`, mirroring the habits
state-dir convention (`/data/services/openclaw/state/habits/`). The intake
helpers **self-provision** it on first run (`mkdir(parents=True, exist_ok=True)`
in `scan_inbox.py` and `apply_reply.py`) — no deploy manifest creates it. It is
**not** git-tracked and is backed up by the nightly Restic job.

```
/data/services/openclaw/state/intake/
├── digests/
│   └── intake-<digest_id>.json      # one IMMUTABLE record per digest (never overwritten)
├── latest.json                      # pointer to the newest digest record
├── intake-tick-<ET-date>.json       # per-tick observability (scan counts + apply aggregates)
├── intake-tick-latest.json          # stable copy of the newest tick artifact (health probe)
└── intake-apply-<ET-date>.jsonl     # append-only per-line ApplyResult ledger
```

**Why per-digest immutable records?** The loop fires ~4×/day. A same-day
overwrite would let a delayed reply map number `1` to a *different* task across
ticks. Each digest is therefore an immutable file keyed by `digest_id`; records
older than the 48h retention window are expired on the next scan. Correlation is
**content-based** — the apply step selects the digest whose entries match the
reply's **line-number set + task-title evidence** (habits
`correlate_reply_to_checkin` semantics), never by position in the newest file
alone. A reply line whose number has no unambiguous task is `echoed_back`.

### Digest record shape

```json
{
  "digest_id": "2026-07-17T2200Z-inbox-5pm",
  "created_utc": "2026-07-17T22:00:11Z",
  "created_et_date": "2026-07-17",
  "source_cron": "inbox-5pm",
  "entries": [
    { "n": 1, "task_id": 412, "title": "Draft onboarding deck",
      "missing_fields": ["project", "friction", "quadrant"] }
  ]
}
```

## Shorthand grammar

Kent replies with **one line per task**, keyed by the digest number. Every token
after `<n>` is **optional** — a line supplies only the fields the digest reported
missing (a task that already carries a valid `f:` or `q:` need not repeat it).

```
<n> [project-token] [f<1-4>] [quadrant-token] [due:<date>] [habit] [loe:<s|m|l>]
```

- `<n>` — the digest number, correlated to a `task_id`.
- **project-token** — a canonical project name or documented short-name
  (case-insensitive), resolved via the seam. Documented short-names
  (`scripts/intake/shorthand.py` `PROJECT_ALIASES`): `personal`, `felix`
  → `felix_kg_automation`, `clients`, `pointerhealth`, `spec-kitty`/`spec_kitty`
  → `spec_kitty`, `intentional`, `habits`.
- **friction** (`FRICTION_ALIASES`) — `f1` → `f:1-flow`, `f2` → `f:2-growth`,
  `f3` → `f:3-edge`, `f4` → `f:4-overload`. Applying a new `f:` **replaces** any
  existing `f:`-family label (family-replace). `f:4-overload` is a
  **decomposition trigger, not a schedulable friction**: it records
  decomposition-pending, confirms once, and the task **stops re-prompting** (it is
  not counted Tier-1-incomplete-for-prompting) — it is never routed to a working
  queue.
- **quadrant** (`QUADRANT_ALIASES`) — `do` → `q:do`,
  `sched`/`schedule` → `q:schedule`, `deleg`/`delegate` → `q:delegate`,
  `elim`/`eliminate` → `q:eliminate`. Applying a new `q:` replaces any existing
  `q:`-family label. `eliminate` marks the task **done** (a valid resolution — it
  stops appearing).
- **Tier-2 (optional)** — `due:<date>` (written per the ET end-of-day
  convention), `habit`/`t:habit` → the `t:habit` label, `loe:s`/`loe:m`/`loe:l`.
  Tier-2 **never blocks** Tier-1 completion. A `q:do`/`q:schedule` reply with no
  `due:` triggers a **non-blocking** due-date follow-up. Incompatible Tier-2
  (`due:` with `q:eliminate` or `f:4`) is **ignored-with-note**, never silently
  applied (the FR-017 compatibility matrix).

**Examples**

| Reply line | Meaning |
|---|---|
| `1 personal` | only the project was missing → assign `personal` |
| `2 f2 schedule` | only labels missing → `f:2-growth` + `q:schedule` |
| `3 clients f3 do due:fri` | project + labels + a Friday due date |
| `4 f4` | overload → decomposition-pending; stops re-prompting |
| `5 elim` | eliminate → mark done |

A token not in the alias table and not a seam-declared name → **LLM fallback**;
still unresolved → the line is `echoed_back` to Kent with what was understood and
what failed. Nothing is silently applied or dropped.

### Per-line apply statuses

Each reply line resolves to exactly one status, confirmed to Kent, without
blocking the others: `applied`, `echoed_back` (unparseable/unresolvable),
`overload_flagged` (`f:4` decomposition-pending), `noop` (live state already
matches the intended values), `not_found` (task gone), `already_done`,
`moved_conflict` (task left Inbox by another process), `access_denied` (kent
token can't write), `failed` (write/verify error).

## 30-second health check

Latest tick, from the stable pointer:

```bash
ssh office2-claude 'jq -r "[.exit_status, .started_at_utc, (.errors|length), .scanned, .incomplete, .prompted] | @tsv" /data/services/openclaw/state/intake/intake-tick-latest.json'
```

A healthy tick prints e.g. `success   2026-07-17T22:00:11Z   0   14   3   3`
(exit_status · started · error-count · scanned · incomplete · prompted).

Today's apply aggregates (if any replies were processed):

```bash
ssh office2-claude 'jq ".aggregates // {}" /data/services/openclaw/state/intake/intake-tick-$(date -u +%Y-%m-%d).json'
```

Confirm the state dir + kent-token secret are present:

```bash
ssh office2-claude 'ls -ld /data/services/openclaw/state/intake /data/services/openclaw/state/intake/digests && ls -l /data/services/openclaw/secrets/vikunja-api-kent'
```

## Manual / debugging invocations

Run helpers from the checkout root with the mandatory `-m` module form (office2
is python3-only; a bare `python` fails — see the memory note). Both helpers
support `--dry-run` (no writes) and `--json`.

Preview a scan without writing state:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.intake.scan_inbox --dry-run --json'
```

Preview applying a reply (correlate + plan + classify; **no** Vikunja writes, no
ledger append):

```bash
ssh office2-claude "cd /home/claude/kg-automation && python3 -m scripts.intake.apply_reply --reply '1 personal f2 schedule' --dry-run --json"
```

The apply helper **refuses the felix-bot token path** — writes go only through
`--token-file /data/services/openclaw/secrets/vikunja-api-kent` (the default).
The `--unresolved` flag is the constrained LLM-fallback channel: a JSON list of
`{line, token, position, canonical_name}` where each `canonical_name` is
re-resolved through the seam; raw ids and free-form values are rejected.

## Troubleshooting

- **Digest sent but reply not applied** — confirm the reply's numbers match a
  live digest inside the 48h window: `jq . /data/services/openclaw/state/intake/latest.json`
  then inspect the referenced `digests/intake-<id>.json`. An orphan number is
  expected to `echoed_back`, not apply.
- **`access_denied` on every line** — the kent token is missing/unreadable:
  `ssh office2-claude 'ls -l /data/services/openclaw/secrets/vikunja-api-kent'`
  (expect it present and readable by `claude`). felix-bot cannot substitute (it
  403s — that is the #750 defect this loop routes around).
- **A task keeps re-prompting** — it is still Tier-1-incomplete. Either it never
  received a working project + `f:` + `q:`, or a write failed (check the apply
  ledger `intake-apply-<ET-date>.jsonl` for its `status`). `f:4-overload` and
  `q:eliminate` are the two terminal resolutions that stop the re-prompt.
- **Unexpected id or a seam drift error** — the loop resolves every project/label
  through `scripts/common/vikunja_refs.py`; a fail-loud error means the seam
  registry (`scripts/common/vikunja_refs.json`) does not declare a needed label.
  Extend the seam under its drift/AST gate (`vikunja_refs_validate.py`); never
  hardcode an id.

## Deploy

**Manifest-free** (the #746 / #720 / #733 pattern; C-002 — a `deploys/queued/`
manifest is added *only if* an office2 apply step beyond self-pull is needed, and
here it isn't):

- **Helpers** (`scripts/intake/scan_inbox.py`, `apply_reply.py`, `shorthand.py`)
  deploy via the **office2 checkout self-pull** — felix-deployer git-pulls
  `origin/main` on each tick; no explicit copy step. The state dir is
  **self-provisioned on first run** (`mkdir(parents=True, exist_ok=True)`), so no
  manifest is needed to create it.
- **Agent prompts** — `felix-admin-capture` (runs the scan after
  `route_and_finalize`) and the `main` DM agent (applies the reply) deploy via
  **`agent-prompt-sync`**, the standing prompt-deploy pipeline.
- **kent-token secret** (`/data/services/openclaw/secrets/vikunja-api-kent`) is a
  **pre-existing #715 dependency** — this mission consumes it, it does not
  provision it (already present on office2).
- **Rebaseline: not required — #621** (only `AGENTS.md` + non-audited code
  changed; `audit.sh` hashes `openclaw.json`, never agent `AGENTS.md`).

## Related

- [`inbox-ops.md`](<./inbox-ops.md>) — the inbox-processing crons this loop rides.
- [`habits-ops.md`](<./habits-ops.md>) — the state-dir + correlation-record pattern this mirrors.
- [`vikunja-configuration-design.md`](<../design/vikunja-configuration-design.md>) — the Tier-1 standard (§Required Fields).
- Architecture records: `inbox-processing` service + `intake-validation-loop` flow in `docs/design/architecture/data/`.
