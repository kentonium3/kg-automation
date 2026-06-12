# Research: Restore WhatsApp DM Reply Delivery

**Mission**: `restore-whatsapp-dm-reply-delivery-01KTVVHH`
**Phase**: Plan-phase research (full root-cause depth per Decision `01KTVXK5AT0X8BC5EAEDHBGYV8`)
**Date**: 2026-06-11

This document captures the architectural-baseline review (FR-011), recent-changes audit (FR-007), live diagnostic probe of office2 (DIR-015), and the resulting root-cause hypothesis ranking that the implementation lane(s) will test.

---

## 1. Architectural baseline (FR-011) — discrepancies found

Read from `docs/design/architecture/data/`:

### 1.1 Documented vs deployed: openclaw-gateway version
- **Documented** (`service-inventory.json`): `version: "v2026.3.24"`
- **Deployed** (`openclaw --version`): `OpenClaw 2026.5.28 (e932160)`
- **Last config touch** (`/home/claude/.openclaw/openclaw.json#meta.lastTouchedAt`): `2026-06-02T18:18:52Z`
- **Doc-debt**: stale by 1 patch-cycle. Reconciliation target for FR-012.

### 1.2 Documented vs deployed: whatsapp dm_policy
- **Documented** (`service-inventory.json#openclaw-gateway.channels.whatsapp.dm_policy`): `"disabled"` (per memory `project_whatsapp_dmpolicy.md`, changed 2026-03-31)
- **Deployed** (`openclaw.json#channels.whatsapp.dmPolicy`): `"allowlist"` with `allowFrom: ["+16179300916"]`
- **Reality**: the deployed config permits DMs from Kent's number. This is intentional but undocumented.
- **Doc-debt**: significant; reconciliation target for FR-012. The memory `project_whatsapp_dmpolicy.md` is also stale.

### 1.3 Undocumented config: session scoping
- **Deployed** (`openclaw.json#session.dmScope`): `"per-channel-peer"`
- **Documented**: no architecture doc mentions session scoping
- **Doc-debt**: new arch surface, missing entirely. Reconciliation target for FR-012.

### 1.4 Missing data-flow: DM-reply path
- `data-flows.json` (1403 lines, 30+ flows registered) contains **no entry** for the inbound-WhatsApp → main/subagent → reply → channel-send flow.
- Documented flows are: vikunja-web-ui, obsidian-sync, second-brain-sync, nightly-backup, security-audit, openclaw-vikunja-api, observation-digest, habits-completion-* (multiple), escalation-* (multiple), enrichment-* (multiple), doc-audit-* (multiple).
- **No flow** describes how an inbound WhatsApp message reaches an agent and how the agent's reply reaches the channel-send subsystem.
- **Doc-debt**: critical gap. Reconciliation target for FR-012.

### 1.5 Audited-surfaces coverage
- `audited-surfaces.json` correctly lists `openclaw-agent-prompts` and `openclaw-config` as rebaseline-required surfaces.
- The mission's fix will touch one or both of these → #557 rebaseline trailer required in merge commit.

### 1.6 Doc-target lookup (signal-to-doc-map)
For the upcoming fix, the relevant `change_class` filters from `signal-to-doc-map.json#match.source == "mission-architecture-impact"`:

| change_class | doc_targets |
|---|---|
| `service-added-or-modified` | service-inventory.json + .md, service-dependencies.view.md, felix-capability-roadmap.md |
| `data-flow-added-or-modified` | data-flows.json + .md, data-flows.view.md |
| `runbook-modified` | INDEX.md |
| `runbook-added` (if a new diagnostic runbook is warranted) | INDEX.md, DEVELOPER_PORTAL.md |
| `agent-prompt-changed` (if AGENTS.md gets updated) | service-inventory.json + .md, openclaw-agent-setup.md, agent-prompt-sync-ops.md, audited-surfaces.json |
| `systemd-unit-added-or-modified` (if gateway unit changes) | service-inventory.json + .md, audited-surfaces.json |

---

## 2. Recent-changes audit (FR-007)

Git log since `2026-06-09T00:00Z` touching openclaw-related paths:

| Commit | Date | Summary | Suspect? |
|---|---|---|---|
| `c7509851` | 2026-06-11 13:31 | feat(restore-dm-reply): add mission spec for #588 | this mission |
| `3b500d3b` | 2026-06-11 12:45 | fix(deploy-felix-admin-calendar): add Stage 3b idempotent agentDir setup | Inline fix today. Touches agentDir layout for felix-admin-calendar. **Sequence:** the agentDir was missing → manually copied from felix-admin-habits → this commit folds the fix into the deploy script. The DM-reply break PRE-DATED the agentDir creation, so this is not the root cause. |
| `a814f2e4` | 2026-06-11 01:22 | chore(#01KTTA33): Rebaseline trailer | observability only |
| `3f0ab7a6` | 2026-06-11 01:11 | fix(deploy-felix-admin-calendar): use `python3 -m pytest` | toolchain only |
| `3208656d` | 2026-06-11 01:03 | chore(#01KTTA33): flip #579 verdict | doc-only |
| `132963b1` | 2026-06-11 01:01 | fix(WP01-tests): disambiguate test package | tests only |
| `ea057955` | 2026-06-11 00:57 | chore(#01KTTA33): set baseline_merge_commit | doc-only |
| **`37b3bf56`** | **2026-06-11 00:57** | **feat(kitty/mission-felix-calendar-subagent-extraction-01KTTA33): squash merge** | **HIGH SUSPECT** — added `felix-admin-calendar` to openclaw.json AND modified `scripts/openclaw/agents/main/AGENTS.md`. This is the exact mission #588 references as "the recent agent-extraction work." |
| `3177ca26` | 2026-06-11 00:48 | chore(spec-kitty): populate acceptance-matrix + add shell_pid to WP frontmatter | doc-only |
| `1ef26f99` | 2026-06-11 00:37 | fix(repo): untrack .worktrees/ paths | repo hygiene only |

**Earlier evidence point**: per #588 issue body, the bug was observable **from at least 2026-06-09** (per the #579 mission's original observation). So the actual root cause likely predates the 2026-06-11 commit cluster.

**Earlier upgrade**: `openclaw.json#meta.lastTouchedAt` records `2026-06-02T18:18:52Z` — the openclaw runtime upgrade to 2026.5.28 (and per-memory channel-plugin externalization). This is the strongest candidate for the original break: a runtime upgrade introduced new lifecycle semantics that our config doesn't fully satisfy, or a regression in the runtime itself that surfaces under the per-channel-peer DM-reply path.

**Decision (recent-changes audit)**:
- 37b3bf56 (#579) is a contributing factor but unlikely to be the root cause given the 2026-06-09 evidence point.
- The 2026-06-02 openclaw 2026.5.28 upgrade is the strongest candidate trigger.
- Both will be validated during implementation by:
  1. Checking the openclaw 2026.5.28 release notes / changelog for embedded_run lifecycle changes.
  2. Test-rolling-back the post-#579 main/AGENTS.md changes (in a controlled probe) to see if DM delivery returns.

---

## 3. Live diagnostic probe (DIR-015) — definitive symptom isolation

### 3.1 Probe sequence (read-only)

1. `cat /home/claude/.openclaw/openclaw.json` — full deployed config.
2. `ls /home/claude/.openclaw/agents/` — registered agent slugs.
3. `systemctl --user status openclaw-gateway.service` — runtime health (active since 16:44:40 UTC; PID 1015899; mem 338M).
4. `journalctl --user -u openclaw-gateway --since "2 hours ago"` — filtered for: Inbound message, embedded_run, sessions.resolve, Sending message, Sent message, stuck/stalled session, Sent by, model.call.
5. `ls /home/claude/.openclaw/agents/{main,felix-admin-habits,felix-admin-calendar}/agent/` + contents — per-agent config files.
6. Read-only source dive into `/usr/lib/node_modules/openclaw/dist/` for: embedded_run lifecycle, stuck-session classification, diagnostic-event listener.

### 3.2 Decisive symptom: embedded_run start without end

Journal pattern for **every** DM-initiated run:

```
T+0s    [whatsapp] Inbound message +16179300916 -> +16179300916 (direct, N chars)
T+~10s  [agent/embedded] workspace bootstrap … sessionKey=agent:<X>:<Y>:main
T+~12s  Sent by felix-admin-<role>:<model>\n<reply text>       ← agent stdout, NOT a gateway completion event
T+144s  [diagnostic] stalled session: sessionId=… sessionKey=agent:main:whatsapp:direct:+16179300916
        state=processing activeWorkKind=embedded_run lastProgress=embedded_run:started
        lastProgressAge=350s reason=active_work_without_progress classification=stalled_agent_run
        (recurring every 30s for 4 more cycles)
T+378s  [diagnostic] stuck session recovery: action=abort_embedded_run aborted=true drained=true
T+378s  [diagnostic] stuck session recovery outcome: status=aborted action=abort_embedded_run
```

Repeated **identically** across both pre-restart (16:27→16:39 UTC) and post-restart (16:44→16:54 UTC) windows with the same `sessionKey=agent:main:whatsapp:direct:+16179300916`. Confirms structural, not transient.

### 3.3 Comparison: working paths

| Path | Journal pattern | Status |
|---|---|---|
| Cron `delivery.mode: "announce"` (7am habit checkin) | `[whatsapp] Sending message` → `[whatsapp] Sent message` (~580ms) | working |
| Direct CLI `openclaw agent ... --deliver` (16:51:47 UTC) | `[whatsapp] Sending message` → `[whatsapp] Sent message` (241ms) | working |
| DM-initiated (any inbound DM from +16179300916) | `embedded_run:started` → stall → `abort_embedded_run` (378s) | **broken** |

The channel-send subsystem is healthy. Only the DM-initiated reply-dispatch path fails.

### 3.4 Source-dive: where `embedded_run:ended` should fire

In `/usr/lib/node_modules/openclaw/dist/`:

- `diagnostic-run-activity-DfY2SXQ5.js`:
  - Line 129: `markDiagnosticEmbeddedRunStarted(params)` → emits `lastProgress=embedded_run:started`
  - Line 146: `markDiagnosticEmbeddedRunEnded(params)` → emits `lastProgress=embedded_run:ended`
- `runs-DMxJUP3Q.js`:
  - Line 419: `markDiagnosticEmbeddedRunStarted(...)` called from `setActiveEmbeddedRun(...)` ← fires once per DM
  - Line 454: `markDiagnosticEmbeddedRunEnded(...)` called from `clearActiveEmbeddedRun(...)` ← **NEVER fires for DM sessions**
  - Line 476: `markDiagnosticEmbeddedRunEnded(...)` called from `forceClearEmbeddedAgentRun(...)` ← only fires from stuck-recovery
- `reply-run-registry-BYXDUcCT.js`:
  - Line 68 / Line 75: alternative start/end pair used by the reply-turn admission layer

`clearActiveEmbeddedRun(sessionId, handle, ...)` is exported (`as r`) from runs-DMxJUP3Q. It MUST be called when the embedded run finishes for the session lifecycle to complete. For our DM sessions, no caller invokes it — so the runtime keeps the session in `processing` state until the stale-threshold expires.

The agent's `Sent by <role>:<model>` text comes from the agent's prompt-driven output (workflow marker per #561, mirrored across AGENTS.md prompts) — NOT from the openclaw runtime. So we observe the agent producing reply text, but the gateway never observes a "run completed" signal.

### 3.5 Other observations

- `getDiagnosticSessionActivitySnapshot` (line 154+ of diagnostic-run-activity-DfY2SXQ5.js) classifies `activeWorkKind` in priority order: `tool_call` > `model_call` > `embedded_run`. The journal shows `activeWorkKind=embedded_run` consistently — meaning **no `activeModelCalls` or `activeTools` are tracked during the stall**. Either (a) the model call instrumentation isn't firing for whatever code path the DM dispatch uses, or (b) the model call genuinely never starts.
- The `sessions.resolve INVALID_REQUEST: No session found: current` errors at 16:29:04 fire 75 seconds AFTER the inbound DMs and are best interpreted as **downstream symptoms**: some caller (likely a status/snapshot consumer) asks for the `current` session, the resolver can't find one because the session for this peer is stuck in `processing` and not yet promoted to "current."
- `/usr/lib/node_modules/openclaw/dist/doctor-whatsapp-responsiveness-BTqfhRPQ.js` exists — there is a diagnostic command for WhatsApp responsiveness. Worth running during implementation.
- The `claude` and `felix-doc-auditor` directories under `~/.openclaw/agents/` are NOT in `openclaw.json#agents.list[]` — vestigial but harmless (the runtime only routes to agents in the list).

---

## 4. Root-cause hypothesis ranking (post-probe)

| # | Hypothesis | Confidence | If true, fix shape | In scope? |
|---|---|---|---|---|
| 1 | **openclaw 2026.5.28 introduced a regression in the embedded_run completion handoff for DM-initiated runs**. The agent produces output but `clearActiveEmbeddedRun` is not invoked at the end of the reply turn. | High (~50%) | Internal tracking issue per FR-009; documented operational workaround; mission concludes. Vendored runtime is out of scope per C-001. | No (per Kent's decision) |
| 2 | **A config field is missing in openclaw.json or the agent surface** that the 2026.5.28 runtime expects in order to complete the embedded_run lifecycle. Examples: a `delivery` block under `channels.whatsapp`, a per-agent reply-routing field, a `channels.whatsapp.reply` block. | Medium (~25%) | Add the field; deploy; smoke test. Fits in scope. | Yes |
| 3 | **Post-#579 agent-extraction left a behavioral hole**. The new `felix-admin-calendar` was added, `main/AGENTS.md` was reduced, and some delegation rule that previously kept the session "active" through completion is no longer being followed. | Low (~10%) | Restore the missing instruction in `main/AGENTS.md`. Smoke test. | Yes |
| 4 | **The new `session.dmScope: per-channel-peer` config + `dmPolicy: allowlist`** combination has a wiring gap that breaks reply admission. Try changing `dmScope` or `dmPolicy`. | Low (~10%) | Config swap; smoke test. | Yes |
| 5 | **WhatsApp plugin (`@openclaw/whatsapp`) version mismatch or external-plugin install state issue** (per memory: channels moved to external plugins in 2026.5.28). | Low (~5%) | Verify plugin install via `openclaw plugins list/info`; reinstall if needed. | Yes |

Notes on the ranking:
- Hypothesis 1 (vendored runtime regression) is the most likely *area* but is explicitly **out of scope** per FR-009/C-001. If 2–5 are all disproven, the mission concludes with the internal tracking issue.
- Hypotheses 2–5 are all in-scope and tractable. The implementation lane validates them in order of cost (config probe < AGENTS.md restoration < plugin reinstall < runtime workaround).

---

## 5. Decisions

### D1 — Investigation order during implementation
**Decision**: Validate hypotheses in this order: H4 (config swap) → H5 (plugin info) → H2 (missing field discovery via openclaw docs + diff against pre-upgrade openclaw.json if available) → H3 (AGENTS.md restoration) → H1 (concede + file internal issue).
**Rationale**: cheapest to most expensive; if any one validates, mission proceeds to deploy + smoke test + doc reconciliation.
**Alternatives considered**:
- H1 first (vendored source dive): rejected — out of scope per C-001.
- H3 first (AGENTS.md restoration): rejected — only 10% confidence; more expensive than config probes.

### D2 — Behavioral baseline rollback test
**Decision**: Include a quick "what-if" probe: temporarily reload the pre-#579 `main/AGENTS.md` (from git history) into office2 and re-test DM delivery, **without committing** the rollback. If delivery returns, H3 is validated and we proceed to redo the #579 changes in a way that preserves DM delivery.
**Rationale**: cheap (one file copy + restart + DM), high information-yield, fully reversible.

### D3 — Doc reconciliation scope
**Decision**: Update the following docs as part of the mission per FR-012:
1. `docs/design/architecture/data/service-inventory.json` — bump `openclaw-gateway.version` to `v2026.5.28`; correct `channels.whatsapp.dm_policy` to `allowlist`; add `session.dmScope` field.
2. `docs/design/architecture/data/data-flows.json` — add a new `whatsapp-dm-reply` flow describing inbound → main → (delegation) → subagent → reply → channel-send.
3. `docs/design/architecture/data/audited-surfaces.json` — verify openclaw-agent-prompts + openclaw-config patterns still cover the surfaces we touched.
4. `docs/design/architecture/service-inventory.md` — narrative update mirroring (1).
5. `docs/design/architecture/data-flows.md` + `data-flows.view.md` — narrative + Mermaid update mirroring (2).
6. `docs/runbooks/openclaw-agent-setup.md` — note about the `sessions.resolve current` symptom and the diagnostic recovery action, including the doctor-whatsapp-responsiveness command.
7. `docs/INDEX.md` — only if a new runbook is added.
8. Memory `project_whatsapp_dmpolicy.md` — update to reflect the actual `allowlist` policy.

### D4 — Update memory entries
**Decision**: After fix lands, update or add memory entries for:
- `reference_openclaw_dm_reply_lifecycle` (new) — name the embedded_run start/end markers, the `lastProgress=embedded_run:started` pattern as the stuck-session signature, and the `[diagnostic] stuck session recovery` log-line as the recovery boundary.
- `project_whatsapp_dmpolicy` — correct from `disabled` → `allowlist`.

### D5 — Test mechanism for the acceptance smoke (DIR-015 + Engineering Principle 5)
**Decision**: The smoke test is operator-in-the-loop because no scripted test harness can simulate WhatsApp pairing without re-authenticating. The runbook documents a 5-DM send-and-verify protocol with `journalctl` assertions and operator-verified receipt timestamps.
**Rationale**: the bug only manifests via WhatsApp DMs; the channel itself is paired by QR and the gateway holds the live session. Per memory `feedback_live_integration_tests`, do not propose `--live-probe` workarounds — document the operator protocol instead.
**Alternatives considered**:
- Mocked tests against gateway HTTP API: rejected — would not exercise the broken path (gateway's reply-turn admission for the channel-source).
- pytest-driven journal scraping with no DM input: rejected — would only assert healthy startup, not delivery.

### D6 — Investigation artifact discipline
**Decision**: Every discovery during implementation that contradicts a documented assumption MUST be appended to a `discovery_findings` section of this `research.md` (in an "Update" block per the bulk-edit/append pattern). Reconciliation (D3) updates the canonical docs; this file remains the audit trail.

---

## 6. Open questions deferred to implementation

These are NOT spec-blocking but should be confirmed during the implement lane:

- **Q1**: Does `openclaw plugins list` report `@openclaw/whatsapp` as installed? If not, reinstall is the first try (H5).
- **Q2**: Does the openclaw 2026.5.28 changelog / release notes mention any breaking changes to `embedded_run` or reply-turn dispatch? (Source: ClawHub / openclaw docs / GitHub.)
- **Q3**: Is there a `channels.whatsapp.delivery` config field (analogous to `delivery.mode: "announce"` for cron) that the gateway expects for the DM-reply path?
- **Q4**: When was openclaw 2026.5.28 actually installed on office2? If pre-2026-06-02, then 2026-06-02 was a config-only touch — narrows the trigger window further.

---

## 7. Tools & references

- Local diagnostic command (read-only): `ssh office2-claude 'journalctl --user -u openclaw-gateway --since "<TS>" 2>&1 | grep -E "(embedded_run|stalled|stuck|Inbound|Sending|Sent)"'`
- Live WhatsApp doctor (read-only): `ssh office2-claude 'openclaw doctor --json'` and `ssh office2-claude 'node /usr/lib/node_modules/openclaw/dist/doctor-whatsapp-responsiveness-*.js --help'` (verify before running)
- Plugin status: `ssh office2-claude 'openclaw plugins list 2>&1'`
- Channel-send isolation control: `ssh office2-claude 'openclaw agent --agent main --channel whatsapp --to "+16179300916" --deliver --message "..." --json'`
- Vendored runtime (READ ONLY per C-001): `/usr/lib/node_modules/openclaw/dist/{embedded-agent-*.js, runs-*.js, diagnostic-*.js, reply-*.js}`
- ClawHub: `https://clawhub.openclaw.dev/` (external; do not authenticate from this mission)

---

## 8. Doctrine compliance

| Directive | How this research satisfies it |
|---|---|
| **DIR-015** (Probe the real environment during design phase) | Full live SSH probe documented in §3; root-cause hypothesis ranked from observed symptoms. |
| **DIR-014** (Doc-sync requirement) | Reconciliation scope in §5 D3 is specific and traceable to `signal-to-doc-map.json`. |
| **DIR-008** (Read real service paths) | All deployed-config reads use `/home/claude/.openclaw/openclaw.json` (canonical workspace path), not repo-side templates. |
| **C-001** (No vendored openclaw modifications) | Source dive in §3.4 is read-only; H1 explicitly out of scope. |
| **Engineering Principle: Architecture docs first** (per `feedback_architecture_docs_first` memory) | §1 reads JSONs before §3 SSH probes. |
| **Spec Fidelity** (DIRECTIVE_010) | All §4 hypotheses map cleanly to FR-004 (`sessions.resolve current` proximate cause) and FR-009 (vendored-runtime out-of-scope branch). |

---

## 9. Update — H6 (openclaw upgrade) added at tasks phase (2026-06-11T18:50:00Z)

**Trigger**: Codex review of the openclaw 2026.6.5 release notes during the tasks-phase planning, surfaced via the operator (Kent) in the tasks-phase session.

**Codex evidence summary** (verbatim from operator's message):

> Relevant 2026.6.5 fixes include:
> - Replies captured during a restart use the successor controller instead of stale controller state
> - WhatsApp startup waits are bounded
> - Failed sockets close cleanly
> - Account configuration changes trigger proper restarts
> - Disabled accounts shut down on reload
> - Reconnect handling is more reliable
> - Broader agent/Anthropic recovery improvements address stalled thinking, interrupted tools, stale compaction state, and gateway restarts
>
> The strongest log evidence is repeated: `classification=stalled_agent_run`, `activeWorkKind=embedded_run`, `recovery=abort_embedded_run` — exactly our journal pattern from §3.2.

**New hypothesis ranking** (supersedes §4):

| # | Hypothesis | Confidence | Cost | Order in WP01 ramp |
|---|---|---|---|---|
| **H6** | **openclaw 2026.5.28 → 2026.6.5 upgrade resolves the embedded_run completion path via runtime fixes named in the release notes** | **High (~55%)** | Low (npm-global upgrade + verification per `reference_openclaw_upgrade_gotchas` checklist) | **1st** |
| H5 | `@openclaw/whatsapp` plugin install state | Low | Lowest | 2nd |
| H4 | Config-swap (dmPolicy / dmScope) | Low | Low | 3rd |
| H2 | Missing config field | Medium | Medium | 4th |
| H3 | AGENTS.md post-#579 hole | Low | Medium (rollback probe) | 5th |
| H1 | Vendored regression with no available fix | Low (downgraded from "high area" because H6 may consume the fix) | High (file upstream + wait) | Escalation only |

**Decision D7 — Relax spec assumption A3**

Spec assumption A3 ("Upgrade/downgrade of openclaw is not contemplated by this mission") is **relaxed** as of this update. Rationale: Codex's release-notes review provides concrete evidence that the 2026.6.5 upgrade likely addresses the bug. Per the user's confirmation in the tasks-phase session, openclaw upgrade is now an in-scope remediation candidate (H6). C-001 (no vendored runtime *modification*) still holds — npm-global upgrade replaces the package; it doesn't patch vendored binaries.

**Implications for WP plans**:
- WP01 ramp adds T001 (H6 probe + plan); execution priority highest
- WP02 gets an upgrade-path branch (when WP01 verdict = H6); execution follows the operational upgrade procedure with the `reference_openclaw_upgrade_gotchas` checklist baked in
- WP05 acceptance smoke runs against the upgraded runtime; the deploy script handles both `apt`-style upgrades and config edits
- C-003 Tier classification: openclaw upgrade is Tier 2 (Application/State); does NOT escalate to Tier 1 because openclaw-gateway already runs as a user-level service and the upgrade is via `pipx`/`npm` (not host-level systemd changes). Pre-flight is the standard Tier 2 Restic-≤24h attestation.

**Implications for FR-009 / C-001**:
- FR-009 escalation path is preserved but reframed: it now fires ONLY if H6 AND H2-H5 all fail. The probability of reaching it is lower than the original §4 ranking suggested.
- C-001 unchanged: vendored runtime code at `/usr/lib/node_modules/openclaw/dist/` is not modified by this mission, regardless of upgrade path.

**Implications for the smoke contract**:
- `contracts/journal-event-assertions.md` patterns remain valid post-upgrade (they assert against event log markers that are stable across runtime versions)
- The expected post-fix output (`stall=0 recovery=0 resolve_fail=0`) is the same regardless of which hypothesis (H6 / H2 / H3 / H4 / H5) was the actual fix path

**Operator-side checklist for H6** (per memory `reference_openclaw_upgrade_gotchas`):
- Verify pre-upgrade openclaw.json captures all required fields (especially `models.providers.<x>.models[]` — already present in our deployed config)
- Confirm `@openclaw/whatsapp` external plugin version is current after upgrade
- Verify systemd unit Description is current (cosmetic but per memory it's known to lag)
- Run `openclaw doctor --json` after upgrade and before sending test DMs
- Standard Tier 2: Restic ≤24h before, rebaseline reset per #557 after

---

## Discovery Findings (WP01 — 2026-06-11T19:07:18Z)

Full investigation report: [`docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-investigation.md`](../../docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-investigation.md). Per the WP01 frontmatter `owned_files` contract, the report is the authoritative surface; this block is the audit trail summary per Decision D6.

### H6 (openclaw 2026.5.28 → 2026.6.5 upgrade)
**VALIDATED by desk review.** The 2026.6.5 CHANGELOG (fetched read-only via `npm pack openclaw@2026.6.5`) contains three independent fixes that map to our bug signature: #85823 (WhatsApp captured replies route through successor controller, not stale pre-restart controller — matches per-restart persistence), #90667/#90697 (Anthropic stream-start events wait for `message_start`, with stale-compaction stripping + "reject empty completion handoffs" — matches `markDiagnosticEmbeddedRunEnded` never firing at `runs-DMxJUP3Q.js#454`), and #90208 (isolated agent turn payload messages preserve timeout context — matches 350s stall before `abort_embedded_run`).

### H5 (`@openclaw/whatsapp` plugin install state)
**REFUTED.** Plugin is installed at `/home/claude/.openclaw/extensions/whatsapp/` version 2026.5.28, enabled, peer-deps `openclaw >=2026.5.28`. Install date 2026-06-02 matches `openclaw.json#meta.lastTouchedAt`. No staleness or version mismatch.

### H4 (config-swap probe)
**not-tested-actively — desk review of deployed config matches docs.** `channels.whatsapp.dmPolicy="allowlist"` + `allowFrom=["+16179300916"]` + `session.dmScope="per-channel-peer"` matches the documented "recommended for multi-user" pattern at `/usr/lib/node_modules/openclaw/docs/gateway/configuration.md:295`. Active probe skipped per orchestrator instruction (H6 desk verdict was clear).

### H2 (missing config field)
**REFUTED.** No `channels.whatsapp.reply`, `channels.whatsapp.delivery`, or `agents.<id>.reply` field is documented as required for DM-reply dispatch. The deployed config exactly matches the documented config shape.

### H3 (post-#579 AGENTS.md hole)
**not-tested-actively — skipped per orchestrator instruction (H6 desk verdict was clear).** The destructive rollback probe would have re-triggered #579's 12K-cap truncation during the probe window. `research.md` §2 already reasoned that the 2026-06-09 evidence point pre-dates #579 by 2 days, so #579 is at most a contributing factor, not the root cause. The #85823 WhatsApp restart-stale-controller fix in 2026.6.5 addresses the structural cause regardless of #579.

### Decision Record

**Fix shape**: H6 — upgrade openclaw 2026.6.5 (release-notes mapping below). Upgrade plan: pre-flight Restic ≤24h + `openclaw doctor --json` baseline + plugin snapshot + AGENTS.md snapshot; execution via `ssh office2-kgale 'sudo npm install -g openclaw@2026.6.5'` (sudo surfaced to Kent per CLAUDE.md); post-upgrade verification via `openclaw --version` + `openclaw doctor --json` + `openclaw plugins list` (confirm `@openclaw/whatsapp` enabled) + `systemctl --user restart openclaw-gateway.service` + operator-in-the-loop 1-DM smoke (expect `[whatsapp] Inbound message` → `embedded_run:started` → `embedded_run:ended` → `[whatsapp] Sending message` → `[whatsapp] Sent message` within ~30s) + rebaseline reset per #557. Rollback shape: `npm install -g openclaw@2026.5.28` + restore openclaw.json from pre-upgrade backup + restart gateway. Full plan in §8 of the investigation report. WP02 owns execution.
