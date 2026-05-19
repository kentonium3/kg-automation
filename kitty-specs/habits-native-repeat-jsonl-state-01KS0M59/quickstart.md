# Quickstart — Phase 3 operator + agent walkthroughs

**Mission**: `habits-native-repeat-jsonl-state-01KS0M59`
**Audience**: Kent (operator running the migration), implementers of Phase 4 (#307) + Phase 5 (#308) (future consumers of the new helpers)

This is the end-to-end walkthrough for the Phase 3 mission. Once Phase 3 merges, the only operationally-active piece is the Vikunja task state (PATCHed schedules + retired workout + 3 new MWF tasks). The new scripts exist on disk but are not invoked by the cron until Phase 5 cutover (#308).

---

## Operator walkthrough — applying the migration

### Pre-flight (Tier 2 protocol)

1. Confirm Restic snapshot exists within the last 24h:
   ```bash
   ssh office2-claude 'sudo restic snapshots --latest 1 || tail -5 /data/services/backup/logs/backup-$(date -u +%Y-%m-%d).log'
   ```

2. Confirm Vikunja is reachable and openclaw-gateway is up:
   ```bash
   ssh office2-claude 'systemctl --user is-active openclaw-gateway.service'
   ssh office2-claude 'curl -sS -o /dev/null -w "%{http_code}\n" http://100.92.197.90:3456/api/v1/info'
   ```

3. Confirm the felix-bot Vikunja token is in place:
   ```bash
   ssh office2-claude 'stat -c "%a %U:%G %n" /data/services/openclaw/secrets/vikunja-api'
   # Expected: 600 claude:claude /data/services/openclaw/secrets/vikunja-api
   ```

### Step 1 — Identify the workout task

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.identify_workout_task'
```

stdout will print one JSON object describing the current workout task:

```json
{"task_id": 17, "title": "Workout", "project_id": 1, "labels": ["personal"], "repeat_after": 0, "due_date": "2026-05-19T08:00:00Z"}
```

Note the `task_id`. If multiple workout-like tasks are returned (exit 1), disambiguate manually via the Vikunja UI and pick the right one.

### Step 2 — Populate habits-schedule.yaml

In the repo (laptop):

```bash
$EDITOR kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml
```

Update the `retire` operation's `task_id` to the value from Step 1. Verify the 7 daily PATCH operations cover the other 7 IDs (14, 15, 16, 18, 19, 20, 65 — minus whichever ID is the workout).

Commit + push the schedule file:

```bash
git add kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml
git commit -m "config(habits-phase3): fill workout task ID in schedule.yaml"
git push origin main
```

### Step 3 — Dry-run

Pull the latest on office2 and dry-run:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && git pull --rebase origin main'

ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.migrate_schedule \
    --schedule kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml \
    --snapshot-out /data/services/openclaw/state/habits-pre-phase3-snapshot.json \
    --dry-run'
```

Review the per-operation output. Confirm:
- 7 daily PATCHes target the right IDs and `repeat_after=86400`
- 1 retire targets the workout task
- 3 creates with `repeat_after=604800` and correct titles

The snapshot file is written with `before_states` even in dry-run mode (no applied_changes yet).

### Step 4 — Apply the migration

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.migrate_schedule \
    --schedule kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml \
    --snapshot-out /data/services/openclaw/state/habits-pre-phase3-snapshot.json'
```

Expected output: `SUMMARY: applied 11/11 operations; snapshot at /data/services/openclaw/state/habits-pre-phase3-snapshot.json`. Exit 0.

### Step 5 — Verify post-PATCH state

For each of the 7 daily habits:

```bash
ssh office2-claude 'curl -sS -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
    "http://100.92.197.90:3456/api/v1/tasks/14" | python3 -m json.tool | grep -E "repeat_after|repeat_mode|done"'
```

Expected: `repeat_after: 86400, repeat_mode: 0, done: false` for each daily task.

For the retired workout:

```bash
ssh office2-claude 'curl -sS -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
    "http://100.92.197.90:3456/api/v1/tasks/17"'
# Expected: done=true, repeat_after=0 (unchanged)
```

For the 3 new MWF tasks: their IDs are in `snapshot["created_tasks"]`. GET each one:

```bash
ssh office2-claude 'cat /data/services/openclaw/state/habits-pre-phase3-snapshot.json | python3 -m json.tool | grep -A 2 "created_tasks"'
```

### Step 6 — Smoke-test record_completion against a sandbox task

Pick a sandbox Vikunja task (e.g., one of the dev test-targets — NOT a production habit). Run:

```bash
ssh office2-claude 'echo "{\"task_id\":999,\"title\":\"Test sandbox\",\"date\":\"2026-05-20\",\"state\":\"complete\",\"source\":\"manual\"}" \
    | python3 -m scripts.habits.record_completion'
```

Verify:
- Vikunja GET `/tasks/999` shows `done=true`
- Vikunja GET `/tasks/999/comments` shows a `[Felix] 2026-05-20 | complete` entry with `author.username = "felix-bot"`
- `/data/services/openclaw/state/habits-history.jsonl` has a new line with `domain=habits, task_id=999, state=complete, source=manual`

Re-run the same command. Verify: exit 0, no new Vikunja calls, no new JSONL line (idempotent).

### Step 7 — Smoke-test reconcile

Kent: tick the sandbox task done in the Vikunja UI (un-tick first if needed). Verify `done_at` is set. Then:

```bash
ssh office2-claude 'python3 -m scripts.habits.reconcile_completions'
```

Expected: a backfill line for the sandbox task with `source=vikunja-ui`. JSONL gains a new entry.

### Rollback (NO-GO recovery)

If any post-step verification fails:

```bash
ssh office2-claude 'python3 -m scripts.habits.migrate_schedule \
    --rollback \
    --snapshot-file /data/services/openclaw/state/habits-pre-phase3-snapshot.json'
```

Expected: `SUMMARY: rollback complete; 11 changes reversed`. Then re-verify each task via GET; all should match the BEFORE state in the snapshot.

---

## Future agent integration (Phase 5 callers — not in this mission)

After Phase 5 cutover, the felix-admin-habits agent's standing orders (`AGENTS.md`) will reference the new helpers. The integration shape:

### Morning check-in flow (Phase 5+)

1. Agent invokes `reconcile_completions.py` first — catches up on any UI completions since the last tick.
2. Agent invokes `query_active_habits_v2.py` — gets the active-today list via Vikunja-native filter.
3. Agent pipes that through `exclude_completed_v2.py` — drops anything already marked complete in JSONL.
4. For each remaining task, agent surfaces a WhatsApp prompt.
5. On positive WhatsApp response: agent invokes `record_completion.py` with `state=complete, source=whatsapp`.
6. On negative WhatsApp response: agent invokes `record_completion.py` with `state=incomplete, source=whatsapp`.
7. On skipped (e.g., Kent says "skipping today"): `state=skipped, source=whatsapp, note=<reason>`.

### Adding a new habit (operator-driven, no code change)

To add guitar practice (Tuesdays) after Phase 3 merges:

1. Create the task in Vikunja UI: title "Guitar practice — Tuesday", project = personal, label = music.
2. PATCH its schedule via a one-off invocation of `migrate_schedule.py` with a minimal schedule.yaml containing only that task's create+schedule op. The mission's helper is generic enough to apply.
3. Or: simply set `repeat_after=604800` via the Vikunja UI (the schedule.yaml + migrate_schedule.py workflow is the "automated and snapshot-backed" path; manual UI edits work too).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `identify_workout_task` returns null | No task title matches `workout` regex | Manually search Vikunja UI; pass `--candidate-ids` to override |
| `migrate_schedule --dry-run` fails YAML validation | schedule.yaml malformed | stderr names the operation index + field; fix and re-dry-run |
| `migrate_schedule` partial failure (exit 1) | Network blip mid-batch; snapshot has partial state | Inspect snapshot file; either retry from where it stopped OR `--rollback` to BEFORE |
| `record_completion` exit 2 (Vikunja OK but JSONL fail) | Local disk full or perm denied on `/data/services/openclaw/state/` | Free disk OR fix perms via the same approach as #323 (group write enabled) |
| `reconcile_completions` reports drift | Kent un-ticked a UI completion OR write race | Operator decides which source of truth wins; manual JSONL append or UI re-tick |
| Sandbox `record_completion` smoke test fails on comment readback | Vikunja v0.24.6 API quirk | Check Verified API gotchas in `docs/design/research/vikunja-task-model-research.md` (esp G3, G4) |
