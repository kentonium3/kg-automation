# Contract: Trust-scan detector CLI & record schemas

**Mission**: felix-truthful-reporting-01KX6MN5
**Phase**: 1 (Design)

These are the interface contracts the implementation and tests bind to. All
helpers follow the repo helper-script conventions: `python3 -m` invocation,
stdout = machine-readable summary, exit code = status, fail-safe.

---

## C1 — `openclaw cron list --json` (external input shape)

Consumed by the drift detector. Verified live on office2 (2026-07-10). Relevant
shape (mock at this boundary in tests):

```json
{
  "jobs": [
    {
      "id": "4ea46768-fac9-4620-825e-5d0f8214238b",
      "name": "inbox-5pm",
      "enabled": true,
      "createdAtMs": 1775153265189,
      "updatedAtMs": 1783630804889,
      "agentId": "felix-admin-capture",
      "schedule": { "kind": "cron", "expr": "0 17 * * *", "tz": "America/New_York" }
    }
  ]
}
```

Contract note: the detector must tolerate additional/unknown fields and a
missing `schedule.tz`. If the CLI errors or returns non-JSON, the detector
fails safe (no alert, non-zero internal log, exit code documented below) — it
does **not** treat "can't read crons" as "no unapproved crons".

## C2 — `run_trust_scan.py` (timer entrypoint)

```
python3 -m scripts.trust.run_trust_scan [--dry-run] [--once] [--json]
```

- Runs the cron-drift scan and the assertion-verification scan.
- `--dry-run`: compute findings and print them; **do not** emit alerts, do not
  advance state/watermark. For deploy self-test and local verification.
- `--json`: emit a machine-readable summary to stdout:
  ```json
  {"ok": true, "drift_findings": 0, "assertion_findings": 0, "alerts_emitted": 0, "errors": []}
  ```
- **Exit codes**: `0` = scan completed (findings may exist and may have alerted;
  this is normal operation, not a failure); `2` = the scan itself could not run
  (e.g., baseline file unreadable) — fail-safe, no partial alerts. Never a
  non-zero exit merely because drift was found (drift is expected signal).
- Fail-safe: an exception in one sub-scan is caught, recorded in `errors[]`, and
  does not abort the other sub-scan.

## C3 — `cron_drift_detector` (library)

```
detect_cron_drift(live_jobs: list[dict], baseline: list[ApprovedCron]) -> list[CronDriftFinding]
```

Pure function (no I/O): given parsed live jobs and the loaded baseline, returns
findings. Matching key = `name` (+ `agent_id` when present). This is the unit-
testable core (deterministic; no subprocess).

## C4 — `completion_assertion` record + helper

Agent-facing helper to emit a completion-assertion:

```
python3 -m scripts.trust.completion_assertion \
  --agent main \
  --request "create daily reminder todo for the refresh test" \
  --artifact-kind vikunja_task \
  --artifact-id 91 \
  --claim "Created Vikunja reminder task #91"
```

- Appends one JSON line (schema = `CompletionAssertion` in data-model.md) with
  `fcntl.LOCK_EX`. Best-effort/fail-safe: a write failure must not break the
  calling agent's turn (returns non-zero but never raises into the agent).
- The doctrine (IC-01) points agents at this helper for delegated create/do
  completions.

## C5 — `assertion_verifier` (library + existence checks)

```
verify_assertion(a: CompletionAssertion) -> AssertionFinding | None
```

- `vikunja_task` → look up the task id via the Vikunja client; `None` if it
  exists, `artifact_missing` finding if not.
- `calendar_event` / `vault_note` → existence check where cheaply available;
  otherwise `unverifiable_kind` (warn) rather than a false `artifact_missing`.
- `other` → `unverifiable_kind` (warn).
- Verification is deterministic; **no LLM**. Mock the Vikunja client in tests.

## C6 — Alert emission (reuse #701)

Findings render to `scripts.common.alert_bus.model.Alert` and emit via the bus's
existing delivery path. Severity map per data-model.md. No new topic, no
parallel channel (C-002). Every emitted alert is captured by the #706 ledger for
free.

## Acceptance-relevant contracts (map to Success Criteria)

- **SC-001/SC-002** (regression): a delegated "create a reminder todo" flow yields
  exactly the requested Vikunja task and zero unrequested crons, and the report
  makes no ungrounded completion claim. Verified by: (a) drift scan shows no
  `unapproved_present`; (b) an assertion for the created task verifies present.
- **SC-003**: inject an `unapproved_present` cron and an `artifact_missing`
  assertion → both produce an alert within one cycle (≤15 min). Test with a
  forced/immediate scan + mocked bus asserting `emit` was called.
- **SC-004**: doctrine present in all 7 agent prompts; no-unrequested-infra block
  present in `main`. Verified by a prompt-content test.
- **SC-005**: force the detector to fail (unreadable baseline / CLI error) →
  `--json` reports `ok:false`/`errors[]`, exit `2`, **no** alert emitted, and no
  agent-facing effect.
