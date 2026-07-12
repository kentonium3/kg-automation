# Contract: weekly_report_driver (IC-03)

**Module**: `scripts/habits/weekly_report_driver.py`
**Invocation**: `python3 -m scripts.habits.weekly_report_driver [--dry-run]` (run by the systemd timer)

## Behavior
1. Run the report helper: `query_active_habits_weekly --output text` (subprocess or in-process). Capture stdout.
2. On helper failure (non-zero) → write a `failure` TickSignal, exit non-zero (OnFailure ntfy fires). Do NOT deliver a partial/fabricated report.
3. Compose the message: `"<attribution line>\n\n" + report_body` (FR-005 — report portion byte-identical).
4. Deliver: `openclaw message send --channel whatsapp --target <E.164> --message <message> --json`.
5. Confirm delivery from the `--json` result. Stamp `delivery_confirmed=true` ONLY on confirmed success (FR-006).
6. Write `last-tick.json` (`completed_at_utc`, `exit_code`, `status`) atomically.

## Flags
- `--dry-run` → runs the helper + composes, calls `openclaw message send --dry-run` (no real send), writes no state. Used by the deploy self-test.

## Attribution
Fixed identity line (e.g. `Sent by felix-habits-weekly-driver`) so observed-mode attribution survives the move off the agent.

## Tests (tests/habits/test_weekly_report_driver.py) — fake subprocess/send, no network/LLM
- Happy path: helper stdout delivered verbatim after the attribution line; TickSignal `status=success`, `delivery_confirmed=true`.
- Helper failure → no send, TickSignal `status=failure`, non-zero exit.
- Send failure (send result not confirmed) → `delivery_confirmed=false`, non-zero exit, TickSignal `status=failure` (FR-006: never claim delivery).
- `--dry-run` writes no state and issues no real send.
