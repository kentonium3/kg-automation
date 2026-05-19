# Research: Engineering decisions

**Mission**: `habits-native-repeat-jsonl-state-01KS0M59`
**Phase**: 0 (research — resolve all tactical decisions before design)

This document records the engineering decisions for Phase 3 of ADR-0002 (habits migration). The ADR-0002 architectural decisions (Q1-Q8) are pre-settled; this research focuses on tactical implementation choices.

---

## D1 — Vikunja API client pattern

**Decision**: Each new helper in `scripts/habits/` implements its own `urllib`-based HTTP wrapper, mirroring the existing pattern in `scripts/vikunja/*.py`. No shared `api_client.py` library extracted in this mission.

**Rationale**:
- The existing 5 Vikunja helpers (`provision_felix_bot`, `validate_felix_bot`, `swap_vikunja_secrets`, `revoke_kent_tokens`, `setup_goals`) are each self-contained with their own `_http_request()` helper. Introducing a shared library mid-stream would be a refactor with cross-cutting impact.
- Each helper's HTTP needs are narrow (3-6 endpoints) and the duplication is < 30 lines per helper.
- Future extraction is possible as its own dedicated refactor mission.

**Rejected alternatives**:
- **Extract `scripts/vikunja/api_client.py`**: cleaner long-term but bigger scope creep for this mission. Defer.
- **Use the `requests` library**: violates NFR-006 (no new third-party deps).

---

## D2 — Workout task ID lookup

**Decision**: Add a one-shot operator tool `scripts/habits/identify_workout_task.py` that queries Vikunja for tasks matching `title ~ "workout"` (case-insensitive) among the 8 known habit task IDs. Outputs the task ID + title + project_id + label set on stdout. Operator runs this once during plan/pre-flight and manually edits `habits-schedule.yaml` with the result.

**Rationale**:
- Keeps `migrate_schedule.py` deterministic and config-driven — the schedule file is the contract.
- Separates "what's the current state?" (read-only inspection) from "apply changes" (mutation). Each can be tested independently.
- The operator gets a visible chance to verify the lookup result before authorizing changes.

**Rejected alternatives**:
- **Embed lookup in `migrate_schedule.py`**: couples discovery and mutation; harder to dry-run safely.
- **Operator manually queries Vikunja UI and copies the ID**: works, but human-error prone.

---

## D3 — Migration helper transaction model

**Decision**: Sequential single-task atomicity. Each PATCH/POST/DELETE is its own atomic operation. Rollback is per-task reversal from the snapshot (replay each `before` value back). No batch all-or-nothing transaction.

**Rationale**:
- Vikunja's REST API has no multi-task atomic-update endpoint. We work with what's there.
- The snapshot captures BEFORE state for every touched task before any mutation, so a partial-run failure mid-batch is fully recoverable: rollback restores all touched tasks (including the ones already migrated).
- Per-task atomicity matches the spec's NFR-004 5-minute rollback budget (11 tasks * ~5s each = ~55s, well under budget).

**Failure modes**:
- Mid-batch failure (e.g., network blip on PATCH 5 of 7): snapshot has all 7 BEFORE states; rollback replays the 4 already-applied PATCHes back to BEFORE, and tasks 5-7 are still BEFORE-state, so the system is clean.
- Mid-create failure (e.g., the Wednesday-create succeeds but Friday fails): snapshot includes `created_tasks` records as we go; rollback deletes already-created tasks.

**Rejected alternatives**:
- **Two-phase commit pattern**: overkill for ~11 single-task ops; Vikunja doesn't support 2PC anyway.
- **Stop on first failure without rollback**: leaves the system in a partial state requiring manual triage.

---

## D4 — record_completion three-write ordering

**Decision**: Order is (a) `POST /tasks/<id>` with `done=true` (Vikunja), (b) `PUT /tasks/<id>/comments` with `[Felix] <date> | <state>` (Vikunja comment), (c) `state_log.append("habits", record)` (local JSONL).

**Rationale**:
- Vikunja operations are the failure-prone steps (network + remote service). Fail fast on those.
- `state_log.append` is local + fcntl-locked + idempotent; it's the most reliable step. Doing it last ensures the JSONL only records completions that actually landed in Vikunja.
- If (a) succeeds but (b) fails: the task is marked done in Vikunja but no comment exists. Reconcile will detect this next tick (done=true with no JSONL entry; backfill with `source=vikunja-ui`). The lost comment is a UI-only loss; the canonical state log catches up.
- If (a) and (b) succeed but (c) fails: rare (state_log is local). Reconcile detects (Vikunja done=true, no JSONL) and backfills. The agent's exit-nonzero surfaces the issue.

**Idempotency check first**: BEFORE any of the three writes, call `state_log.read("habits", task_id=<id>, date=<date>)`. If a `state=complete` entry exists, the helper exits 0 immediately (no writes). This avoids re-posting Vikunja `done=true` (which is idempotent at the API level but generates redundant audit-log entries on the Vikunja side).

**Rejected alternatives**:
- **Write state_log first, then Vikunja**: records a "complete" event that may not have actually committed in Vikunja. Bad signal for downstream consumers.
- **All three in parallel**: races + harder to attribute failures.

---

## D5 — Testing approach

**Decision**: Three test layers.

1. **Unit tests with mocked urllib** (`pytest tests/habits/`): cover all logic — schedule.yaml parsing, snapshot capture, idempotency checks, dry-run output, rollback replay, drift detection. Mocked `urllib.request.urlopen` returns canned `MagicMock` responses. ~85% coverage from this layer alone.

2. **Smoke tests against `scripts.common.state_log`** (real local I/O, monkey-patched `STATE_DIR`): cover the integration with Phase 2's library. Test `record_completion.py` writes through to the JSONL correctly.

3. **Canary live-probe against a sandbox Vikunja task** (operator-driven during Phase 3 canary, not in CI): exercise `record_completion.py` against a single non-production task ID (e.g., the project 13 test-target used in Phase 1 WP02 validation). Verify the three-write path produces the expected Vikunja state + JSONL entry. Document any new API behaviors discovered as an addendum to the Verified API gotchas in `docs/design/research/vikunja-task-model-research.md`.

**Rationale**:
- Per the #317 lesson: mock-only tests miss API contract bugs. Live-probe must be in the test mix.
- Per Kent's "live integration test modes declined" memory: don't propose `--live-probe` flags that depend on Tailscale for CI runs. Keep the canary operator-driven, not CI-automated.
- 85% coverage (NFR-005) is achievable from layers 1+2 alone; layer 3 is operational verification, not a CI gate.

**Rejected alternatives**:
- **CI integration tests against live Vikunja**: rejected per Kent's standing preference; adds Tailscale + credentials to test runs.
- **Mock-only with no canary**: this is the Phase 1 pattern that produced #317. Don't repeat.

---

## D6 — Idempotency mechanism

**Decision**: For both `migrate_schedule.py` and `record_completion.py`, idempotency is tuple-keyed via `state_log` or explicit BEFORE-state checks.

- **migrate_schedule**: before each PATCH, compare current Vikunja state against the schedule's intended state. If they match (e.g., `repeat_after` already equals 86400), skip the PATCH and log "task <id> already matches target schedule". Snapshot still captures the BEFORE state for completeness.
- **record_completion**: idempotency key `(task_id, date, state)` per Phase 2 contract. Pre-flight read of state_log; if entry exists, exit 0 without writes.
- **reconcile_completions**: idempotency by definition (read Vikunja state, append backfill IF MISSING from JSONL). Re-running reconcile multiple times in a row is a no-op after the first run.

**Rationale**: Tier 2 work demands re-runnability. An operator hitting Ctrl-C mid-migration and re-running should see the helper complete cleanly, not error out or re-apply changes.

---

## D7 — Drift handling in reconcile

**Decision**: `reconcile_completions.py` reports drift on stdout (one line per drift) but exits 0 unless a hard failure occurs (e.g., Vikunja API down). Drift is operator-actionable, not a script failure.

**Format**:
```
DRIFT: task_id=14 (Wake at 5:00 AM): JSONL says complete for 2026-05-19 but Vikunja shows done=false
```

**Rationale**:
- Drift indicates a conflict between sources of truth (JSONL + Vikunja). Auto-resolution risks data loss either way.
- The operator (or Phase 5+ self-observation agents) decides which side wins. The script's job is to surface, not arbitrate.
- Exit 0 keeps reconcile usable as a cron pre-flight — a drift entry shouldn't block the morning check-in from running.

**Rejected alternatives**:
- **Auto-resolve toward Vikunja (overwrite JSONL)**: loses the historical record of when the JSONL claim was made.
- **Auto-resolve toward JSONL (re-PATCH Vikunja `done=true`)**: silently overrides operator UI actions (e.g., Kent un-ticking).
- **Exit non-zero on drift**: makes reconcile a hard gate, but drift is informational; gating on it would block the cron.

---

## D8 — Config validation in migrate_schedule

**Decision**: Full YAML schema validation BEFORE any HTTP call. Refuse to run if:
- Required keys missing
- `op` values not in `{patch, create, retire}`
- `task_id` not present for `patch` and `retire` ops
- `attributes.title` not present for `create` ops
- `schedule.repeat_after` is negative or zero (zero would mean "not recurring" — explicit and intentional, but the spec disallows it for this mission)
- `schedule.repeat_mode` is not in `{0, 1, 2}`

On validation failure: print the offending operation index + the specific field error on stderr, exit 2 (usage error per `contracts/cli.md`).

**Rationale**:
- Validating before any HTTP call means a bad config never touches production state.
- Per-op error messages let the operator fix the YAML quickly without guessing.

**Rejected alternatives**:
- **Validate-as-you-go (mid-mutation)**: same failure ergonomics as no-validation; bad config can already have changed state.

---

## D9 — Workout task replacement due dates

**Decision**: When generating the 3 new MWF strength-training tasks, set `due_date` to the next Monday/Wednesday/Friday at or after the migration run date, at 08:00 UTC. The migration helper computes these defaults; operator can override via `habits-schedule.yaml` if a specific cycle is desired.

**Rationale**:
- "Next Mon/Wed/Fri" is the operator's likely intent (start the new schedule immediately).
- 08:00 UTC is the existing morning check-in window's mid-point (the check-in fires at 7am ET = 11:00 UTC, plus checks throughout the day). The due_date is for surfacing-on-the-day; it doesn't need to be a specific time.

**Computation**:
- Run date = today UTC.
- Next Monday = run_date + ((0 - run_date.weekday()) mod 7) days; if 0, today is Monday and "next Monday" = today.
- Same for Wed (target weekday 2) and Fri (target weekday 4).

**Rejected alternatives**:
- **Hardcode specific dates in the YAML**: brittle if the operator runs the migration on a different day than expected.
- **Use the workout task's existing due_date for all 3**: would surface all 3 on the same day, defeating the MWF spread.

---

## D10 — Verified API gotchas — known behaviors to honor

**Decision**: Phase 3 helpers explicitly handle the 4 Vikunja API quirks documented in the Verified API gotchas appendix of `docs/design/research/vikunja-task-model-research.md`:

| Gotcha | Phase 3 helper that hits it | Honored how |
|---|---|---|
| G1: share payload `user_id` is username string | none (not sharing projects in this mission) | N/A |
| G2: share-list response uses `username` | none | N/A |
| G3: comment attribution lives on `author.username` not `created_by` | `record_completion.py` verify-readback (if added); canary smoke test verifies `comment.author.username == "felix-bot"` | Explicit check |
| G4: comment-create endpoint is `PUT` not `POST` | `record_completion.py` write (b) — comment creation | Use PUT |

These are all in the public research doc — the implementer should re-read that doc when starting WP work.

**Rationale**: Don't repeat the #317 mistakes. Lessons from the Phase 1 live run apply here too.

---

## Summary

Ten engineering decisions documented, all aligned with the spec's NFRs/constraints + ADR-0002 + prior phases' lessons. No `[NEEDS CLARIFICATION]` markers remain. Ready for Phase 1 design artifacts.
