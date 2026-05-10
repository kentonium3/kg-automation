# Tasks: Felix Doc Auditor Agent

**Mission**: `felix-doc-auditor-agent-01KR7JK9`
**Phase**: 2 (Tasks)
**Generated**: 2026-05-09
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Data model**: [data-model.md](./data-model.md) | **Contracts**: [contracts/](./contracts/) | **Quickstart**: [quickstart.md](./quickstart.md)

## Mission Branch Strategy

- Planning/base branch: **`main`** (no worktree at this phase)
- Final merge target: **`main`**
- Execution worktrees allocated per WP via `lanes.json` after `finalize-tasks`
- WP01–WP04 are parallelizable (independent file scopes). WP05 depends on all four. WP06 depends on WP05.

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create IDENTITY.md for felix-doc-auditor agent | WP01 | [P] | [D] |
| T002 | Create SOUL.md for felix-doc-auditor agent | WP01 | [D] |
| T003 | Create TOOLS.md for felix-doc-auditor agent | WP01 | [D] |
| T004 | Create USER.md for felix-doc-auditor agent | WP01 | [D] |
| T005 | Create AGENTS.md for felix-doc-auditor (standing orders) | WP01 | | [D] |
| T006 | Write doc-audit skill SKILL.md | WP02 | | [D] |
| T007 | Add worked examples section to SKILL.md | WP02 | | [D] |
| T008 | Validate skill against skill-author conventions | WP02 | | [D] |
| T009 | Add felix-doc-auditor entry to AGENT-REGISTRY.md | WP03 | [D] |
| T010 | Add felix-doc-auditor entry to agent-registry.json | WP03 | [D] |
| T011 | Add felix-doc-auditor entry to service-inventory.json | WP03 | [D] |
| T012 | Add narrative section for felix-doc-auditor to service-inventory.md | WP03 | [D] |
| T013 | Add doc-auditor-ops.md reference to doc-domain-map.json | WP03 | [D] |
| T014 | Write docs/runbooks/doc-auditor-ops.md | WP04 | | [D] |
| T015 | Update docs/INDEX.md with new runbook + skill references | WP04 | [D] |
| T016 | Modify .github/workflows/doc-audit-weekly.yml per R-012 (FR-008 fix) | WP04 | [D] |
| T017 | Create scripts/office2/deploy/felix-doc-auditor.sh deploy helper | WP05 | | [D] |
| T018 | Run the deploy helper on office2 (Kent runs with sudo where needed) | WP05 | | [D] |
| T019 | Register agent in /home/claude/.openclaw/openclaw.json (cron initially disabled) | WP05 | | [D] |
| T020 | Create GitHub label `status:in-progress` (one-time, via gh CLI) | WP05 | [D] |
| T021 | Verify OpenClaw recognizes the agent and label exists | WP05 | | [D] |
| T022 | Manually invoke agent against issue #186 via openclaw delegate | WP06 | | [D] |
| T023 | Receive WhatsApp summary; reply with `approve`/`reject`/`skip` per agent's proposal | WP06 | | [D] |
| T024 | Verify canary outputs (commit, debt issues, audit closed, label removed, activity log) | WP06 | | [D] |
| T025 | Enable cron entry in openclaw.json + restart OpenClaw cron service | WP06 | | [D] |
| T026 | Watch ≥6 cron ticks; verify all 5 remaining backlog issues processed within NFR-006 window | WP06 | | [D] |

---

## Work Packages

### WP01 — Agent workspace files

- [WP01 prompt](./tasks/WP01-agent-workspace-files.md)
- Estimated prompt size: ~450 lines
- **Goal**: Create the four required + one optional OpenClaw agent workspace files (`IDENTITY.md`, `SOUL.md`, `TOOLS.md`, `USER.md`, `AGENTS.md`) for `felix-doc-auditor` per `docs/runbooks/openclaw-agent-setup.md`, with `AGENTS.md` containing the full standing orders for cron-driven doc audit processing at Assisted (Level 1).
- **Priority**: P1 — foundational; all other WPs reference these files
- **Independent test**: New agent passes `openclaw agents` listing locally if deployed (deploy is WP05); standing orders document compiles cleanly when read by another agent for review
- **Included subtasks**:
  - [x] T001 Create IDENTITY.md
  - [x] T002 Create SOUL.md
  - [x] T003 Create TOOLS.md
  - [x] T004 Create USER.md
  - [x] T005 Create AGENTS.md (the standing-orders document — the largest of the five)
- **Implementation sketch**: Read `scripts/openclaw/agents/felix-admin-habits/` for the pattern. Write the four small files (IDENTITY, SOUL, TOOLS, USER) in any order. Write AGENTS.md last because it references all the others. AGENTS.md embeds the WhatsApp reply parser pattern (per R-007, copied from felix-admin-habits) and the audit workflow per the data-model lifecycle diagram. Use the contracts in `contracts/` as authoritative templates for message formats.
- **Parallel opportunities**: T001-T004 are [P] — independent files. T005 sequenced last (references the others).
- **Dependencies**: None
- **Risks**: AGENTS.md is the single longest deliverable in the mission; verbose prompt design has a quality ceiling — keep iterating until it parses correctly to the agent without ambiguity.

---

### WP02 — doc-audit skill

- [WP02 prompt](./tasks/WP02-doc-audit-skill.md)
- Estimated prompt size: ~280 lines
- **Goal**: Create `scripts/openclaw/skills/doc-audit/SKILL.md` per FR-006 / R-013, encoding the audit logic such that the agent can run a full audit using only this skill plus the domain map.
- **Priority**: P1 — agent depends on this for execution
- **Independent test**: Skill passes `skill-author/SKILL.md` conformance check (front matter, structure, sections per `scripts/openclaw/skills/skill-author/SKILL.md`).
- **Included subtasks**:
  - [x] T006 Write SKILL.md (front matter, what-this-skill-is, inputs, workflow, confidence rules, comparison rules, commit format, error handling)
  - [x] T007 Add a worked-examples section using recent commits as illustrations (frontmatter date update, version bump, dead-ref removal)
  - [x] T008 Validate against `skill-author/SKILL.md` conventions (review pass)
- **Implementation sketch**: Read `scripts/openclaw/skills/skill-author/SKILL.md` first to internalize conventions. Read `scripts/openclaw/skills/vikunja-api/SKILL.md` and `scripts/openclaw/skills/escalation/SKILL.md` for examples of the format. Compose the skill section by section per R-013. Examples should reference real recent commits in this repo to demonstrate the high-confidence threshold.
- **Parallel opportunities**: None internal (sequential sections build on each other).
- **Dependencies**: None (skill is independent of the agent workspace; cross-reference is in WP01's AGENTS.md).
- **Risks**: Confidence threshold rules need to be precise — too aggressive risks bad commits (mitigated by Level 1 approval gate), too conservative produces a flood of debt issues (defeats the purpose).

---

### WP03 — Governance + inventory updates

- [WP03 prompt](./tasks/WP03-governance-and-inventory.md)
- Estimated prompt size: ~320 lines
- **Goal**: Register the agent in both governance (AGENT-REGISTRY.md + agent-registry.json) and operational inventories (service-inventory.json + service-inventory.md + doc-domain-map.json) per the templates in `contracts/agent-registry-entry.template.md`.
- **Priority**: P1 — governance registration is required for the agent to operate under Felix
- **Independent test**: `python3 -m json.tool` validates both modified JSON files cleanly; `git diff` shows the new entries match the contract templates.
- **Included subtasks**:
  - [x] T009 Add felix-doc-auditor entry to AGENT-REGISTRY.md
  - [x] T010 Add felix-doc-auditor entry to agent-registry.json (transition_history seeded)
  - [x] T011 Add felix-doc-auditor entry to service-inventory.json
  - [x] T012 Add narrative section for felix-doc-auditor to service-inventory.md
  - [x] T013 Add doc-auditor-ops.md reference to doc-domain-map.json (under area/felix-core)
- **Implementation sketch**: All five subtasks are file-modification tasks with templated content. Use `contracts/agent-registry-entry.template.md` as the authoritative source for AGENT-REGISTRY.md and agent-registry.json content. For service-inventory.json, follow the felix-admin-tasker entry as a structural model (it's the closest existing OpenClaw cron agent). For service-inventory.md, follow the prose pattern of the existing felix-admin-* sections.
- **Parallel opportunities**: All 5 subtasks are [P] — independent files (no cross-dependencies between the 5 file edits).
- **Dependencies**: None (registration entries can land before the agent workspace files exist; the registry is metadata).
- **Risks**: Drift between markdown narrative and JSON authoritative source — verify both match before commit. JSON file `last_updated` and `updated_by` bumps required per change-control protocol.

---

### WP04 — Ops runbook + INDEX + weekly workflow fix

- [WP04 prompt](./tasks/WP04-runbook-index-workflow-fix.md)
- Estimated prompt size: ~340 lines
- **Goal**: Author the operations runbook (`docs/runbooks/doc-auditor-ops.md`) per FR-007, update `docs/INDEX.md` with the new runbook + skill references, and fix the silent-suppression bug in `.github/workflows/doc-audit-weekly.yml` per FR-008 / R-012.
- **Priority**: P1 — runbook is required by FR-007; weekly fix unblocks suppressed weekly audits
- **Independent test**: Manual workflow trigger via `gh workflow run doc-audit-weekly.yml` after the fix lands creates a new weekly issue even with #186 still open (proves R-012 fix); runbook is readable and complete; INDEX has the new entries linked.
- **Included subtasks**:
  - [x] T014 Write `docs/runbooks/doc-auditor-ops.md` (operation, manual trigger, domain-map management, threshold tuning, troubleshooting, kill switch, stale-lock recovery)
  - [x] T015 Update `docs/INDEX.md` with the new runbook + skill references (per change-control protocol for new docs)
  - [x] T016 Modify `.github/workflows/doc-audit-weekly.yml` per R-012 — scope the "skip if exists" check to current week's date in title
- **Implementation sketch**: T014 is the largest piece — write the runbook covering all FR-007 topics. T015 is a short addition to the index following the existing alphabetical pattern. T016 is a 5-line YAML change exactly per R-012. Order: T014 → T015 (index references the new runbook so order matters) → T016 (independent).
- **Parallel opportunities**: T015 and T016 are [P] within the WP. T014 is sequenced first.
- **Dependencies**: None
- **Risks**: T016 YAML change must preserve the rest of the workflow logic; verify by running the workflow once via `gh workflow run` after merge before declaring victory.

---

### WP05 — Office2 deployment

- [WP05 prompt](./tasks/WP05-office2-deployment.md)
- Estimated prompt size: ~370 lines
- **Goal**: Deploy the agent and skill to office2, register the agent in OpenClaw config, and create the `status:in-progress` GitHub label. Initial cron entry is disabled (canary first).
- **Priority**: P1 — required for canary + run
- **Independent test**: `openclaw agents | grep felix-doc-auditor` returns the agent identity card; `gh label list --repo kentonium3/kg-automation | grep status:in-progress` returns the new label; the cron entry exists in openclaw.json but is disabled.
- **Included subtasks**:
  - [x] T017 Create `scripts/office2/deploy/felix-doc-auditor.sh` (idempotent helper that pulls the repo, deploys workspace + skill, prints verification commands)
  - [x] T018 Run the deploy helper on office2 (Kent runs with sudo where needed)
  - [x] T019 Register agent in `/home/claude/.openclaw/openclaw.json` (manual edit — sensitive config not in repo; cron entry initially disabled)
  - [x] T020 Create GitHub label `status:in-progress` via `gh label create` (one-time)
  - [x] T021 Verify deployment (openclaw agents listing, label list, openclaw.json content)
- **Implementation sketch**: Write deploy.sh first (T017) — it codifies the procedure for re-deployment. Run it (T018) which exercises pull + workspace deploy + skill deploy. Then T019 manually edits openclaw.json. T020 is a quick gh command. T021 confirms everything.
- **Parallel opportunities**: T020 (label) is [P] — can happen any time before the canary, independent of office2 work.
- **Dependencies**: WP01, WP02, WP03, WP04 (all in-repo work must be merged to main before office2 pulls).
- **Risks**: openclaw.json editing risk — corrupted JSON breaks ALL OpenClaw agents. Validate with `jq . /home/claude/.openclaw/openclaw.json` before reload.

---

### WP06 — Canary + cron enablement + backlog drain

- [WP06 prompt](./tasks/WP06-canary-and-backlog-drain.md)
- Estimated prompt size: ~390 lines
- **Goal**: Execute the manual canary against issue #186 to validate the full Level 1 flow end-to-end. If canary succeeds, enable the cron and verify the 5 remaining backlog issues drain within NFR-006 (≤6 hours).
- **Priority**: P1 — final validation before mission can be considered done
- **Independent test**: After canary, issue #186 is closed with the agent's audit summary comment; commits and/or debt issues are present per the agent's proposal; status:in-progress label is removed. After cron enabled, ≥1 additional audit issue is processed end-to-end via cron without manual intervention.
- **Included subtasks**:
  - [x] T022 Manually invoke agent against #186: `openclaw delegate felix-doc-auditor "Process audit issue #186"`
  - [x] T023 Receive WhatsApp summary; reply per the vocabulary in `contracts/whatsapp-reply-vocabulary.md`
  - [x] T024 Verify all canary outputs: commit (if any), debt issues created, audit summary comment, audit issue closed, status:in-progress label removed, activity log entry written
  - [x] T025 Enable cron entry in `/home/claude/.openclaw/openclaw.json` + restart OpenClaw cron service
  - [x] T026 Watch ≥6 cron ticks (≥6 hours); verify backlog drains per NFR-006 (all 5 remaining backlog issues processed within 6-hour window)
- **Implementation sketch**: This WP is mostly operational — subtasks describe what to observe and verify. Record observations in `kitty-specs/felix-doc-auditor-agent-01KR7JK9/canary-log.md` (the WP's owned file). If canary reveals issues with the agent or skill, file them as separate issues and stop the cron-enable step.
- **Parallel opportunities**: None (sequential validation steps).
- **Dependencies**: WP05 (deployment must be complete).
- **Risks**:
  - Agent makes a wrong proposal and WhatsApp approval flow allows commit anyway — mitigated by Kent reviewing the WhatsApp summary before approving
  - Backlog drain takes >6 hours — investigate but not necessarily a blocker (NFR-006 is a target, not a hard threshold)
  - WhatsApp delivery fails during canary — agent stays at status:in-progress; recovery procedure in quickstart.md / runbook

---

## MVP scope

**WP01 + WP02 + WP03 + WP04** = the in-repo deliverables. Once these are committed and pushed, the next four checkboxes (manual deploy, canary, cron enable, drain validation) make the agent live.

**Minimum demonstrable milestone**: WP01 + WP02 alone proves the agent design (workspace + skill); WP05 + WP06 prove operation. Don't merge mission until WP06 is green.

## Promotion-readiness criteria (out of scope for this mission, for reference)

After ~1 week at Assisted (Level 1), the autonomy promotion review checks:
- Audit issues processed without false-positive edits
- WhatsApp approval cycle worked smoothly (no recurring `reject` for genuine proposals)
- No edits to constitution / CLAUDE.md / credentials (per SC-005)
- Audit trail intact (per SC-006)

If yes → promote to Supervised (Level 2) via separate governance decision.

## Notes

- Tests: not requested. No unit-test framework for OpenClaw agents exists; validation is operational (canary + drain in WP06).
- The `[P]` markers in the Subtask Index are reference-only (parallelism hint). Per-WP checkboxes in WP sections are the canonical tracking surface for `mark-status`.
