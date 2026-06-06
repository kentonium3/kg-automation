---
title: kg-automation Epic Reorganization Plan (from Architecture Review)
doc_type: project
status: draft
last_updated: '2026-06-05'
tags: [architecture, planning, epics, issue-management, 270, 281, 516, 137, 535, 537, 539, 542, 543, 545, 547, 549, 551, 164, 165, 271, 138, 520, 276, 366, 489, 492, 517, 521, 518, 172, 175, 194, 281/Epic, 133, 164/]
---

# Epic Reorganization Plan

**Purpose**: translate the architecture review's 8 proposed Epics into a concrete reorganization of the GitHub issue queue — accounting for existing Epics, orphan issues that should become children, and the order of operations.

**Source**: [`findings.md`](<./findings.md>), [`issue-roadmap.md`](<./issue-roadmap.md>), [`open-epic-cross-check.md`](<./open-epic-cross-check.md>)

**Status when this is approved**: this plan becomes the spec for the issue-reorg execution. No issues are created, merged, restructured, or closed before operator sign-off on this plan.

**Execution progress** (updated as Day-N completes):

- **Day-0** ✅ Complete (commits `90e4b4f2`, `c7738f08`, `58c54d33`, `75d52719` on 2026-06-05): F-001 ad-hoc fix + office2 deploy; F-002 test stabilization; principles ratified at `docs/design/engineering-principles.md`; report package committed.
- **Day-1** ✅ Complete (2026-06-05): #137 renamed to "Epic: LLM Cost Visibility & Reporting" + `spec: pending` label. Cross-reference comments added to #270 / #281 / #516. Filed 5 new Epics: A=#529, B=#530, D=#531, E=#532, G=#533. Filed 17 candidate issues: under A (#534 closed retroactive, #535), B (#536 closed retroactive, #537), #516 (#538, #539), D (#541, #542, #543), E (#544, #545), #281 (#546, #547), G (#548, #549), #270 (#550, #551). Re-parented 22 orphans under target Epics.
- **Day-2+** ⏳ Pending: ratify `helper-script-conventions.md` (gates Epic F / #281 first child); governance updates (CLAUDE.md, Constitution Directive 6, Charter, issue templates); P1 Epic execution begins.

---

## Current State Snapshot

**Open issues**: 55 total
**Open Epics** (7): #137, #164, #165, #270, #271, #281, #516

### Current Epic inventory

| # | Title | Labels | Open children |
|---|-------|--------|---------------|
| #137 | LLM Cost Visibility & Reporting | P1-infra · area/felix-core | #138 |
| #164 | Felix EA Calendar Management Capability | P1-feature · area/ea · spec: pending | (none linked) |
| #165 | Felix EA Email Management Capability | P1-feature · area/ea · spec: pending | (none linked) |
| #270 | Felix governance discipline — tier-aware change protocol + issue queueing | P1-feature · area/felix-core · spec: pending | (none linked) |
| #271 | Felix as mirror — back-chaining intent to priorities, surfacing tangents | P1-feature · area/ea · spec: pending | (none linked) |
| #281 | Felix-wide Directive 6 audit + helper script management hardening | P2-debt · area/felix-core · spec: brief | (none linked) |
| #516 | Felix-wide observability and status-emission framework — research spike | P2-rfc · area/felix-core · spec: brief | (none linked) |

Most Epics have empty child trees today. The reorganization is largely additive (give existing Epics the children they should have), not destructive.

---

## Proposed Epics from Report → Final Disposition

The architecture review proposes 8 Epics (A through H). After cross-checking against existing Epics, the recommended disposition is:

| Proposed | Disposition | Existing Epic | Rationale |
|----------|-------------|---------------|-----------|
| **A — Privacy Boundary Hardening** | **File NEW** | — | No existing Epic covers privacy-boundary lint/consistency cross-cutting. |
| **B — CI/Test Enforcement Baseline** | **File NEW** | — | No existing Epic owns CI policy. |
| **C — Observability Lifecycle Contract** | **MERGE into #516** | #516 | #516 already scoped as the Felix-wide observability framework — proposed Epic C is its concrete deliverable shape. Expand #516's scope to include the lifecycle-state contract from F-003. |
| **D — Shared Vikunja Client** | **File NEW** | — | Natural successor to #520's `vikunja_config.py` foundation. No existing Epic covers integration-client consolidation. |
| **E — Architecture JSON Validation** | **File NEW** | — | No existing Epic covers JSON-schema enforcement. Stands alone as a tooling/CI Epic. |
| **F — Helper/Library/Skill Conventions Ratification** | **MERGE into #281** | #281 | #281 is "Felix-wide Directive 6 audit + helper script management hardening" — proposed Epic F's helper-conventions ratification is the missing piece that closes #281's hardening goal. |
| **G — Deploy Script Surface Cleanup** | **File NEW** | — | No existing Epic owns deploy-script governance. |
| **H — Agent Mutation Governance Enforcement** | **MERGE into #270** | #270 | #270 IS "tier-aware change protocol + issue queueing" — Epic H's deterministic mutation wrapper is the implementation shape of #270's protocol. |

**Net result**: 5 new Epics to file (A, B, D, E, G), 3 existing Epics to expand (#270, #281, #516).

---

## Orphan Issues → Recommended Parenting

Of the 48 non-Epic open issues, the following are good candidates for becoming children of an Epic (new or existing). The remaining ~30 are either ad-hoc bugs, spec-kitty tooling tracking, or features that genuinely stand alone.

### Should become children of **#137** (LLM spend, existing)

- **#138** — OpenClaw agent API usage observability and budget alerting (already linked)
- **#296** — Anthropic Workspaces: dev vs felix API usage attribution (P1-infra)
- **#297** — Cross-provider LLM usage retrieval tool — automate #276 manual sweep (P2-feature)

### Should become children of **#270** (Governance discipline, absorbs Epic H)

- **#275** — RFC: Emergency override authority during cascading incidents (P2-rfc)
- **#288** — Felix governance discipline Layer 1: GOVERNANCE.md + main/AGENTS.md pointer (P2-feature)
- **#327** — RFC: universal error and alerting primitives for silent failure detection (P1-rfc) *(could also fit #516)*
- **#154** — Charter amendment: recognize shared deploy primitives in deployment rule (P2-infra) *(could also fit Epic G)*

### Should become children of **#281** (Directive 6 audit, absorbs Epic F)

- **#339** — Bug: Felix-main fell back to ad-hoc gh issue create despite felix-file-issue.py being present (P2-bug) — exact Directive 6 enforcement gap
- **#167** — Audit and populate OpenClaw agent workspace files (P3-candidate) — helper/script consistency

### Should become children of **#516** (Observability framework, absorbs Epic C)

- **#269** — Felix outage watchdog: out-of-band Sev-0 alert (P2-feature)
- **#327** — RFC: universal error and alerting primitives (P1-rfc) *(could also fit #270; pick the better fit)*
- **#511** — P3-debt: Restic backup discoverability — health pointer + service inventory (P3-debt)
- **#124** — Infra: OpenTelemetry central action logging (P2-infra)

### Should become children of **NEW Epic D** (Shared Vikunja Client)

- **#527** — Escalation reconciler hard-fail on operator-deleted tasks (P2-bug) — fixing this is a natural client-modernization step
- **#506** — Watch: Vikunja RRULE implementation (upstream go-vikunja#2032) — will require habits refactor (P3-candidate)
- **#103** — Feature: Task Attribute Enhancements (P2-feature) — Vikunja-shape
- **#515** — P3-debt: pipe correlated_checkin_date_et through record_completion into habits-history.jsonl (P3-debt) — touches the same Vikunja write surface

### Should become children of **NEW Epic G** (Deploy Script Cleanup)

- **#136** — Feature: Deployment model for Mac → office2 with tier-aware controls (P1-infra)
- **#154** — Charter amendment for shared deploy primitives (P2-infra) *(could also fit #270; pick the better fit)*

### Should become children of **#164** or **#165** (EA Calendar/Email, existing)

These EA-area issues currently stand alone but are squarely the Capability work the Epics describe:

- **#117** — Task ↔ calendar event linking (F021) → child of #164
- **#121** — Email triage + digest agent (F025) → child of #165
- **#122** — Solicitation folder hygiene (F026) → child of #165
- **#119** — Level 1-2 escalation heartbeat (F023) → child of #165 *(probably; escalation here is email-driven)*
- **#216** — Integrate OpenClaw with Google Calendar and Gmail → spans #164 + #165 (parent both)
- **#324** — Inbox parser: forward calendar items to Felix for automatic Google Calendar creation → child of #164

### Should become children of **#366 RFC: Theme + Initiatives** (NOT an Epic, but a parent RFC)

#366 is filed as an RFC but functions as a parent for Initiative work. Recommend converting #366 to an Epic OR leaving it as RFC and creating an actual "Epic: Felix as life-steering substrate" parent:

- **#375** — Smarter escalation + prioritization (Initiative 3 under #366) — already linked
- **#367** — Research: Survey of life-goal-to-task hierarchy models (Initiative 1) — already linked
- **#271** is an Epic that overlaps with #366's Initiative 2 — relationship needs clarifying

### Standalone — NOT to become children of any Epic

These genuinely stand alone:

- **Spec-kitty tooling bugs** tracked separately: #489, #492, #517, #521 (upstream-filed)
- **#525** — P3-debt: janitor for #518 (already-merged #518; standalone cleanup)
- **#106** — RFC: Full System State Auditor (broader than any one Epic; arguably an Epic itself)
- **#133** — RFC: Canonical agent inventory and system self-awareness (broader RFC)
- **#114** — Encrypt secrets at rest on office2 (R-001) — security, standalone
- **#68** — Off-site backup for office2 restic repository — standalone infra
- **#101** — RFC: Commitment Manager Agent (broader RFC)
- **#125** — RFC: CRM and relationship management tooling (D07) — biz-ops; standalone
- **#160** — media-consumption.yaml artifact decision — standalone
- **#116** — Dedicated felix-ops service account for shared state (R-004) — security, standalone
- **#194** — Voice interaction via WhatsApp (P2-feature) — possibly elevate to its own Epic with #172, #175
- **#172, #175** — Voice research issues — could form a voice-interaction Epic with #194
- **#330** — Codex sandbox profile (already P2-infra, mid-investigation)
- **#409** — Standing orders conflict in habits SOUL.md vs AGENTS.md
- **#323** — Bug: felix-admin-capture phone perm 0644 vs 0664
- **#325** — Feature: scripts/inbox/finalize_inbox_file.py atomic post-routing cleanup
- **#131** — Feature: Add escalation delegation to main agent AGENTS.md

---

## New Issues to File (Beyond the New Epics)

These are the candidate issues the report's `issue-roadmap.md` proposes, with my assessment of which should land as children of which Epic.

### Under **NEW Epic A — Privacy Boundary Hardening** (P1)

1. **Fix: Update stale tasker privacy boundary references to `04-Growth/_private`** (P1-bug)
   - Scope: tasker workspace files, runbook, service inventory, deployed office2 workspace
   - Acceptance: `rg "02-Growth/_private"` returns only allowlisted historical/migration docs
   - **NOTE**: This is the F-001 ad-hoc fix scheduled for TODAY. File the issue retroactively after the fix lands, so the issue records the cleanup commit hash.
2. **CI: Add stale private-boundary lint** (P2-infra)
   - Scope: validator in `tooling/scripts/` that blocks stale references outside allowlist
   - Acceptance: validator fails on a synthetic stale active prompt

### Under **NEW Epic B — CI/Test Enforcement Baseline** (P1)

3. **Fix: Stabilize date-sensitive habits parser correlation test** (P2-bug)
   - Scope: `tests/habits/test_parse_morning_reply_48hr_correlation.py` — inject a clock instead of wall-time
   - Acceptance: passes on dates after 2026-06-04
4. **CI: Run non-live pytest suite on push to main** (P1-infra)
   - Scope: `make test` target + GH Actions workflow
   - Acceptance: workflow passes on main; future failing tests block

### Under **#516** (existing, now absorbs Epic C — Observability Lifecycle Contract)

5. **Research/ADR: Define Felix component lifecycle status contract** (P1-rfc)
   - Scope: lifecycle states (`active`, `suspended`, `disabled`, `failed`, `stale`, `degraded`), freshness rules, suspension semantics
   - Acceptance: ADR or principle maps states to service inventory + per-component health files
6. **Fix: Reconcile felix-doc-auditor suspended state** (P2-bug)
   - Scope: service-inventory.json + runbook + live `last-tick.json` alignment
   - Acceptance: repo docs and live read-only checks tell the same story

### Under **NEW Epic D — Shared Vikunja Client** (P2)

7. **ADR: Standardize Vikunja client, base URL, token, timeout, and error policy** (P2-rfc)
   - Scope: hostname vs IP default; redaction-safe error messages; override semantics
8. **Refactor: Introduce shared Vikunja client library** (P2-feature)
   - Scope: `scripts/lib/vikunja.py` or `scripts/vikunja/client.py`
   - Acceptance: at least two existing helpers use the client + tests
9. **Migration: Move remaining Vikunja helpers to shared client** (P3-debt)
   - Scope: per-domain children as needed

### Under **NEW Epic E — Architecture Data Validation** (P2)

10. **Tooling: Add semantic validator for architecture JSON** (P2-infra)
    - Scope: date sanity, status enums, required fields, health-check rules by entity type, schema-version exceptions
    - Acceptance: catches future dates + active services lacking required health checks
11. **Fix: Clean current architecture-data inconsistencies** (P2-bug)
    - Scope: Anthropic `created_date` 2026-10-18, doc-auditor `active` vs suspended, module-vs-service mixed entries

### Under **#281** (existing, now absorbs Epic F — Helper/Library/Skill Conventions Ratification)

12. **Governance: Approve helper-script conventions and wire into Directive 6** (P1-rfc)
    - Scope: status: draft → approved; reference from Constitution Directive 6
    - Acceptance: future issue templates and CLAUDE.md point to the conventions
13. **Template: Add helper/library/skill decision prompt to issue templates** (P2-infra)
    - Scope: spec-ready criteria ask whether deterministic work should be a helper, shared library, or skill

### Under **NEW Epic G — Deploy Script Surface Cleanup** (P2/P3)

14. **Audit: Classify deploy scripts as active, deprecated, or historical** (P3-debt)
    - Scope: header annotations or archive moves for `deploy-f013.sh`, `deploy-f014.sh`, `deploy-f026.sh`, `deploy-028.sh`, `deploy-149.sh`
    - Acceptance: active scripts do not preserve deprecated crontab mutation examples unless explicitly justified
15. **Runbook: Document canonical deploy-script template** (P3-debt)
    - Scope: deploy-149 as reference for dry-run/apply, no system crontab, rollback, smoke verification

### Under **#270** (existing, now absorbs Epic H — Agent Mutation Governance Enforcement)

16. **Research/ADR: Tier-aware mutation wrapper contract** (P1-rfc)
    - Scope: classify tier → require approval reference → preflight → mutate via wrapper → update authoritative docs in same change → verify post-mutation → audit-trail comment
    - Acceptance: ADR defines the seven-step protocol + per-tier exemptions
17. **Tooling: Implement Tier 2+ mutation wrapper** (P1-feature)
    - Scope: deterministic helper that codifies the protocol
    - Acceptance: at least one Tier 2 mutation class flows through the wrapper end-to-end

---

## Governance Ratifications (Independent of Epic Filing)

These need decisions before the new Epics start work:

1. **Ratify `principles.md`** — currently draft. Decided home: `docs/design/engineering-principles.md` (per operator decision 2026-06-05). Promote status to `approved`; link from `CLAUDE.md` "Engineering Principles" section + Constitution Directive 6.

2. **Ratify `docs/design/helper-script-conventions.md`** — currently draft per F-006. This blocks #281/Epic F's execution. Promote status to `approved` if no edits required; otherwise file as a small RFC.

3. **Constitution updates** (per `governance-update-map.md`):
   - Directive 6: reference helper-script-conventions.md
   - New/amended observability directive: every deployed component has a machine-readable lifecycle/status signal and named observer
   - Privacy boundary: add lint-violation note for stale historical path references outside migration docs

4. **CLAUDE.md updates**:
   - Add "Engineering Principles" section pointing to engineering-principles.md
   - Add rule: suspended services must be represented in architecture data + health checks as suspended, not merely disabled
   - Add reminder: new Vikunja integrations should use the shared client once Epic D delivers it

5. **Spec Kitty Charter updates**:
   - Testing standards: require non-live pytest in CI (gates Epic B)
   - Quality gates: require architecture-data validation when authoritative JSON changes (gates Epic E)
   - Deployment constraints: active deploy scripts must not use deprecated cron mutation patterns unless grandfathered (gates Epic G)

6. **Issue template updates** (gated by Epic ratifications):
   - Feature template: add "Observability / operation" prompt
   - Infra template: add lifecycle-state check + JSON validation requirement
   - Bug/debt: add "guardrail gap" field
   - Research template: add "principle extraction" output

---

## Execution Order

### Day-0 (today)

1. **F-001 ad-hoc fix** — privacy boundary correction across 5 file surfaces + deploy on office2. Stand-alone maintenance commit. No issue filed pre-fix; issue filed retroactively after commit lands (so it records the fix hash).
2. **F-002 quick fix** — patch the date-sensitive `test_explicit_iso_date_in_reply_swaps_correlation.py` to inject clock. Stand-alone maintenance commit.
3. **Move + ratify `principles.md`** — `docs/research/...` → `docs/design/engineering-principles.md`. Promote `status: draft` → `approved`. Single commit.
4. **Commit the architecture review report package** — currently untracked. Single commit so the report itself is preserved as the source for all subsequent work.

### Day-1 (after operator review of this plan)

5. **Add comments to existing Epics** (#270, #281, #516) referencing the report findings and their absorbed-Epic content (C → #516, F → #281, H → #270). Update their bodies if needed.
6. **File 5 new Epics**: A (P1), B (P1), D (P2), E (P2), G (P2/P3). Use the "Epic:" prefix per memory `feedback_github_issue_structure`.
7. **File 17 candidate issues** (listed above), each linked to its parent Epic via GitHub native sub-issue.
8. **Re-parent existing orphan issues** to their target Epics (per the recommended-parenting section above). Operator approves each re-parenting.

### Day-2 onward

9. **Ratify `helper-script-conventions.md`** — gates Epic F (#281) execution.
10. **Update Constitution + CLAUDE.md + Charter + issue templates** per `governance-update-map.md`. Some of these can be a single PR.
11. **Begin execution** on P1 Epic work (B, possibly the #270 protocol ADR, and the #516 lifecycle contract ADR). P2/P3 work follows by priority.

---

## Open Decisions for Operator

Before any reorg begins, the following need explicit decisions:

| # | Decision | Default if you don't specify |
|---|----------|------------------------------|
| 1 | **F-001 fix scope**: just the listed 5 files, or sweep `rg` first for any other stale `02-Growth/_private` references? | Sweep first, then fix all hits |
| 2 | **principles.md ratification path**: silent promote (this is a small repo, you're the operator) or open a "Charter amendment" PR for the record? | Silent promote with a doc-audit-tagged commit |
| 3 | **helper-script-conventions.md ratification**: same question — silent promote vs PR? | Silent promote |
| 4 | **#366 RFC → Epic conversion**: convert #366 to an Epic, or keep it as an RFC with #271 as the EA-side Epic? | Keep as RFC; revisit if Theme/Initiatives become operational |
| 5 | **#327 RFC parenting**: child of #270 (mutation governance / silent-failure) OR child of #516 (observability)? | #516 — error/alerting primitives is closer to observability than to mutation control |
| 6 | **#154 Charter amendment parenting**: child of #270 (charter amendment is governance) OR child of new Epic G (deploy scripts)? | Epic G — deploy-scripts is the operational scope; charter amendment is the mechanism |
| 7 | **Voice interaction issues (#172, #175, #194)**: file a new Epic for voice, or leave as standalone? | Leave standalone for now; revisit if any become active |
| 8 | **#106 + #133 RFCs**: should these become Epics? | Leave as RFCs; revisit if either is approved to start implementation |
| 9 | **Re-parenting EA features under #164/#165**: do this batch, or wait until each gets active? | Batch now — easier to maintain Epic hygiene; existing features stay clearly grouped |

---

## Bottom Line

The architecture review's findings are sound. The proposed Epics are mostly net-new but several have natural homes in existing Epics. Net result is a manageable reorg: 5 new Epics, 3 existing Epics expanded with absorbed content, 17 candidate issues filed, ~25 orphans re-parented.

Two things create real blocking value if done first:

1. **F-001** because it's a real (small but real) privacy boundary integrity issue
2. **Ratifying principles.md + helper-script-conventions.md** because they gate the helper/Directive-6 hardening work that #281 and Epic F both depend on

Everything else is sequential issue/Epic management once operator approves the plan.
