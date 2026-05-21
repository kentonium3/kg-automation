---
work_package_id: WP03
title: record_completion (atomic three-write)
dependencies:
- WP02
requirement_refs:
- C-001
- FR-002
- FR-004
- FR-010
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-21T17:45:30+00:00'
subtasks:
- T009
- T010
- T011
agent: "claude:opus:python-implementer:implementer"
shell_pid: "94862"
history:
- at: '2026-05-21T17:45:30+00:00'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/escalation/
execution_mode: code_change
mission_id: 01KS5R4D79WQQWY2MCHZVCT85G
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
owned_files:
- scripts/escalation/record_completion.py
- tests/escalation/test_record_completion.py
tags: []
---

# WP03 — record_completion (atomic three-write)

## Objective

Implement the atomic three-write helper that every live escalation event flows through: agent sends a Level alert, Kent replies with snooze/done/dismiss, reconcile emits a synthetic record. Vikunja side-effect FIRST (WhatsApp + `[Felix-Escalation]` comment + done PATCH where applicable), JSONL append SECOND. During the soak window per C-001, both the v1 comment AND the new JSONL record are written.

## Context

- **Mission spec**: FR-002 (atomic three-write), FR-004 (snooze_until at write-time), FR-010 (felix-bot identity), C-001 (v1 parity during soak)
- **Research**: D6 (three-write ordering rationale), D4 (snooze_until TZ + write-time), D11 (comment-write parity during soak)
- **API contract**: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/api.md` — `record_event`, `idempotent_record_event`, exception types
- **CLI contract**: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/cli.md` — exit codes 0/1/2/3
- **Habits Phase 3 precedent**: `scripts/habits/record_completion.py` (commit 231e8801..) — same three-write pattern. Reuse the HTTP wrapper structure.
- **Existing SKILL.md vocabulary**: `scripts/openclaw/skills/escalation/SKILL.md` § 3 "Escalation Comment Format" — the v1 comment vocabulary written during soak.
- **Dependency**: WP02 (record_event indirectly validates by re-deriving state; not strictly required but tests should verify post-write derive_state correctness)
- **Phase 2 library**: `scripts/common/state_log.py` `append`/`read` — consumed as-is.
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T009 — Implement `scripts/escalation/record_completion.py`

**Purpose**: Atomic three-write per research D6. Vikunja side-effect FIRST, JSONL second.

**Steps**:

1. Module docstring describing the three-write contract + per-event_type Vikunja side-effects.
2. Imports: stdlib only (`argparse`, `json`, `sys`, `urllib.request`, `urllib.error`, `datetime`, `zoneinfo`, `pathlib`, `typing`). Plus `scripts.common.state_log`, `scripts.common.state_log_schema`, `scripts.escalation.schema`.
3. Module constants per contracts/api.md:
   ```python
   DEFAULT_BASE_URL = "http://100.92.197.90:3456/api/v1/"
   DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")
   HTTP_TIMEOUT_SECONDS = 30
   JSONL_STATE_DIR = Path("/data/services/openclaw/state/escalation")
   LOCAL_TZ = zoneinfo.ZoneInfo("America/New_York")
   ```
4. Define custom exceptions:
   ```python
   class VikunjaError(Exception): ...
   class StateLogError(Exception): ...
   ```
   (`EscalationSchemaError` re-imported from `scripts.escalation.schema`.)
5. Helper `_read_token(token_path: Path) -> str` — reads token, strips, raises `FileNotFoundError` on missing.
6. Helper `_http_request(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, dict]` — wraps `urllib.request`. Returns `(status_code, parsed_json)`. Raises `VikunjaError` on non-2xx, network errors.
7. Helper `_jsonl_path_for_record(record: dict) -> Path`:
   - Construct `<JSONL_STATE_DIR>/project-<project_id>-escalation-history.jsonl`.
   - Note: D2 specifies slug-based filenames; the slug derivation requires a Vikunja API call to fetch project title. For simplicity and offline-test compatibility, T009 uses `project-<id>` as the filename stem. T010's CLI may optionally invoke a slug-resolution call. This is a planning decision: KEEP IT SIMPLE in T009 — `project-<id>-escalation-history.jsonl`.
8. Helper `_today_local_date_str() -> str` — `datetime.now(LOCAL_TZ).date().isoformat()`.
9. Helper `_format_v1_comment(record: dict) -> str` — per data-model Entity 3 reverse mapping. For each event_type, produce the v1 `[Felix-Escalation] YYYY-MM-DD | state | disposition` string. Handles `level_sent` → `level-N | sent`, `snoozed` → `snoozed:Nd | acknowledged`, etc.
10. Implement `record_event(record: dict, *, base_url=..., token_path=...) -> dict`:
    - **Step 1**: validate via `scripts.escalation.schema.validate_event_params(record)` AND `scripts.common.state_log_schema.validate_record("escalation", record)`. Either failure raises `EscalationSchemaError` (no writes attempted).
    - **Step 2 (Vikunja side-effect)**:
      - For `state="done"`: PATCH `/tasks/{task_id}` with `{"done": true}`. Then PUT comment.
      - For `state="rescheduled"`: PATCH `/tasks/{task_id}` with `{"due_date": "<reschedule_to>T00:00:00Z"}`. Then PUT comment.
      - For `state="level_sent"`: PUT comment ONLY (WhatsApp sending is outside this helper's scope — the agent or upstream caller does that). The comment write is the visible-in-Vikunja signal.
      - For `state="snoozed"`, `state="dismissed"`: PUT comment ONLY.
      - All side-effects use the felix-bot token (loaded from `token_path`).
      - On `VikunjaError`: re-raise immediately. No JSONL write. Helper exits via raised exception.
    - **Step 3 (JSONL append)**:
      - Compute `_jsonl_path_for_record`.
      - Call `scripts.common.state_log.append(...)` — but state_log's API may take `domain` + record, with the file location determined by `state_log`'s internal config. **If `state_log.append` doesn't accept a custom path, T009 should write the JSONL line directly using the same atomic three-write pattern (`open(path, 'a') as f: f.write(json.dumps(record) + '\n'); f.flush(); os.fsync(f.fileno())`).** Read `scripts/common/state_log.py` first and use whichever path is correct.
      - On any IOError: raise `StateLogError`. Vikunja already committed — the caller (CLI) logs and exits with code 2 for operator triage.
    - Return `{"ok": True, "jsonl_path": str(path), "vikunja_actions": [...], "deduped": False}`.
11. Implement `idempotent_record_event(record: dict, ...) -> dict`:
    - Pre-check via `state_log.read("escalation", task_id, date, state)` (or equivalent JSONL scan).
    - If matching record exists: return `{"ok": True, "deduped": True, ...}`.
    - Else: call `record_event(...)`.
12. Helper `_compute_snooze_until(snooze_days: int) -> str` — per D4. Returns `(today_local + timedelta(days=snooze_days)).isoformat()`.

**Files**:
- `scripts/escalation/record_completion.py` (new, ~400 lines)

**Validation**:
- [ ] No third-party imports.
- [ ] `python3 -c "from scripts.escalation.record_completion import record_event, idempotent_record_event, VikunjaError, StateLogError; print('ok')"` prints `ok`.
- [ ] Three-write ordering is testable via mock call-sequence assertions.

---

### T010 — CLI surface for `record_completion`

**Purpose**: Per contracts/cli.md. The OpenClaw skill invokes this CLI.

**Steps**:

1. Add `def main(argv=None) -> int` to `record_completion.py`.
2. argparse with all flags from contracts/cli.md:
   - `--task-id`, `--project-id`, `--title`, `--date`, `--state`, `--source` (all required unless stdin)
   - `--level`, `--snooze-days`, `--reschedule-to`, `--reason`, `--note` (conditionally required per `--state`)
   - `--idempotent` (flag), `--no-vikunja` (flag), `--base-url`, `--token-path`
3. Alternatively accept full JSON record on stdin if no `--task-id` provided. (Mirrors habits Phase 3 CLI.)
4. Build the record dict:
   - Set `domain="escalation"`.
   - Compute `timestamp` as `datetime.now(timezone.utc).isoformat()`.
   - For `--state snoozed`: compute `snooze_until` via `_compute_snooze_until(args.snooze_days)`.
5. Call `record_event` or `idempotent_record_event` based on `--idempotent`.
6. Exit codes per contracts/cli.md:
   - 0: success
   - 1: `VikunjaError` (helper logs stderr with step name + HTTP code)
   - 2: `StateLogError` (Vikunja already committed; operator triages)
   - 3: validation or usage error (`EscalationSchemaError`, argparse errors, file-not-found on token)
7. Stdout on success: structured JSON per contracts/cli.md.
8. Stderr on failure: one structured line naming the failed step.
9. `if __name__ == "__main__": sys.exit(main())`.

**Files**:
- `scripts/escalation/record_completion.py` (extended with CLI, +~120 lines)

**Validation**:
- [ ] `python3 -m scripts.escalation.record_completion --help` prints help, exits 0.
- [ ] Missing required flag for the chosen `--state` exits 3 with clear error.

---

### T011 — Tests for `record_completion`

**Purpose**: Cover the three-write contract end-to-end. Verify ordering, idempotency, and failure modes.

**Steps**:

1. Create `tests/escalation/test_record_completion.py`.
2. Use the conftest fixtures (`mock_urlopen`, `mock_state_log_dir`, `make_jsonl_record`).
3. Test cases:
   - **Happy paths per event_type** (verify Vikunja-first ordering):
     - `test_record_level_sent_writes_comment_then_jsonl` — mock_urlopen succeeds; assert comment PUT happened before JSONL line was written. Use `mock_urlopen.mock_calls` ordering check.
     - `test_record_snoozed_computes_snooze_until_at_write_time` — `snooze_days=3`; assert the persisted JSONL has `snooze_until = today + 3 days` in America/New_York TZ. Monkeypatch `datetime.now(LOCAL_TZ)`.
     - `test_record_done_patches_task_then_comments` — verify PATCH /tasks/{id} with `done=true` precedes comment PUT.
     - `test_record_rescheduled_patches_due_date_then_comments` — verify PATCH /tasks/{id} with new `due_date`.
     - `test_record_dismissed_writes_comment_only` — no PATCH; one PUT.
   - **Three-write ordering invariant** (research D6):
     - `test_vikunja_failure_no_jsonl_write` — mock_urlopen raises `URLError`. Assert (a) `VikunjaError` raised, (b) JSONL file is empty after.
     - `test_jsonl_failure_after_vikunja_commit` — mock_urlopen succeeds; monkeypatch the JSONL write path to raise IOError. Assert (a) `StateLogError` raised, (b) Vikunja PUT was called once.
   - **Idempotency**:
     - `test_idempotent_record_event_no_op_on_duplicate` — pre-populate JSONL with a matching record. Call `idempotent_record_event`. Assert no Vikunja calls AND no new JSONL line.
     - `test_idempotent_record_event_writes_on_no_match` — empty JSONL. Call. Assert normal three-write happens.
   - **Schema validation**:
     - `test_invalid_record_raises_schema_error_no_writes` — record with missing `level` for `state="level_sent"`. Assert `EscalationSchemaError` AND no mock_urlopen calls.
   - **felix-bot identity (FR-010)**:
     - `test_request_uses_felix_bot_token` — assert the Authorization header is `Bearer <token>` where token matches the token file content.
   - **v1 comment format (data-model Entity 3 reverse)**:
     - `test_comment_format_level_1_sent` — record with `state="level_sent", level=1` → comment body contains `level-1 | sent`.
     - `test_comment_format_snoozed_3d` — record with `state="snoozed", snooze_days=3` → comment body contains `snoozed:3d | acknowledged`.
     - `test_comment_format_rescheduled` — record with `state="rescheduled", reschedule_to="2026-06-15"` → comment body contains `rescheduled:2026-06-15 | acknowledged`.
4. CLI smoke tests:
   - `test_cli_exit_code_3_on_missing_required` — invoke `main(['--task-id', '1', ...])` missing `--level`; assert returns 3.
   - `test_cli_exit_code_1_on_vikunja_failure` — happy CLI invocation but mock_urlopen raises; assert returns 1.
   - `test_cli_exit_code_0_on_success` — happy invocation; assert returns 0 + stdout has `"ok": true`.
5. Coverage target: ≥85% line + branch.

**Files**:
- `tests/escalation/test_record_completion.py` (new, ~400 lines, ~16 test cases)

**Validation**:
- [ ] `pytest tests/escalation/test_record_completion.py -v` all green.
- [ ] Coverage ≥85% line + branch on `scripts.escalation.record_completion`.
- [ ] At least one test directly asserts Vikunja-call-then-JSONL-write ordering via mock call sequence.

---

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Execution worktree allocated per `lanes.json` after `finalize_tasks`.

## Test Strategy

pytest. All HTTP mocked via `mock_urlopen` fixture (no live Vikunja calls in CI). JSONL writes mocked or directed to `tmp_path` via `mock_state_log_dir`. Coverage ≥85% on the helper.

## Definition of Done

- [ ] T009-T011 subtasks complete with all validations green.
- [ ] `pytest tests/escalation/test_record_completion.py -v` passes.
- [ ] Coverage ≥85% line + branch.
- [ ] Three-write ordering invariant verified by at least one test using mock call-sequence ordering.
- [ ] CLI exit codes match contracts/cli.md.
- [ ] `_format_v1_comment` produces strings that the existing SKILL.md regex parsers can roundtrip (verified via test against the SKILL.md vocabulary table).

## Risks

- **Three-write ordering**: an implementer-introduced reordering (JSONL first, Vikunja second) is the dominant failure mode. Test must assert mock call ordering.
- **C-001 parity write**: easy to forget the v1 comment PUT during the soak. The implementer MUST keep it in for every event_type that previously wrote a comment.
- **TZ handling for snooze_until**: snooze arithmetic uses America/New_York. Tests must monkeypatch the clock; do NOT use real `date.today()`.
- **state_log.append API shape**: if Phase 2's library doesn't accept a custom output path, T009 must write the JSONL line directly. Read `scripts/common/state_log.py` first.

## Reviewer Guidance

1. Verify three-write ordering with explicit mock call-sequence assertion.
2. Verify the v1 comment vocabulary matches data-model Entity 3 reverse mapping.
3. Verify `_compute_snooze_until` uses America/New_York TZ (FR-004).
4. Verify `EscalationSchemaError` is raised BEFORE any side-effects on validation failure.
5. Verify exit codes 0/1/2/3 align with contracts/cli.md.
6. Coverage report ≥85%.

## Implementation Command

```bash
spec-kitty agent action implement WP03 --mission migrate-escalation-to-jsonl-state-model-01KS5R4D --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-21T20:14:43Z – claude:opus:python-implementer:implementer – shell_pid=94862 – Started implementation via action command
- 2026-05-21T20:25:33Z – claude:opus:python-implementer:implementer – shell_pid=94862 – Ready for review — three-write contract verified via mock call sequence, 88% coverage. WP04 review-cycle artifacts in kitty-specs/ are unrelated to WP03 (owned files: scripts/escalation/record_completion.py + tests/escalation/test_record_completion.py committed at 6cc7ec81)
