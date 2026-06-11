# Phase 1 — Data Model

**Mission**: `felix-calendar-subagent-extraction-01KTTA33`

This mission introduces no new persistent data structures. All "data models" here are config/registry entries the mission must produce, plus the preserved message contracts moved from `main` to `felix-admin-calendar`.

## openclaw.json — `agents.list[]` entry for felix-admin-calendar

Shape (matches existing subagent entries; see `felix-admin-tasker` in live openclaw.json probe):

```json
{
  "id": "felix-admin-calendar",
  "name": "felix-admin-calendar",
  "workspace": "/data/services/openclaw/calendar-agent",
  "agentDir": "/home/claude/.openclaw/agents/felix-admin-calendar/agent",
  "model": "anthropic/claude-haiku-4-5"
}
```

| Field | Type | Source | Notes |
|---|---|---|---|
| `id` | string | Constant for this mission | `felix-admin-calendar`. Must match the openclaw-agent-setup.md naming convention. |
| `name` | string | Constant | Same as `id` for clarity (matches existing entries). |
| `workspace` | string | F-04 convention | `/data/services/openclaw/calendar-agent` — pattern `<role>-agent`. |
| `agentDir` | string | F-04 convention | `/home/claude/.openclaw/agents/felix-admin-calendar/agent`. |
| `model` | string | F-06 decision | `anthropic/claude-haiku-4-5` — routine workload, validator-driven. |

Validation rules (encoded in `tests/test_openclaw_config_schema.py`):
- Entry present in `agents.list[]`
- All 5 required keys present, non-empty
- Workspace matches `^/data/services/openclaw/[a-z-]+-agent$`
- agentDir matches `^/home/claude/\.openclaw/agents/[a-z-]+/agent$`
- Model is a known anthropic model id (presence in `agents.defaults.models` keys)

## agent-registry.json — `agents.felix-admin-calendar` entry

Shape (matches existing subagent entries; see `felix-admin-capture` in repo):

```json
{
  "team": "SuperAdmin (B)",
  "scope": "Calendar substrate — event creation via gog/Google Calendar, clarification reply handler for incomplete inbox-captured events; future home for calendar credential health, recurrence, attendee tracking",
  "autonomy_level": "assisted",
  "model": "anthropic/claude-haiku-4-5",
  "model_policy": "optimizable",
  "model_rationale": "Routine deterministic-validator-driven workflow — matches capture / habits / tasker shape. Re-evaluate if accuracy is poor in production.",
  "log_verbosity": "standard",
  "deployed_feature": "#579",
  "registered": "2026-06-11",
  "transition_history": [
    {
      "date": "2026-06-11",
      "autonomy_level": "assisted",
      "direction": "registration",
      "reason": "Extracted from main/AGENTS.md per kentonium3/kg-automation#579 to restore WhatsApp reply relay; broader calendar-substrate charter per mission spec discovery Q2 = A+C",
      "decided_by": "Kent Gale"
    }
  ]
}
```

| Field | Source |
|---|---|
| `team` | "SuperAdmin (B)" (matches all existing felix-admin-* entries) |
| `scope` | Reflects broader charter (per spec Q2=A+C) |
| `autonomy_level` | "assisted" (matches subagent default; calendar writes affect Kent's Google Calendar) |
| `model` | F-06: haiku-4-5 |
| `deployed_feature` | "#579" (originating issue) |
| `registered` | 2026-06-11 (today) |

## Calendar event creation payload (PRESERVED, not redesigned)

This payload contract is moved 1:1 from `main/AGENTS.md` lines 259–331. Authoritative reference: `kitty-specs/inbox-calendar-and-aspiration-routing-01KTHHXS/contracts/capture_to_main_calendar_payload.md`.

```json
{
  "action": "create_calendar_event",
  "calendar_id": "<string, default 'primary'>",
  "account": "<email, default 'kent@intentional.biz'>",
  "summary": "<string>",
  "start_rfc3339": "<RFC3339 timestamp>",
  "end_rfc3339": "<RFC3339 timestamp>",
  "source_inbox_path": "<absolute path to inbox note>",
  "start_timezone": "<IANA tz, optional>",
  "location": "<string, optional>",
  "description": "<string, optional>",
  "rrule": "<RFC 5545 RRULE, optional>",
  "attendees": ["<email>", "..."],
  "clarification_id": "<string, null on first dispatch>"
}
```

**Contract owner after extraction**: `felix-admin-calendar` (was: `main`).

**Dispatcher**: `felix-admin-capture` (unchanged) routes inbox-captured calendar events via openclaw-agent dispatch.

**Response envelope** (returned to caller; unchanged):

```json
{
  "status": "created",
  "gcal_event_id": "<string>",
  "html_link": "<url>",
  "summary": "<string>",
  "start_rfc3339": "<RFC3339>",
  "rrule": "<RFC 5545 RRULE | null>"
}
```

or:

```json
{
  "status": "error",
  "error": "<gog stderr verbatim>",
  "exit_code": "<int>"
}
```

## Calendar clarification reply state file (PRESERVED)

`~/second-brain/agents/state/pending-calendar-clarifications.jsonl` — file path and JSONL record shape unchanged. The handler that reads/writes it moves from `main/AGENTS.md` lines 333–440 to `felix-admin-calendar/AGENTS.md` with no behavioral change.

Atomic-write protocol (LOCK_EX + .tmp + rename) preserved verbatim — this is shared with capture's append-record pattern.

## Service-inventory.json entry (NEW)

felix-admin-calendar gets a new entry under whatever the existing convention is for felix-admin-* subagents in `docs/design/architecture/data/service-inventory.json`. Plan phase does NOT redesign that schema; the implementation WP reads the existing felix-admin-capture / felix-admin-habits entries as the template.

## Smoke-runbook structure (NEW deliverable)

`docs/runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md` — an operator-facing markdown checklist. Structure:

```markdown
# Smoke checklist — Felix Calendar Subagent Extraction (#579)

## Prereqs
- [ ] Deploy script completed without errors
- [ ] Journal watch reported zero `truncating in injected context` warnings
- [ ] Current time

## DMs to send (one per subagent)
- [ ] **felix-admin-habits**: "mark habits 1, 3, 5 complete" → reply received within 30s
- [ ] **felix-admin-capture**: send an inbox-routable WhatsApp message → routed correctly
- [ ] **felix-admin-tasker**: "what's on my list today" → reply received within 30s
- [ ] **felix-admin-escalation**: trigger via [...path...] → reply received within 30s
- [ ] **felix-admin-calendar (NEW)**: "schedule a 30-min check-in tomorrow at 2pm" → event created OR clarification asked
- [ ] **felix-admin-calendar clarification round-trip**: respond to clarification prompt → event created

## Non-DM checks
- [ ] **felix-doc-auditor** `last-tick.json` updated within last hour: `ssh office2-claude 'cat /data/services/openclaw/felix-doc-auditor-driver/last-tick.json | jq .'`
- [ ] **Morning checkin** fires at 7am ET next day with no incident
- [ ] **IDLE pings** continue normal cadence
- [ ] **Periodic digests** fire on schedule

## Verification record
- Operator initials, timestamp, observed latencies per DM.
- Any unexpected behavior → file bug, do NOT mark mission complete.
```

The full content is authored in an implementation WP.

## What this mission does NOT introduce

- No new database tables
- No new persistent storage paths beyond the agent workspace dir
- No new authentication / authorization surfaces
- No new external service integrations (calendar substrate is the existing `gog` CLI + Google Calendar)
- No new credential management (`GOG_KEYRING_PASSWORD` and `openclaw-gateway-env` continue serving the same flow, just from a different agent's process)
