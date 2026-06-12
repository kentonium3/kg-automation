# Restore WhatsApp DM Reply Delivery

**Mission ID**: `01KTVVHHBJKKG3JPMGRVHSB81P` (mid8: `01KTVVHH`)
**Mission Slug**: `restore-whatsapp-dm-reply-delivery-01KTVVHH`
**Mission Type**: software-dev
**Created**: 2026-06-11
**Source**: GitHub issue [#588](https://github.com/kentonium3/kg-automation/issues/588)
**Status**: Draft

---

## Purpose (TLDR)

Fix Felix's WhatsApp DM-reply path so inbound DMs receive a delivered reply, restoring the primary conversational interface.

## Purpose (Context)

Felix's WhatsApp DM reply delivery has been silently broken since the recent agent-extraction work, leaving cron-driven announce-mode outbound (morning checkin, IDLE pings, digests) as the only working WhatsApp surface. Inbound DMs are received and processed end-to-end, but the gateway never bridges the agent's reply output to the channel-send subsystem on DM-initiated turns. The fix restores conversational interaction, the primary daily interface for Kent to query and direct Felix via mobile.

## Intent Summary

- **Primary actor**: Kent, interacting with Felix via WhatsApp DM
- **Trigger**: Any DM sent to Felix's WhatsApp number (`+16179300916`)
- **Desired outcome**: Felix's reply (from `main` or any subagent) is delivered to the originating DM thread within normal latency (a few seconds), with the WhatsApp typing indicator firing during the agent run
- **Invariant 1**: Cron-driven announce-mode outbound (morning checkin, IDLE pings, periodic digests) continues working with no behavioral change
- **Invariant 2**: #579's truncation fix is preserved — `main/AGENTS.md` stays under the 12K cap and `felix-admin-calendar` stays cleanly registered
- **Bulk-edit?**: No — runtime/wiring bug, not a rename across files

## Background & Diagnostic Findings (from #588)

The break has been isolated to the gateway's DM-reply dispatch wiring:

- **Working**: cron `delivery.mode: "announce"` outbound — verified 16:00:07Z (580ms delivery)
- **Working**: direct CLI `openclaw agent --agent main --channel whatsapp --to ... --deliver` — verified 16:51:47Z (241ms delivery, operator-confirmed receipt)
- **Working**: inbound channel receipt (WhatsApp pairing, message delivery into the gateway)
- **Working**: agent harness — `Sent by <agent>:<model>` outputs appear in journal for every DM
- **Broken**: gateway DM-reply dispatch — agent runs complete, output never reaches channel-send. Zero `[whatsapp] Sending message` events for 30+ minutes following DM bursts.

Persistence across 4 gateway restarts (05:10, 16:18, 16:27, 16:44 UTC) rules out stuck-session-lane as the cause — this is structural / config / wiring, not transient state.

**Prime proximate-cause candidate**: `[ws] ⇄ res ✗ sessions.resolve INVALID_REQUEST errorMessage=No session found: current` errors firing repeatedly during DM-dispatched agent runs. The `current` session resolver returning empty is the strongest signal that the originating DM session is not being retrieved (or registered) when the agent reply needs routing back to that thread.

**Investigation prior** (per Kent): root cause strongly suspected to be in changes made 2026-06-09 onward (recent agent-extraction work, deploy script changes, openclaw config edits) OR a configuration issue. Vendored openclaw runtime (`/usr/lib/node_modules/openclaw/dist/`) is the lowest-priority hypothesis.

## Domain Language

| Canonical term | Meaning | Synonyms to avoid |
|---|---|---|
| Gateway DM-reply dispatch | The wiring inside openclaw-gateway that routes inbound DM → agent → reply → channel-send for DM-initiated turns | "reply path" (ambiguous), "WhatsApp loop" (vague) |
| Announce-mode delivery | `delivery.mode: "announce"` fire-and-forget cron outbound; does NOT require `current` session | "cron path", "morning checkin path" |
| `current` session | The `sessions.resolve current` lookup that the DM-reply path appears to depend on | "active session", "default session" |
| `[whatsapp] Sending message` | Gateway journal event that fires when a payload is handed to the channel-send subsystem | "outbound event" (ambiguous) |
| `[whatsapp] Sent message` | Gateway journal event that fires when WhatsApp acknowledges delivery | "ack event" |

## User Scenarios & Testing

### Primary scenarios

1. **Happy path**: Kent DMs "what's my checkin today" → gateway logs `[whatsapp] Inbound message` → main routes to `felix-admin-habits` subagent → subagent generates reply (`Sent by felix-admin-habits:haiku ...`) → gateway dispatches reply to channel-send → `[whatsapp] Sending message` + `[whatsapp] Sent message` fire → reply delivered to Kent's WhatsApp within 30 seconds, with typing indicator visible during agent run.

2. **Multi-DM burst**: Kent sends 3 DMs in quick succession (e.g., habit check + calendar request + task list query) → 3 corresponding subagent replies generated and dispatched → 3 messages delivered (none dropped, none merged, ordering preserved within a tolerance).

3. **Subagent chain**: A DM triggers `felix-admin-tasker` which routes through `felix-admin-escalation` → the final reply (from escalation or main) is delivered to the originating DM thread.

4. **Cron-only baseline (no DM)**: 7am cron fires habit checkin via `announce` mode → message delivered through unchanged announce path. No regression vs. pre-fix behavior.

### Edge cases

5. **Empty / minimal subagent reply**: Subagent returns an empty or near-empty reply → gateway either delivers gracefully or short-circuits cleanly without leaving the gateway in a stuck state.

6. **Cross-restart**: A DM arrives, agent run completes, but the gateway restarts mid-dispatch → on next start, either the in-flight reply is delivered, or the loss is observable in the journal (no silent drop).

7. **Vendored-openclaw fork** (scope-bounded): If diagnosis identifies a vendored runtime cause, mission concludes with the diagnosis + internal tracking issue; no patching of `/usr/lib/node_modules/openclaw/dist/`.

## Functional Requirements

| ID | Description | Status |
|---|---|---|
| FR-001 | Gateway DM-reply dispatch routes the agent's reply output to the channel-send subsystem for delivery to the originating DM thread on every DM-initiated turn | Confirmed |
| FR-002 | When `main` or any subagent generates a reply during a DM-initiated turn, `[whatsapp] Sending message` (followed by `[whatsapp] Sent message`) fires in the openclaw-gateway journal | Confirmed |
| FR-003 | WhatsApp typing indicator fires during DM-initiated agent runs (same outbound presence/send path) | Confirmed |
| FR-004 | Fix addresses the proximate cause around `sessions.resolve current` — either by making `current` resolvable during DM dispatch, or by removing the reply path's dependency on it | Confirmed |
| FR-005 | Cron-driven `delivery.mode: "announce"` outbound (morning checkin, IDLE pings, periodic digests) continues working with no behavioral change | Confirmed |
| FR-006 | #579's truncation fix is preserved: `main/AGENTS.md` stays under 12K cap; `felix-admin-calendar` stays cleanly registered with valid `agentDir` | Confirmed |
| FR-007 | Investigation includes an audit of changes made 2026-06-09 onward (openclaw config edits, agentDir layouts, deploy scripts, recent merges) as a *behavioral* baseline | Confirmed |
| FR-008 | Deploy script for the fix follows DIR-004 / DIR-005 strict-order safe-deploy pattern with pre-flight + post-flight verification | Confirmed |
| FR-009 | If root cause traces to vendored openclaw runtime (`/usr/lib/node_modules/openclaw/dist/`), mission concludes with an internal tracking issue and a documented operational workaround; mission does NOT patch vendored binaries | Confirmed |
| FR-010 | Acceptance test exercises the DM-initiated reply path end-to-end on office2, capturing both the journal `[whatsapp] Sending message` event and operator-confirmed WhatsApp receipt | Confirmed |
| FR-011 | Investigation references the architecture and design documentation as the initial *architectural* baseline before SSH probing or source-diving. Scope includes `docs/design/architecture/data/` JSONs (especially `service-inventory.json`, `data-flows.json`, `audited-surfaces.json`), the architecture markdown views, and `docs/design/architecture/data/signal-to-doc-map.json` for change-class doc-target lookup. Discrepancies between documented behavior and observed/discovered behavior are recorded during discovery (in `research.md` or equivalent) with source and resolution disposition | Confirmed |
| FR-012 | Upon fix resolution, gaps or inconsistencies discovered between the architecture/design docs and the actual (resolved-state) system are corrected in the same mission. At minimum: openclaw-related entries in `service-inventory.json`, DM-reply path entries in `data-flows.json`, the openclaw-gateway runbook, and any architecture markdown views that referenced the corrected behavior. Full doc list derived from `signal-to-doc-map.json` change-class lookup | Confirmed |

## Non-Functional Requirements

| ID | Description | Threshold | Status |
|---|---|---|---|
| NFR-001 | DM reply delivery latency from inbound receipt to `[whatsapp] Sent message` event | < 30 seconds for happy-path subagent reply | Confirmed |
| NFR-002 | `sessions.resolve INVALID_REQUEST: No session found: current` errors during DM-initiated agent runs after the fix | 0 occurrences in 30 minutes of mixed-DM exercise (or `current` lookup removed from the reply path, verified by absence of the call) | Confirmed |
| NFR-003 | `truncating in injected context` warnings on `agent:main:*` bootstrap after the fix | 0 occurrences (preserves #579 fix) | Confirmed |
| NFR-004 | Cron `announce` outbound delivery latency after the fix | < 1 second (current baseline ~580ms; no degradation) | Confirmed |
| NFR-005 | Verifiability of the fix from a single repro session | Captured in `journalctl --user -u openclaw-gateway` evidence + operator-observed WhatsApp delivery | Confirmed |

## Constraints

| ID | Description | Status |
|---|---|---|
| C-001 | Vendored openclaw runtime binaries at `/usr/lib/node_modules/openclaw/dist/` are OUT OF SCOPE for direct modification. If root cause traces to runtime code, mission concludes with an internal tracking issue per FR-009. | Confirmed |
| C-002 | Investigation prior: strongly suspect root cause is in changes made 2026-06-09 onward OR a configuration issue. Diff/audit recent changes (FR-007) and read architecture docs (FR-011) BEFORE source-diving into openclaw runtime. | Confirmed |
| C-003 | Tier 2 (Application/State) per change-risk taxonomy — requires Restic backup ≤24h before deploy. Affects audited surfaces per #557, so deploy script MUST emit a rebaseline trailer (`Rebaseline: completed at <ts>` or `Rebaseline: not required — <reason>`). | Confirmed |
| C-004 | All work targets office2 (DIR-001). Mac is authoring only. | Confirmed |
| C-005 | Linux-only (DIR-002). No Windows references. | Confirmed |
| C-006 | Deploy follows DIR-005 strict-order safe-deploy pattern: pre-flight → copy artifacts → verify artifacts → edit config → post-flight smoke test. No system crontab use (DIR-007). | Confirmed |
| C-007 | SSH as `office2-claude` for agent traceability (CLAUDE.md). claude user has no sudo; if root commands needed, surface to Kent for manual `office2-kgale` execution. | Confirmed |
| C-008 | WhatsApp `dmPolicy: disabled` remains unchanged — reply flow happens on existing paired session. | Confirmed |
| C-009 | Doc-sync per DIR-014 is mandatory. FR-012 carries the specific reconciliation scope and the `signal-to-doc-map.json` lookup mechanism. | Confirmed |

## Key Entities

| Entity | Shape / Source |
|---|---|
| Inbound DM event | `[whatsapp] Inbound message <from> -> <to> (direct, <N> chars)` in `journalctl --user -u openclaw-gateway` |
| Agent reply payload | `Sent by <agent>:<model>\n<reply text>` in gateway journal |
| Channel-send event | `[whatsapp] Sending message -> <sha>` → `[whatsapp] Sent message <id> -> <sha> (<ms>ms)` |
| Session resolution call | `[ws] ⇄ res ... sessions.resolve <key> ...` — `<key>` includes `current` for the DM-reply path |
| openclaw.json agent config | `/data/services/openclaw/openclaw.json` on office2 (canonical workspace path; see DIR-008) |
| Agent directory | `~/.openclaw/agents/<slug>/agent/` containing AGENTS.md + IDENTITY.md + SOUL.md + auth/models/plugins config |

## Success Criteria

| ID | Description |
|---|---|
| SC-001 | 5 consecutive test DMs sent to Felix during smoke test all receive replies in WhatsApp within 30 seconds each |
| SC-002 | Journal shows matching `[whatsapp] Sending message` + `[whatsapp] Sent message` events for every DM-initiated agent reply during the smoke test |
| SC-003 | Zero `sessions.resolve INVALID_REQUEST: No session found: current` errors during the DM smoke test — OR, if the `current` lookup is removed from the reply path, the corresponding call is verified absent |
| SC-004 | WhatsApp typing indicator visibly fires for the operator during DM-initiated agent runs |
| SC-005 | Daily 7am cron habit checkin continues to deliver via `[whatsapp] Sending message` path (verified by the next-day morning run after deploy) |
| SC-006 | No `truncating in injected context` warnings on `agent:main:*` bootstrap during post-deploy verification (preserves #579 fix) |
| SC-007 | Architecture / design docs are reconciled with the resolved-state system per FR-012; merge commit either references the doc updates or records `Rebaseline: not required — <reason>` where applicable |

## Assumptions

- A1: Felix's WhatsApp pairing on office2 remains valid throughout the mission. Re-pairing is out of scope; if pairing is lost during work, mission pauses until restored.
- A2: The `+16179300916` test number remains the canonical operator phone for DM-initiated smoke tests.
- A3: The openclaw runtime version on office2 is `2026.5.28` (per `openclaw doctor`). Upgrade/downgrade of openclaw is not contemplated by this mission; if a workaround requires a runtime change, it surfaces as a follow-up.
- A4: `main/AGENTS.md` is 11,934 chars post-#579 fix and remains under cap throughout the mission (any spec authoring that bloats it back over 12K is regression).
- A5: The `signal-to-doc-map.json` change-class taxonomy adequately captures the doc surfaces touched by this fix. If a doc surface is missing from the map, that itself is a small reconciliation deliverable.

## Dependencies

- **GitHub issue #588** — source of truth for the bug report and diagnostic evidence
- **#579** (CLOSED via 37b3bf56) — truncation fix; this mission must preserve its outcome
- **#557** — rebaseline obligation for audited surfaces; mission deploy script emits the required trailer
- **Felix Constitution** (`docs/constitution/FELIX-CONSTITUTION.md`) — Directive 6 (deterministic vs stochastic split), Directive 8 (symptom required for issues)
- **Engineering principles** (`docs/design/engineering-principles.md`) — runtime state, integration boundaries, observability per feature
- **Architecture documentation** (`docs/design/architecture/`) — FR-011 baseline; FR-012 reconciliation target

## Architecture Impact

The fix will modify one or more of the following surfaces; the precise set is bounded by what diagnosis reveals:

- **openclaw service config / agent surface** — likely (Tier 2). Probably touches: `openclaw.json` (one or more agent entries), agentDir contents (`AGENTS.md`, `IDENTITY.md`, `SOUL.md`, channels/plugins config), or the gateway routing surface exposed by agent config.
- **systemd user unit** — possible if gateway start-up or environment needs to change.
- **Architecture data JSONs** — Almost certain to require update for FR-012:
  - `docs/design/architecture/data/service-inventory.json` — openclaw-gateway service entry, channels exposed, dependencies
  - `docs/design/architecture/data/data-flows.json` — DM-reply flow (currently may be missing or incorrect)
  - `docs/design/architecture/data/audited-surfaces.json` — verify openclaw agent prompts + openclaw config + systemd user units are all listed; add if missing
- **Architecture markdown views** — any view that diagrams or narrates the DM-reply path
- **Runbooks** — `docs/runbooks/` likely needs an openclaw-gateway diagnostic runbook update (or new entry) covering the `sessions.resolve current` failure mode
- **Diagnostics index** — `docs/diagnostics/` or `docs/INDEX.md` cross-reference updates

Filter `signal-to-doc-map.json` by `match.source == "mission-architecture-impact"` and the following `change_class` values during plan:
- `service-added-or-modified` (openclaw-gateway entry)
- `data-flow-added-or-modified` (DM-reply path)
- `systemd-unit-added-or-modified` (if gateway unit changes)
- `runbook-modified` (openclaw-gateway diagnostic runbook)
- `architecture-doc-added` (if a new diagnostic view is warranted)

## Out of Scope

- Patching vendored `openclaw` runtime binaries (per FR-009 / C-001)
- Upgrading or downgrading `openclaw` runtime version (per A3)
- Re-pairing WhatsApp on office2 (per A1)
- Generalizing the fix beyond DM-reply dispatch (e.g., cron-mode improvements, channel-rate-limiting, multi-number routing)
- Changes to `dmPolicy: disabled` configuration (per C-008)
- Migration of `felix-admin-*` agent set membership (out of band — handled in adjacent missions)
