# Contract: rule inventory and repair helpers

Both helpers follow `docs/design/helper-script-conventions.md`. They are invoked as `python3 -m scripts.vikunja.<name>`, and the last line of stdout is a JSON summary.

## `scripts.vikunja.rule_inventory` (read-only)

```
python3 -m scripts.vikunja.rule_inventory \
  --baseline-db <path-to-READ-ONLY-COPY-of-snapshot-db> \
  [--schedule-path scripts/habits/migrations/phase3-schedule.yaml] \
  --out <private-json-path>
```

- Opens `--baseline-db` with `sqlite3.connect("file:<path>?mode=ro", uri=True)` and refuses `/data/services/vikunja/data/vikunja.db`, the live DB. It reads only `id, repeats, repeats_from_current_date`.
- Fetches each candidate task's current state with `get_task_v2`. Makes no writes; a test asserts the client is never asked to PATCH, POST or PUT.
- Classifies each task as `ok | progressed | ended | lost | removed | changed | unresolved` (`data-model.md`). A lower COUNT and a normal series end are expected progress, not damage. `lost` additionally requires Felix-write attribution; without it the status is `removed`, which goes to Kent. Each entry records a `current_fingerprint`.
- `--felix-logs <dir>...` gives the attribution sources: the sweeper ledger, habits history, escalation JSONL and intake logs, all read-only.
- `--seed-ledger <path>` (optional) cross-checks the sync's `seed-ledger.jsonl`. It is applied after the normal-end check. A seeded no-rule task whose baseline rule had COUNT or UNTIL is `ended` or `removed`, never `lost`. Otherwise it is `lost` only with Felix attribution.
- Writes the full entries to `--out` (mode 600). Stdout is `{"ok":true,"checked":N,"progressed":p,"ended":e,"lost":a,"changed":b,"unresolved":c,"out":"<path>"}`.
- Exit codes: 0 ok, 2 bad args/refused path, 3 Vikunja error.

## `scripts.vikunja.rule_repair`

```
python3 -m scripts.vikunja.rule_repair --plan <inventory-out.json> [--task-id N ...] --dry-run
python3 -m scripts.vikunja.rule_repair --plan <inventory-out.json> [--task-id N ...] --apply
python3 -m scripts.vikunja.rule_repair --restore <snapshot.before.json>
```

`--apply` only acts on tasks with status `lost`. A `removed`, `ended`, `changed` or `unresolved` task is acted on only when it is named with `--task-id` and `--accept-changed` is passed, which records Kent's explicit choice.

Per task, in `--apply` (revised by post-plan review findings 4 and 6):
1. **Fresh read and drift check.** Run `get_task_v2` and compare it with the inventory's `current_fingerprint`. On any difference, record `{outcome:"skipped_drift"}` and move to the next task. Never overwrite a later UI edit.
2. **Snapshot, then journal the intent.** Write `<state>/vikunja-repair/<run_id>/<id>.before.json` (mode 600, fsync). Then append `{phase:"intent", task_id, snapshot_path, intended, restore_command}` to `<run_id>/journal.jsonl` and fsync it. If either write fails, stop the whole run before touching Vikunja.
3. **Write.** If a rule exists, PATCH `{"repeat": null}` first, then PATCH `{"repeats_rrule": <text>, "repeats_from_current_date": <bool>}`. The clear-first step defeats the stale-COUNT echo.
4. **Readback.** Run `get_task_v2` again and check `same_rule(readback, intended)`.
5. **Journal the outcome, always.** Append `{phase:"outcome", task_id, outcome: ok|mismatch|unknown, after, error?}`. On a timeout or transport error the outcome is `unknown`, and the next step is a fresh read. On `mismatch` or `unknown`, stop the run and print the restore command.
6. **Resume.** `--resume <run_id>` reads `journal.jsonl`. For every intent with no outcome it does a fresh read and records `ok`, `mismatch` or `unknown` before doing anything else.

**Before `--apply`**, the operator posts the `--dry-run` output for the `lost` set on #1111, so Kent can see it before any write. This is a visibility step, not a new gate, since live writes are pre-approved.

`--dry-run` prints, for each task, the before value, intended after value, drift status and snapshot path, and writes nothing to Vikunja. A test asserts that no write verb is used.

`--restore <snapshot>` follows the ordered restore algorithm in `data-model.md`: rule by canonical text with clear-first, then reminders (`[]` for null), then due date, then a controlled return to `done=false`. A restore to `done=true` on a task with a rule is refused. Readback compares every field. Restore is journalled the same way as `--apply`.

**UI exclusion during a run:** the runbook tells Kent not to edit the affected tasks while a run is in progress, and the per-task drift check in step 1 catches any edit made between the inventory and the write.

**Recording on #1111** is a separate step: `--emit-issue-markdown <run_id>` prints a markdown table of task id, before and after rule, readback result and restore command. The operator posts it with `gh issue comment 1111 --body-file`. Because the helper has no GitHub access, the credential surface stays as it is.
