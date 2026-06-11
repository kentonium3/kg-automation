# Felix Calendar Subagent Extraction

**Mission slug**: `felix-calendar-subagent-extraction-01KTTA33`
**Mission ID**: `01KTTA33XZ0VG1SXQH3YD854K1`
**Mission type**: `software-dev`
**Origin**: kentonium3/kg-automation#579 (P1-bug, area/felix-core)
**Status**: spec-phase

## Purpose

### TLDR
Restore Felix's WhatsApp reply relay by extracting calendar handling into a new `felix-admin-calendar` subagent so `main/AGENTS.md` fits under the OpenClaw 12K bootstrap context cap.

### Context
Since 2026-06-09 ~17:00 UTC, Felix's main agent has stopped relaying subagent replies to WhatsApp because `main/AGENTS.md` (25,982 chars) grew past OpenClaw's 12K bootstrap context cap. The runtime silently truncates the file at injection time, dropping the "Habit tracking delegation" section (lines 217–235) and everything past it. Without those delegation instructions in context, the main agent processes inbound DMs and the subagent produces a reply, but no outbound `[whatsapp] Sending message` event ever fires — the reply is lost. Scheduled outbound flows (morning checkin, IDLE pings, periodic digests) bypass the relay and still work, so the visible symptom is "Felix reads my DMs but never replies."

This mission resolves the bug by extracting the largest delegation section — the calendar event creation handler and calendar clarification reply handler (lines 259–440, ~10–11K chars, ~41% of `main/AGENTS.md`) — into a new `felix-admin-calendar` subagent that follows the established Felix subagent pattern (`felix-admin-habits`, `felix-admin-capture`, `felix-admin-tasker`, `felix-admin-escalation`, `felix-doc-auditor`). `main/AGENTS.md` is also tightened to fit under the 12K hard cap. Calendar gets a permanent architectural home with a broader charter for future work; conversational reply flow is restored.

## Domain Language

| Canonical term | Meaning | Synonyms to avoid |
|---|---|---|
| Subagent | An OpenClaw agent that owns one narrow Felix domain, dispatched to by the main agent. Current roster: `felix-admin-habits`, `felix-admin-capture`, `felix-admin-tasker`, `felix-admin-escalation`, `felix-doc-auditor`. | "Helper agent", "child agent" |
| Main agent | The orchestrating Felix agent (`main`) that receives inbound WhatsApp DMs, dispatches to subagents, and relays subagent replies back. | "Orchestrator", "router" |
| Bootstrap context cap | OpenClaw 3.2.x runtime limit of 12,000 chars for `AGENTS.md` injection into agent context at session-init. When exceeded, the runtime emits a `truncating in injected context` warning and silently drops the tail. | "Token limit", "context window" |
| Effective source budget | The looser ~14–15K char threshold per the `reference_openclaw_gotchas` memory; below this, the truncation warning does not fire even though the file is over the documented cap. | "Soft cap" |
| Rebaseline | Resetting `security-monitor` audit baselines on office2 after touching an audited surface (per kentonium3/kg-automation#557). Required for openclaw agent prompts + openclaw config changes. | "Reset audit", "snapshot refresh" |
| `felix-admin-calendar` | The new subagent created by this mission. Owns all calendar-substrate work. | "calendar agent", "cal-bot" |

## User Scenarios & Testing

### Primary scenario (calendar DM → relayed reply)

1. Kent sends a calendar-related WhatsApp DM to Felix (e.g., "schedule a 30-min check-in with Rob next Wednesday afternoon").
2. Felix main agent receives the inbound message; the bootstrap context now includes the calendar delegation section because `main/AGENTS.md` fits under the cap.
3. Main agent dispatches the message to `felix-admin-calendar`.
4. `felix-admin-calendar` handles event creation (consulting Google Calendar via `gog` as today), produces a reply.
5. Main agent relays the reply verbatim to Kent's WhatsApp channel.
6. Kent receives the reply on WhatsApp within a few seconds.

### Critical regression scenario (habit DM → relayed reply)

The originating bug specifically dropped habit delegation, so this scenario must be re-validated post-fix:

1. Kent sends a habit-status WhatsApp DM (e.g., "mark habits 1, 3, 5 complete").
2. Main agent dispatches to `felix-admin-habits`.
3. `felix-admin-habits` produces a reply.
4. Main agent relays the reply to Kent's WhatsApp within a few seconds.

### Edge cases

- **Calendar DM requiring clarification.** The existing "calendar clarification reply handler" round-trip (subagent asks a question, Kent replies, subagent finalizes) must continue to work after extraction.
- **Calendar DM that fails downstream** (e.g., gog refresh token expired per `reference_gog_credential_health_gap`). The error reply must still relay back to Kent rather than silently failing.
- **Mixed-domain DMs in the same session window.** Kent sends a habit DM then a calendar DM back-to-back; each should route to its respective subagent and the replies should not cross.
- **Bootstrap warning observation.** Restarting `openclaw-gateway.service` after deploy must produce no `agent/embedded] workspace bootstrap file AGENTS.md is NNNN chars (limit 12000); truncating in injected context` log line for the `main` agent.
- **Concurrent inbound flow with scheduled outbound.** A morning checkin fires at 7am ET; at the same window Kent sends a DM. Both paths must succeed independently (scheduled outbound was never affected by the bug, but the regression guard is explicit here).

### Out-of-scope scenarios

- Inbox-processing delegation extraction (lines 197–216 of `main/AGENTS.md`). Sitting at the truncation cliff but not yet over it; close follow-on if this mission's tightening doesn't leave it with adequate headroom.
- Raising OpenClaw's bootstrap cap (discovery Option D — rejected).
- Lazy-load delegation sections in OpenClaw (discovery Option C — rejected as upstream-owned).
- Calendar feature additions beyond the current handlers (gog refresh-token liveness, Vikunja RRULE work, attendee tracking, etc.). The new subagent's *charter* declares calendar as its domain; code-level scope is strict 1:1 with current handlers.

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | Felix's main agent shall relay subagent replies to the originating WhatsApp channel for every inbound DM that successfully produces a subagent reply. | Required |
| FR-002 | Calendar-related WhatsApp DMs shall route to a `felix-admin-calendar` subagent (not handled in `main/AGENTS.md` directly). | Required |
| FR-003 | `felix-admin-calendar` shall handle the same two scenarios currently handled in `main/AGENTS.md` lines 259–440: calendar event creation and calendar clarification replies. Behavior shall be a 1:1 functional move, not a redesign. | Required |
| FR-004 | `felix-admin-calendar` shall be registered with OpenClaw per `docs/runbooks/openclaw-agent-setup.md`: `IDENTITY.md`, `SOUL.md`, `AGENTS.md`, and an `openclaw.json` entry. | Required |
| FR-005 | `felix-admin-calendar` shall be added to `docs/constitution/AGENT-REGISTRY.md` following the existing entry pattern for Felix subagents. | Required |
| FR-006 | `felix-admin-calendar`'s `AGENTS.md` shall declare a broader charter for the calendar-substrate domain (not only the two current handlers), establishing it as the home for future calendar work. | Required |
| FR-007 | Existing Felix subagents (`felix-admin-habits`, `felix-admin-capture`, `felix-admin-tasker`, `felix-admin-escalation`, `felix-doc-auditor`) shall continue to function with no behavioral regression. | Required |
| FR-008 | Scheduled outbound flows (morning checkin, IDLE pings, periodic digests) shall continue to function with no behavioral regression. | Required |
| FR-009 | A deploy script shall apply this change to office2 following the strict-order-of-operations safe-deploy pattern (per DIR-005): pre-flight → copy artifacts → verify artifacts → edit `openclaw.json` → post-flight smoke test. | Required |
| FR-010 | The deploy script shall include or document the rebaseline step that resets `security-monitor` baselines post-deploy (canonical command per `docs/runbooks/security-baseline-ops.md`), with the merge commit recording either `Rebaseline: completed at <ts>` or an explicit reason for omission. | Required |
| FR-011 | All architecture documentation surfaces flagged by `docs/design/architecture/data/signal-to-doc-map.json` for change classes `openclaw-agent-added`, `audited-surface-touched`, and any others applicable to this change shall be updated as part of the merge. | Required |
| FR-012 | Calendar handler content shall be removed from `main/AGENTS.md` (lines 259–440 of the current file) as part of the same change; `main/AGENTS.md` shall not retain duplicated or stale calendar handler text. | Required |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | Post-extraction, `main/AGENTS.md` shall fit under the OpenClaw 12K bootstrap context hard cap. | `wc -c scripts/openclaw/agents/main/AGENTS.md` reports a value strictly less than 12,000. | Required |
| NFR-002 | After `openclaw-gateway.service` restart and 24h observation, no `truncating in injected context` warning shall be emitted for `agent:main:*` session-init events. | Zero matching log lines in `journalctl --user -u openclaw-gateway --since "<deploy-time>"`. | Required |
| NFR-003 | WhatsApp reply latency (from `[whatsapp] Inbound message` to `[whatsapp] Sent message` in gateway logs) for normal DMs shall not regress meaningfully versus pre-bug baseline. | P95 latency ≤ 30 seconds for the relay segment over a 24-hour observation window with at least 10 sample replies. | Required |
| NFR-004 | `felix-admin-calendar`'s `AGENTS.md` shall itself fit under the OpenClaw 12K bootstrap context hard cap. | `wc -c scripts/openclaw/agents/felix-admin-calendar/AGENTS.md` reports a value strictly less than 12,000. | Required |

## Constraints

| ID | Constraint | Source | Status |
|---|---|---|---|
| C-001 | All Felix services remain Tailscale-internal; no public-internet exposure for any new agent endpoint. | DIR-003 | Required |
| C-002 | Deploy follows the strict-order-of-operations safe-deploy pattern; no cron pause/resume; manual rollback only. | DIR-005 / DIR-006 | Required |
| C-003 | All openclaw cron operations route through `openclaw cron list/edit/run/runs`; no system crontab usage. | DIR-007 | Required |
| C-004 | Office2 deploy targets are read from `/home/claude/.openclaw/openclaw.json` for `workspace` and `agentDir`; no hardcoded path assumptions. | DIR-008 | Required |
| C-005 | Mission execution shall not modify the project charter (`.kittify/charter/`) or any `kitty-specs/` content outside this mission's own `feature_dir`. | Spec-kitty workflow invariants | Required |
| C-006 | Production deploy actions on office2 run as the `claude` user via `ssh office2-claude`. Sudo-requiring steps stop and present commands for manual operator execution. | CLAUDE.md | Required |
| C-007 | The mission shall not extract delegation sections other than calendar (inbox-processing delegation stays in `main/AGENTS.md` for this mission per discovery Q3). | Discovery Q3 (Option A) | Required |

## Success Criteria

| ID | Criterion |
|---|---|
| SC-001 | After deploy, sending a habit-status WhatsApp DM to Felix produces a relayed reply on WhatsApp within 30 seconds. |
| SC-002 | After deploy, sending a calendar-related WhatsApp DM produces a relayed reply on WhatsApp within 30 seconds and the event is created (or clarification requested) as designed. |
| SC-003 | After deploy, `main/AGENTS.md` is under 12,000 characters. |
| SC-004 | After deploy, no `truncating in injected context` warning is observed for `main` agent bootstrap over a 24-hour observation window. |
| SC-005 | Inbox triage, tasker, escalation, and doc-auditor delegation flows each continue to work as before (verified via at least one representative DM or scheduled flow per subagent). |
| SC-006 | Morning checkin, IDLE pings, and periodic digest scheduled outbound flows continue to fire and deliver during a 24-hour observation window post-deploy. |
| SC-007 | Security-monitor baselines are reset post-deploy and the subsequent audit run completes with no spurious surface drift alerts. |
| SC-008 | `docs/constitution/AGENT-REGISTRY.md` and all signal-to-doc-map-flagged architecture surfaces show the new `felix-admin-calendar` agent and reflect the post-mission state. |

## Key Entities

| Entity | Lifecycle | Notes |
|---|---|---|
| `scripts/openclaw/agents/felix-admin-calendar/IDENTITY.md` | New | Per openclaw-agent-setup runbook |
| `scripts/openclaw/agents/felix-admin-calendar/SOUL.md` | New | Per openclaw-agent-setup runbook |
| `scripts/openclaw/agents/felix-admin-calendar/AGENTS.md` | New | Calendar handler content + broader charter declaration |
| `scripts/openclaw/agents/main/AGENTS.md` | Modified | Calendar sections removed; whole-file tightening to <12K chars |
| `openclaw.json` (office2: `/home/claude/.openclaw/openclaw.json`) | Modified | New agent registration entry |
| `docs/constitution/AGENT-REGISTRY.md` | Modified | New entry for felix-admin-calendar |
| `docs/design/architecture/data/*.json` (subset flagged by signal-to-doc-map) | Modified | Service / agent inventory surfaces |
| `scripts/deploy/<mission-slug>.sh` | New | Strict-order-of-operations deploy wrapper |

## Assumptions

- The current calendar handlers in `main/AGENTS.md` lines 259–440 are a faithful representation of intended calendar workflow; no hidden behavior depends on them being executed in the *main* agent's context rather than a subagent's.
- The 12K bootstrap context cap is the relevant runtime threshold for OpenClaw 3.2.x. It is not a per-installation tunable that should be raised as the fix (discovery Option D explicitly rejected).
- The standard Felix subagent architectural pattern (single-domain charter, narrow scope, `IDENTITY.md` / `SOUL.md` / `AGENTS.md` triad, openclaw.json registration) is the correct shape for calendar work.
- The reply relay is stateless; no in-flight calendar conversation requires state migration at cutover.
- The signal-to-doc-map.json entries for `openclaw-agent-added` (or equivalent change classes) accurately enumerate the architecture docs that need updating. Plan phase verifies this against the live map.
- Future calendar work (gog refresh-token liveness from `reference_gog_credential_health_gap`, Vikunja RRULE integration from project_vikunja_pr_2032_contribution, attendee tracking) is out of scope for this mission and will be follow-on issues filed against the new `felix-admin-calendar` subagent's charter.

## Scope

### In scope
- Create `felix-admin-calendar` subagent (IDENTITY.md, SOUL.md, AGENTS.md, openclaw.json registration)
- Move calendar event creation handler + calendar clarification reply handler from `main/AGENTS.md` (current lines 259–440) into `felix-admin-calendar/AGENTS.md`, with no behavioral change
- Declare a broader calendar-substrate charter inside `felix-admin-calendar/AGENTS.md`
- Tighten `main/AGENTS.md` to fit under the 12K hard cap
- Update `docs/constitution/AGENT-REGISTRY.md` for the new subagent
- Update architecture surfaces flagged by signal-to-doc-map.json
- Deploy script and runbook updates as needed
- Rebaseline on office2 post-deploy (audited surfaces touched: openclaw agent prompts, openclaw config)
- Post-deploy verification covering SC-001 through SC-008

### Out of scope
- Extracting other delegation sections (inbox-processing, etc.) — close follow-on if needed
- Raising the OpenClaw bootstrap context cap (Option D from discovery)
- Implementing lazy-load delegation sections (Option C from discovery, upstream-owned)
- Gog refresh-token credential health work
- Vikunja RRULE integration
- Any net-new calendar functionality beyond what currently exists in `main/AGENTS.md`

## Open Decisions

None at spec-phase conclusion. The three discovery questions (solution approach, scope boundary, budget target) are all resolved and recorded in `## User Scenarios & Testing` and `## Constraints`.

## Notes for Plan Phase

- Probe office2 live during plan (per DIR-015): confirm current `main/AGENTS.md` char count on the deployed copy, current `openclaw.json` schema, the `agentDir` value, and that `felix-admin-calendar` is not already registered.
- Consult `docs/design/architecture/data/signal-to-doc-map.json` for the canonical list of doc targets per change class (`openclaw-agent-added`, `audited-surface-touched`, etc.) and enumerate them explicitly in plan.md so they're not missed (per #492 precedent on signal-to-doc-map usage).
- Identify deterministic vs stochastic work per Constitution Directive 6 and `docs/design/helper-script-conventions.md`. Char-count checks, file-size assertions, and post-deploy smoke tests are deterministic and should live in scripts the agent invokes.
- Confirm the rebaseline step uses the canonical command from `docs/runbooks/security-baseline-ops.md` and that the merge commit's `Rebaseline:` footer is wired into the deploy or merge step.
