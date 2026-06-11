---
work_package_id: WP03
title: Architecture Data Reconciliation
dependencies: []
requirement_refs:
- FR-011
- FR-012
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T013
- T014
- T015
- T016
- T017
agent: claude
history:
- event: created
  timestamp: '2026-06-11T18:30:00Z'
  by: /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/
execution_mode: planning_artifact
mission_id: 01KTVVHHBJKKG3JPMGRVHSB81P
mission_slug: restore-whatsapp-dm-reply-delivery-01KTVVHH
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data/audited-surfaces.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data-flows.md
- docs/design/architecture/data-flows.view.md
role: curator
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, load your assigned profile:

```
/ad-hoc-profile-load curator-carla
```

This sets your identity, governance scope, and boundaries for this work package. Adopt the profile fully before proceeding.

---

## Objective

Reconcile the architecture data + narrative docs against the actual deployed state of the openclaw-gateway. Per `research.md` §1, four discrepancies were identified during the architectural baseline review (FR-011) — this WP closes them, and documents the previously-undocumented `whatsapp-dm-reply` data flow.

Deliverables (mapping to `data-model.md` E4):
- **DR-1**: `service-inventory.json` — bump openclaw-gateway version, correct dm_policy, add session.dmScope
- **DR-2**: `data-flows.json` — add a new `whatsapp-dm-reply` flow entry
- **DR-3**: `audited-surfaces.json` — verify coverage (likely read-only)
- **DR-4**: `service-inventory.md` — narrative mirror of DR-1
- **DR-5**: `data-flows.md` + `data-flows.view.md` — narrative + Mermaid mirror of DR-2

You succeed when all 6 files in `owned_files` are committed, JSONs are still valid (`jq .` parses cleanly), and the Mermaid view renders (no syntax errors). The doc edits are independent of WP02's fix shape — they correct documented drift regardless.

## Context

Read these BEFORE starting:

1. [`research.md`](../research.md) §1 — the four discrepancies (version, dm_policy, dmScope, missing flow) with exact evidence
2. [`research.md`](../research.md) §5 D3 — the doc reconciliation decision (which docs, what scope)
3. [`data-model.md`](../data-model.md) E4 — DR-1 through DR-5 table with reconciliation type per file
4. `docs/design/architecture/change-control.md` — the canonical protocol for editing arch docs (read-only — defines invariants)
5. `docs/design/architecture/data/signal-to-doc-map.json` (already read in plan-phase) — confirms doc-target lookup for `mission-service-added-or-modified` and `mission-data-flow-added-or-modified`

**Editing discipline** (from `change-control.md` + memory `feedback_architecture_docs_first`):
- JSON files are authoritative; narrative `.md` files mirror them. NEVER edit narrative without first updating JSON.
- Use `jq` (or Python) for JSON edits; never hand-edit JSON merge conflicts
- Mermaid `.view.md` files are first-class deliverables, not decoration; their edges must match `data-flows.json` paths exactly

## Detailed guidance per subtask

### T013 [P] — DR-1: update service-inventory.json

**File**: `docs/design/architecture/data/service-inventory.json`

**Find the openclaw-gateway entry** (search for `"name": "openclaw-gateway"` — currently around line 354 per the plan-phase read).

**Three changes** (apply ALL):

1. **Version bump**:
   - From: `"version": "v2026.3.24"`
   - To: `"version": "v2026.5.28"`
   - Evidence: `openclaw --version` on office2 returns `OpenClaw 2026.5.28 (e932160)`

2. **dm_policy correction**:
   - From: `"dm_policy": "disabled"` (inside the `channels.whatsapp` block)
   - To: `"dm_policy": "allowlist"`
   - Add an `allow_from` field listing the canonical operator number:
     ```json
     "allow_from": ["+16179300916"]
     ```
   - Evidence: `jq ".channels.whatsapp.dmPolicy, .channels.whatsapp.allowFrom" /home/claude/.openclaw/openclaw.json` returns `"allowlist"` and `["+16179300916"]`

3. **Add session.dmScope to the openclaw-gateway entry**:
   - New top-level field (sibling of `channels`):
     ```json
     "session": {
       "dmScope": "per-channel-peer",
       "notes": "Sessions are scoped per channel + peer phone-number; the gateway uses sessionKey format `agent:<agent_id>:<channel>:<scope>:<peer>` (e.g., `agent:main:whatsapp:direct:+16179300916`)."
     }
     ```
   - Evidence: `jq ".session" /home/claude/.openclaw/openclaw.json` returns the per-channel-peer scoping; introduced in openclaw 2026.5.28

**Also update**:
- Top-level `last_updated` field: bump to today's date (e.g., `"2026-06-11"`)
- Top-level `updated_by` field: append `+ restore-whatsapp-dm-reply-delivery-01KTVVHH (#588)`

**Validation**:
```bash
jq . docs/design/architecture/data/service-inventory.json > /dev/null  # parses cleanly
jq '.services[] | select(.name == "openclaw-gateway") | {version, channels: .channels.whatsapp.dm_policy, session: .session.dmScope}' docs/design/architecture/data/service-inventory.json
# Expected: {"version": "v2026.5.28", "channels": "allowlist", "session": "per-channel-peer"}
```

### T014 [P] — DR-2: add whatsapp-dm-reply flow to data-flows.json

**File**: `docs/design/architecture/data/data-flows.json`

**Add a new entry to the `flows` array** modeling the previously-undocumented DM-reply path:

```json
{
  "name": "whatsapp-dm-reply",
  "status": "active",
  "deployed_by": "F002",
  "updated_by": "restore-whatsapp-dm-reply-delivery-01KTVVHH (#588)",
  "introduced_at": "2026-06-11",
  "description": "Bidirectional DM-reply path. Inbound WhatsApp DM enters the openclaw-gateway; the gateway creates a session keyed `agent:main:whatsapp:direct:<peer>`; main agent processes the message (delegating to felix-admin-* subagents as appropriate); the agent's reply text reaches the channel-send subsystem; openclaw-gateway sends the reply back to the originating WhatsApp thread. Distinct from cron-driven announce-mode delivery (separate fire-and-forget path).",
  "path": [
    {
      "from": "operator (WhatsApp client on phone)",
      "to": "openclaw-gateway (inbound channel)",
      "protocol": "WhatsApp Web (Baileys plugin)",
      "endpoint": "+16179300916",
      "description": "Operator sends a DM to Felix's WhatsApp number"
    },
    {
      "from": "openclaw-gateway",
      "to": "main agent (embedded_run)",
      "protocol": "internal IPC (openclaw runtime)",
      "session_key_format": "agent:main:whatsapp:direct:<peer>",
      "description": "Gateway creates a session, starts an embedded_run for the main agent; routes the inbound message as the agent's input"
    },
    {
      "from": "main agent",
      "to": "felix-admin-* subagent (delegation, conditional)",
      "protocol": "openclaw-agent dispatch",
      "description": "main agent classifies the DM intent and delegates to felix-admin-habits / felix-admin-tasker / felix-admin-escalation / felix-admin-calendar / felix-admin-capture per its AGENTS.md routing rules"
    },
    {
      "from": "subagent (or main directly)",
      "to": "openclaw-gateway (channel-send subsystem)",
      "protocol": "internal IPC",
      "description": "Agent's reply text is returned through the embedded_run completion path; gateway invokes the WhatsApp plugin's send function"
    },
    {
      "from": "openclaw-gateway",
      "to": "operator (WhatsApp client)",
      "protocol": "WhatsApp Web (Baileys plugin)",
      "endpoint": "+16179300916",
      "description": "Reply delivered to the originating DM thread within seconds; typing indicator fires during the agent run"
    }
  ],
  "consumers": [
    {
      "agent": "main",
      "purpose": "Top-level orchestrator; handles DM intent classification + delegation"
    },
    {
      "agent": "felix-admin-habits",
      "purpose": "Habit check-in queries via DM (delegation target)"
    },
    {
      "agent": "felix-admin-tasker",
      "purpose": "Task creation/update via DM (delegation target)"
    },
    {
      "agent": "felix-admin-escalation",
      "purpose": "Escalation reply handling (delegation target)"
    },
    {
      "agent": "felix-admin-calendar",
      "purpose": "Calendar event create + reply handling (delegation target)"
    }
  ],
  "operational_notes": "Per the embedded_run lifecycle contract (kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/contracts/embedded-run-lifecycle.md): `embedded_run:started` must be followed by `embedded_run:ended` via `clearActiveEmbeddedRun`. If `clearActiveEmbeddedRun` is not called, the session enters the stuck-recovery path after ~378s, the run is aborted, and no reply is dispatched. See #588 + the openclaw-agent-setup runbook DM-reply troubleshooting section."
}
```

**Status field choice** (depends on the mission's terminal disposition — read `terminal-disposition.md` from WP02):
- If WP02 took the fix path AND WP05 smoke passes: `"status": "active"`
- If WP02 took the escalation path: `"status": "degraded-known-broken"` AND add an `operational_status: "suspended"` block with `suspension_metadata: {since, reason, unblock_signal: "kentonium3/kg-automation#<N>"}` (the issue WP02 filed)

If WP05 hasn't smoke-tested yet, default to `"status": "active"` with a note `"smoke pending"` — WP05 will flip the status if needed.

**Also update**:
- Top-level `last_updated`: today's date
- Top-level `updated_by`: append `+ restore-whatsapp-dm-reply-delivery-01KTVVHH (#588)`

**Validation**:
```bash
jq . docs/design/architecture/data/data-flows.json > /dev/null
jq '.flows[] | select(.name == "whatsapp-dm-reply") | {status, consumer_count: (.consumers | length)}' docs/design/architecture/data/data-flows.json
```

### T015 — DR-3: verify audited-surfaces.json coverage (read + conditional edit)

**File**: `docs/design/architecture/data/audited-surfaces.json`

**Purpose**: confirm the deploy artifacts WP02 produced are covered by the rebaseline-required surfaces. Add patterns ONLY if a gap is found.

**Verify**:
- `openclaw-agent-prompts` surface includes `scripts/openclaw/agents/main/AGENTS.md` (it does — via `scripts/openclaw/agents/*/AGENTS.md` glob)
- `openclaw-config` surface includes `scripts/openclaw/openclaw.json` (it does)
- `systemd-user-units` is unchanged (no new systemd units in this mission)

**Decision**:
- If all surfaces are already covered: no edit needed. Add a one-line entry in your WP03 commit message: `DR-3: audited-surfaces.json — verified, no change needed`.
- If a gap is found: add the missing pattern under the relevant surface block. (Unlikely; the existing globs cover everything WP02 touches.)

**Validation**:
```bash
jq '.audited_surfaces[] | select(.id == "openclaw-agent-prompts" or .id == "openclaw-config") | {id, patterns}' docs/design/architecture/data/audited-surfaces.json
```

### T016 — DR-4: update service-inventory.md narrative

**File**: `docs/design/architecture/service-inventory.md`

**Find the openclaw-gateway subsection** and mirror the DR-1 JSON changes:

- Update the version reference (from v2026.3.24 → v2026.5.28)
- Update the DM-policy description ("disabled" → "allowlist with operator phone number")
- Add a sentence about the per-channel-peer session scoping

**Style**: match the existing narrative voice. Don't expand into "future plans" or speculation — describe current behavior.

**Cross-link**: add a one-liner pointing readers to the new DR-2 data-flow:
> See also the `whatsapp-dm-reply` data flow in `docs/design/architecture/data-flows.md` for the runtime path semantics.

### T017 — DR-5: update data-flows.md + data-flows.view.md

**Files**: `docs/design/architecture/data-flows.md` and `docs/design/architecture/data-flows.view.md`

**For data-flows.md** (narrative):
- Add a new subsection: `### whatsapp-dm-reply (bidirectional DM-initiated reply path)`
- Describe the flow at a stakeholder level (1–2 paragraphs)
- Cross-link to: `data-flows.json#flows[?name=whatsapp-dm-reply]`, `contracts/embedded-run-lifecycle.md` (in the mission dir for now; WP05/mission close-out may relocate)

**For data-flows.view.md** (Mermaid):
- Add nodes (if not already present): `Phone[WhatsApp Phone]`, `Gateway[openclaw-gateway]`, `Main[main agent]`, `Subagent[felix-admin-*]`, `ChannelSend[channel-send subsystem]`
- Add directed edges showing the DM-reply path:
  ```mermaid
  Phone -- "inbound DM" --> Gateway
  Gateway -- "embedded_run" --> Main
  Main -- "delegate (cond.)" --> Subagent
  Subagent -- "reply" --> Main
  Main -- "reply text" --> ChannelSend
  ChannelSend -- "[whatsapp] Sending" --> Phone
  ```
- Match the existing Mermaid theme/style of the file (don't introduce new classDef rules unnecessarily)

**Validation**:
```bash
# Mermaid syntax check is operator-side (no CLI tool); preview in an editor that supports Mermaid
# OR: render via a temporary mmdc invocation if mmdc is installed locally
mmdc --version 2>&1 || echo "mmdc not installed locally — verify by previewing in VS Code/Obsidian"
```

## Branch Strategy

- **Planning base branch**: `main`
- **Execution worktree**: assigned by `lanes.json`
- **Final merge target**: `main` (via spec-kitty merge gate)
- **Commit discipline**: per DIRECTIVE_033, stage ONLY the WP03 owned_files. Do NOT touch other docs/design/architecture/ files even if drift is spotted (file follow-up issues instead).

## Definition of Done

- [ ] T013 service-inventory.json: openclaw-gateway entry has v2026.5.28 + allowlist + per-channel-peer; JSON parses cleanly
- [ ] T014 data-flows.json: new `whatsapp-dm-reply` flow entry committed; JSON parses cleanly
- [ ] T015 audited-surfaces.json: verified (no edit) OR coverage gap closed
- [ ] T016 service-inventory.md: openclaw-gateway narrative mirrors DR-1
- [ ] T017 data-flows.md + data-flows.view.md: new flow described in narrative + present as Mermaid edges
- [ ] All 6 owned files committed; no other files in the commit
- [ ] `jq .` passes for all 3 JSON files (`service-inventory.json`, `data-flows.json`, `audited-surfaces.json`)
- [ ] Cross-references between markdown files and JSON files are consistent (no dangling refs)

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Drift correction inadvertently changes other service entries | High | Edit ONLY the openclaw-gateway block; use targeted jq/Python edits, never multi-line text replacement |
| Mermaid syntax breaks the .view.md render | Medium | Test render locally in Obsidian or VS Code Mermaid preview before commit; match existing style |
| The `whatsapp-dm-reply` flow description claims behavior that isn't true post-WP02 (e.g., status: active when escalation path taken) | High | T014 explicitly conditions status on WP02 disposition; read `terminal-disposition.md` first |
| `[Obsidian Better Markdown Links]` plugin auto-rewrites links to `(<#anchor>)` format on Kent's machine | Low | Per memory `reference_obsidian_better_markdown_links`, this is expected; do not fight the transform |

## Reviewer guidance

Check:

1. **JSON correctness**: all 3 JSONs parse via `jq .`; the openclaw-gateway version is v2026.5.28; dm_policy is "allowlist"; session.dmScope is present
2. **No collateral damage**: `git diff` on the 6 owned files shows only the intended changes; no whitespace-only or unrelated edits
3. **Narrative-JSON consistency**: claims in `.md` files are backed by JSON entries; no narrative drift
4. **Mermaid render**: open `data-flows.view.md` in a Mermaid preview; the new edges render correctly
5. **Status field correctness**: the `whatsapp-dm-reply` flow status reflects the actual deployed state (fix path → active; escalation → degraded-known-broken)
6. **DIRECTIVE_033**: commit stages only WP03 owned files; no spurious files
