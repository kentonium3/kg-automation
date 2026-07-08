# Contract: Health-Check Runner (off-agent)

**New units**: `felix-health-check.service` + `felix-health-check.timer` (systemd user)
**Wrapper**: a non-agent script invoked by the service
**Removes**: openclaw crons `health-check-morning` + `health-check-evening`

## Schedule

- Timer `OnCalendar` fires at **11:00** and **23:00** (matching the removed crons'
  `0 11 * * *` and `0 23 * * *`). Cadence 2×/day (FR-010) — unchanged.
- Runs as the `claude` systemd user manager, like `felix-core-digest.timer` and
  `credential-health-check.timer` (both confirmed enabled on office2).

## Wrapper behavior

1. `exec bash /home/claude/helper-scripts/health-check.sh` (reused unchanged, FR-010),
   capturing stdout+stderr and exit code.
2. Classify:
   - stdout contains `ALL_HEALTHY` → `status = ALL_HEALTHY`
   - stdout contains `FAILURES_DETECTED` → `status = FAILURES_DETECTED`
   - else (or non-zero exit) → `status = UNKNOWN`
3. Deliver:
   - `ALL_HEALTHY` → **no alert**; stamp a health-signal file (e.g.
     `/data/services/openclaw/felix-health-check/last-run.json`) for observability.
   - `FAILURES_DETECTED` / `UNKNOWN` → **ntfy** push with the full raw output
     ([[reference_ntfy_notification_pattern]]); also stamp the signal file.
4. Exit `0` on any completed run (health failure is data, not a runner error). Non-zero
   only if the wrapper itself fails (e.g. `health-check.sh` missing) — which surfaces
   via systemd `status=failed` and the standard service-failure path.

## Invariants (acceptance)

- **NFR-002**: zero `main` (Sonnet) sessions created per run — verified via
  `openclaw cron runs` showing no health-check cron and `openclaw` session logs
  showing no health-check-triggered main session.
- The `health-check.sh` assertions are unchanged (FR-010) — only execution + delivery
  move off the agent.
- Healthy runs remain silent (parity with today's `delivery.mode: none`).

## Delivery-channel note (review point)

Failure alerts move **WhatsApp → ntfy**. Rationale in research R5: WhatsApp is an
agent/openclaw-messaging capability; a non-agent timer using it would reintroduce the
coupling being removed. If Kent prefers WhatsApp for health failures, the deliver step
can shell a non-agent `openclaw` send instead (fold on request).
