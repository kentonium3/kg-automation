# Research: Felix RRULE recurrence adaptation

Phase 0 findings, 2026-11-19.

**Sources:**
- Vikunja fork `kentonium3/vikunja-harness` @ `d7e202228` (what office2 runs as v2.8.0-rrule.4), read with `git show`, plus huma v2.40.0 `autopatch/autopatch.go` (cited as AP:line).
- kg-automation @ `cc4f2154`, the mission base. `scripts/` and `tests/` are unchanged on the mission branch.
- Read-only probes on office2 as `claude`. Tokens were never printed.
- The #1111 audit and the Vikunja core worker's comment [7019366561](https://github.com/kentonium3/kg-automation/issues/1111#issuecomment-7019366561).

Confidence tags: **[V]** verified in code, **[T]** also pinned by an upstream webtest, **[L]** observed live, **[I]** inferred.

## R-001 — v2 PATCH semantics

- **Decision**: Use `PATCH /api/v2/tasks/{id}` with `Content-Type: application/merge-patch+json` and only the changed keys. This is the main write path (C-001).
- **Rationale**:
  - AutoPatch runs an internal GET, applies an RFC 7396 merge patch, then runs an internal PUT (AP:276-457). It accepts `application/json` and `merge-patch+json` as merge patch (AP:345, 366).
  - The PUT reaches the same `models.Task.Update` as v1 with no field mask (`pkg/models/tasks.go:1419-1421, 1495-1501`). Because the merged body already carries every field the GET returned, omitted fields survive. **[V]**
  - `{"done":true}` on a repeating task keeps the rule, advances the task and reopens it (`tasks.go:2339-2373`; webtest `huma_task_occurrences_test.go:130`). **[V][T]**
  - `{"due_date":…}` keeps `repeat`, `repeats_from_current_date` and `reminders`. **[V]**
- **Hazards the client must absorb**:
  1. An explicit `null` deletes that key, so the field takes its zero value. **[V]** The client therefore refuses `None` values, except in `end_series`.
  2. When the merged body equals the GET body, the server returns **304 with an empty body** (AP:408-410). This is "unchanged", not an error.
  3. `{"repeat":null,"done":true}` in one call **reopens** the task (`tasks.go:1735-1767`; webtest `task_recurrence_fidelity_test.go:305-311`). **[V][T]** Ending a series takes two calls: first `{"repeat":null}`, then `{"done":true}`. With no rule, `isRepeating()` is false and the task stays done (`tasks.go:1715-1720`). **[I, built from V parts]** A WP01 test pins the two-call shape.
  4. The If-Match header has no effect (the `tasksUpdate` input has no conditional params, `tasks.go:379-383`). **[I]** The last write wins, which is the same as v1 full echo today.
  5. The query string is dropped on internal legs, so `?format=` is not available. Felix does not use it.
  6. Changing `due_date` does not move absolute reminders, though relative reminders are recomputed. Habit tasks have no reminders today **[L]**. The behaviour is documented, not changed.
- **Alternatives considered**:
  - v1 full echo through `update_task_fields`. It is safe for the rule (stored-text echo rule, `task_repeat_update.go:66-70`), but it re-sends every field and widens the overwrite race. It is kept only as a fallback.
  - JSON Patch (RFC 6902). More verbose and nothing gained.

## R-002 — Reaching v2 without changing the config contract

- **Decision**: Keep `VIKUNJA_BASE_URL` / `vikunja-base-url.txt` as the `/api/v1` URL. Its validation stays at `vikunja_config.py:53` and `vikunja_client.py:112`. The client derives `v2_base = base_url[:-len("/api/v1")] + "/api/v2"`.
- **Rationale**: The config file, its validator and the architecture records (`data-flows.json:1947`, `service-inventory.json:3091`) all pin `/api/v1`. Deriving v2 changes nothing operators configure, and it worked in the live probe **[L]**.
- **Alternatives considered**: Make the config a host root, or allow both suffixes. Rejected because it touches deployed config and every reader for no benefit.

## R-003 — v2 task body shape (live sample)

- **Finding [L]**: `GET /api/v2/tasks/14` returns 200 with these keys: `$schema, assignees, attachments, bucket_id, cover_image_attachment_id, created, created_by, description, done, done_at, due_date, end_date, hex_color, id, identifier, index, is_favorite, labels, max_permission, percent_done, position, priority, project_id, reactions, related_tasks, reminders, repeat, repeats_from_current_date, repeats_rrule, start_date, subscription, title, updated`.
- For task 14 the values are `repeat={"freq":"daily","interval":1}`, `repeats_rrule="FREQ=DAILY;INTERVAL=1"`, `repeats_from_current_date=false`, `reminders=null`.
- **Decision**: The new-shape fixture factory (`tests/common/conftest.py`) is built from this key set, satisfying the charter rule that fixtures mirror real inputs.
- **Casing [V]**: input is case-insensitive, `repeat` responses are lowercase (`daily`, `mo`), and `repeats_rrule` is RFC 5545 uppercase. v1 and v2 serialise the same model. `repeats_rrule` appears only on v2 single-task responses, not on lists (`tasks.go:129-133`).

## R-004 — Token permissions for occurrences and preview

- **Findings**:
  - v2 GET task needs `tasks.read_one` and PATCH or PUT need `tasks.update`. PATCH is an alias of PUT (`api_routes.go:275-280, 569-575`), and v2 create needs `tasks.create` **[V]**. Felix's token holds all three: the v2 GET returned 200 live.
  - Occurrences needs `tasks.occurrences` and preview needs `tasks.occurrences_preview`. These are new keys in the existing `tasks` group (`api_routes.go:388-449`; webtest `huma_task_occurrences_test.go:364-411`) **[V][T]**.
  - Felix's token (`vikunja-api-kent`, created 2026-07-12, `credential-manifest.json:401`) gets **401 code 11** on both **[L]**.
  - Vikunja API tokens cannot be edited. The routes are create, list and delete only (`routes.go:936-938`) **[V]**.
- **Decision** (Decision `01M7TTJY`, Kent: "go ahead with the plan", recommended option adopted): Before the merge, Kent re-issues `vikunja-api-kent` with its current permissions plus `tasks.occurrences` and `tasks.occurrences_preview`, writes it to `/data/services/openclaw/secrets/vikunja-api-kent`, and revokes the old token. Code that calls occurrences or preview fails loudly on 401. It never falls back to guessed dates.
- **Pre-merge permission probe** (read-only, as `claude` on office2; uses only deployed code; prints status codes, never the token):

  ```bash
  ssh office2-claude 'cd /home/claude/kg-automation && python3 - <<"EOF"
  import json, urllib.request, urllib.error
  from scripts.common.vikunja_client import VikunjaClient
  c = VikunjaClient(); v2 = c.base_url[:-len("/api/v1")] + "/api/v2"
  def st(m, p, b=None):
      r = urllib.request.Request(v2 + p, data=json.dumps(b).encode() if b else None, method=m,
          headers={"Authorization": "Bearer " + c.token, "Content-Type": "application/json"})
      try:
          return urllib.request.urlopen(r, timeout=15).status
      except urllib.error.HTTPError as e:
          return e.code
  print("occurrences=%s preview=%s" % (st("GET", "/tasks/14/occurrences?count=1"),
        st("POST", "/tasks/occurrences/preview", {"repeats_rrule": "FREQ=DAILY", "initial_due_time": "07:30", "timezone": "America/New_York", "count": 1})))
  EOF'
  ```

- **Live impact if the grant slips**: none for daily habits. The sweeper does not write them, and their scheduled days are computed locally from `FREQ=DAILY`. Tasks 75–77 stay Done (C-008), so no day-specific habit is active. Only rule proposals (FR-019) and any future non-daily habit need the grant.
- **Alternatives considered**: A Felix-side fallback (two sources of truth, rejected), or dropping O1/O4/O5 (rejected because it loses FR-004/012/019's value).

## R-005 — Escalation write path today

- **Findings [V]**:
  - `scripts/escalation/record_completion.py:192-228` sends `PATCH <base>/api/v1/tasks/{id}`. v1 registers no task PATCH (`routes.go:720-724`), so the call returns 405, raises `VikunjaError`, and the CLI exits 1 *before* the JSONL append (`record_event` 491-501).
  - The agent's `N done` sequence (`felix-admin-escalation/AGENTS.md:202-212`; `TOOLS.md:26-33`; `skills/escalation/SKILL.md:218`) is: (1) a bare `POST /api/v1/tasks/{id}` with `{"done": true}`, then (2) the helper.
  - So step 1 strips the rule and step 2 fails, and no record is written.
  - Live history shows no `kent_reply` `done` since 2026-07-25 **[L]**, so this has not yet hit a recurring task.
- **Decision**:
  - The agent docs drop step 1.
  - The helper uses `patch_task` on v2, which fixes the 405.
  - A test pins that the agent docs contain no direct Vikunja write instruction (grep-style test over `scripts/openclaw/**`).

## R-006 — Sweeper write scope

- **Finding [V]**:
  - `_vikunja_put_due_date` is called only for day-specific habits (`sweeper.py:796-798, 820-892`). Daily habits get only a history event.
  - All 147 auto-skips since the cutover were daily habits, and all 7 still carry `FREQ=DAILY;INTERVAL=1` (core worker, read-only DB copy) **[L]**.
- **Decision**:
  - Keep "no Vikunja write for daily habits".
  - Day-specific habits take their next date from `occurrences?count=1`, as the first value after now.
  - A missing rule or a 401 skips the habit and emits a tick error/alert. The tick still completes for the other habits.

## R-007 — Allowlists are duplicated

- **Finding [V]**: The writable-field tuple exists twice: `scripts/intake/apply_reply.py:168-181` (it only "mirrors") and `scripts/vikunja/migrate_tasks.py:143-156`, which `migrate_date_only_due_dates.py:37-41` imports.
- **Decision**: Delete both allowlists. Callers send only their changed fields through `patch_task`, and the post-write check compares `repeat` before and after via `vikunja_rule.same_rule`.

## R-008 — Sync first-cycle behaviour

- **Finding [V]**:
  - `compute_divergences` (`diff.py:175+`) compares `task.get(f)` with `cached.get(f)`. A newly tracked key reads as `None` from the old cache, so every task with a rule would diverge once.
  - If the field is also downstream-affecting (`classify.py:38-45`), each divergence is unsafe and goes through the G-3 daily cap.
  - `state.py:32` hard-rejects a schema-version mismatch, so a version bump forces an operator re-bootstrap.
- **Decision**:
  - Add `repeat` and `repeats_from_current_date` to `TRACKED_TASK_FIELDS` and to `DOWNSTREAM_AFFECTING_FIELDS`.
  - Add a dict normaliser for `repeat`: drop `read_only`, lowercase, sort the `by_*` lists, drop zero or empty parts.
  - In `compute_divergences`, a cached entry that **lacks the key** adopts the live value with no divergence. This happens at most once per task per field, and is logged as a `baseline_seeded` count.
  - No schema bump.
- **Test**: the first cycle over a pre-upgrade cache produces 0 divergences and N seeds. The second cycle with one rule removed produces exactly 1 unsafe divergence.

## R-009 — Restore source for lost rules

- **Findings**:
  - The release baseline stores only a *hash* of the `(id, repeats, repeats_from_current_date)` rows (`scripts/deploy/vikunja_release/baseline.py:189-197`), not the values.
  - The pre-cutover rollback snapshot exists at `/data/services/vikunja/snapshots/20261030T081520Z/` (claude-owned, mode 700) **[L]**.
  - The core worker's read-only DB copy from 2026-11-19 is a second reference point.
- **Decision**:
  - `rule_inventory.py` reads a **read-only copy** of a snapshot DB, given with `--baseline-db` (opened as `file:…?mode=ro`, never the live DB), for the rule columns only.
  - It reads current state through the API (`GET /api/v2/tasks/{id}`).
  - For habits, the schedule's `rrule` is a second source.
  - It outputs task id, baseline rule, current rule, proposed restore value, source and status.
  - Output goes to a private state file plus a summary of ids and rule text only, posted on #1111. Titles are posted only for habit tasks, which already appear on #1111.
- **Expected result**: an empty or near-empty inventory (R-006, R-005).

## R-010 — Finished series detection

- **Findings [V][T]**:
  - When COUNT is exhausted, the task stays done and the rule is cleared (`tasks.go:2342-2347`).
  - When UNTIL has passed, the task stays done and the rule is kept (`tasks.go:2349-2351`).
  - A normal completion returns `done=false` with the due date advanced.
- **Decision**: `vikunja_rule.completion_outcome(before, after)` returns `advanced`, `series_ended` or `unexpected`, judged from the PATCH response (or the readback after a 304):
  - `advanced`: the task was repeating before, and after the write it is `done=false` with a later due date.
  - `series_ended`: after the write it is `done=true`.
  - `unexpected`: anything else.

  Habits and escalation record `series_ended` distinctly and never report it as "advanced" or "rescheduled".

> **Revised 2026-11-19 (post-plan review finding 2):** `done=true` alone does not prove a normal end. Evaluation refusal and horizon limits also leave a task Done. `series_ended` now requires exhaustion to be *expected before the write*: COUNT==1 locally, or UNTIL checked by preview. Otherwise the outcome is `unexpected`. See data-model.md.

## R-011 — Deploy path and docs

- **Findings**:
  - Helpers ride the office2 checkout's ff-only self-pull, and agent docs ride the 5-minute agent-prompt-sync and agent-skill-sync. No manifest is needed unless a cron, unit or service config changes (`docs/runbooks/deploy/discipline.md:19-25`; `office2-deploy-paths.md:72-91`).
  - Agent prompts are not hashed, so no rebaseline is needed (`audited-surfaces.json:12-23`).
  - Doc targets come from the signal-to-doc map: data-flow, credential, service, agent-prompt-changed, habits-flow-changed and runbook-added.
  - Stale 2.4.0 `/tasks/all` caveats remain at `vikunja-api/SKILL.md:311,465`, `task-intelligence/SKILL.md:188` and `felix-admin-escalation/TOOLS.md:14`.
  - `mutation-surfaces.json:177` pattern lacks PATCH and `/api/v2`.
  - No runbook exists for task-level repair.
- **Decision**:
  - No manifest; FR-023 is corrected in the spec.
  - Re-enabling the sweeper is Kent's go. The command `systemctl --user enable --now felix-habit-sweeper.timer` is run as `claude` (Persistent=true, so it catches up one missed run).
  - The new runbook is `docs/runbooks/vikunja-task-repair.md`.

## R-012 — Audit corrections

The re-check against code found the audit's rows 1–28 confirmed, with these corrections:

- **Row 10**: the allowlist is not shared (R-007).
- **Row 15**: it misses the retire-rollback write at `migrate_schedule.py:949-962`. This is moot because the tool is retired.
- **Rows 5/6**: the combined effect is in R-005.
- **Missed but harmless**: label attaches and deletes, task deletes, comments, and the non-recurring creates in `setup_goals.py` and `validate_felix_bot.py`. These are not rule-bearing writes.
- **Weekly report**: it ignores the schedule YAML. It classifies on `repeat_after` alone, so all habits are "other" today.
- **`tests/architectural/test_habits_history_canonical_read.py:63`** must drop `migrate_schedule`, or `test_allowlist_contains_no_stale_entries` fails.
