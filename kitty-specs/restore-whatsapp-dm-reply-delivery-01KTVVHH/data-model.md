# Data Model: Restore WhatsApp DM Reply Delivery

**Mission**: `restore-whatsapp-dm-reply-delivery-01KTVVHH`
**Phase**: Plan-phase data model
**Status**: Draft (observational model — this mission does not persist new data; the model below describes the runtime state machine the mission must restore to healthy operation)

This mission is a bug-fix in runtime wiring. There are no new persistent entities. The entities below describe the **observable runtime state** that the mission's acceptance test will assert against, and the **invariants** that must hold post-fix.

---

## E1 — Session (gateway-owned, in-memory)

**Source**: `/usr/lib/node_modules/openclaw/dist/runs-DMxJUP3Q.js` `ACTIVE_EMBEDDED_RUNS` Map + `setActiveEmbeddedRun` / `clearActiveEmbeddedRun` + `getDiagnosticSessionActivitySnapshot`.

| Field | Type | Notes |
|---|---|---|
| `sessionId` | UUID | Stable identity for a session lifecycle. Re-emitted by gateway on restart for the same `sessionKey` (observed behavior). |
| `sessionKey` | String | Compound key: `agent:<agent_id>:<channel>:<scope>:<peer>`. Example: `agent:main:whatsapp:direct:+16179300916`. The mission's broken path always shows scope=`direct` (DM) and peer=Kent's number. |
| `state` | Enum | `processing` / `idle`. Set by `setActiveEmbeddedRun` (→ processing) and `clearActiveEmbeddedRun` (→ idle). |
| `queueDepth` | Int | Count of queued messages waiting for the active run. |
| `lastProgressReason` | String | Last activity marker; values include `embedded_run:started`, `embedded_run:ended`, `model.call.started/completed/error`, `tool.execution.started/completed/error/blocked`. The bug signature is `lastProgressReason = "embedded_run:started"` for ≥6 minutes. |
| `lastProgressAt` | Timestamp | When `lastProgressReason` was last touched. |
| `activeEmbeddedRuns` | Set\<String\> | Per-session set of active embedded-run work-keys. Populated by `markDiagnosticEmbeddedRunStarted`; cleared by `markDiagnosticEmbeddedRunEnded`. Bug signature: set stays non-empty for ≥6 minutes. |
| `activeModelCalls` | Set\<Object\> | Per-session set of active model-call descriptors. **Notably empty during the bug** — the journal classifies `activeWorkKind=embedded_run` (not `model_call`), meaning no model call is registered as active during the stall, even though the agent does produce text output. |
| `activeTools` | Set\<Object\> | Per-session set of active tool-call descriptors. Empty in the broken DM path. |

**Invariant (must hold post-fix)**:

> For every observed `Inbound message` event whose target is in `channels.whatsapp.allowFrom`, exactly one `Session` enters `processing` within ≤2s, makes progress (model/tool/embedded events advance `lastProgressReason`), and returns to `idle` via `clearActiveEmbeddedRun` within the run's natural duration. **`lastProgressReason` may visit `embedded_run:ended` AT MOST ONCE per `(sessionKey, runId)` pair.**

The current pre-fix violation: `embedded_run:ended` is never reached; instead the stuck-recovery path fires `abort_embedded_run`.

---

## E2 — EmbeddedRun (run lifecycle handle)

**Source**: `runs-DMxJUP3Q.js` exports `setActiveEmbeddedRun`, `clearActiveEmbeddedRun`, `forceClearEmbeddedAgentRun`.

| Field | Type | Notes |
|---|---|---|
| `runId` | UUID | Per-run identity. Multiple runs can share a `sessionId` over time. |
| `sessionId` | UUID | FK to `Session`. |
| `sessionKey` | String | Mirror of `Session.sessionKey` (for routing). |
| `sessionFile` | Path | Per-run session-state file on disk (gateway uses these for replay/recovery). |
| `handle` | Object | Opaque process/promise handle the runtime uses to control the run. |

**Lifecycle states**:

```
   ┌──────────────────────────────────────────────────────┐
   │             (no run)                                 │
   └──────────────────────────────────────────────────────┘
                │  setActiveEmbeddedRun({sessionId, handle, sessionKey, sessionFile})
                ▼
   ┌──────────────────────────────────────────────────────┐
   │ ACTIVE_EMBEDDED_RUNS[sessionId] = handle              │
   │ lastProgressReason = "embedded_run:started"           │
   │ activity.activeEmbeddedRuns.add(workKey)              │
   └──────────────────────────────────────────────────────┘
                │
                │  ──── HAPPY PATH: agent run completes ────►  clearActiveEmbeddedRun(sessionId, handle, ...)
                │                                                ▼
                │                                              ┌──────────────────────────────────────────┐
                │                                              │ delete ACTIVE_EMBEDDED_RUNS[sessionId]    │
                │                                              │ lastProgressReason = "embedded_run:ended" │
                │                                              │ state = idle, reason = "run_completed"    │
                │                                              │ notifyEmbeddedRunEnded(sessionId)         │
                │                                              └──────────────────────────────────────────┘
                │
                │  ──── BUG PATH (current) ────────────────────►  no caller invokes clearActiveEmbeddedRun
                │                                                 │
                │                                                 │ (stale-threshold 378s)
                │                                                 ▼
                └─►  forceClearEmbeddedAgentRun(sessionId, sessionKey, reason="stuck_recovery")
                                                                  │
                                                                  ▼
                                                              ┌──────────────────────────────────────────┐
                                                              │ delete ACTIVE_EMBEDDED_RUNS[sessionId]    │
                                                              │ lastProgressReason = "embedded_run:ended" │
                                                              │ state = idle, reason = "stuck_recovery"   │
                                                              │ run is aborted; NO reply dispatched       │
                                                              └──────────────────────────────────────────┘
```

**Invariant (must hold post-fix)**: Every `setActiveEmbeddedRun` for a DM-initiated session is followed by a `clearActiveEmbeddedRun` (NOT `forceClearEmbeddedAgentRun`) within the run's natural duration. The "stuck recovery" branch is a safety net for genuine hangs, not the normal completion path.

---

## E3 — ChannelEvent (journal observation entity)

**Source**: openclaw-gateway journal (`journalctl --user -u openclaw-gateway`). This is the canonical observation substrate the smoke test asserts against.

| Event | Format (regex-able) | Phase |
|---|---|---|
| `whatsapp.inbound` | `[whatsapp] Inbound message <from> -> <to> (direct, N chars)` | Session create |
| `bootstrap` | `[agent/embedded] workspace bootstrap file AGENTS.md is N chars … sessionKey=…` | Session warm-up |
| `agent.output` | `Sent by <agent>:<model>\n<reply text>` | Agent produces output (workflow marker per #561). **Note**: this is the AGENT'S stdout, NOT a gateway lifecycle event. Used by the smoke test as a "did the agent run at all" signal, but does NOT prove delivery. |
| `whatsapp.send` | `[whatsapp] Sending message -> sha256:<digest>` | Channel dispatch |
| `whatsapp.sent` | `[whatsapp] Sent message <id> -> sha256:<digest> (Nms)` | Channel acknowledged |
| `diagnostic.stalled` | `[diagnostic] stalled session: … classification=stalled_agent_run … lastProgress=embedded_run:started …` | Bug signature — fires every 30s |
| `diagnostic.recovery` | `[diagnostic] stuck session recovery: … action=abort_embedded_run aborted=true drained=true` | Bug terminal — recovery aborted the run |
| `sessions.resolve.fail` | `[ws] ⇄ res ✗ sessions.resolve … errorCode=INVALID_REQUEST errorMessage=No session found: current` | Downstream symptom — some caller asked for the `current` session while the broken session was stuck |

**Smoke-test acceptance pattern (post-fix)**:

For each test DM sent:
- ✓ exactly one `whatsapp.inbound` event matching the DM
- ✓ ≥1 `agent.output` event (`Sent by …`) within 30s
- ✓ exactly one `whatsapp.send` + `whatsapp.sent` pair within 30s of the inbound
- ✗ ZERO `diagnostic.stalled` events for that `sessionKey`
- ✗ ZERO `diagnostic.recovery` events for that `sessionKey`
- ✗ ZERO `sessions.resolve.fail current` events within the smoke window

---

## E4 — DocumentationReconciliation (mission deliverable — FR-012)

This is not a runtime entity; it's the structured set of doc edits the mission produces. Tracked so the implementation lane WPs have an explicit deliverable scope.

| ID | Source-of-truth doc | Reconciliation type | Reason |
|---|---|---|---|
| DR-1 | `docs/design/architecture/data/service-inventory.json` | Update — openclaw-gateway entry | version + dm_policy + session.dmScope (per research §1.1–1.3) |
| DR-2 | `docs/design/architecture/data/data-flows.json` | Add new entry — `whatsapp-dm-reply` | DM-reply path currently undocumented (per research §1.4) |
| DR-3 | `docs/design/architecture/data/audited-surfaces.json` | Verify (no edit if coverage is complete) | Confirm openclaw-config + openclaw-agent-prompts cover all touched surfaces |
| DR-4 | `docs/design/architecture/service-inventory.md` | Update — narrative mirror of DR-1 | Documentation-Standards Directive |
| DR-5 | `docs/design/architecture/data-flows.md` + `data-flows.view.md` | Update + add — narrative + Mermaid mirror of DR-2 | Documentation-Standards Directive |
| DR-6 | `docs/runbooks/openclaw-agent-setup.md` | Update — add a "DM-reply lifecycle troubleshooting" section | Operator readability for the next time this class of bug recurs |
| DR-7 | `docs/INDEX.md` | Update only if a new runbook is added (DR-6 is an update, not a new file) | Documentation discoverability |
| DR-8 | Memory `project_whatsapp_dmpolicy.md` | Update — change `disabled` → `allowlist` | Per research §1.2 — current memory is stale |
| DR-9 | New memory `reference_openclaw_dm_reply_lifecycle` | Add — capture embedded_run start/end markers + stuck-session signature + recovery action | Future-investigation cost reduction (per Engineering Principle "observability per feature") |

---

## E5 — RebaselineAttestation (post-deploy obligation)

This mission touches audited surfaces (openclaw-agent-prompts and/or openclaw-config per `audited-surfaces.json`), so per #557:

- The deploy script MUST emit one of these two trailer lines in the final commit:
  - `Rebaseline: completed at <ISO8601-UTC>` — if the rebaseline was executed as part of the deploy
  - `Rebaseline: not required — <reason>` — if the deploy did not touch a baseline-affecting surface (only applies to no-op missions; this one will require rebaseline)
- Operator command (per `audited-surfaces.json#rebaseline_command`): `ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'`

---

## Mapping back to spec

| Spec Requirement | Data-model linkage |
|---|---|
| FR-001 (gateway DM-reply dispatch) | Invariant on E1: `embedded_run:ended` reached via `clearActiveEmbeddedRun`. |
| FR-002 (`Sending message` fires) | E3 smoke pattern: `whatsapp.send` + `whatsapp.sent` per DM. |
| FR-003 (typing indicator) | E3: same outbound presence path; verified by operator-observed typing. |
| FR-004 (`sessions.resolve current` proximate cause) | E3 `sessions.resolve.fail` is treated as DOWNSTREAM symptom per research §3.5; success criterion = absence of this event during smoke. |
| FR-005 (cron `announce` continues) | E3: existing `whatsapp.send` events for cron continue with no regression. |
| FR-006 (#579 preservation) | E3 bootstrap event: no `truncating in injected context` warning for `agent:main:*` post-deploy. |
| FR-011 + FR-012 (docs reconciliation) | E4 (DR-1 through DR-9). |
| C-003 (#557 rebaseline) | E5 trailer obligation. |
