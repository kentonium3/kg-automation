# Contract: `scripts/habits/set_due_dates.py`

**FR**: FR-003 (Due-date setting helper)
**Invocation tier**: Helper
**Run frequency**: Once per `habits-morning-checkin` cron invocation

---

## Purpose

For each scheduled habit ID, set its Vikunja `due_date` to end-of-day Eastern Time so the habit appears in Vikunja's "Today" filter without being treated as overdue at the moment the morning cron fires. Tolerant of per-habit failures: continues processing remaining habits on individual error; aggregates results.

Exists because the current agent prompt encodes the rule "never use UTC `Z` suffix; compute the current ET offset via `TZ=America/New_York date +%:z`; format as `YYYY-MM-DDT23:59:59<offset>`" — high-criticality (off-by-one causes habits to appear overdue, which is exactly the bug #112 fixed and we MUST NOT regress), high hallucination risk (format easily mangled).

---

## CLI

```
python3 scripts/habits/set_due_dates.py --habit-ids <comma-separated-int-list>
                                        --iso-eod-et <ISO-8601-with-explicit-offset>
                                        [--vikunja-token-path <path>]
                                        [--vikunja-base-url <url>]
                                        [--dry-run]
```

| Flag | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `--habit-ids` | string | YES | — | Comma-separated integers (e.g., `123,124,125`). From `query_active_habits.py` output. |
| `--iso-eod-et` | string | YES | — | End-of-day-ET ISO timestamp. From `compute_today.py` output. Validated to NOT end with `Z`. |
| `--vikunja-token-path` | path | No | `/data/services/openclaw/secrets/vikunja-api` | Override for testing. |
| `--vikunja-base-url` | URL | No | `https://office2.tail0f5f56.ts.net/api/v1` | Override for testing. |
| `--dry-run` | flag | No | False | Don't actually PUT to Vikunja; print what would happen. |

---

## Output

### stdout (JSON object, then SUMMARY line)

```json
{
  "succeeded": [123, 124],
  "failed": [{"id": 125, "reason": "HTTP 500: Internal Server Error"}]
}
```

```
SUMMARY: total=3 succeeded=2 failed=1
```

(In `--dry-run` mode, the same shape is emitted with `succeeded` listing all habit IDs and `failed: []`, plus a `(DRY-RUN)` suffix on the SUMMARY line.)

### stderr

Per-failure stderr line:
```
ERROR: habit 125 PUT failed: HTTP 500: Internal Server Error
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | All habit due_dates set successfully (or `--dry-run` completed) |
| 1 | At least one habit failed (partial state); succeeded subset in stdout `succeeded` array |
| 2 | Usage error (missing required flag, `--iso-eod-et` ends with `Z`, malformed habit IDs) |

**Critical**: exit code 1 with non-empty `succeeded` array communicates **partial success**. The calling agent's failure handling (per [conventions § 6](../../../docs/design/helper-script-conventions.md)) checks both exit code AND `succeeded` array to determine whether to proceed.

---

## Side effects

**MUTATING**: PUTs `{"due_date": "<iso_eod_et>"}` to `/api/v1/tasks/{habit_id}` for each habit ID.

**Idempotency**: PUT with the same `due_date` value is idempotent on the Vikunja side — re-running yields the same state. Helper does NOT check-before-write (no GET); the PUT is the source-of-truth operation.

**`--dry-run`** mode performs no mutations.

---

## Validation rules (#112 regression-prevention)

- `--iso-eod-et` value MUST contain an explicit numeric offset (`-04:00` or `-05:00`). Validated by regex `^\d{4}-\d{2}-\d{2}T23:59:59[+-]\d{2}:\d{2}$`. If it ends with `Z`, helper exits 2 with usage error.
- The helper does NOT compute or transform the timestamp; it takes whatever `compute_today.py` produced and uses it verbatim. Decoupling validation from computation makes the regression-prevention contract clearer.

---

## Test coverage (NFR-005)

Tests at `tests/habits/test_set_due_dates.py`:

| Test | Scenario |
|---|---|
| `test_happy_path_all_succeed` | Mock Vikunja: PUT 200 on all 3 habits; exit 0, `succeeded` has all 3, `failed` empty |
| `test_partial_failure` | Mock: PUT 200 on 2, PUT 500 on 1; exit 1, `succeeded` has 2, `failed` has 1 with reason |
| `test_all_fail` | Mock: PUT 500 on all 3; exit 1, `succeeded` empty, `failed` has 3 |
| `test_dry_run_makes_no_calls` | `--dry-run` flag; mock asserts no HTTP calls made; exit 0 |
| `test_z_suffix_rejected` | `--iso-eod-et 2026-05-15T23:59:59Z`; exit 2 with regression-prevention message |
| `test_malformed_iso` | `--iso-eod-et garbage`; exit 2 |
| `test_idempotency` | Mock PUT 200; run helper twice with same input; same result both times, second run does not error |
| `test_empty_habit_ids` | `--habit-ids ""`; exit 0 with empty arrays (no work; not an error) |
