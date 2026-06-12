# Tasks: Restore WhatsApp DM Reply Delivery

**Mission**: `restore-whatsapp-dm-reply-delivery-01KTVVHH`
**Mission ID**: `01KTVVHHBJKKG3JPMGRVHSB81P` (mid8 `01KTVVHH`)
**Spec**: [`spec.md`](spec.md)
**Plan**: [`plan.md`](plan.md)
**Research**: [`research.md`](research.md) (now includes §9 H6 update + A3 relaxation)
**Data model**: [`data-model.md`](data-model.md)
**Contracts**: [`contracts/embedded-run-lifecycle.md`](contracts/embedded-run-lifecycle.md), [`contracts/journal-event-assertions.md`](contracts/journal-event-assertions.md)
**Quickstart**: [`quickstart.md`](quickstart.md)

**Mission type**: software-dev (bug fix)
**Total work packages**: 5
**Total subtasks**: 26
**MVP scope**: WP01 + WP02 + WP03 + WP04 + WP05 (this is a bug-fix mission, all WPs required)

---

## Subtask Index (reference table — not a tracking surface)

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | H6 openclaw 2026.5.28 → 2026.6.5 upgrade probe + plan (FIRST in ramp) | WP01 |  |
| T002 | H5 plugin install state + version check (read-only) | WP01 | [P] |
| T003 | H4 config-swap probe matrix (with full rollback discipline) | WP01 | [P] |
| T004 | H2 missing-field discovery via openclaw docs + config diff | WP01 | [P] |
| T005 | H3 AGENTS.md rollback probe (mutates + restores; never persists rollback state) | WP01 |  |
| T006 | Synthesize Decision Record into research.md "Discoveries" append block | WP01 |  |
| T007 | Open + resolve spec-kitty decision recording fix shape OR escalation | WP01 |  |
| T008 | Apply named remediation per WP01 outcome (upgrade OR config edit OR AGENTS.md OR plugin) | WP02 |  |
| T009 | Create scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh per DIR-004/005 (handles upgrade + config paths) | WP02 |  |
| T010 | Add post-flight smoke assertion to deploy script using contracts/journal-event-assertions.md | WP02 |  |
| T011 | Alt-path: draft + file internal tracking issue (per FR-009) if WP01 escalated to H1 | WP02 |  |
| T012 | Append terminal disposition to terminal-disposition.md (path taken + commit SHA + issue if escalation) | WP02 |  |
| T013 | DR-1: update service-inventory.json (version, dm_policy, session.dmScope) | WP03 | [P] |
| T014 | DR-2: add `whatsapp-dm-reply` flow to data-flows.json | WP03 | [P] |
| T015 | DR-3: verify audited-surfaces.json coverage (read-only verify likely) | WP03 |  |
| T016 | DR-4: update service-inventory.md narrative to mirror DR-1 | WP03 |  |
| T017 | DR-5: update data-flows.md + Mermaid in data-flows.view.md | WP03 |  |
| T018 | DR-6: add "DM-reply lifecycle troubleshooting" section to openclaw-agent-setup.md | WP04 |  |
| T019 | DR-7: update INDEX.md (conditional, only if runbook scope materially changed) | WP04 |  |
| T020 | DR-8: update memory `project_whatsapp_dmpolicy.md` (disabled → allowlist) | WP04 | [P] |
| T021 | DR-9: add memory `reference_openclaw_dm_reply_lifecycle` (lifecycle markers + bug signature) | WP04 | [P] |
| T022 | Tier 2 pre-flight (Restic ≤24h attestation per DIR-009) | WP05 |  |
| T023 | Execute deploy via scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh --backup-confirmed | WP05 |  |
| T024 | Operator smoke (5 DMs, 5-min window) + journal-event assertion per contracts | WP05 |  |
| T025 | #557 rebaseline: reset security-monitor baselines; record timestamp for trailer | WP05 |  |
| T026 | SC-005 next-day cron regression check (deferred ~14h to 7:10 AM ET) | WP05 |  |

---

## Phase 1 — Diagnostic Investigation

### WP01 — Diagnostic Investigation

**Goal**: Validate hypotheses **H6** (openclaw upgrade) → H5 → H4 → H2 → H3 → H1-escalation in priority order (per `research.md` §9), and emit a **Decision Record** naming the verdict. If all in-scope hypotheses fail (including H6), escalate to H1 per FR-009/C-001.

**Priority**: P0 (blocks WP02 and WP05)
**Estimated prompt size**: ~500 lines
**Dependencies**: none
**Independent test**: WP01 is done when `research.md` contains a "Discoveries" append block with a Decision Record line of the form `Fix shape: <H6|H5|H4|H2|H3> — <specific change>` OR `Escalation: H1 (vendored runtime); evidence summary attached`.

**Maps to**: FR-007, FR-009, FR-011, C-001, C-002 (+ research.md §9 A3 relaxation)

**Included subtasks**:

- [x] T001 H6 openclaw upgrade probe + plan (WP01)
- [x] T002 H5 plugin install state + version check (WP01)
- [x] T003 H4 config-swap probe matrix (WP01)
- [x] T004 H2 missing-field discovery (WP01)
- [x] T005 H3 AGENTS.md rollback probe (WP01)
- [x] T006 Synthesize Decision Record into research.md (WP01)
- [x] T007 Open + resolve spec-kitty decision (WP01)

**Implementation sketch**:
1. **First**: read openclaw 2026.6.5 release notes; map the named fixes to our journal signature. If the mapping is strong (Codex review already done in research.md §9 says it is), draft an upgrade plan and present to Kent for go/no-go before running the actual upgrade.
2. If H6 isn't validated by desk review, proceed with H5 → H4 → H2 → H3 in cost order (parallel-safe where marked [P]).
3. H3 (AGENTS.md probe) is destructive-but-reversible — always finish with rollback regardless of outcome.
4. Synthesize a Decision Record append block into research.md (do NOT rewrite earlier sections).
5. Open + resolve the spec-kitty decision recording the verdict.

**Parallel opportunities**: T002, T003, T004 are [P]. T001 must run first (it's the cheapest + highest-confidence). T005, T006, T007 are sequential.

**Risks**: H6 upgrade introduces unrelated breakage (per memory `reference_openclaw_upgrade_gotchas`); mitigated by the upgrade-gotchas checklist baked into T001 + WP02. H3 probe leaves wrong AGENTS.md if rollback skipped; mitigated by mandatory rollback step.

---

## Phase 2 — Apply Remediation

### WP02 — Apply Remediation

**Goal**: Implement the verdict from WP01's Decision Record. Three execution paths:

- **Upgrade path** (H6): execute the openclaw upgrade per `reference_openclaw_upgrade_gotchas` checklist; deploy script handles the upgrade sequence
- **Config / AGENTS.md / plugin path** (H2/H3/H4/H5): edit the named source file; deploy script syncs to office2
- **Escalation path** (H1): file internal tracking issue per FR-009; no source-code edit

**Priority**: P0 (blocks WP05; tail-blocks the mission)
**Estimated prompt size**: ~500 lines
**Dependencies**: WP01 (needs the Decision Record)
**Independent test**: WP02 is done when EITHER (a) the named remediation is applied + a deploy script is committed that exercises it with a post-flight smoke step, OR (b) an internal tracking issue is filed with full diagnostic evidence and `terminal-disposition.md` is committed.

**Maps to**: FR-001, FR-002, FR-003, FR-004, FR-006, FR-008, FR-009

**Included subtasks**:

- [ ] T008 Apply named remediation per WP01 outcome (WP02)
- [ ] T009 Create scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh (WP02)
- [ ] T010 Add post-flight smoke assertion to deploy script (WP02)
- [ ] T011 Alt-path: file internal tracking issue per FR-009 if escalated (WP02)
- [ ] T012 Append terminal disposition to terminal-disposition.md (WP02)

**Implementation sketch**:
1. Read WP01's Decision Record to determine which of the 3 execution paths.
2. **Upgrade path** (most likely per H6 prior): write the deploy script around the upgrade sequence (npm/pipx upgrade, openclaw doctor, restart gateway, run post-flight smoke). Apply the `reference_openclaw_upgrade_gotchas` checklist.
3. **Config/edit path**: edit the named repo source file; deploy script syncs to office2 via DIR-005 strict-order.
4. **Escalation path**: draft + file the internal tracking issue per memory `feedback_upstream_issue_title_pre_approval` (present title + body to Kent for approval BEFORE filing).
5. Author `terminal-disposition.md` capturing path taken + commit SHA + (if escalation) issue number.

**Parallel opportunities**: subtasks within WP02 sequential. WP02 itself can run in parallel with WP03 + WP04.

**Risks**: openclaw upgrade introduces unrelated regression (mitigated by the gotchas checklist + post-flight smoke); fix applied to office2 but NOT to repo source (mitigated by edit-repo-then-deploy discipline per DIR-008); escalation filed without Kent's approval (mitigated by explicit approval gate).

---

## Phase 3 — Documentation Reconciliation (parallel with WP02)

### WP03 — Architecture Data Reconciliation

**Goal**: Land DR-1 through DR-5 per `data-model.md` E4 — correct architectural drift identified in `research.md` §1 and add the missing `whatsapp-dm-reply` data flow.

**Priority**: P1 (independent of fix outcome; closes doc-debt FR-011 / FR-012 found during baseline review)
**Estimated prompt size**: ~400 lines
**Dependencies**: none (drift correction + flow documentation is true regardless of remediation shape)
**Independent test**: WP03 is done when `service-inventory.json` reflects openclaw-gateway v2026.5.28 + `dm_policy: "allowlist"` + `session.dmScope: "per-channel-peer"` (or v2026.6.5 if WP02 took the upgrade path); `data-flows.json` contains a `whatsapp-dm-reply` flow entry; narrative `.md` mirrors are updated; `data-flows.view.md` Mermaid includes the new edge.

**Maps to**: FR-011, FR-012, DIR-014

**Included subtasks**:

- [ ] T013 DR-1 update service-inventory.json (WP03)
- [ ] T014 DR-2 add whatsapp-dm-reply flow to data-flows.json (WP03)
- [ ] T015 DR-3 verify audited-surfaces.json coverage (WP03)
- [ ] T016 DR-4 update service-inventory.md narrative (WP03)
- [ ] T017 DR-5 update data-flows.md + .view.md (WP03)

**Implementation sketch**:
1. T013 + T014 are parallel-safe ([P]) — distinct files.
2. Use `signal-to-doc-map.json` change-class entries as the authoritative doc-target list.
3. For DR-1 service-inventory edits: update only the openclaw-gateway entry; do NOT touch any other service block. Version field reflects the actual deployed runtime post-WP02 (2026.5.28 if config/escalation path; 2026.6.5 if upgrade path).

**Parallel opportunities**: T013, T014 are [P]. WP03 itself is parallel with WP02 + WP04.

**Risks**: drift correction touches load-bearing JSONs that other automation reads. Mitigated by: edit one block at a time; validate JSON parse after each edit (`jq .` on the modified file).

---

### WP04 — Runbook + Memory Reconciliation

**Goal**: Land DR-6 through DR-9 — runbook troubleshooting section, conditional INDEX update, and the two memory updates (`project_whatsapp_dmpolicy` correction + new `reference_openclaw_dm_reply_lifecycle`).

**Priority**: P1 (independent of fix outcome and other WPs)
**Estimated prompt size**: ~350 lines
**Dependencies**: none (parallel with WP02 + WP03)
**Independent test**: WP04 is done when `docs/runbooks/openclaw-agent-setup.md` has a new "DM-reply lifecycle troubleshooting" section linking the contracts; `project_whatsapp_dmpolicy.md` memory says `allowlist`; `reference_openclaw_dm_reply_lifecycle.md` memory exists with the lifecycle markers + bug signature + smoke command; `MEMORY.md` index updated.

**Maps to**: FR-011, FR-012, DIR-014

**Included subtasks**:

- [ ] T018 DR-6 add "DM-reply lifecycle troubleshooting" section to openclaw-agent-setup.md (WP04)
- [ ] T019 DR-7 update INDEX.md (conditional) (WP04)
- [ ] T020 DR-8 update memory project_whatsapp_dmpolicy.md (WP04)
- [ ] T021 DR-9 add memory reference_openclaw_dm_reply_lifecycle.md (WP04)

**Implementation sketch**:
1. T020 + T021 are parallel-safe ([P]) — distinct memory files at `/Users/kentgale/.claude/projects/-Users-kentgale-repos-kg-automation/memory/`. Remember to update `MEMORY.md` index as part of each.
2. For DR-6 runbook section: cite the lifecycle markers from `contracts/embedded-run-lifecycle.md`; include the operator smoke awk one-liner from `contracts/journal-event-assertions.md`; cross-reference the new `reference_openclaw_dm_reply_lifecycle` memory.
3. For DR-7 INDEX update: only edit if DR-6 added a *new* section heading that should be cross-linked from the diagnostics index.

**Parallel opportunities**: T020, T021 are [P]. WP04 itself is parallel with WP02 + WP03.

**Risks**: memory edits live OUTSIDE the spec-kitty file-tracking — won't appear in the merge commit. Operator must verify memory updates landed via `ls -la /Users/kentgale/.claude/projects/.../memory/`. Documented in DoD.

---

## Phase 4 — Deploy + Acceptance Smoke

### WP05 — Deploy + Smoke + Rebaseline

**Goal**: Execute the deploy script on office2 with operator-driven smoke. Validate SC-001 through SC-006 immediately + SC-005 next-day. Apply #557 rebaseline trailer per C-003. Handles three branches based on WP02's terminal disposition: (a) upgrade-path deploy, (b) config/AGENTS.md-path deploy, (c) escalation-path (NO-OP except for documentation).

**Priority**: P0 (mission completion gate)
**Estimated prompt size**: ~450 lines
**Dependencies**: WP02 (deploy script + terminal-disposition.md)
**Independent test**: WP05 is done when (a) deploy completes successfully on office2, (b) operator smoke result matches the expected post-fix journal counts, (c) rebaseline timestamp is recorded for the merge trailer — OR for the escalation path: a deploy-smoke-evidence.md file exists explicitly documenting the no-op with link to the internal tracking issue.

**Maps to**: FR-008, FR-010, NFR-001, NFR-002, NFR-003, NFR-004, NFR-005, C-003, SC-001..SC-007

**Included subtasks**:

- [ ] T022 Tier 2 pre-flight (Restic ≤24h attestation per DIR-009) (WP05)
- [ ] T023 Execute deploy via scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh (WP05)
- [ ] T024 Operator smoke (5 DMs, 5-min window) + journal assertion (WP05)
- [ ] T025 #557 rebaseline: reset security-monitor baselines; record timestamp (WP05)
- [ ] T026 SC-005 next-day cron regression check (deferred ~14h) (WP05)

**Implementation sketch**:
1. Read WP02's `terminal-disposition.md` first to determine path (upgrade / config / escalation).
2. For upgrade + config paths: follow `quickstart.md` §4 step-by-step.
3. For escalation path: skip T023–T025 actual execution; document the no-op with link to the internal tracking issue in `deploy-smoke-evidence.md`.
4. Always run T026 (next-day check) for non-escalation paths — it's the cron regression sentinel.

**Special-case (escalation path)**: WP05 reads `terminal-disposition.md`, confirms escalation, marks subtasks complete with `(skipped: escalation-path)` annotation, and produces a `deploy-smoke-evidence.md` documenting "no deploy executed; mission concluded via internal tracking issue #NNN per FR-009."

**Parallel opportunities**: subtasks sequential. WP05 sequentially depends on WP02. T026 is intentionally deferred ~14h.

**Risks**:
- Tier 2 deploy regresses cron-announce path (mitigated by post-flight smoke + quickstart §4.6 rollback)
- Operator forgets rebaseline (mitigated by explicit T025; trailer checked at merge time per #557)
- Operator forgets SC-005 next-day check (mitigated by T026 being a tracked subtask)
- Upgrade-path introduces a new gotcha not covered by the existing checklist (mitigated by `openclaw doctor --json` post-upgrade verification)

---

## MVP Scope

Bug-fix mission, not a feature mission. There is no MVP cut: all 5 WPs must complete. The closest analog to "MVP" is the escalation path — documented internal tracking issue rather than deployed fix, acceptable per FR-009.

## Parallelization Plan

| Lane | WPs | Notes |
|---|---|---|
| Lane A (diagnostic + fix) | WP01 → WP02 | Sequential; WP02 depends on WP01 Decision Record. WP01 T002/T003/T004 are [P]. |
| Lane B (doc reconciliation) | WP03 \|\| WP04 | Parallel with Lane A. Both can fully complete while WP01/WP02 are in flight. |
| Lane C (deploy + smoke) | WP05 | Sequentially after WP02 lands. T026 intentionally deferred ~14h. |

Reasonable execution: spawn Lane A, B in parallel; Lane C starts after WP02 commits. Total wall-clock: ~3–6 hours for upgrade-path (H6 + verification), ~4–8 hours for config-path, ~2 hours for escalation path. ~12+ hours of calendar elapsed for T026 deferral on non-escalation paths.

## Next Step

User runs `/spec-kitty.implement` (or invokes `spec-kitty-implement-review` skill for orchestrated execution).
