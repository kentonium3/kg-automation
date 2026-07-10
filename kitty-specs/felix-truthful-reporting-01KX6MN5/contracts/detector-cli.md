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
- **Exit codes (two modes — Codex finding 8):**
  - *Timer mode* (default, systemd target): **always exit 0**; a scan fault is
    reported via `ok:false` + `errors[]` (avoids putting the systemd unit into a
    failed/restart loop).
  - *Preflight/explicit mode* (`--once`, deploy self-test, manual): **may exit 2**
    when the scan itself could not run (e.g., baseline unreadable) — hard signal
    for the operator/entrypoint. Select with `--preflight` (or `--once`).
  - **Never** a non-zero exit merely because drift was *found* (drift is expected
    signal), in either mode.
- Fail-safe: an exception in one sub-scan is caught, recorded in `errors[]`, and
  does not abort the other sub-scan.

## C3 — `cron_drift_detector` (library)

```
detect_cron_drift(live_jobs: list[dict], baseline: list[ApprovedCron]) -> list[CronDriftFinding]
```

Pure function (no I/O): given parsed live jobs and the loaded baseline, returns
findings. **Match key = `(name, agent_id)`** (an approved name under a different
agent is `unapproved_present` — the owner-mismatch/incident case). For a matched
pair, diff `schedule.expr`, `schedule.tz`, `enabled` → `schedule_mismatch` /
`enabled_mismatch`. Baseline entry with no live match → `approved_missing`. See
data-model.md finding kinds. This is the unit-testable core (deterministic; no
subprocess) — cover present/missing/schedule-mismatch/enabled-mismatch/
owner-mismatch cases.

## C4 — `completion_assertion` record + helper (auto-emit)

Primary path (Codex finding 2): the **artifact-creation helper auto-emits** on
success. `scripts/vikunja/create_task.py` calls the record API after a
successful create:

```python
from scripts.trust.completion_assertion import record_assertion
record_assertion(agent="main", artifact_kind="vikunja_task",
                 artifact_ids=["91","92","93","94","95","96","97"],
                 claim="Created 7 Vikunja reminder tasks", request_ref=None)
```

A thin CLI exists for the manual/bypass path:

```
python3 -m scripts.trust.completion_assertion \
  --agent main --artifact-kind vikunja_task \
  --artifact-id 91 --artifact-id 92 \
  --claim "Created Vikunja reminder tasks #91,#92"
```

- Appends one JSON line (schema = `CompletionAssertion` in data-model.md, with an
  `artifact_ids` **list** — Codex finding 7) via `fcntl.LOCK_EX`.
- **Best-effort/fail-safe**: a ledger-write failure must **not** break the
  caller — `record_assertion` swallows its own errors (logs, returns falsey);
  the CLI returns non-zero but never raises into the agent. Task creation must
  succeed even if the assertion write fails.
- Doctrine (IC-01) asks an agent to record a manual assertion **only** when it
  bypasses a wrapped helper.

## C5 — `assertion_verifier` (library + existence checks)

```
verify_assertion(a: CompletionAssertion) -> list[AssertionFinding]
```

- Verifies **each** id in `artifact_ids` independently (Codex finding 7) and
  returns zero or more findings (one per missing/unverifiable id).
- `vikunja_task` → look up each task id via the Vikunja client; `artifact_missing`
  for any id not found.
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

- **SC-001/SC-002** (regression): a delegated "create N reminder todos" flow
  yields exactly the requested Vikunja tasks (the motivating case = 7) and zero
  unrequested crons, and the report makes no ungrounded completion claim.
  Verified by: (a) drift scan shows no `unapproved_present`; (b) the auto-emitted
  assertion carries all N `artifact_ids` and each verifies present.
- **SC-003** (scoped to the two detectable classes — Codex finding 1): inject an
  `unapproved_present` cron and an `artifact_missing` assertion → both produce an
  alert within one cycle (≤15 min). Test with a forced/immediate scan + mocked
  bus asserting `emit` was called. **Not** covered: a pure verbal completion lie
  with no artifact/assertion (FR-006 blind spot — doctrine-only).
- **SC-004**: doctrine present in all 7 agent prompts; no-unrequested-infra block
  present in `main`. Verified by a prompt-content test.
- **SC-005**: force the detector to fail (unreadable baseline / CLI error) →
  `--json` reports `ok:false`/`errors[]`, exit `2`, **no** alert emitted, and no
  agent-facing effect.
