# Contract: felix-admin-calendar reshape (judgment-only) + capture inbox rewire

**Goal**: Remove `gog` from the calendar surface. The calendar agent keeps only
the work that needs an LLM (conversation + clarification judgment); the terminal
"create/update/delete" becomes a deterministic `calendar_helper` call. Inbox
capture reaches the calendar **directly** (no agent-to-agent hop) → closes #679.

## felix-admin-calendar — before → after

| Aspect | Before | After |
|---|---|---|
| openclaw.json `skills` | `["gog"]` | `[]` (gog removed) — no calendar skill; the helper is invoked via `exec` |
| Create call | `gog calendar create <cal> --account <a> --summary … -j` | `cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.calendar_helper create --payload-file <tmp> --json` |
| Account default | `kent@intentional.biz` | `personal` |
| Judgment retained | clarification round-trips; conversational calendar path | unchanged (LLM parses Kent's replies, fills missing fields, re-validates) |
| Result envelope | `{status:created, gcal_event_id, html_link}` on success; verbatim gog stderr on error | `{status:created, event_id, html_link}` from helper stdout; verbatim helper `ERROR:`/exit-3 on failure (surface, never fake success) |
| Logging | `log_action.py` on every attempt | unchanged |

**Fail-safe**: a helper exit `3` (auth) or `1` (operational) is surfaced to Kent
verbatim; the agent never reports a created event that did not create
(#683 trust defect). It must **not** fall back to gog.

## felix-admin-capture — inbox calendar step, before → after

| Aspect | Before (#679, broken) | After |
|---|---|---|
| Build envelope | `python3 -m scripts.inbox.route_calendar_event --payload-file <tmp> --as-delegation-payload --source-path <abs>` | unchanged (still builds the `create_calendar_event` envelope deterministically) |
| Terminal step | `openclaw agent --agent felix-admin-calendar --message '<envelope>' --json` (agent-to-agent hop; haiku mishandles it) | `… venv/bin/python -m scripts.google.calendar_helper create --payload-file <tmp> --json` (**direct helper call, no hop**) |
| Incomplete note | record `PendingClarificationRecord`, ask Kent once | unchanged — clarification reply is later handled by felix-admin-calendar (Kent→agent, not capture→agent) |
| gog | never (capture had no gog) | never |

**Net effect**: the common happy path (complete inbox note → event) no longer
crosses an agent boundary. The clarification path still uses felix-admin-calendar
but only via a *separate inbound message from Kent*, which is not capture→agent
delegation.

## Acceptance mapping

- FR-008: felix-admin-calendar `skills` = `[]`; no `gog` string in its prompt on
  the calendar surface; terminal action is the helper. (SC-003)
- FR-009: capture's calendar step invokes the helper directly; a complete inbox
  note creates an event with no `openclaw agent`/`sessions_send` hop. (SC-002 —
  verified by a live office2 end-to-end run.)
- The `DEFAULT_ACCOUNT` constant flips `kent@intentional.biz` → `personal` in
  `scripts/inbox/route_calendar_event.py` and
  `scripts/calendar_routing/validate_calendar_event.py` (+ affected fixtures).

## Deploy note

Prompt edits (`AGENTS.md` / `AGENTS.md.tmpl`) reach office2 via the
agent-prompt-sync timer. The openclaw.json `skills` edit (removing `gog`) is a
manual out-of-band office2 change + gateway restart → **manual rebaseline**
(monitored surface, out-of-band exception). See quickstart.md.
