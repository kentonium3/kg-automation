# Research: Felix-Vikunja Sync Reconciliation Driver — Phase 0

**Mission**: `felix-vikunja-sync-reconciliation-driver-01KTA1J3`
**Date**: 2026-06-04
**Researcher**: Claude (via live-probe on office2 + repo inspection on Mac)

This document resolves the three load-bearing unknowns identified during planning interrogation, plus one critical finding that emerged from probing and reshapes the classification design. Each unknown is recorded as **Decision** / **Rationale** / **Alternatives considered** per the spec-kitty research template.

---

## Unknown 1 — Does a deterministic-script-callable WhatsApp send mechanism exist in OpenClaw? (Spec assumption A-3)

**Decision**: Yes. The driver invokes `openclaw agent --agent main --message "..." --deliver --channel whatsapp --to <number>` as a subprocess. No new send helper or new agent is built as part of this mission.

**Rationale**: Live-probe of `/home/claude/kg-automation/scripts/obsidian/sync-heartbeat.py` (a production cron job on office2) shows this exact pattern is already in production use for deterministic-script-driven WhatsApp alerts. The pattern is documented at `sync-heartbeat.py:114-138`:

```python
result = subprocess.run(
    [
        "openclaw", "agent",
        "--agent", OPENCLAW_AGENT,           # "main"
        "--message", message,
        "--deliver",
        "--channel", "whatsapp",
        "--to", WHATSAPP_RECIPIENT,
    ],
    capture_output=True, text=True, timeout=60,
)
```

The `--agent main` argument spawns a short-lived OpenClaw agent run scoped to the delivery action. The message content is passed verbatim via `--message`; the agent does no formatting or judgment — it acts as a thin shim across the WhatsApp credential boundary. From the driver's perspective the call is deterministic: input is a fully-formatted message string, output is exit code 0 (delivered) or non-zero (failure).

Directive 6 alignment is preserved: all classification, formatting, dedup, and threshold logic lives in the driver's deterministic Python code. The OpenClaw agent run is the credential-boundary crossing, not a judgment layer.

**Alternatives considered**:

- *Build a new direct-send Python helper.* Rejected: would require accessing OpenClaw's WhatsApp credentials from outside the OpenClaw runtime, expanding the credential blast radius and duplicating Baileys session management. Pre-accepted as fallback in operator Q1 if needed, but research shows it's unnecessary.
- *File-drop pattern (driver writes events, separate agent polls and delivers).* Rejected: introduces an LLM judgment layer between detection and delivery; violates Directive 6. Also: lossier (agent's delivery decision is independent of the driver's detection decision) and adds coordination lag.

**Implication for spec**: Spec C-006 (deterministic-script-callable WhatsApp send) is satisfied by the existing pattern. No scope expansion needed. Assumption A-3 holds without falsification.

---

## Unknown 2 — What is the conflict-event log rotation interface today? (Spec assumption A-7)

**Decision**: No rotation interface exists today. `habits-history.jsonl` and `escalation/project-9-escalation-history.jsonl` both grow indefinitely. The sync driver's conflict-event log follows the same pattern: append-only, no built-in rotation, externally rotatable when a need arises.

**Rationale**: Live-probe on office2 found:

- `/data/services/openclaw/state/habits-history.jsonl` (53 entries as of 2026-06-04, no rotation log, no logrotate config under `/etc/logrotate.d/`, no systemd timer)
- `/data/services/openclaw/state/escalation/project-9-escalation-history.jsonl` (same pattern)
- `~/.config/systemd/user/` contains no logrotate or rotation timer for these files
- The only "rotation" found in `scripts/openclaw/helpers/rotate_main_session.py` is for OpenClaw session continuity, unrelated to JSONL state logs

At current Felix scale (≤1 unsafe-class WhatsApp/day target, ~tens of conflict events per day across all classes), the conflict-event log grows on the order of single-digit KB per day. A year of accumulation is single-digit MB. Disk pressure is not a near-term concern. Restic backup overhead is negligible.

**Alternatives considered**:

- *Driver owns rotation (e.g., size-based rolling).* Rejected: complicates the driver, breaks the established pattern, and creates a second source of truth (current file + archive). No precedent in the codebase.
- *systemd-managed rotation via timer + helper script.* Acceptable future option, but deferred as a separate concern. Not a blocker for this mission.

**Implication for spec**: NFR-004 (rotation policy externally managed) is honored. Assumption A-7 narrowed: there is no rotation precedent today; the driver does not own rotation and the absence of rotation is acknowledged as a future-tracked tech-debt item, not a blocker.

---

## Unknown 3 — How do existing Felix scripts identify "felix-bot wrote this" vs. "Kent wrote this" on a Vikunja task? (UC-1 / UC-2 dependency)

**Decision**: Vikunja v0.24.6 does NOT return `updated_by` on the standard `GET /api/v1/tasks/{id}` response. The driver therefore does NOT rely on a direct Vikunja author signal for UC-1 (`kent_edit_after_felix_write`) or UC-2 (`operator_authored_field`). Both criteria collapse into a single test: **does Vikunja's current value differ from the value the driver's cache says Felix last expected to be there?** This is implemented as the value-comparison phase of the cycle's `diff` step.

**Rationale**: Live-probe against the production Vikunja instance:

```
$ curl -H "Authorization: Bearer <token>" \
       https://office2.tail0f5f56.ts.net/api/v1/tasks/18 \
  | jq '{title, created_by, updated_by, updated, done}'
{
  "title": "Get steps in today",
  "created_by": { "id": 1, "username": "kent", ... },
  "updated_by": null,                           ← always null
  "updated": "2026-06-01T22:05:08Z",
  "done": false
}
```

Task 18 has been written to multiple times by felix-bot (via `record_completion.py`) over recent weeks, yet `updated_by` is null. The `created_by` field is populated (original task author) but `updated_by` is not. This is consistent across all tasks probed.

Therefore, the four unsafe-class criteria from RQ-3 reduce as follows when implemented in the driver:

| Criterion (RQ-3 spec) | Felix-side implementation |
|---|---|
| **UC-1** `kent_edit_after_felix_write` | Vikunja value ≠ driver's cached "Felix-known" value for that field. |
| **UC-2** `operator_authored_field` | Same as UC-1 (collapses). |
| **UC-3** `downstream_behavior_depends` | Field is in a curated set of "downstream-affecting" fields (e.g., `due_date`, `project_id`, `repeat_after`, `repeat_mode`, `done`). Independent of UC-1. |
| **UC-4** `manual_override_signal` | Task title contains `[NO FELIX]` marker OR labels include `felix:ignore` (or equivalent — exact marker confirmed in plan phase via a test task). |

UC-1 and UC-2 are therefore implemented as one check (cache divergence). UC-3 and UC-4 remain distinct, both computable from log fields alone. **Net result: the four-criterion classification is preserved at the conceptual level, but UC-1 and UC-2 are operationally one test in code.**

**Alternatives considered**:

- *Query Vikunja's per-task comment thread to find the most recent author.* Vikunja DOES expose `GET /api/v1/tasks/{id}/comments` with author info per comment, and Felix's `record_completion.py` writes "[Felix] ..." comments on every completion. Using comment authorship as an authorship proxy works but adds an extra HTTP call per task per cycle, and only captures completion events (not all field updates). Rejected as the primary mechanism; useful as a future-only verification cross-check.
- *Add an authorship metadata field to each task description (Felix-managed convention).* Rejected: introduces a write-path requirement from Felix that doesn't exist today and would conflict with operator UI freedom to edit descriptions.
- *Query Vikunja's audit log (if it has one).* Vikunja v0.24.6 has no public audit-log endpoint. Rejected as not currently exposed.
- *Maintain a separate "felix-bot write timeline" log.* This is essentially what the driver's value cache becomes. The cache is the authorship signal.

**Implication for spec**: spec FR-005 references UC-1..UC-4 as separate criteria; the implementation collapses UC-1/UC-2. The contract document `contracts/cycle-pipeline.md` describes this explicitly. No spec changes needed — the four-criterion model survives as the conceptual classification, the implementation simply notes that UC-1 ≡ UC-2 in code.

---

## Cross-cutting evidence

The probes above also confirmed several lower-stakes assumptions from spec § Assumptions:

- **A-1 (Vikunja token sufficiency)**: Confirmed. The `vikunja-api` token at `/data/services/openclaw/secrets/vikunja-api` reaches `GET /tasks/{id}` and `GET /tasks/all?updated_since=<ts>`. The earlier probe in this conversation also confirmed `GET /projects` works with the same token.
- **A-2 (state directory location)**: Confirmed. `/data/services/openclaw/state/` already houses `habits-history.jsonl`, `habits/`, `escalation/`, `enrichment/` subdirectories. Adding a `sync/` subdirectory follows the established pattern.
- **A-5 (`updated_since` reliability)**: Not directly probed in this phase. Plan phase confirms via the implementation's first integration smoke test. Documented as a load-bearing assumption to be validated by an early test, not by additional research.
- **A-6 (felix-bot-author transparency through classification)**: Reshaped by Unknown 3. Felix's own writes generate `updated > driver_cache_ts` but `vikunja_value == driver_cache_expected_value` (because the driver knows what Felix wrote). Net result: Felix's writes produce a cache update (no divergence, no classification fires) — auto_resolved without any UC firing. Confirmed by tracing through the diff-phase logic against a worked example.

---

## Open items deferred to implement phase

- The exact marker syntax for UC-4 (`[NO FELIX]` title prefix, `felix:ignore` label, or both) — settled by operator preference or by a smoke test against the production Vikunja during the first WP. Default proposal: `felix:ignore` label, since labels are queryable in the task fetch payload and don't require parsing free-text titles.
- The "downstream-affecting" field whitelist for UC-3 — initial proposal: `due_date`, `project_id`, `done`, `repeat_after`, `repeat_mode`, `title`. Operator confirms in implement phase or via cycle-pipeline contract review.
- The exact first-run bootstrap behavior (spec assumption A-4) — initial proposal: `last_polled_utc` initialized at install time; one explicit operator command runs the bootstrap and commits the initial cache snapshot. Documented in `quickstart.md`.

---

## Research summary

Three planning unknowns resolved; one critical finding (Vikunja `updated_by: null`) discovered and absorbed into the classification design without scope expansion. No spec changes triggered. All gates (Charter Check, Constitutional Compliance, Risk Considerations) remain green.

**Phase 0 status**: complete. Proceeding to Phase 1 (data-model.md, contracts/, quickstart.md).
