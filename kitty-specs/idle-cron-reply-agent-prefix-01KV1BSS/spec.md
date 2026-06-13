# Specification: Prefix IDLE Cron Replies With Agent Slug

**Mission ID**: `01KV1BSS2A5085M762PQ7TYNPY`
**Mission slug**: `idle-cron-reply-agent-prefix-01KV1BSS`
**Source issue**: [#592](https://github.com/kentonium3/kg-automation/issues/592)
**Risk tier**: 3 (Logic/Workflow — agent prompt change)
**Branch contract**: `feat/idle-cron-reply-agent-prefix` → `main`

---

## Overview

Felix sub-agents run scheduled cron jobs in observed mode. When a cron job
finds nothing to process, the agent currently replies with the bare
four-character string `IDLE`. That format was hardened in response to two
documented IDLE-violation incidents — the 2026-05-20 02:00 UTC cron emitted a
`Helper exit code 0…` preamble around IDLE, and the 2026-06-09 10:56 UTC cron
emitted a similar wrapped form — both of which reached the operator's
WhatsApp. The current Hard rule #1 in each Felix sub-agent's AGENTS.md
enforces the bare four-character spec specifically to slam that door.

The rule worked, but it was incomplete. Non-IDLE replies already carry a
structured `Sent by <agent>:<model>` identity line; the IDLE class was the
only reply shape without identity attribution. During the 2026-06-12 OpenClaw
auth-store rotation recovery (sibling incident #591), the operator received
five `IDLE` WhatsApp messages in quick succession from replayed cron jobs and
could not attribute any of them to a source agent without SSHing to office2
and running `openclaw cron runs --id <id>` per job. While the agents are in
observed mode, this breaks WhatsApp as the observability surface.

This mission adds identity-attribution parity by changing the no-op reply
format to the exact byte string `[<agent-slug>]: IDLE`, while explicitly
preserving every anti-narrative invariant from the original Hard rule #1.
The change is editorial across all five Felix sub-agents' AGENTS.md files —
both their in-repo source-of-truth copies and the deployed copies on office2.
No code changes, no infrastructure changes, no runtime enforcement (a CI
lint or runtime guard was considered and deferred — see Out of scope).

This is a small, scoped mission whose secondary purpose is to exercise the
spec-kitty 3.2.0rc43 upgrade and confirm previously observed friction
(rc40/rc41/rc42 quirks at #1716, #1764, #1784, #1817, plus per-agent auth
shadows at #596) does not recur on the post-upgrade toolchain.

---

## User Scenarios & Testing

The actor is the **observability operator** (Kent) watching WhatsApp during
observed-mode Felix operation. Acceptance scenarios describe operator-visible
flows; edge cases describe correctness boundaries.

### Acceptance scenarios

**AS-1 — Routine no-op cron reply carries agent identity**
The `felix-admin-capture` cron fires on its schedule and finds an empty
inbox. A WhatsApp message arrives containing the exact byte string
`[felix-admin-capture]: IDLE` and nothing else. The operator can identify the
issuing agent from the message text alone, with no recourse to SSH or to the
OpenClaw cron-run log.

**AS-2 — Recovery-verification window stays unambiguous**
After an OpenClaw or WhatsApp routing incident, several replayed cron jobs
land in the operator's WhatsApp in quick succession (e.g., five IDLE messages
within two hours). Each message is uniquely attributable to one of the five
Felix sub-agents. The operator confirms which agents recovered cleanly and
which (if any) need attention without consulting any other surface.

**AS-3 — Anti-narrative invariants still hold**
A model that previously produced `Helper exit code 0; IDLE` (the 2026-05-20
incident shape) or `All clean — IDLE` (a narrative-wrapping shape) MUST NOT
produce those shapes against the new rule. Every reply that contains the
four-character `IDLE` marker MUST be exactly `[<agent-slug>]: IDLE` with no
preamble before `[` and no prose after `IDLE`.

**AS-4 — Non-IDLE replies are unaffected**
A Felix sub-agent that takes action (e.g., `felix-admin-capture` parses an
inbound message into a Vikunja task) continues to reply with its existing
non-IDLE format including the `Sent by <agent>:<model>` identity line. This
mission does not change that path.

### Edge cases

**EC-1 — Calendar agent in fleet scope**
The calendar agent shipped under mission #027 is the newest sub-agent in the
Felix fleet. The plan phase MUST confirm that its AGENTS.md is in scope and
that its agent-slug literal (`felix-admin-calendar` per
[[reference_office2_agent_deploy_paths]]) matches the deployed substitution.

**EC-2 — Agent slug vs deploy-directory mismatch**
Per [[reference_office2_agent_deploy_paths]], `felix-admin-capture` is
deployed under `/data/services/openclaw/inbox-agent/`, not
`/data/services/openclaw/felix-admin-capture/`. The literal substituted into
each AGENTS.md MUST be the **agent slug** (the canonical identifier the
OpenClaw runtime uses for that agent), not the deploy-directory name. The
plan phase MUST verify each slug against the OpenClaw registry.

**EC-3 — Source-of-truth drift between repo and office2**
The kg-automation repo is the canonical source-of-truth for AGENTS.md (per
`docs/runbooks/openclaw-agent-setup.md`); deployed copies on office2 are
mirrored via the manifest-driven deploy pipeline. If any agent's deployed
AGENTS.md drifts from the in-repo copy before this mission lands, that drift
MUST be surfaced and reconciled by the plan phase, not silently overwritten
by the new content.

**EC-4 — Token-budget impact on AGENTS.md**
Per [[reference_openclaw_gotchas]], AGENTS.md has ~26% rawChars inflation
relative to its source bytes; the observed effective budget is 14-15K source
not 20K. The rule-text change adds approximately one paragraph plus one
example line per file. Plan phase MUST measure and confirm the change keeps
each AGENTS.md inside the observed effective budget.

**EC-5 — Post-deploy rebaseline obligation (#557)**
AGENTS.md is in the audited-surfaces set per
`docs/design/architecture/data/audited-surfaces.json`. Per the rebaseline
obligation, the security-monitor baselines MUST be reset on office2 after
this deploys, and the merge commit MUST record `Rebaseline: completed at
<ts>`. The plan and tasks phases MUST surface this as an explicit step.

---

## Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | Each Felix sub-agent's no-op turn reply is exactly the byte string `[<agent-slug>]: IDLE` (literal brackets, colon, single space, then the four-character IDLE marker), and nothing else. | Locked |
| FR-002 | The `<agent-slug>` placeholder is substituted with the canonical agent slug for that agent: `felix-admin-capture`, `habits-agent`, `tasker-agent`, `escalation-agent`, `felix-admin-calendar`. (Final slug list verified by plan against the OpenClaw registry; see EC-1, EC-2.) | Proposed |
| FR-003 | The Hard rule #1 text in AGENTS.md is updated for all 5 affected sub-agents in **both** the in-repo source-of-truth copies and the deployed copies on office2. | Locked |
| FR-004 | The updated Hard rule #1 enumerates the still-prohibited patterns explicitly with prior-incident anchors: no `Helper exit code…` preamble (2026-05-20), no narrative-wrapped form like `All clean — IDLE` (2026-06-09 class), no leading text before `[`, no trailing prose after `IDLE`. | Locked |
| FR-005 | The updated rule includes a one-line operator rationale: "observed-mode attribution is a load-bearing observability surface; the structured prefix is required for that." | Locked |
| FR-006 | The updated Hard rule #1 includes an explicit byte-format example (e.g., `[felix-admin-capture]: IDLE`) and a trailing-newline directive consistent with the WhatsApp egress path. | Locked |
| FR-007 | Non-IDLE reply formatting (including the `Sent by <agent>:<model>` identity line) is **not** modified by this mission. | Locked |
| FR-008 | The deploy of the updated AGENTS.md files to office2 uses the existing manifest pipeline at `deploys/queued/<name>.yaml` per `docs/runbooks/deploy/discipline.md`. | Locked |

---

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | After deploy, the rule-text body across all 5 AGENTS.md files is byte-identical except for the substituted agent-slug literal. | Verified by diff — the only per-file delta within the Hard rule #1 block is the slug literal. | Locked |
| NFR-002 | The post-change AGENTS.md size stays inside the observed effective system-prompt budget (14-15K source per [[reference_openclaw_gotchas]]). | Each updated AGENTS.md ≤ 15,000 source bytes; no agent exceeds its pre-change size by more than 5%. | Locked |
| NFR-003 | The change ships without modifying non-IDLE reply paths or any code in the WhatsApp egress pipeline. | Diff of merge commit contains no changes outside AGENTS.md files, deploy manifest, doc-sync targets, and (if needed) the OpenClaw registry. | Locked |

---

## Constraints

| ID | Constraint | Source | Status |
|----|-----------|--------|--------|
| C-001 | Tier 3 (Logic/Workflow). Standard sandbox validation. No infrastructure, credential, network topology, or Restic-snapshot precondition. | `docs/design/architecture/data/change-risk-taxonomy.json` | Locked |
| C-002 | kg-automation in-repo AGENTS.md files are the canonical source-of-truth. Deployed copies on office2 are produced via the manifest-driven deploy pipeline; never hand-edited on the server. | `docs/runbooks/openclaw-agent-setup.md`; operator decision Q2 (2026-06-13) | Locked |
| C-003 | The post-deploy rebaseline obligation per #557 applies: security-monitor baselines reset on office2, merge commit records `Rebaseline: completed at <ts>`. | `docs/runbooks/security-baseline-ops.md`; `docs/design/architecture/data/audited-surfaces.json`; CLAUDE.md | Locked |
| C-004 | No mechanical enforcement is added in this mission (no CI lint, no runtime regex guard, no egress rewrite). Per-file prompt change only. | Operator decision Q3 (2026-06-13) | Locked |
| C-005 | The existing anti-narrative invariants from the original Hard rule #1 remain in force. Identity attribution is **added**, not substituted for, the bare-output discipline. | Issue #592 spec section "Proposed change: spec completion, not relaxation" | Locked |
| C-006 | The five affected agents are the complete IDLE-emitting set as of 2026-06-13: `felix-admin-capture`, `habits-agent`, `tasker-agent`, `escalation-agent`, `felix-admin-calendar`. The plan phase MUST verify this list against `docs/constitution/AGENT-REGISTRY.md` and surface any additions. | Issue #592; mission-027 calendar agent fleet status | Locked |
| C-007 | OpenClaw `systemPromptReport` caches at session-init and may show stale content for in-session checks (per [[reference_openclaw_gotchas]]). Post-deploy verification MUST be done via a fresh `openclaw cron run --wait <id>` rather than relying on `systemPromptReport`. | [[reference_openclaw_gotchas]] | Locked |

---

## Success Criteria

| ID | Criterion (measurable, technology-agnostic) | Verification |
|----|--------------------------------------------|--------------|
| SC-001 | After deploy and rebaseline, one manually-triggered IDLE cron per agent produces a WhatsApp reply equal to the exact byte string `[<agent-slug>]: IDLE` for that agent (5/5 agents pass). | `openclaw cron run --wait <id>` per agent; visual inspection of WhatsApp thread. |
| SC-002 | Over a 24-hour observation window of naturally-fired cron jobs across all five agents, zero rule-#1 violations occur (no narrative wrapping, no missing prefix, no preamble, no trailing prose). | 24-hour observation; sample at least one natural IDLE reply per agent. |
| SC-003 | For any IDLE WhatsApp message received during normal operation, the operator can identify the issuing agent from the message text alone, without SSH or any other surface. | Operator self-report at SC-002 completion. |
| SC-004 | After this mission lands, no Felix sub-agent emits the legacy bare four-character `IDLE` reply on any subsequent cron firing. | SC-002 observation; failure of this criterion is a regression. |
| SC-005 | The security-monitor baselines on office2 are reset post-deploy and the merge commit records `Rebaseline: completed at <ts>`. | `ls -la /data/services/security-monitor/baselines/` post-deploy; commit message inspection. |

---

## Domain Language

- **IDLE reply** — A no-op response from a Felix sub-agent cron job. Today: the
  bare four-character string `IDLE`. After this mission: the structured byte
  string `[<agent-slug>]: IDLE`.
- **Hard rule #1** — The first rule in each Felix sub-agent's AGENTS.md output
  discipline section, governing no-op replies.
- **Observed mode** — The current operating mode for Felix sub-agents in which
  the operator manually verifies every action before granting more autonomy.
- **Agent slug** — The canonical kebab-case identifier the OpenClaw runtime
  uses for an agent (e.g., `felix-admin-capture`), distinct from the
  deploy-directory name (e.g., `inbox-agent`). Reference:
  [[reference_office2_agent_deploy_paths]].
- **Sub-agent / Felix sub-agent** — One of the five OpenClaw agents in the
  Felix fleet that runs scheduled cron jobs and emits IDLE replies on no-op
  turns: `felix-admin-capture`, `habits-agent`, `tasker-agent`,
  `escalation-agent`, `felix-admin-calendar`.

---

## Documentation Synchronization (DIR-014)

The merge of this mission MUST update:

- All 5 in-repo AGENTS.md source-of-truth files (paths confirmed by plan).
- The deploy manifest at `deploys/queued/<name>.yaml` for the AGENTS.md
  redeploy.
- `docs/design/architecture/data/audited-surfaces.json` (if AGENTS.md path
  coverage requires verification — plan phase confirms).
- Any narrative architecture doc that describes Felix sub-agent output
  discipline (e.g., `docs/design/architecture/agent-architecture.*`,
  AGENT-REGISTRY.md) so the documented rule matches the deployed rule.
- `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md` if any new artifact is
  introduced (none expected for this mission).

Architecture Impact change classes (per
`docs/design/architecture/data/signal-to-doc-map.json`):

- `service-added-or-modified` — false (no service change)
- `credential-added-or-modified` — false
- `data-flow-added-or-modified` — false
- `network-topology-changed` — false
- `runbook-added` — false
- `runbook-modified` — likely false (verified in plan)
- `architecture-doc-added` — false
- `systemd-unit-added-or-modified` — false
- `agent-prompt-modified` — **true** (the primary signal for this mission)

The `agent-prompt-modified` signal triggers the rebaseline obligation per
C-003.

---

## Assumptions

- The five affected agents are the complete set of Felix sub-agents that
  emit IDLE replies as of 2026-06-13. The plan phase verifies against
  `docs/constitution/AGENT-REGISTRY.md`.
- AGENTS.md in the kg-automation repo is the canonical source-of-truth, and
  the deploy pipeline produces byte-identical copies on office2. Any drift
  surfaced by the plan phase is reconciled before this mission's rule-text
  change overwrites the deployed copy.
- The OpenClaw runtime's effective system-prompt budget remains the observed
  14-15K source bytes (per [[reference_openclaw_gotchas]]); no concurrent
  OpenClaw upgrade increases or decreases that ceiling during this mission.
- The WhatsApp egress path (OpenClaw's reply pipeline) does not transform
  the agent's literal reply text. If transformation exists (whitespace
  stripping, trailing-newline policy, etc.), plan phase surfaces it and
  adjusts FR-006 accordingly.

---

## Dependencies

- `docs/runbooks/openclaw-agent-setup.md` — defines the workspace and
  AGENTS.md mirroring contract.
- `docs/runbooks/deploy/discipline.md` — defines the deploy manifest format
  and the felix-deployer applier behavior.
- `docs/runbooks/security-baseline-ops.md` — rebaseline procedure for #557.
- `docs/design/architecture/data/audited-surfaces.json` — confirms AGENTS.md
  is in scope for the rebaseline obligation.
- `docs/constitution/AGENT-REGISTRY.md` — canonical agent-slug list for
  FR-002 verification.
- [[reference_office2_agent_deploy_paths]] — agent-slug vs deploy-dir
  distinction (load-bearing for FR-002 and EC-2).
- [[reference_openclaw_gotchas]] — token budget and `systemPromptReport`
  staleness (load-bearing for NFR-002 and C-007).

---

## Out of Scope

- Mechanical enforcement of the new format (CI lint on AGENTS.md, runtime
  regex guard, WhatsApp egress rewrite). Deferred per operator decision
  Q3 (2026-06-13). If a regression occurs at SC-002, a follow-on issue
  considers mechanical enforcement.
- Changing the non-IDLE reply format (`Sent by <agent>:<model>` identity
  line is unchanged).
- Reducing the cadence of inbox-cron IDLE pings. Per
  [[feedback_idle_pings_acceptable_for_now]], 4+ IDLE pings/day are
  currently accepted; cadence is a separate concern.
- Adding IDLE attribution to non-cron paths (interactive sub-agent runs do
  not currently emit IDLE).
- Migrating any Felix sub-agent that does not currently emit IDLE (e.g.,
  felix-doc-auditor, which runs as a deterministic Python driver post-#343
  and never speaks IDLE).
