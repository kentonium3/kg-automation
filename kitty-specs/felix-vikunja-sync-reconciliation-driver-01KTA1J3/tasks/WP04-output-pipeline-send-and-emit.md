---
work_package_id: WP04
title: 'Output pipeline: WhatsApp send + conflict-event emit'
dependencies:
- WP03
requirement_refs:
- FR-002
- FR-004
- FR-006
- FR-007
- FR-010
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T014
- T015
- T016
- T017
history:
- at: '2026-06-04T19:53:57Z'
  by: spec-kitty.tasks
  note: Created WP04 from plan.md + contracts/conflict-event-schema.md + contracts/whatsapp-send.md
authoritative_surface: scripts/sync/
execution_mode: code_change
owned_files:
- scripts/sync/send_whatsapp.py
- scripts/sync/emit.py
- tests/sync/test_send_whatsapp.py
- tests/sync/test_emit.py
tags: []
---

# WP04 — Output pipeline: WhatsApp send + conflict-event emit

## Objective

Format and deliver unsafe-class WhatsApp messages via the established deterministic `openclaw agent --deliver --channel whatsapp` subprocess pattern. Append every classified event (`auto_resolved` AND `unsafe_to_auto_resolve`) to the JSONL log with a deterministic `event_id` that makes re-runs idempotent. Apply the three guards from WP03 in order before any unsafe delivery.

After this WP, downstream WP05 can:
- Call `send_whatsapp.send(message=..., recipient=..., dry_run=...)` to deliver a formatted message.
- Call `emit.emit_events(classified_conflicts, ...) → list[ConflictEvent]` to commit events to the log and dispatch deliveries.

## Context

Research finding from `research.md` Unknown 1 confirms the deterministic WhatsApp send pattern: `subprocess.run(["openclaw", "agent", "--agent", "main", "--message", msg, "--deliver", "--channel", "whatsapp", "--to", recipient], ...)`. Same pattern as `scripts/obsidian/sync-heartbeat.py:114-138`. No new helper is built — only the WP04-specific wrapper that turns a `ConflictEvent` into the message string and invokes the subprocess.

The 15-field event schema is documented in `contracts/conflict-event-schema.md`. The deterministic `event_id` is computed from `sha256(layer|entity|field|ts|canonical_value)[:16]`. WP03 already implemented `event_id_stem` (without the timestamp and value); WP04 extends it to the full `event_id`.

**Branch Strategy**: planning_base_branch = `main`; merge_target_branch = `main`. Lane worktree per WP; commits inside the worktree.

## Implementation command

```bash
spec-kitty agent action implement WP04 --agent <name>
```

Depends on WP03.

---

## Subtask T014 — `scripts/sync/send_whatsapp.py`: subprocess wrapper + 3-line message formatter

**Purpose**: Provide the deterministic-script WhatsApp send entry point, plus the formatter that turns a `ConflictEvent` into the 3-line message body.

**Steps**:

1. Define `@dataclass(frozen=True) class SendResult`:

   ```python
   @dataclass(frozen=True)
   class SendResult:
       success: bool
       exit_code: int
       stderr: str | None
   ```

2. Implement `send(*, message: str, recipient: str, agent: str = "main", timeout_seconds: int = 60, dry_run: bool = False) → SendResult`:

   - **Dry-run path**: if `dry_run=True`, write `"[whatsapp send: dry-run] {message[:200]}"` to stderr and return `SendResult(True, 0, None)`. No subprocess invocation.
   - **Live path**: `subprocess.run` with the exact argument list documented in `contracts/whatsapp-send.md`:

     ```python
     subprocess.run(
         [
             "openclaw", "agent",
             "--agent", agent,
             "--message", message,
             "--deliver",
             "--channel", "whatsapp",
             "--to", recipient,
         ],
         capture_output=True,
         text=True,
         timeout=timeout_seconds,
     )
     ```

   - **Outcome mapping**:
     - Exit 0 → `SendResult(True, 0, None)`
     - Exit nonzero → `SendResult(False, exit_code, stderr_text)`
     - `subprocess.TimeoutExpired` → `SendResult(False, -1, "timeout after {N}s")`
     - `FileNotFoundError` → `SendResult(False, -2, "openclaw binary not found on PATH")`

   - **Never raises**. All failure modes return a SendResult.

3. Implement `format_message(event: ConflictEvent, task_title: str | None) → str`:

   - Build the 3-line shape per `contracts/whatsapp-send.md` § Message shape.
   - Line 1: `"🟠 Vikunja edit (unsafe)"` if `"uc3_downstream_behavior" in event.unsafe_reasons` else `"🟡 Vikunja edit (caution)"`.
   - Line 2: `f"Task #{event.vikunja_entity_id}: {truncate(task_title, 60)}"`. If `task_title` is None or task is privacy-redacted → `"<redacted>"`.
   - Line 3: `f"{event.diff_field}: {short_repr(event.felix_cached_value)} → {short_repr(event.vikunja_value)}"`. For privacy-redacted: `"<redacted>: <redacted> → <redacted>"`.
   - `short_repr`: `json.dumps(value)` truncated to 30 chars with `…` suffix.
   - Pure function. No I/O.

4. Export `WHATSAPP_RECIPIENT_ENV_VAR = "FELIX_WHATSAPP_RECIPIENT"` and a helper `def resolve_recipient(cli_arg: str | None) → str` that returns CLI > env > raise OSError if unset.

**Files**:
- `scripts/sync/send_whatsapp.py` (~210 lines)

**Reference precedent**: `scripts/obsidian/sync-heartbeat.py:114-138`. EXACT same subprocess argument order.

**Files this WP must NOT touch**: `scripts/obsidian/sync-heartbeat.py` (existing — DO NOT modify even though we're studying its pattern).

**Validation**:
- [ ] Subprocess argument list matches `sync-heartbeat.py:121-131` byte-for-byte (excluding the agent name and recipient values)
- [ ] `dry_run=True` does not invoke subprocess (test asserts `mock_run.call_count == 0`)
- [ ] All four failure modes map to documented exit codes
- [ ] `format_message` is pure (test runs it twice with same input → same output)

---

## Subtask T015 — `scripts/sync/emit.py`: event_id + JSONL append + guard application + delivery

**Purpose**: Orchestrate the emit phase. For each `ClassifiedConflict`, apply guards, build the event row, append to JSONL, optionally deliver.

**Steps**:

1. Define `@dataclass(frozen=True) class ConflictEvent` matching the 15-field schema in `contracts/conflict-event-schema.md`. All fields strongly typed.

2. Implement `compute_event_id(layer: str, entity_id: int, field: str, ts_observed_utc: str, vikunja_value: Any) → str`:

   ```python
   def compute_event_id(layer, entity_id, field, ts_observed_utc, vikunja_value):
       canonical = json.dumps(vikunja_value, sort_keys=True, separators=(",", ":"))
       payload = f"{layer}|{entity_id}|{field}|{ts_observed_utc}|{canonical}"
       return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
   ```

3. Implement `build_event(classified: ClassifiedConflict, tick_id: str, ts_observed_utc: str, delivery_status: str, delivery_error: str | None) → ConflictEvent`:
   - Populate all 15 fields per schema.
   - `event_id` from compute_event_id.
   - `schema_version = 1`.
   - `router_route_set = ("whatsapp",) if classified.class_ == "unsafe_to_auto_resolve" else ()`.
   - `vikunja_updated_at = classified.candidate.vikunja_updated_at`.

4. Implement `validate_event(event: ConflictEvent) → None`:
   - Check all 15 fields populated.
   - `event_id` is 16-char lowercase hex.
   - `delivery_status` ∈ documented enum.
   - `delivery_error` is None iff `delivery_status != "error"`.
   - Raise `OSError` on failure (cycle error per spec FR-010).

5. Implement `emit_events(classified_conflicts: list[ClassifiedConflict], tick_id: str, ts_observed_utc: str, jsonl_path: Path, task_cache: TaskCacheRecord, guard_state: GuardState, recent_events: list[ConflictEvent], send_callable: Callable[[str, str], SendResult], recipient: str, cycle_started_at: datetime) → tuple[list[ConflictEvent], GuardState]`:

   - Sort `classified_conflicts` by `candidate.vikunja_updated_at` ascending (stable G-1 behavior on multi-field divergences).
   - For each classified:
     - If class is `auto_resolved`: build event with `delivery_status="not_unsafe"`, validate, append to JSONL, add to result list. (G-2 et al do not apply to auto_resolved.)
     - If class is `unsafe_to_auto_resolve`:
       - Call `guards.apply_guards(...)`.
       - If `decision="suppress"`: build event with `delivery_status=f"suppressed_by_{guard_id}"`, validate, append, add to result.
       - If `decision="approve"`:
         - Build message via `send_whatsapp.format_message(event_so_far, task_title)`.
         - Call `send_callable(message=msg, recipient=recipient)` → SendResult.
         - If `result.success`: build event with `delivery_status="delivered"`, `delivery_error=None`. Increment `guard_state.g3_daily_cap.unsafe_pings_sent_today`.
         - Else: build event with `delivery_status="error"`, `delivery_error=result.stderr`.
         - Validate, append, add to result.
   - Return `(committed_events, updated_guard_state)`.

6. Implement helper `read_recent_events(jsonl_path: Path, lookback_hours: int = 24, now_utc: datetime) → list[ConflictEvent]`:
   - Read the entire JSONL file (acceptable at current scale).
   - Parse each line; skip malformed (defensive).
   - Filter to events within the lookback window by `ts_observed_utc`.
   - Return as a list of ConflictEvent.
   - Note: at log sizes >100MB this becomes slow; documented in `contracts/conflict-event-schema.md` as optimization for future work.

7. **Privacy redaction**: when `event.layer == "status_and_task"` AND the task is in `PRIVATE_PROJECT_IDS` (config-driven, empty default), replace `vikunja_value`, `felix_cached_value`, `diff_field` with the literal string `"<redacted>"` BEFORE validation and append.

**Files**:
- `scripts/sync/emit.py` (~320 lines)

**Validation**:
- [ ] `compute_event_id` is deterministic: identical inputs → identical 16-char hex
- [ ] JSONL append is atomic per-line (single `write` + `flush`)
- [ ] Validation failure on a malformed event raises OSError BEFORE the JSONL is appended (no half-written log)
- [ ] G-3 daily count is incremented only on successful delivery (not on suppression, not on error)

---

## Subtask T016 — `tests/sync/test_send_whatsapp.py`: send wrapper tests [P]

**Purpose**: Cover the subprocess wrapper's outcome mapping, dry-run behavior, message formatting, and recipient resolution.

**Steps**:

1. Mock `subprocess.run` via `unittest.mock.patch`.

2. Test cases for `send`:

   - `test_send_happy_path`: subprocess returns exit 0 → SendResult(True, 0, None).
   - `test_send_nonzero_exit`: subprocess returns exit 1, stderr text → SendResult(False, 1, stderr text).
   - `test_send_timeout`: subprocess.TimeoutExpired raised → SendResult(False, -1, contains "timeout").
   - `test_send_binary_missing`: FileNotFoundError raised → SendResult(False, -2, contains "openclaw binary not found").
   - `test_send_dry_run_does_not_invoke_subprocess`: `dry_run=True` → mock_run.call_count == 0; SendResult(True, 0, None).
   - `test_send_argument_order_matches_contract`: verify the args list passed to subprocess.run matches the exact documented order.

3. Test cases for `format_message`:

   - `test_format_unsafe_with_uc3_uses_orange_marker`: event with `uc3_downstream_behavior` → first line starts with `🟠`.
   - `test_format_unsafe_without_uc3_uses_yellow_marker`: event without uc3 → first line starts with `🟡`.
   - `test_format_includes_task_id_and_title`: line 2 contains `Task #{id}: {title}`.
   - `test_format_truncates_long_title`: title > 60 chars → truncated with `…`.
   - `test_format_diff_line_uses_json_repr`: line 3 has `field: {old} → {new}` with JSON-formatted values.
   - `test_format_redacted_for_private_task`: task_title=None → all three lines use `<redacted>`.

4. Test cases for `resolve_recipient`:

   - `test_resolve_recipient_cli_wins`: CLI arg = "+1234567890" → returns "+1234567890" (env ignored).
   - `test_resolve_recipient_env_fallback`: CLI = None, env set → returns env value.
   - `test_resolve_recipient_missing_raises`: both unset → raises OSError.

**Files**:
- `tests/sync/test_send_whatsapp.py` (~250 lines)

**Validation**:
- [ ] `python3 -m pytest tests/sync/test_send_whatsapp.py -q` passes
- [ ] Mock subprocess invocation never reaches the real `openclaw` binary

---

## Subtask T017 — `tests/sync/test_emit.py`: emit phase tests [P]

**Purpose**: Cover event_id determinism, JSONL append, guard interaction order, delivery dispatch paths, and validation failure modes.

**Steps**:

1. Build fixtures: synthetic ClassifiedConflict lists, TaskCacheRecord, GuardState, recent_events list. Use `tmp_path` for the JSONL file.

2. Test cases for `compute_event_id`:

   - `test_event_id_deterministic`: same inputs → same 16-char hex twice.
   - `test_event_id_differs_on_value_change`: different `vikunja_value` → different id (same stem prefix).
   - `test_event_id_format_is_lowercase_hex`: result matches regex `^[0-9a-f]{16}$`.

3. Test cases for `emit_events` (the main orchestrator):

   - `test_auto_resolved_appends_without_delivery`: one auto_resolved conflict → JSONL has one row with `delivery_status="not_unsafe"`, mock_send.call_count == 0.
   - `test_unsafe_approved_dispatches_send`: one unsafe with all guards passing → mock_send called once with the formatted message; JSONL row has `delivery_status="delivered"`.
   - `test_unsafe_g3_suppressed`: cap reached → JSONL row `delivery_status="suppressed_by_g3"`; mock_send.call_count == 0.
   - `test_unsafe_g2_suppressed`: post-write window → row `suppressed_by_g2`.
   - `test_unsafe_g1_suppressed`: stem matches recent → row `suppressed_by_g1`.
   - `test_unsafe_send_failure_records_error`: mock_send returns SendResult(False, 1, "boom") → row has `delivery_status="error"`, `delivery_error="boom"`.
   - `test_g3_daily_count_increments_on_delivered_only`: 2 deliveries + 1 suppressed → count incremented by 2.
   - `test_g3_daily_count_does_not_increment_on_error`: send returns failure → count NOT incremented.
   - `test_jsonl_append_failure_raises`: `tmp_path` set read-only → OSError propagates.
   - `test_validation_failure_blocks_append`: synthesize an event with `delivery_error` set when status is `delivered` → validation raises; the JSONL file is empty.
   - `test_privacy_redaction_applied`: task in PRIVATE_PROJECT_IDS → row's `vikunja_value`, `felix_cached_value`, `diff_field` are `"<redacted>"`.
   - `test_processing_order_by_vikunja_updated_at`: 3 conflicts with timestamps in reverse order → JSONL rows appear in ascending timestamp order.

4. Mock `send_callable` as a `MagicMock` to inspect call args.

**Files**:
- `tests/sync/test_emit.py` (~340 lines)

**Validation**:
- [ ] `python3 -m pytest tests/sync/test_emit.py -q` passes
- [ ] G-3 count tests verify both directions (incremented on success, not on error)

---

## Test strategy

Both files use mocks for subprocess and synthetic fixtures for the conflict data. Run via:

```bash
python3 -m pytest tests/sync/test_send_whatsapp.py tests/sync/test_emit.py -q
```

Combined target: ≥80% line coverage of `scripts/sync/send_whatsapp.py` and `scripts/sync/emit.py`.

---

## Definition of Done

- [ ] All 4 subtasks complete; all listed files committed in the WP04 worktree
- [ ] `python3 -m pytest tests/sync/ -q` passes (WP01 + WP02 + WP03 + WP04 tests)
- [ ] No edits to files outside the WP's `owned_files` list
- [ ] `ConflictEvent` dataclass exported from `scripts/sync/emit.py` (downstream WP05 imports for cycle orchestration)
- [ ] `compute_event_id` exported from emit.py (downstream WP05 also reads from JSONL using this)
- [ ] Subprocess invocation in `send_whatsapp.py` is byte-for-byte identical to `sync-heartbeat.py:121-131` except for the message/recipient values

---

## Risks and mitigations

- **Risk: subprocess.run timeout includes setup time, not just openclaw execution time.** Mitigation: 60s default is generous (Baileys QR-code-less delivery typically <2s); tests assert correct behavior under simulated timeout.
- **Risk: JSONL append race between concurrent driver invocations.** Mitigation: systemd timer is configured `OnUnitInactiveSec`, meaning the next tick only fires after the previous exits. No concurrent invocations possible by design. Documented in WP06 systemd unit comments.
- **Risk: G-3 cap state file corruption between cycles.** Mitigation: atomic write via `state.write_guard_state(...)`. On corrupted-file read failure, WP05's cycle.py exits with code 1 and writes the failure to `last-tick.errors.jsonl` — operator notices via the health record.
- **Risk: `format_message` rendering quirks (emoji, control chars in titles).** Mitigation: smoke test (post-merge, on office2) sends a message with a known-tricky title and verifies delivery integrity.

---

## Reviewer guidance

When reviewing this WP, verify:
1. **Subprocess args match precedent exactly**: open `scripts/obsidian/sync-heartbeat.py:121-131` and the new `scripts/sync/send_whatsapp.py` side-by-side. The list MUST be identical.
2. **`send` never raises**: every failure mode returns a SendResult. Tests assert this.
3. **`compute_event_id` is deterministic AND idempotent**: re-running the same cycle data produces the same event_id values. JSONL append idempotency depends on this.
4. **Privacy redaction applied at event build time**: `<redacted>` appears in the JSONL row for private tasks.
5. **G-3 increment ONLY on `delivery_status == "delivered"`**: not on suppression, not on error.
6. **No edits to WP01-WP03 owned files** (state.py, http.py, fetch.py, diff.py, classify.py, guards.py).

Reject if subprocess args drift from precedent, if `send` raises in any path, if event_id is non-deterministic, or if guards are applied in the wrong order.

---

## References

- Mission spec: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/spec.md`
- Pipeline contract: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/cycle-pipeline.md` § Phase 4
- Event schema: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/conflict-event-schema.md`
- WhatsApp send contract: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/whatsapp-send.md`
- Research finding (deterministic send confirmed): `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/research.md` § Unknown 1
- Subprocess precedent: `scripts/obsidian/sync-heartbeat.py:114-138`
- From WP03: `scripts/sync/classify.py` (ClassifiedConflict type), `scripts/sync/guards.py` (apply_guards, event_id_stem)
- From WP01: `scripts/sync/state.py` (TaskCacheRecord, GuardState)
