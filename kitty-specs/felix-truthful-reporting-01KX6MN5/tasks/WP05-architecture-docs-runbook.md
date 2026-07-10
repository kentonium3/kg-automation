---
work_package_id: WP05
title: Architecture docs, runbook & regression checklist
dependencies:
- WP02
- WP03
- WP04
requirement_refs:
- C-004
- NFR-003
tracker_refs: []
planning_base_branch: fix/felix-truthful-reporting
merge_target_branch: fix/felix-truthful-reporting
branch_strategy: Planning artifacts for this mission were generated on fix/felix-truthful-reporting. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-truthful-reporting unless the human explicitly redirects the landing branch.
subtasks:
- T021
- T022
- T023
- T024
phase: Phase 3 - Docs
assignee: ''
agent: "claude:opus:reviewer-renata:reviewer"
agent_profile: "curator-carla"
shell_pid: "18707"
history:
- at: '2026-07-10T18:45:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/
create_intent:
- docs/runbooks/trust-reporting-detector.md
execution_mode: code_change
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/runbooks/trust-reporting-detector.md
- docs/INDEX.md
- docs/DEVELOPER_PORTAL.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before doing anything else, load your assigned agent profile so you inherit the
right identity, governance scope, and boundaries for this repo. Run the
`/ad-hoc-profile-load` skill with the `agent`/`role` from this WP's frontmatter
(`claude` / `implementer`). Do not begin the subtasks until the profile's
initialization declaration has been applied.

## Branch Strategy

- **Current branch at workflow start**: `fix/felix-truthful-reporting`.
- **Planning/base branch for this feature**: `fix/felix-truthful-reporting`.
- **Completed changes must merge into**: `fix/felix-truthful-reporting`.
- The concrete lane/worktree is resolved by `/spec-kitty.implement` — do **not**
  create branches or worktrees by hand. Commit through the workflow.
- **DEPENDS ON WP02 + WP03 + WP04.** This WP is docs-only: it *documents* the
  detector runner/deploy (WP02 cron-drift + runner, WP03 assertion ledger +
  verifier, WP04 doctrine/prompt edits per the plan's IC map). Their code and
  the deployed systemd unit are the source of truth; this WP must describe what
  they actually build, not invent behavior.

## Objectives & Success Criteria

Reconcile the architecture docs and author the operations runbook for the new
`felix-trust-scan` service, covering **C-004** (deploy/rebaseline posture) and
**NFR-003** (doctrine budget context) at the documentation layer:

- The new service is a first-class entry in `service-inventory.json` (+ narrative
  in `service-inventory.md`) and the **architecture-data validator passes**.
- A `docs/runbooks/trust-reporting-detector.md` ops runbook exists covering what
  the detector does, how to read its alerts, **baseline maintenance**, run modes
  + exit-code discipline, disable/rollback, and the fail-safe guarantee.
- The new service and runbook are **discoverable**: `docs/INDEX.md` (correct
  group + Divio type) and, where appropriate, `docs/DEVELOPER_PORTAL.md` link to
  it, and all links resolve.
- The SC-001..005 regression-verification checklist is recorded (drawn from
  `quickstart.md`) for the post-merge operator-run deploy.

## Context & Constraints

- **JSON is authoritative; markdown is narrative** (repo doctrine, CLAUDE.md /
  Constitution Directive 5). `service-inventory.json` is the source of truth; the
  `.md` view restates it in prose. When they disagree, the JSON wins — so edit
  the JSON first, then reflect it in the narrative.
- The **architecture-data validator** (`tooling/scripts/validate_architecture_data.py`)
  is a **blocking Docs-CI gate**. Any `service-inventory.json` edit must satisfy
  its schema, so mirror an existing timer-service entry's field shape exactly
  rather than inventing keys.
- **Rebaseline is NOT required** for this mission (gap #621): per
  `docs/design/architecture/data/audited-surfaces.json`, `audit.sh` does not hash
  deployed `AGENTS.md` and the detector code is not a hashed baseline. The merge
  commit records `Rebaseline: not required — <reason>`. Do not add a rebaseline
  step to the runbook's happy path.
- Do **not** edit `signal-to-doc-map.json` in this WP — consult it only for
  reference on which doc surfaces a service change should touch.
- Keep this WP docs-only: no code, no schema files, no deploy manifest (those are
  WP02/WP03/WP04 territory). Cross-reference `quickstart.md` instead of copying it.

## Subtasks & Detailed Guidance

### T021 — Add `felix-trust-scan` to the service inventory (JSON + narrative)

- **Purpose**: Model the new detector service so the architecture store reflects
  what WP02/WP03/WP04 deploy.
- **Steps**:
  1. Add a new object to the `services` array in
     `docs/design/architecture/data/service-inventory.json`, **mirroring the shape
     of the existing timer entries** `felix-health-check` and `felix-doc-auditor`
     (both `"type": "systemd-timer"`). Use these values, adjusting to what
     WP02/WP03/WP04 actually built:
     - `name`: `felix-trust-scan`; `type`: `systemd-timer`; `host`: `office2`;
       `user`/`systemd_user`: `claude`.
     - `systemd_unit`: `felix-trust-scan.timer (user unit) + felix-trust-scan.service (user oneshot)`.
     - `schedule`: ≤15-min cadence (NFR-002) — state the real `OnCalendar`/
       `OnUnitActiveSec` the WP02 unit uses.
     - `exec_start`: `/usr/bin/python3 -m scripts.trust.run_trust_scan` (the
       `python3 -m` form — office2 is python3-only).
     - `purpose`: cron-drift detection (live crons vs approved baseline) +
       completion-assertion verification; alerts via the **#701 unified alert
       bus** (`felix-alert` topic); fail-safe (NFR-001).
     - `dependencies`: the #701 alert bus (`scripts/common/alert_bus/`), the
       OpenClaw CLI (`openclaw cron list --json`), the Vikunja API, and the
       committed baseline `docs/design/architecture/data/approved-crons.json`.
     - `health_check`: a signal-file entry mirroring the sibling timers
       (endpoint under `/data/services/…`), if WP02 emits one.
     - `config_files`: the timer/service unit sources + the `scripts/trust/` package.
     - `risk_tier`: `3`; `status`/`operational_status`: `active`;
       `deployed_by`/`deployed_on`/`updated_by`: this mission (#683).
  2. Add a narrative entry for the service in
     `docs/design/architecture/service-inventory.md`, matching how the other
     timer services are described there.
- **Files**: `docs/design/architecture/data/service-inventory.json`,
  `docs/design/architecture/service-inventory.md`.
- **Notes**: After editing, **run the architecture-data validator** (see Test
  Strategy) and fix any schema complaint before moving on. Do not add keys the
  sibling entries don't have.

### T022 — Author the operations runbook `docs/runbooks/trust-reporting-detector.md`

- **Purpose**: Give the operator a single runbook for the detector.
- **Steps**: Create the file with standard runbook frontmatter (`doc_type:
  runbook`, plus `title`, `audience: agents_and_humans`, `status`, `created`,
  `last_validated`, `last_updated`, `version`, `owners: [kgale]`) matching other
  files in `docs/runbooks/`. Cover:
  1. **What the detector does** — the two deterministic scans: cron-drift (live
     OpenClaw crons vs the approved baseline — the load-bearing, agent-independent
     guard) and assertion-verification (asserted artifacts checked against their
     owning system).
  2. **How to read its alerts** — they arrive via the **#701 unified alert bus**
     (`felix-alert` topic); what each alert identifies (divergence, owning agent
     where known, missing corroboration).
  3. **Baseline maintenance** — how to add/remove an approved cron in
     `docs/design/architecture/data/approved-crons.json`, and the **ordering
     rule**: the baseline entry must land **before or together with** the
     legitimate cron, or the detector will alert on the (correct) new cron as
     unapproved drift.
  4. **Run modes + exit-code discipline** — timer mode (`run_trust_scan --json`)
     always exits 0 even on fault (no systemd failure loop); preflight/self-test
     mode (`run_trust_scan --preflight --json`) may exit 2 on a hard fault. State
     the exact exit-code contract WP02 implemented.
  5. **Disable / rollback** — `systemctl --user disable --now felix-trust-scan.timer`
     (agents unaffected; out-of-band, no rebaseline).
  6. **Fail-safe guarantee** — a detector fault never blocks or breaks normal
     agent request handling (NFR-001); on fault it emits no spurious alert.
- **Files**: `docs/runbooks/trust-reporting-detector.md` (new — declared in
  `create_intent`).
- **Notes**: Wrap any shell/CLI tokens and `<` `>` placeholders in backticks so
  the doc validator/markdown lint is happy.

### T023 — Make the runbook + service discoverable (INDEX + portal)

- **Purpose**: Prevent the "new doc surface routinely missed" failure (#492).
- **Steps**:
  1. Add `trust-reporting-detector.md` to `docs/INDEX.md` under the operational
     runbooks group — most likely alongside the other periodic office2 sweeps
     (the security-baseline / credential-liveness cluster) and/or the
     agent-executable runbooks list — with a one-line description and the correct
     Divio type annotation used by neighboring entries.
  2. If appropriate, add a pointer in `docs/DEVELOPER_PORTAL.md` (e.g. under the
     runbook-execution guidance) so an onboarding reader can find it.
- **Files**: `docs/INDEX.md`, `docs/DEVELOPER_PORTAL.md`.
- **Notes**: Match the existing link syntax exactly (the `[label](<./path>)`
  angle-bracket form used throughout INDEX). Confirm the new links resolve.

### T024 — Record the SC-001..005 regression-verification checklist

- **Purpose**: Give the post-merge operator a concrete deploy-verification
  checklist, framed for the operator-run deploy.
- **Steps**: In the runbook (a clearly-labelled `## Regression verification
  (SC-001..005)` section), record the checklist drawn from `quickstart.md`:
  - **SC-004** — doctrine present in all fleet prompts (grep check).
  - **SC-001/SC-002** — create-N-reminders regression: DM `main` to create a
    Vikunja reminder todo; confirm the task(s) exist, `openclaw cron list` shows
    **no** new cron, and the reply claims only what was actually done.
  - **SC-003** — inject a throwaway cron + a bogus (nonexistent-id) assertion, run
    `run_trust_scan --once`, confirm **two** alerts reach Kent's phone within one
    cycle, then remove the throwaway cron.
  - **SC-005** — forced-fault fail-safe: point the baseline at an unreadable file;
    confirm preflight exits 2 and timer mode exits 0, both emitting **no** alert
    and leaving agents unaffected.
- **Files**: `docs/runbooks/trust-reporting-detector.md`.
- **Notes**: **Cross-reference `quickstart.md`** as the canonical source rather
  than duplicating its full deploy steps — the checklist is the operator's live
  verification, `quickstart.md` holds the deploy sequence.

## Test Strategy

No code tests in this WP. Validate the docs:

- Run `python3 tooling/scripts/validate_docs.py` (frontmatter + link validation).
- Run the **architecture-data validator**
  `python3 tooling/scripts/validate_architecture_data.py` — must pass with the new
  service entry (this is the blocking Docs-CI gate).
- Confirm **no broken links**: every new `docs/INDEX.md` / portal entry resolves
  to the runbook, and the runbook's internal references resolve.

## Definition of Done

- [ ] `felix-trust-scan` added to `service-inventory.json` (mirrors the existing
      timer entries) **and** reflected in `service-inventory.md`; the
      architecture-data validator is **green**.
- [ ] `docs/runbooks/trust-reporting-detector.md` created with standard runbook
      frontmatter, covering detector behavior, alert-reading, **baseline
      maintenance + ordering rule**, run modes + exit-code discipline, **rollback**,
      and the fail-safe guarantee.
- [ ] The SC-001..005 regression checklist is recorded in the runbook and
      cross-references `quickstart.md`.
- [ ] `docs/INDEX.md` updated (correct group + Divio type) and, where
      appropriate, `docs/DEVELOPER_PORTAL.md`; all links resolve.
- [ ] `validate_docs.py` and `validate_architecture_data.py` pass locally (Docs
      CI green).

## Risks

- **Architecture-data validator schema mismatch** — the highest-probability
  failure. Mirror an existing timer entry (`felix-health-check` /
  `felix-doc-auditor`) field-for-field; don't add unknown keys; run the validator
  before declaring done.
- **JSON vs narrative drift** — keep the JSON authoritative and make the `.md`
  restate it; never let the narrative assert something the JSON doesn't carry.
- **Duplication with quickstart** — don't copy the full deploy sequence into the
  runbook; cross-reference `quickstart.md` so there's one source of truth.
- **Documenting intended vs built behavior** — since this WP depends on
  WP02/WP03/WP04, verify the real unit name, `exec_start`, schedule, and
  exit-code contract they shipped before writing them down.

## Reviewer Guidance

- `validate_architecture_data.py` and `validate_docs.py` both pass.
- The `felix-trust-scan` entry matches the **real deployed unit** (name,
  `exec_start` = `python3 -m scripts.trust.run_trust_scan`, ≤15-min schedule,
  #701 alert dependency) and mirrors the sibling timer-service shape.
- The runbook covers **baseline maintenance (with the ordering rule)** and
  **disable/rollback** — the two ops procedures most likely to be needed.
- The SC-001..005 checklist is present and cross-references `quickstart.md`.
- INDEX/portal links resolve; the new service and runbook are discoverable.

## Activity Log

- 2026-07-10T20:04:28Z – claude:sonnet:curator-carla:implementer – shell_pid=16480 – Assigned agent via action command
- 2026-07-10T20:11:23Z – claude:sonnet:curator-carla:implementer – shell_pid=16480 – Docs: felix-trust-scan inventory + ops runbook + regression checklist; validators green; links resolve; verified against code; commit d3959c4f.
- 2026-07-10T20:11:28Z – claude:opus:reviewer-renata:reviewer – shell_pid=18707 – Started review via action command
- 2026-07-10T20:14:48Z – user – shell_pid=18707 – review-passed-observe
