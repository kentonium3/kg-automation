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
| Build + create | build envelope (`route_calendar_event … --as-delegation-payload`), THEN a second exec to hand it off | **one deterministic command**: `route_calendar_event --create --payload-file <tmp> --source-path <abs>` validates → builds envelope → invokes the calendar helper → emits `{status: created\|error\|needs_clarification, …}`. Capture runs a single opaque command (no JSON-bridging between two execs). |
| Terminal step | `openclaw agent --agent felix-admin-calendar --message '<envelope>' --json` (agent-to-agent hop; haiku mishandles it) | folded into the one command above — the create runs in-process via the helper; **no agent hop** |
| Haiku's job | detect intent, extract fields, build envelope, parse stdout, quote+exec a second command | detect intent, extract natural-language fields, run one command, read `status` — the minimum surface |
| Incomplete note | record `PendingClarificationRecord`, ask Kent once | unchanged — `--create` returns `needs_clarification` with the missing fields; capture records the clarification and asks Kent. Reply later handled by felix-admin-calendar (Kent→agent, not capture→agent) |
| gog | never (capture had no gog) | never |

The `--create` mode is added to `scripts/inbox/route_calendar_event.py` (D4);
the deterministic field-mapping + helper invocation stay out of the agent prompt
(two-layer doctrine). The clarification store is the existing JSON array at
`/data/services/openclaw/state/pending-calendar-clarifications.json` (unchanged).

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
agent-prompt-sync timer and require **no rebaseline** — per
`audited-surfaces.json`, `openclaw-agent-prompts` is an *unmonitored* surface
(`rebaseline_required: false`; the audit hashes only `openclaw.json`). The
**only** rebaseline trigger here is the `openclaw.json` `skills` edit (removing
`gog`) → `openclaw-config` surface → manual out-of-band edit + gateway restart +
**manual rebaseline**. See quickstart.md step 5.
