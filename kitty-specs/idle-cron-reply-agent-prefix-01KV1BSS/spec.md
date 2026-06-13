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
The change is editorial across the four Felix sub-agents whose AGENTS.md
currently carries the Hard rule #1 (felix-admin-capture, felix-admin-habits,
felix-admin-tasker, felix-admin-escalation). `felix-admin-calendar` is
excluded: plan-phase probing confirmed it has no Hard rule #1, no IDLE
reply path, and no cron schedule — it's a delegate-only sub-agent. No code
changes, no infrastructure changes, no runtime enforcement (a CI lint or
runtime guard was considered and deferred — see Out of scope).

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

**EC-1 — Calendar agent confirmed out of scope**
Plan-phase probing of `scripts/openclaw/agents/felix-admin-calendar/AGENTS.md`
and live `openclaw cron list` on office2 confirmed that the calendar agent
has no Hard rule #1, no IDLE reply path, and no cron schedule. If a future
mission ever adds an IDLE path to calendar (e.g., a calendar-substrate cron
that polls for events), this mission's rule shape extends naturally:
`[felix-admin-calendar]: IDLE`. No change in this mission.

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
| FR-002 | The `<agent-slug>` placeholder is substituted with the canonical agent slug for that agent: `felix-admin-capture`, `felix-admin-habits`, `felix-admin-tasker`, `felix-admin-escalation`. (Verified during plan against `docs/constitution/agent-registry.json` and live `openclaw cron list` on office2 — `felix-admin-calendar` excluded per EC-1.) | Locked |
| FR-003 | The Hard rule #1 text in AGENTS.md is updated for all 4 affected sub-agents in the in-repo source-of-truth files at `scripts/openclaw/agents/<slug>/AGENTS.md`. Deployed copies on office2 sync automatically via the existing `agent-prompt-sync.service` 5-min timer (see FR-008). | Locked |
| FR-004 | The updated Hard rule #1 enumerates the still-prohibited patterns explicitly with prior-incident anchors: no `Helper exit code…` preamble (2026-05-20), no narrative-wrapped form like `All clean — IDLE` (2026-06-09 class), no leading text before `[`, no trailing prose after `IDLE`. | Locked |
| FR-005 | The updated rule includes a one-line operator rationale: "observed-mode attribution is a load-bearing observability surface; the structured prefix is required for that." | Locked |
| FR-006 | The updated Hard rule #1 includes an explicit byte-format example (e.g., `[felix-admin-capture]: IDLE`) and a trailing-newline directive consistent with the WhatsApp egress path. | Locked |
| FR-007 | Non-IDLE reply formatting (including the `Sent by <agent>:<model>` identity line) is **not** modified by this mission. | Locked |
| FR-008 | Deployment to office2 uses the existing automatic path: committing the updated `scripts/openclaw/agents/<slug>/AGENTS.md` files to `main` triggers the `agent-prompt-sync.service` 5-min systemd timer on office2, which invokes `scripts/openclaw/deploy/deploy_agent_prompts.py` and copies AGENTS.md into `/data/services/openclaw/<workspace>/`. No `deploys/queued/<name>.yaml` manifest is authored for this mission. | Locked |

---

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | After deploy, the new Hard rule #1 rule-text block has the same shape across all 4 updated AGENTS.md files: any per-file prose retained around the rule stays as-is; the only intentional per-file delta within the rule block is the substituted slug literal. | Diff review during implement/review confirms each file's rule block contains the same byte-format spec, the same enumerated prohibited-pattern list, and the same operator-rationale line. | Locked |
| NFR-002 | This mission does not regress AGENTS.md size beyond a small absolute budget per file. (Note: `felix-admin-capture/AGENTS.md` is already 15,288 source bytes at mission start, slightly above the 14-15K observed budget per [[reference_openclaw_gotchas]]; current production has not surfaced budget-related failures, so this mission targets non-regression rather than retroactive compression.) | Per-file post-change source size grows by ≤ 800 bytes vs. pre-mission baseline (measured at the `wc -c` byte level on the in-repo file). Original planning estimate (≤500, expected +150-250) was raised to +800 during WP01 implementation after actual measurements: the original Hard rule #1 line in `felix-admin-habits`, `felix-admin-tasker`, `felix-admin-escalation` was 310-360 bytes against a canonical block of ~936 bytes (FR-001/004/005/006 compliant minimum). Capture is expected to land near +400; habits/tasker/escalation near +700. Reviewer enforces ≤+800 absolute. | Locked |
| NFR-003 | The change ships without modifying non-IDLE reply paths or any code in the WhatsApp egress pipeline. | Merge-commit diff contains no changes outside the 4 AGENTS.md files, the documentation-sync targets, and the spec-kitty mission artifacts. | Locked |

---

## Constraints

| ID | Constraint | Source | Status |
|----|-----------|--------|--------|
| C-001 | Tier 3 (Logic/Workflow). Standard sandbox validation. No infrastructure, credential, network topology, or Restic-snapshot precondition. | `docs/design/architecture/data/change-risk-taxonomy.json` | Locked |
| C-002 | kg-automation in-repo AGENTS.md files at `scripts/openclaw/agents/<slug>/AGENTS.md` are the canonical source-of-truth. Deployed copies on office2 at `/data/services/openclaw/<workspace>/` are produced automatically by `scripts/openclaw/deploy/deploy_agent_prompts.py` invoked by the `agent-prompt-sync.service` 5-min systemd timer; never hand-edited on the server. | `docs/runbooks/openclaw-agent-setup.md`; `docs/design/architecture/data/audited-surfaces.json`; operator decision Q2 (2026-06-13) | Locked |
| C-003 | The post-deploy rebaseline obligation per #557 applies: security-monitor baselines reset on office2, merge commit records `Rebaseline: completed at <ts>`. | `docs/runbooks/security-baseline-ops.md`; `docs/design/architecture/data/audited-surfaces.json`; CLAUDE.md | Locked |
| C-004 | No mechanical enforcement is added in this mission (no CI lint, no runtime regex guard, no egress rewrite). Per-file prompt change only. | Operator decision Q3 (2026-06-13) | Locked |
| C-005 | The existing anti-narrative invariants from the original Hard rule #1 remain in force. Identity attribution is **added**, not substituted for, the bare-output discipline. | Issue #592 spec section "Proposed change: spec completion, not relaxation" | Locked |
| C-006 | The four affected agents are the complete Hard-rule-#1-bearing set as of 2026-06-13 per plan-phase probing: `felix-admin-capture`, `felix-admin-habits`, `felix-admin-tasker`, `felix-admin-escalation`. `felix-admin-calendar` (no Hard rule #1, no IDLE path, no cron) is excluded. `main`, `felix-doc-auditor` (Python driver post-#343, no IDLE) are not Felix sub-agents in this scope. | Plan-phase probe (2026-06-13): `scripts/openclaw/agents/<slug>/AGENTS.md` grep + live `openclaw cron list` | Locked |
| C-007 | OpenClaw `systemPromptReport` caches at session-init and may show stale content for in-session checks (per [[reference_openclaw_gotchas]]). Post-deploy verification MUST be done via a fresh `openclaw cron run --wait <id>` rather than relying on `systemPromptReport`. | [[reference_openclaw_gotchas]] | Locked |

---

## Success Criteria

| ID | Criterion (measurable, technology-agnostic) | Verification |
|----|--------------------------------------------|--------------|
| SC-001 | After deploy and rebaseline, one manually-triggered IDLE cron per **cron-firing** agent produces a WhatsApp reply equal to the exact byte string `[<agent-slug>]: IDLE` for that agent. Agents covered: `felix-admin-capture` (via any inbox-N cron), `felix-admin-habits` (via `habits-morning-checkin`), `felix-admin-escalation` (via `escalation-daily`). | `openclaw cron run --wait <id>` per agent; visual inspection of WhatsApp thread. |
| SC-002 | Over a 24-hour observation window of naturally-fired cron jobs across the three cron-firing affected agents, zero rule-#1 violations occur (no narrative wrapping, no missing prefix, no preamble, no trailing prose). | 24-hour observation; sample at least one natural IDLE reply per agent. |
| SC-003 | For any IDLE WhatsApp message received during normal operation, the operator can identify the issuing agent from the message text alone, without SSH or any other surface. | Operator self-report at SC-002 completion. |
| SC-004 | After this mission lands, no Felix sub-agent emits the legacy bare four-character `IDLE` reply on any subsequent cron firing. | SC-002 observation; failure of this criterion is a regression. |
| SC-005 | The security-monitor baselines on office2 are reset post-deploy and the merge commit records `Rebaseline: completed at <ts>`. | `ls -la /data/services/security-monitor/baselines/` post-deploy; commit message inspection. |
| SC-006 | `felix-admin-tasker` (no cron, delegate-only) is verified at the source level: its updated AGENTS.md Hard rule #1 contains the new `[felix-admin-tasker]: IDLE` byte spec, matches the same rule shape as the three cron-firing agents (NFR-001), and `openclaw systemPromptReport --agent felix-admin-tasker` on office2 returns the updated content in a fresh session. | Source diff + `openclaw systemPromptReport --agent felix-admin-tasker` in a fresh OpenClaw session (avoids the [[reference_openclaw_gotchas]] cache-staleness gotcha). |

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
- **Sub-agent / Felix sub-agent** — A Felix-fleet OpenClaw agent governed by
  its own AGENTS.md. The four sub-agents in scope for this mission carry the
  Hard rule #1: `felix-admin-capture`, `felix-admin-habits`,
  `felix-admin-tasker`, `felix-admin-escalation`. `felix-admin-calendar` is a
  Felix sub-agent but has no Hard rule #1 (no IDLE path) and is out of scope.
- **Cron-firing agent** — A Felix sub-agent that has at least one
  `openclaw cron list` entry. Three of the four in-scope agents are
  cron-firing (`felix-admin-capture`, `felix-admin-habits`,
  `felix-admin-escalation`); `felix-admin-tasker` is delegate-only.

---

## Documentation Synchronization (DIR-014)

The merge of this mission MUST update:

- The 4 in-repo AGENTS.md source-of-truth files at
  `scripts/openclaw/agents/<slug>/AGENTS.md` for `felix-admin-capture`,
  `felix-admin-habits`, `felix-admin-tasker`, `felix-admin-escalation`.
- No `deploys/queued/<name>.yaml` manifest — deployment is automatic via
  `scripts/openclaw/deploy/deploy_agent_prompts.py` triggered by the
  `agent-prompt-sync.service` 5-min systemd timer on office2.
- `docs/design/architecture/data/audited-surfaces.json` — no edit expected;
  AGENTS.md is already covered by the `openclaw-agent-prompts` entry. Plan
  phase confirms.
- Any narrative architecture doc that describes Felix sub-agent output
  discipline (e.g., `docs/design/architecture/agent-architecture.*`) so the
  documented rule matches the deployed rule. `docs/constitution/AGENT-REGISTRY.md`
  itself is **not** updated by this mission (the registry records autonomy
  and team identity, not reply discipline).
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

- The four affected agents (capture, habits, tasker, escalation) are the
  complete Hard-rule-#1-bearing set as of 2026-06-13. Plan-phase probe
  verified this against `scripts/openclaw/agents/*/AGENTS.md` greps and
  `docs/constitution/agent-registry.json`. Any new agent added between mission
  start and merge would need its own rule and is out of scope.
- AGENTS.md in the kg-automation repo is the canonical source-of-truth, and
  the existing `agent-prompt-sync.service` timer produces byte-identical
  copies on office2 within 5 minutes of a `main` push. Any drift surfaced
  before this mission's commit is reconciled first.
- The WhatsApp egress path (OpenClaw `delivery.mode: "announce"`) does not
  transform the agent's literal reply text — the bare `IDLE` reaches WhatsApp
  unchanged today, so `[<agent-slug>]: IDLE` will too. If a transformation
  ever surfaces (whitespace stripping, trailing-newline policy), the SC-001
  byte-exact verification will surface it and FR-006 adjusts.
- The auth-store rotation incident #591 is operationally resolved (auth-store
  baselines reset 2026-06-12 via #596/#597) and does not block IDLE crons
  from firing during the SC-002 24-hour observation window. If the live
  `inbox-5pm` auth error (`FailoverError: LLM error authentication_error:
  invalid x-api-key` observed during plan probe at 2026-06-13T20:54Z) is
  still firing at implement time, it's a separate issue from this mission's
  scope; implement-phase surfaces it and the operator decides whether to
  resolve it inline or proceed with the 3 healthy agents.

---

## Dependencies

- `docs/runbooks/openclaw-agent-setup.md` — workspace and AGENTS.md
  mirroring contract.
- `scripts/openclaw/deploy/deploy_agent_prompts.py` +
  `scripts/office2/agent-prompt-sync.service|timer` — automatic AGENTS.md
  sync pipeline (replaces the deploys/queued manifest path for this file
  class; see C-002, FR-008).
- `docs/runbooks/security-baseline-ops.md` — rebaseline procedure for #557.
- `docs/design/architecture/data/audited-surfaces.json` — confirms AGENTS.md
  is in scope for the rebaseline obligation under `openclaw-agent-prompts`.
- `docs/constitution/agent-registry.json` + `docs/constitution/AGENT-REGISTRY.md`
   — canonical agent-slug list for FR-002 verification.
- [[reference_office2_agent_deploy_paths]] — agent-slug vs deploy-dir
  distinction (load-bearing for FR-002 and EC-2).
- [[reference_openclaw_gotchas]] — token budget and `systemPromptReport`
  staleness (load-bearing for NFR-002, C-007, SC-006).

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
