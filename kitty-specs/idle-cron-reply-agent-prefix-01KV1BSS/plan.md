# Implementation Plan: Prefix IDLE Cron Replies With Agent Slug

**Branch**: `feat/idle-cron-reply-agent-prefix` | **Date**: 2026-06-13 | **Spec**: [spec.md](spec.md)
**Input**: Mission specification from `kitty-specs/idle-cron-reply-agent-prefix-01KV1BSS/spec.md`
**Mission ID**: `01KV1BSS2A5085M762PQ7TYNPY` (mid8: `01KV1BSS`)
**Source issue**: [#592](https://github.com/kentonium3/kg-automation/issues/592)

---

## Summary

Replace the existing "Hard rule #1 — IDLE means the literal four-character
string `IDLE`…" block in 4 Felix sub-agent AGENTS.md files
(`felix-admin-capture`, `felix-admin-habits`, `felix-admin-tasker`,
`felix-admin-escalation`) with a single canonical block that mandates the
byte format `[<agent-slug>]: IDLE` per the spec, preserves every
anti-narrative invariant from the original rule (incident anchors 2026-05-20
+ 2026-06-09), and adds a one-line operator rationale tying the prefix to
observed-mode attribution. The new rule block is the contract; the 4
per-file edits are mechanical applications of that contract with per-file
slug substitution. Deployment is automatic via the
`agent-prompt-sync.service` 5-min systemd timer on office2 — no new code,
no new manifest, no migration script. Verification is layered:
source-level diff at review time (NFR-001), live `openclaw cron run --wait`
per cron-firing agent (SC-001), 24-hour natural-cron observation (SC-002),
and `openclaw systemPromptReport` in a fresh session for the delegate-only
`felix-admin-tasker` (SC-006). Post-merge: rebaseline per #557.

---

## Technical Context

**Language/Version**: Markdown 0.31+ (CommonMark, the prompt content surface);
no production code changes. Existing Python 3.11 infrastructure
(`scripts/openclaw/deploy/deploy_agent_prompts.py`) is invoked unchanged by
the deploy timer.
**Primary Dependencies**: OpenClaw 2026.6.5+ on office2 (read-and-execute
target for AGENTS.md); spec-kitty 3.2.0rc43 (mission workflow);
`agent-prompt-sync.service` + `agent-prompt-sync.timer` (already deployed,
syncs `scripts/openclaw/agents/<slug>/AGENTS.md` to
`/data/services/openclaw/<workspace>/AGENTS.md` every 5 minutes).
**Storage**: 4 in-repo source files at
`scripts/openclaw/agents/{felix-admin-capture,felix-admin-habits,felix-admin-tasker,felix-admin-escalation}/AGENTS.md`.
Deployed mirrors at `/data/services/openclaw/<workspace>/AGENTS.md` (workspace
naming may differ from agent-slug per [[reference_office2_agent_deploy_paths]];
the deploy script handles the mapping).
**Testing**: Three layers — (1) source-level: implement-WP commits include
the rule block in each file; review-WP confirms NFR-001 shape parity by
diffing the rule block across files. (2) live: post-merge,
`openclaw cron run --wait <inbox-7am-id|habits-morning-checkin-id|escalation-daily-id>`
for the 3 cron-firing agents and visual inspection of the WhatsApp thread.
(3) soak: 24-hour observation of naturally-fired cron jobs across the 3
cron-firing agents (SC-002).
**Target Platform**: office2 (Ubuntu 24.04 LTS, Tailscale-internal,
running OpenClaw 2026.6.5+); authoring on MacBook Pro.
**Project Type**: single (no frontend/backend split).
**Performance Goals**: AGENTS.md per-file growth ≤ +500 bytes (NFR-002);
expected ~+150-250 bytes per file. No cron-timing impact (the rule change
adds zero tool calls, zero new helper invocations).
**Constraints**: Tier 3 (Logic/Workflow — agent prompt change). No
infrastructure, credential, network-topology, Restic-snapshot, or sudo
gates. Rebaseline obligation per #557 applies because AGENTS.md is in the
`openclaw-agent-prompts` audited-surface set
(`docs/design/architecture/data/audited-surfaces.json`). Anti-narrative
invariants from the original Hard rule #1 are preserved verbatim, not
relaxed (C-005).
**Scale/Scope**: 4 files changed, ~+800 bytes total source diff excluding
spec-kitty mission artifacts. 1 spec-kitty mission, expected 3 WPs (canonical
rule block + apply + verify-and-doc-sync), each completable inside a single
agent turn.

---

## Charter Check

*Governance: software-dev-default template; paradigm:
c4-incremental-detail-modeling; tools: git, pytest, python, spec-kitty.*

| Directive | Verdict | Evidence |
|-----------|---------|----------|
| **DIRECTIVE_001** Architectural Integrity | PASS | Pure editorial change inside a single bounded context (Felix sub-agent prompt surface). No component boundaries crossed; no cascading change. |
| **DIRECTIVE_003** Decision Documentation | PASS | Scope-reduction call (5→4 agents) captured at decision `01KV1CBKWHJPVSC6JMDH28FCYD` with full rationale (calendar has no IDLE path). Deploy-mechanism correction (manifest → auto-sync timer) documented in spec FR-008 + plan-phase research. |
| **DIRECTIVE_010** Specification Fidelity | PASS | Spec departures from issue #592 (5→4 agents; auto-sync deploy; relative-growth NFR) all explicitly documented in spec EC-1, FR-008, NFR-002 with the reason. |
| **DIRECTIVE_024** Locality of Change | PASS | Change blast radius = 4 sibling files under `scripts/openclaw/agents/`. No code, no infra, no cross-module API. |
| **DIRECTIVE_031** Context-Aware Design | PASS | Spec Domain Language explicitly disambiguates agent-slug vs deploy-dir-name per [[reference_office2_agent_deploy_paths]]. The bounded context is OpenClaw runtime ↔ WhatsApp egress; the change stays inside it. |
| **DIRECTIVE_033** Targeted Staging | PASS | Implement-WP staging lists the 4 specific AGENTS.md paths + the contracts/ artifact + the spec-kitty mission files. No `git add -A`. |
| **DIRECTIVE_034** Test-First Development | PASS (adapted) | For markdown rule changes, "test-first" maps to: lock the canonical Hard rule #1 block as a contract artifact (`contracts/hard-rule-1.md`) **before** any file edit, then apply mechanically. The contract IS the test; review-WP enforces NFR-001 shape parity by diff. |
| **DIR-007** No system crontab | N/A | No cron changes (openclaw cron config unchanged). |
| **DIR-014** Doc-sync requirement | PASS | Spec § "Documentation Synchronization" enumerates the doc-sync targets and explicitly notes which docs do NOT need updates (registry, INDEX, DEVELOPER_PORTAL). |
| **DIR-015** Probe real env in design | PASS | Plan probed: live `openclaw cron list` on office2, AGENTS.md byte sizes via `wc -c`, calendar AGENTS.md grep, audited-surfaces.json. Surfaces produced 3 spec corrections (4 vs 5 agents; auto-sync deploy; relative-growth NFR). |
| **#557 Rebaseline obligation** | PASS (deferred to merge) | Spec C-003 + SC-005 require the rebaseline command and the merge-commit marker. |

No violations require Complexity Tracking. No `[NEEDS CLARIFICATION:]`
markers remain.

---

## Project Structure

### Documentation (this mission)

```
kitty-specs/idle-cron-reply-agent-prefix-01KV1BSS/
├── plan.md                          # This file
├── spec.md                          # Mission specification
├── research.md                      # Phase 0: probe findings (this command)
├── contracts/
│   └── hard-rule-1.md               # Phase 1: canonical Hard rule #1 block
├── meta.json                        # Mission metadata
├── status.events.jsonl              # spec-kitty event log
├── checklists/requirements.md       # Specify-phase quality checklist
├── decisions/                       # Decision-moment artifacts
└── tasks/                           # Populated by /spec-kitty.tasks
```

No `data-model.md` (no entities); no `quickstart.md` (no app to start).

### Source Code (repository root)

```
scripts/openclaw/agents/
├── felix-admin-capture/AGENTS.md    # in-scope: 15,288 bytes pre, target ≤15,788
├── felix-admin-habits/AGENTS.md     # in-scope: 15,043 bytes pre, target ≤15,543
├── felix-admin-tasker/AGENTS.md     # in-scope: 14,994 bytes pre, target ≤15,494
└── felix-admin-escalation/AGENTS.md # in-scope: 12,366 bytes pre, target ≤12,866
                                     # (felix-admin-calendar: NOT modified)
                                     # (felix-doc-auditor: NOT modified — no IDLE path)
                                     # (main: NOT modified — emits HEARTBEAT_OK, not IDLE)
```

**Structure Decision**: Single project; markdown prompt surface only;
no new code path or test file. The contract artifact at
`kitty-specs/<mission>/contracts/hard-rule-1.md` is the load-bearing
shape reference for review-WP enforcement of NFR-001.

---

## Complexity Tracking

*Not applicable — no Charter Check violations to justify.*

---

## Implementation Concern Map

> Implementation concerns are NOT work packages. `/spec-kitty.tasks`
> translates these into WPs — typical decomposition will be 2–3 WPs.

### IC-01 — Canonical Hard rule #1 contract authoring

- **Purpose**: Author the single canonical Hard rule #1 block that all 4
  files must contain, with per-file substitution limited to `<agent-slug>`.
  This is the load-bearing artifact for NFR-001 (shape parity) and the
  contract the review-WP enforces.
- **Relevant requirements**: FR-001, FR-004, FR-005, FR-006, NFR-001, C-005
- **Affected surfaces**:
  `kitty-specs/idle-cron-reply-agent-prefix-01KV1BSS/contracts/hard-rule-1.md`
- **Sequencing/depends-on**: none (this is the first concern; everything
  else depends on it)
- **Risks**: If the canonical block grows beyond ~+250 bytes per file at
  apply time, NFR-002 (≤+500 bytes per file) is tight on
  `felix-admin-capture` (already 15,288). Mitigation: draft the block
  inside the contract artifact, measure its byte size, confirm fits before
  IC-02 begins.

### IC-02 — Apply canonical block across 4 AGENTS.md files

- **Purpose**: Replace the existing Hard rule #1 block in each of the 4
  in-scope AGENTS.md files with the canonical block from
  `contracts/hard-rule-1.md`, substituting only the agent-slug literal.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-007, NFR-001,
  NFR-002, NFR-003
- **Affected surfaces**:
  - `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
  - `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
  - `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`
  - `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md`
- **Sequencing/depends-on**: IC-01
- **Risks**: Each existing file has its own surrounding prose (capture has
  long incident-anchor narrative; habits/tasker are tighter). The
  canonical block REPLACES the existing rule + its tight surroundings, but
  must NOT delete unrelated prose. Reviewer must inspect each file's
  pre/post diff for incidental removal. Per-agent substitution is the
  only intentional per-file delta (NFR-001).

### IC-03 — Verify + doc-sync + rebaseline closeout

- **Purpose**: Confirm SC-001/SC-002/SC-003/SC-006 via live cron run
  + 24h soak + `openclaw systemPromptReport` for tasker; run the rebaseline
  per SC-005; update any narrative architecture docs touched by the
  rule-text change.
- **Relevant requirements**: SC-001 through SC-006, C-003, C-007, FR-008
- **Affected surfaces**:
  - office2: `openclaw cron run --wait` for `inbox-7am`,
    `habits-morning-checkin`, `escalation-daily`
  - office2: `openclaw systemPromptReport --agent felix-admin-tasker`
    in a fresh session (per C-007 + SC-006)
  - office2: rebaseline command per `docs/runbooks/security-baseline-ops.md`
  - Repo narrative docs (e.g. `docs/design/architecture/agent-architecture.*`
    if it describes Felix sub-agent output discipline; plan-phase research
    confirmed AGENT-REGISTRY does NOT need a content edit)
  - Merge commit message: `Rebaseline: completed at <ts>` marker
- **Sequencing/depends-on**: IC-02 (and deploy timer's next 5-min tick must
  have fired, so the deployed files actually carry the new rule)
- **Risks**:
  - **Auth incident overlap**: plan-phase probe surfaced
    `inbox-5pm` in `error` state with `authentication_error: invalid x-api-key`
    (2026-06-13T20:54Z). If still firing at IC-03 time, capture-cron
    verification will fail for reasons unrelated to this mission. Mitigation
    captured in spec § Assumptions: surface to operator, decide whether to
    inline-fix or proceed with the 3 healthy agents.
  - **systemPromptReport staleness**: per [[reference_openclaw_gotchas]],
    `systemPromptReport` caches at session init. SC-006 verification for
    tasker must use a fresh OpenClaw session.
  - **Rebaseline race**: rebaseline must run AFTER the deploy timer has
    synced the new AGENTS.md to office2 (otherwise baselines re-snapshot
    the OLD content). Verification: `wc -c
    /data/services/openclaw/<workspace>/AGENTS.md` on office2 confirms the
    new size before resetting baselines.
