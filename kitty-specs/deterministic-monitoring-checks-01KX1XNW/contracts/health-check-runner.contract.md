# Contract: Health-Check Runner (off-agent)

**New units**: `felix-health-check.service` + `felix-health-check.timer` (systemd user)
**Wrapper**: a non-agent script invoked by the service
**Removes**: openclaw crons `health-check-morning` + `health-check-evening`

## Precedent to mirror

Model the unit + deploy on the existing `credential-health-check` service:
`scripts/office2/credential-health-check.{service,timer}` (`OnCalendar=*-*-* 13:00:00`)
+ `scripts/office2/deploy/credential-health-check.sh`. Model the ntfy send on
`scripts/office2/security-monitor/audit.sh:243-255` (curl POST with `Title`/`Priority`/
`Tags` headers, `NTFY_TOPIC`, non-fatal-on-failure with a log line).

## Schedule

- Timer `OnCalendar` fires at **11:00** and **23:00** (matching the removed crons'
  `0 11 * * *` and `0 23 * * *`). Cadence 2×/day (FR-010) — unchanged.
- Runs as the `claude` systemd user manager, like `felix-core-digest.timer` and
  `credential-health-check.timer` (both confirmed enabled on office2).

## Wrapper behavior

1. Run `bash /home/claude/helper-scripts/health-check.sh` via **`subprocess.run`
   (NOT `exec`)** so the wrapper survives to classify — capture stdout, stderr, and
   exit code. (An `exec` would replace the wrapper process and make classification
   impossible — Codex finding #1.)
2. **Preflight**: if `health-check.sh` is missing/non-executable, treat as
   `status = SCRIPT_MISSING` and **alert via ntfy** (do NOT rely solely on systemd
   `status=failed`, which is easy to miss — Codex #1). A deploy-time presence check
   also guards this.
3. Classify with **failure-wins precedence** (Codex #9):
   - `FAILURES_DETECTED` present in stdout/stderr → `status = FAILURES_DETECTED`
     (wins even if `ALL_HEALTHY` also appears).
   - else `ALL_HEALTHY` present AND exit code 0 → `status = ALL_HEALTHY`.
   - else (neither token, or exit ≠ 0 without a clear token) → `status = UNKNOWN`.
4. Deliver:
   - `ALL_HEALTHY` → **no alert**; stamp a health-signal file
     `/data/services/openclaw/felix-health-check/last-run.json`
     (`{status, ran_at_utc, exit_code}`) for observability.
   - `FAILURES_DETECTED` / `UNKNOWN` / `SCRIPT_MISSING` → **ntfy** push with the full
     raw output (truncated to a bounded size, e.g. first ~4 KB, with a "(truncated)"
     marker), Title `Felix Health Check — office2`, Priority `high`
     ([[reference_ntfy_notification_pattern]]); also stamp the signal file.
   - **ntfy-send failure is logged** (to the service journal + the signal file's
     `delivery` field) and is non-fatal — parity with `audit.sh`'s pattern (Codex #1/#5).
5. Exit `0` on any completed run (a health *failure* is data, not a runner error).
   Non-zero only if the wrapper itself cannot run at all (e.g. python import failure),
   which surfaces via systemd `status=failed`.

## Invariants (acceptance)

- **NFR-002**: zero `main` (Sonnet) sessions created per run — verified via
  `openclaw cron runs` showing no health-check cron and `openclaw` session logs
  showing no health-check-triggered main session.
- The `health-check.sh` assertions are unchanged (FR-010) — only execution + delivery
  move off the agent.
- Healthy runs remain silent (parity with today's `delivery.mode: none`).
- **Delivery parity (Codex #5)**: acceptance MUST verify, operator-visibly — ntfy
  topic configured; a forced `FAILURES_DETECTED` push is actually received; full raw
  output (or its bounded/truncated form) is preserved; `UNKNOWN`/non-zero/
  `SCRIPT_MISSING` all alert; an ntfy delivery failure is recorded where Kent can see
  it (journal + signal file).

## Test matrix (Codex #9)

Cover: stdout-only `ALL_HEALTHY`; stdout-only `FAILURES_DETECTED`; **both tokens
present** (failure wins); token in stderr only; non-zero exit with `ALL_HEALTHY`
(→ UNKNOWN); missing script (→ SCRIPT_MISSING + alert); oversized output (truncation);
ntfy send failure (non-fatal, logged).

## Delivery-channel note (review point)

Failure alerts move **WhatsApp → ntfy**. Rationale in research R5: WhatsApp is an
agent/openclaw-messaging capability; a non-agent timer using it would reintroduce the
coupling being removed. If Kent prefers WhatsApp for health failures, the deliver step
can shell a non-agent `openclaw` send instead (fold on request).
