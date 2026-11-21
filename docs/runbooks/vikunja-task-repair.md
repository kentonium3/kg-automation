---
id: vikunja-task-repair
doc_type: runbook
title: Vikunja Recurrence-Rule Inventory and Repair
status: approved
level: 2
owners: [kent]
audience: agents_and_humans
last_validated: '2026-11-20'
updated_by: '#1111'
version: '1.0.0'
---

# Vikunja Recurrence-Rule Inventory and Repair

## Purpose

Before mission #1111, Felix's narrow v1 writes could strip a task's
recurrence rule (`repeat`) on the RRULE Vikunja fork. This runbook finds
any rules that were lost and puts them back, reversibly. It uses two helpers:

- `scripts.vikunja.rule_inventory`: **read-only**. It compares the rule
  columns of a *copy* of the pre-cutover snapshot DB with each task's live
  state (`GET /api/v2/tasks/{id}`), and classifies each task.
- `scripts.vikunja.rule_repair`: dry-run, apply, resume, restore and
  issue-markdown. Every write is preceded by a durable snapshot and an intent
  journal line, and every attempt ends in an outcome line.

The expected result is an empty or near-empty inventory (#1111 core-worker
audit). Contract:
`kitty-specs/felix-rrule-adaptation-01M7TKNX/contracts/repair-and-inventory-cli.md`.

All commands run on office2 as `claude` (`ssh office2-claude`) from the
kg-automation checkout. The helpers print a JSON summary as the last line of
stdout.

## Preconditions

All of these must hold before you run the inventory:

1. The #1111 fixes are deployed on office2 (the v2 client, rule-preserving
   writers and the sync's seed ledger).
2. The Felix Vikunja token has been re-issued with the v2 task permissions
   (`tasks.read_one`, `tasks.update`), and verified per the mission
   quickstart.
3. The rollout window is closed: affected agent writes were paused and then
   resumed, and **at least one sync cycle has run**, so
   `seed-ledger.jsonl` exists.

## Statuses

| Status | Meaning | Repaired by `--apply`? |
|---|---|---|
| `ok` | same rule | no (nothing to do) |
| `progressed` | same rule, lower COUNT (normal completions) | only with `--task-id N --accept-changed` |
| `ended` | done; COUNT exhausted (rule cleared) or UNTIL passed (rule kept) | only with `--task-id N --accept-changed` |
| `lost` | rule gone, baseline had no COUNT/UNTIL, Felix write within 120 s of `updated` | **yes** |
| `removed` | rule gone without Felix attribution, or a finite rule gone without a confirmed end | only with `--task-id N --accept-changed` |
| `changed` | a different rule (or a different from-current flag) | only with `--task-id N --accept-changed` |
| `unresolved` | no usable restore source (for example a date-only UNTIL) | never |
| `deleted` | task no longer exists (404) | never |

Only `lost` is auto-repaired. Everything else goes to Kent. `--accept-changed`
without `--task-id` is refused (exit 2), so consent always names the task.
A `--task-id` given twice is processed once.

## 1. Make a read-only copy of the snapshot

Never open the original snapshot; the helper refuses
`/data/services/vikunja/snapshots/` and the live data directory
`/data/services/vikunja/data/`. Copy it into a private scratch dir:

```bash
install -d -m 700 /data/services/openclaw/state/vikunja-repair/baseline
```

```bash
cp --preserve=mode /data/services/vikunja/snapshots/20261030T081520Z/vikunja.db /data/services/openclaw/state/vikunja-repair/baseline/vikunja-20261030.db
```

If `claude` cannot read the snapshot, stop and ask Kent to run the same `cp`
via `ssh office2-kgale`, followed by a `chown claude:` of the copy. The helper
opens the copy with `mode=ro`. It reads only `id`, `repeats` and
`repeats_from_current_date`, and finds the columns with
`PRAGMA table_info(tasks)`. If those columns are missing (a legacy
`repeat_after` schema), it exits 2 and names the repeat columns it found.

## 2. Inventory

```bash
python3 -m scripts.vikunja.rule_inventory --baseline-db /data/services/openclaw/state/vikunja-repair/baseline/vikunja-20261030.db --schedule-path scripts/habits/migrations/phase3-schedule.yaml --felix-logs /data/services/openclaw/state/habits/sweeper-ledger.jsonl /data/services/openclaw/state/habits-history.jsonl /data/services/openclaw/state/escalation /data/services/openclaw/state/intake --seed-ledger /data/services/openclaw/state/sync/seed-ledger.jsonl --out /data/services/openclaw/state/vikunja-repair/inventory.json
```

- `--felix-logs` takes files or directories (their `*.jsonl`). Each file is
  read by a parser for its source, and only **successful, non-dry-run writes
  that changed the task** count as attribution:
  - `sweeper-ledger.jsonl`: ticks with `dry_run: false`, and only
    `habits_auto_skipped` entries that carry `new_due_date_et` (the
    day-specific due-date write). Tasks listed in the tick's `errors` don't
    count. Evaluations such as `already_resolved` never count.
  - `habits-history.jsonl` (in the state root, not under `habits/`): habit
    completion rows (`domain: habits`, state `complete`, `incomplete` or
    `skipped`) with `source: whatsapp`, the source Felix's
    `record_completion` uses. `vikunja-ui` rows (reconcile recording a UI
    tick), `historical-backfill` rows and `event_type` rows such as
    `auto_skipped` don't count. None of them wrote Vikunja.
  - `*-escalation-history.jsonl`: rows with state `done` or `rescheduled` and
    `source` `agent` or `kent_reply`. `reconcile` rows are synthesized
    without a Vikunja write, and `backfill` and `operator_repair` rows are
    hand repairs, so none of them count.
  - `intake-apply-*.jsonl`: rows with `status: applied` and `applied.done`
    true. The ledger records the *requested* project and due date even when
    they were unchanged, and it does not log the executed field changes. So
    project-only and due-only rows are treated as no write.

  Any other file is ignored (`unrecognised_files`), and so is any record a
  parser does not recognise. Malformed lines are skipped and counted
  (`felix_log_skipped`).
- The seed ledger may contain duplicate rows from a retried cycle; they are
  collapsed. Malformed lines, and rows whose `seeded_value` is not a rule
  object or `null`, are skipped and counted in `seed_ledger_skipped`.
- `--out` is written mode 600 and holds the full entries, including each
  task's `current_fingerprint`.
- Exit codes: 0 ok, 2 bad args or refused path, 3 Vikunja error.

**Post the summary on #1111.** Stdout lists one line per non-`ok` task (ids
and rule text only, titles only for the public habit ids 14, 15, 16, 18, 19,
20, 65, 75, 76 and 77), then the JSON summary. Save it to a file and post:

```bash
gh issue comment 1111 --repo kentonium3/kg-automation --body-file <summary-file>
```

Never paste `inventory.json` itself: it is private.

## 3. Dry-run, posted on #1111

```bash
python3 -m scripts.vikunja.rule_repair --plan /data/services/openclaw/state/vikunja-repair/inventory.json --dry-run
```

For each selected task (every `lost` task, or the ones named with
`--task-id`) this prints the current rule, the intended rule, the drift
status against the inventory fingerprint (`deleted` for a 404), and an
illustrative snapshot path. A Vikunja read error exits 3. It writes nothing, locally or to Vikunja. Post the output on #1111
before applying, for visibility. This is not a new gate; live writes are
pre-approved.

## 4. Apply

UI exclusion: **do not edit the affected tasks in the Vikunja UI while a run
is in progress.** Each task is drift-checked just before its write, so an
edit made after the inventory is caught (`skipped_drift`) and never
overwritten, but an edit made during a write is not.

```bash
python3 -m scripts.vikunja.rule_repair --plan /data/services/openclaw/state/vikunja-repair/inventory.json --apply
```

To act on a non-`lost` task, Kent names it explicitly:

```bash
python3 -m scripts.vikunja.rule_repair --plan /data/services/openclaw/state/vikunja-repair/inventory.json --task-id 42 --accept-changed --apply
```

What happens per task, in order:

1. a fresh read and drift check (any difference gives `skipped_drift`, and
   the run moves on);
2. `<run_dir>/<id>.before.json` (mode 600, fsynced), then an `intent` line in
   `<run_dir>/journal.jsonl` (fsynced);
3. the write: `{"repeat": null}` first when a rule exists, then
   `{"repeats_rrule": ..., "repeats_from_current_date": ...}`;
4. a readback that checks the rule and that reminders, the due date and
   `done` are unchanged from the snapshot (relative reminders by relation and
   period, absolute ones by exact instant);
5. an `outcome` line: `ok`, `mismatch` or `unknown`.

The run dir is `/data/services/openclaw/state/vikunja-repair/<run_id>/`
(override with `--state-dir`).

| Exit | Meaning | What to do |
|---|---|---|
| 0 | done | emit and post (step 5) |
| 2 | refused (bad selection or args) | read the message |
| 3 | a Vikunja read failed; the message names the run id and how many writes the run already made | check the token or service. If the run made **any** write, run `--resume <run_id>` and emit that run's report (step 5) **before** starting any new `--apply`: a fresh apply would skip the already-repaired tasks as drifted, and their repairs would be missing from the report. Rerun only when zero writes were made |
| 4 | a local snapshot or journal write failed | fix the disk or permissions; nothing was written after the failure |
| 5 | stopped on `mismatch` or `unknown` | the restore command is printed; see steps 6 and 7 |

## 5. Emit and post

```bash
python3 -m scripts.vikunja.rule_repair --emit-issue-markdown <run_id>
```

This writes `<run_dir>/issue-comment.md` (override with `--markdown-out`).
The file is created mode 600; re-emitting over an existing file truncates it
and keeps that file's existing mode. It is a table of task id, before rule, after rule,
readback, outcome and restore command, under a header naming the run id,
the start time and the operator. It contains no `@` and no titles outside
the public habit ids. The helper has no GitHub access. Post it yourself:

```bash
gh issue comment 1111 --repo kentonium3/kg-automation --body-file /data/services/openclaw/state/vikunja-repair/<run_id>/issue-comment.md
```

## 6. Restore (undo)

Every write has a restore command in the journal, the emitted table and the
stop message:

```bash
python3 -m scripts.vikunja.rule_repair --restore /data/services/openclaw/state/vikunja-repair/<run_id>/<id>.before.json
```

Restore is itself journalled as a new run, with its own `.before.json`, so a
restore can be undone too. It runs in this order, so no step triggers
completion semantics:

1. **Rule**: the snapshot's canonical text, clearing first when a different
   rule exists (this defeats the stale-COUNT echo). A no-rule snapshot
   restores `{"repeat": null, "repeats_from_current_date": <snapshot>}`.
2. **Reminders**: the snapshot's list, sending `[]` for `null`.
3. **Due date**: the snapshot's value, or `null` when it had none.
4. **Done**: `done=false` when the snapshot was open and the task is done now,
   and `done=true` when the snapshot was done, the task is open now and
   neither has a rule. A restore to `done=true` on a task with a rule is **refused** (exit 2),
   because completing it would advance the series. Handle that by hand.
5. **Readback**: every restored field is compared, and each difference is
   reported in `diff_fields`.

## 7. Resume after interruption

```bash
python3 -m scripts.vikunja.rule_repair --resume <run_id>
```

Resume uses the task selection saved in the run's `run.json` at apply time
(status, proposed rule and drift fingerprint), not the inventory file. If
the inventory file still exists and has changed since the apply (its
SHA-256 differs), resume refuses (exit 2) before any Vikunja call; a missing
inventory file is fine. Put the original inventory back, or
start a new `--apply`.

For every intent whose latest outcome is missing (a crash) or `unknown` (a
timeout), resume first does a fresh read and records `ok`, `mismatch` or
`unknown`. Only then does it continue with the run's remaining planned
tasks.

If a crash left the journal without a final newline, the next append
repairs it first. A final line that is a complete JSON record is kept and
terminated with a newline. Anything else is a torn line: the journal is
truncated to its last complete line (fsynced) and the fragment is kept in
`journal.jsonl.torn` as evidence. If any task ends in `mismatch` or
`unknown`, resume stops (exit 5). Restore that
task, then start a fresh `--apply` with `--task-id` for whatever is left. The
drift check protects the tasks already handled.

## Residual risk: attribution

`lost` needs a successful, non-dry-run Felix write to the task after
2026-10-30, with the task's `updated` within 120 s of it. Timestamp proximity cannot prove which
write removed the rule. If Kent removed a rule in the UI within 120 s of a
Felix write, the task is classified `lost` and the rule would be re-added.
The impact is one task's rule, and it is fully reversible with `--restore`.
Attribution is conservative on purpose. A Felix write that no log proves,
such as an intake project or due-date change, leaves the task `removed`
(Kent decides) rather than `lost`. One gap remains: an escalation row is not
marked when it was written with `--no-vikunja`. If an operator ever ran
that with `--source agent` or `kent_reply`, the row would still count. No
agent path uses the flag.
Mitigations: the `lost` dry-run list is posted on #1111 before `--apply`,
each write is drift-checked, and the expected inventory is empty.
This was accepted in post-plan-review.md, re-review 2, item 4.
