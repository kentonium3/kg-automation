# Specification: Vault Path Registry and Folder Renumber

**Mission:** `026-vault-path-registry-and-folder-renumber`
**Mission type:** `software-dev`
**Source:** [kentonium3/kg-automation#152](https://github.com/kentonium3/kg-automation/issues/152)
**Created:** 2026-04-11
**Target branch:** `main`

---

## Overview

The Felix personal operating system stores knowledge in an Obsidian vault whose top-level folders are referenced by name across the entire kg-automation codebase — agent standing orders, CLAUDE.md, service inventory, scripts, and runbooks. Today only a single path (the inbox) is abstracted through the vault path registry built in mission 024 (issue #150 MVP). Every other vault folder name is duplicated as a string literal in multiple places, two of those folders share the `00-` numeric prefix (ambiguous ordering in Obsidian), and there is no dedicated destination for processed inbox items — which blocks the follow-on inbox pre-scan helper (issue #149).

This mission finishes the registry methodology started by 024: it extends the registry to every vault folder, renumbers the folders to eliminate the `00-` collision and establish a clean ordinal sequence, creates a dedicated processed-inbox folder, migrates every remaining hardcoded vault reference to template markers resolved at deploy time, synchronizes all architecture and runbook documentation to reflect the new state, and strengthens the `_private/` privacy boundary by gitignoring it in the second-brain repo.

The mission is a refactor plus an operational reconfiguration: it changes the names and locations of things but must not change what the system does. When the mission is done, every cron job still fires, every agent still processes its inputs, and every wikilink in the vault still resolves — the difference is that moving or renaming a vault folder in the future becomes a single-file data change, not a coordinated edit across a dozen files.

---

## Context and Motivation

### Current state problems

1. **Path duplication.** The string `00-Inbox` (and its sibling folder names) appears hardcoded in at least five agent workspaces, CLAUDE.md, `data/service-inventory.json`, and several scripts. Renaming or moving any vault folder requires a coordinated multi-file edit; missing a single reference leaves the system silently broken until the next run of the affected agent.

2. **Ordinal collision.** Two top-level vault folders share the `00-` prefix (`00-System`, `00-Inbox`). Obsidian's folder sort is ambiguous for collisions; visual scan of the vault is harder than it needs to be.

3. **No processed-inbox destination.** The follow-on mission (issue #149) needs a place to move inbox items older than 7 days. No such folder exists today. Blocking dependency.

4. **Privacy path exposed to git.** `_private/` is a constitutional hard boundary (never read, written, or referenced by agents) but it sits inside a git-tracked repo with no ignore rule. Content placed there — once the user starts populating it — would enter git history by default.

5. **Architecture documentation drift risk.** The JSON files under `docs/design/architecture/data/` and their markdown views reference vault paths directly. Any folder rename without a paired doc update creates machine-readable-vs-narrative divergence — which the constitution says must be resolved by updating the narrative (JSON wins), but today that has to be done manually and is easy to forget.

### What success looks like from the user's perspective

The operator (Kent) runs this mission once and afterward:
- Can rename any vault folder by editing a single JSON file and re-running a deploy script — no multi-file hunting.
- Has a clean ordinal folder sequence in Obsidian.
- Can start the `#149` inbox pre-scan helper mission without blockers.
- Knows that placing files under `_private/` will never accidentally enter git history.
- Has documentation that accurately reflects the live system state with no stale path literals.

---

## User Scenarios

The "user" for this mission is the operator of the kg-automation system (Kent, solo maintainer). All scenarios are operator-driven, not end-user driven.

### Primary scenario: operator executes the full migration

1. Operator reviews the prepared migration plan and confirms the vault is in a quiescent state (no in-flight inbox items, no pending agent work).
2. Operator executes the pre-rename code migration: the registry is extended, all hardcoded references are converted to template markers, the deploy script runs, and the system is in a byte-identical (or functionally equivalent) state to before — just with a different internal representation.
3. Operator verifies the pre-rename state: agents still run, cron fires correctly, the inbox still processes.
4. Operator pauses the `felix-admin-capture` cron to open a safe window.
5. Operator creates the new processed-inbox folder directly at its final name.
6. Operator renames each existing vault folder to its new ordinal name via the Obsidian UI. Obsidian auto-updates wikilinks across the vault as each rename completes.
7. Operator updates the registry to point at the new folder names and re-runs the deploy script.
8. Operator verifies the post-rename state: agents run against the new paths, wikilinks resolve, deployed agent files on office2 contain the new paths, no stale literals remain.
9. Operator re-enables the `felix-admin-capture` cron.
10. Operator performs the cross-repo operation in the second-brain repo: adds `_private/` to `.gitignore` and runs the idempotent cached-removal command.
11. Operator confirms all documentation has been updated to reflect the new folder names and the new registry state.
12. Mission complete.

### Recovery scenario: verification fails mid-migration

1. Operator is executing the migration and a verification step fails — for example, a deployed agent file on office2 still contains an unreplaced template marker, or an agent smoke-test invocation fails after the rename.
2. Operator stops immediately. The `felix-admin-capture` cron is still paused, so no agent runs are happening against a broken state.
3. Operator reviews the failure, identifies the root cause, fixes it (may involve re-running deploy, reverting a single file, or re-running a rename), re-verifies, and continues.
4. If the root cause is not quickly identifiable, the operator rolls back: git reverts the repo changes, manually renames folders back via Obsidian UI, and restores the registry to its pre-migration state. The cron is re-enabled and the system returns to its prior working state.

### Cross-repo scenario: operator updates second-brain

1. Operator switches to the `~/second-brain/` repository.
2. Operator adds `_private/` to the `.gitignore` file.
3. Operator runs the idempotent cached-removal command (a no-op today because `_private/` is empty, but safe insurance for the future).
4. Operator commits and pushes the change in the second-brain repo.
5. Operator returns to the kg-automation mission workspace to complete mission closure.

### Future-use scenario: operator adds a new vault folder

(This is a validation scenario — after this mission, adding a new top-level vault folder should be trivial.)

1. Operator adds a new logical name and path to the registry JSON.
2. Operator adds a new template marker to any agent/doc that should reference the new folder (editing the `.tmpl` source, not the deployed file).
3. Operator runs the deploy script.
4. The new folder is now reachable by any consumer of the registry. No other changes required.

---

## Functional Requirements

Each FR describes WHAT the system must do. IDs are stable (`FR-001` through `FR-007`). Status is `Draft` until the spec is accepted.

| ID | Requirement | Status |
|---|---|---|
| FR-001 | The vault path registry shall contain a logical-name-to-physical-path entry for every top-level vault folder that any agent, doc, or script references. | Draft |
| FR-002 | No production file in the kg-automation repo (agent workspaces, CLAUDE.md, architecture JSON/markdown, runbooks, scripts) shall contain a hardcoded vault folder name, except the single `_private/` constitutional boundary reference in CLAUDE.md. | Draft |
| FR-003 | A dedicated processed-inbox folder shall exist as a sibling of the inbox folder in the vault, reachable via its registry marker, and present on every device that syncs the vault. | Draft |
| FR-004 | The top-level vault folders shall be renamed to a clean ordinal sequence with no numeric-prefix collisions, and all Obsidian wikilinks within the vault shall continue to resolve correctly after the rename. | Draft |
| FR-005 | The deploy script shall resolve every template marker to its current registry value, producing resolved files in the repo and on office2 that contain no unreplaced markers. | Draft |
| FR-006 | The second-brain repository shall ignore `_private/` at the git level so that any content placed there in the future does not enter git history by default. This requirement is explicitly cross-repository and executed manually by the operator. | Draft |
| FR-007 | All documentation artifacts impacted by this mission — architecture JSON data files, their markdown views, runbooks, the documentation index, and the capability roadmap — shall be updated within this mission to reflect the new folder names, the new processed-inbox folder, and the expanded registry. A new runbook documenting the migration procedure shall be created so future similar migrations have a playbook. | Draft |

### FR-001 detail: Registry completeness

- The registry must include entries for: the system folder, the inbox folder, the new processed-inbox folder, and one entry for each of the currently-named `Constitution`, `Growth`, `Health`, `Business`, `Finance`, `Journal`, and `Resources` folders.
- The registry must NOT include an entry for `_private/`. That path is deliberately unreachable through the registry so that no agent or script can discover it via the resolver API.
- Marker naming convention: `{{VAULT_<UPPER_SNAKE_NAME>}}` (e.g., `{{VAULT_INBOX_PROCESSED}}`) — consistent with the MVP from mission 024.
- The registry resolver API must raise a clear error when asked to resolve a logical name that does not exist.

### FR-002 detail: Migration completeness

- Migration must cover every agent workspace file (AGENTS.md, TOOLS.md, SOUL.md, USER.md) across all registered OpenClaw agents under `scripts/openclaw/agents/` — currently `felix-admin-capture`, `felix-admin-escalation`, `felix-admin-habits`, `felix-admin-tasker`, plus the `main` and `main-patches` support directories.
- Migration must cover Claude instruction files under `ai-agents/` (e.g., `claude-instructions.md`, `claude-code-instructions.md`).
- Migration must cover CLAUDE.md (all references except the `_private/` boundary).
- Migration must cover every JSON file under `docs/design/architecture/data/` that references vault paths.
- Migration must cover every markdown view under `docs/design/architecture/` that references vault paths.
- Migration must cover every script under `scripts/` that references vault paths.
- Migration must cover every runbook under `docs/runbooks/` that references vault paths.
- A repo-wide search for literal old folder names after migration must return zero hits outside the `_private/` boundary reference and archive/historical files.

### FR-003 detail: Processed-inbox folder

- The folder is created directly at its final target name — it is not renamed into place.
- The folder exists on the physical vault location on office2 and replicates via existing vault sync to any other device.
- The folder has a placeholder file (for example, a `.gitkeep` or an equivalent) so that sync propagates an otherwise-empty directory reliably.
- The registry entry for the processed-inbox folder points at this real path by the end of the mission.

### FR-004 detail: Renumber scheme

The final ordinal sequence for the vault's top-level folders shall be:

| Position | Folder |
|---|---|
| 00 | System |
| 01 | Inbox |
| 02 | Inbox-Processed |
| 03 | Constitution |
| 04 | Growth |
| 05 | Health |
| 06 | Business |
| 07 | Finance |
| 08 | Journal |
| 09 | Resources |

- Renames are executed via the Obsidian UI one folder at a time, with verification of wikilink integrity between each rename.
- The mission may be halted at any rename step without corrupting vault state; each rename is individually committable and verifiable.

### FR-005 detail: Deploy and verification

- The deploy script's existing behavior from mission 024 is extended, not rewritten.
- The deploy is executed in two stages: a **pre-rename deploy** (markers resolve to current folder names — no behavior change) and a **post-rename deploy** (markers resolve to new folder names — new behavior active).
- Post-deploy verification must include: (a) a repo-wide and office2-wide search for any unreplaced `{{VAULT_*}}` marker returning zero hits, and (b) a smoke-test invocation of at least one agent against the new paths confirming end-to-end correctness.
- The `felix-admin-capture` cron is paused before the post-rename deploy and re-enabled only after verification succeeds.

### FR-006 detail: Cross-repository operation

- This requirement is executed by the operator in the `~/second-brain/` git repository, not in the kg-automation repository.
- The operation consists of: adding `_private/` to that repo's `.gitignore`, running an idempotent cached-removal command as safety insurance, committing, and pushing.
- No agent touches the second-brain repo. The operator performs the edit.
- The operation is expected to be a no-op for current content because `_private/` is empty today; the gitignore rule and the cached-removal command are installed pre-emptively so future content is protected by default.
- Completion of this requirement is a manual checkbox in the mission close-out.

### FR-007 detail: Documentation synchronization

- `docs/design/architecture/data/service-inventory.json` and any other JSON under `data/` that references vault paths must be updated to reflect the new folder names and the new processed-inbox folder. Each modified file has its `updated_by` field set to `#152`.
- Every markdown view under `docs/design/architecture/` must be updated so narrative text matches JSON sources.
- Every runbook under `docs/runbooks/` that references vault paths or the `felix-admin-capture` invocation must be updated.
- A new runbook, `docs/runbooks/vault-path-registry-migration.md`, must be created. It documents the full migration procedure (code migration, cron pause, folder creation, rename sequence, registry update, redeploy, verification, cron resume, cross-repo step, doc sync) in enough detail that a future similar migration can be executed from it.
- `docs/INDEX.md` must be updated to include the new migration runbook.
- `docs/design/felix-capability-roadmap.md` must be updated to reflect the registry capability as "full" (or equivalent phrasing) rather than "MVP."
- `docs/design/architecture/change-control.md` must be updated if the change-control protocol itself changes (e.g., if registry-driven deploy becomes a named pattern).
- Documentation edits are first-class deliverables of the mission and flow into the same work packages as the code changes — they are not a post-hoc cleanup.

---

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | **Refactor fidelity — pre-rename deploy** | The pre-rename deploy (FR-005 stage 1) must not change any runtime behavior. Agent outputs and cron outcomes before and after this stage must be indistinguishable. | Draft |
| NFR-002 | **Zero hardcoded residue** | After mission completion, a repo-wide search for any literal old folder name (`00-Inbox`, `01-Constitution`, `02-Growth`, `03-Health`, `04-Business`, `05-Finance`, `06-Journal`, `07-Resources`) returns zero hits in production files, except the single `_private/` boundary reference in CLAUDE.md and any historical archive files under `docs/archive/`. | Draft |
| NFR-003 | **Zero unreplaced markers post-deploy** | After the post-rename deploy (FR-005 stage 2), a search for any unreplaced `{{VAULT_*}}` marker in deployed files (repo and office2) returns zero hits. | Draft |
| NFR-004 | **Migration window duration** | The risky window — from cron pause to cron resume — completes within 90 minutes under nominal conditions. If it exceeds 90 minutes, the operator reassesses rather than continuing blindly. | Draft |
| NFR-005 | **Wikilink integrity** | After all renames complete, every Obsidian wikilink in the vault continues to resolve. Measured by an Obsidian "unresolved links" report showing zero new entries attributable to this mission. | Draft |
| NFR-006 | **Documentation synchronization at merge** | At mission merge time, every architecture JSON data file modified by this mission has its corresponding markdown view updated. No machine-readable-vs-narrative drift is introduced. | Draft |

---

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | The `_private/` privacy boundary (Felix Constitution) is a hard limit: no agent, script, or mission artifact may read, write, or enumerate content under `_private/` during this mission. The cached-removal operation in FR-006 may reference the path name but must not read its contents. | Draft |
| C-002 | The `_private/` path shall not be resolvable through the vault path registry. The registry resolver must raise an error for any attempt to look it up. | Draft |
| C-003 | Mission 026 must merge before mission 027 (issue #149, inbox pre-scan helper) enters spec-kitty. #149 depends on the `{{VAULT_INBOX_PROCESSED}}` marker and the physical `Inbox-Processed` folder defined by this mission. | Draft |
| C-004 | The mission must not upgrade spec-kitty or any other foundational tool mid-flight (per the "no mid-feature upgrades" project directive). If an upgrade is needed, the mission pauses, the upgrade is completed and verified outside the mission, then the mission resumes. | Draft |
| C-005 | Deploy operations are sequential-with-verification, not atomic. The repo is authoritative; office2 is downstream. A failed verification triggers rollback from the repo's known-good state, not a forced retry. | Draft |
| C-006 | The operator drives the folder renames manually through the Obsidian UI. No agent, script, or automation performs the Obsidian folder rename — this keeps wikilink auto-update reliable and failure behavior visible. | Draft |
| C-007 | Every commit in this mission must follow the project's semantic commit convention (`feat:`, `chore:`, `docs:`, etc.). Commits that are pure documentation synchronization append the `[doc-audit]` tag per the project's commit convention. | Draft |

---

## Success Criteria

These are the measurable, technology-agnostic outcomes that indicate the mission is complete. Each is verifiable without reference to implementation detail.

1. **Registry completeness** — Every top-level vault folder in the operator's knowledge vault is reachable by a logical name through the registry, except the private path which is deliberately unreachable.
2. **Reference hygiene** — The operator can find no occurrences of the old hardcoded vault folder names in any production file, outside the single constitutional privacy-boundary reference and historical archive files.
3. **Folder renumbering** — Every top-level vault folder has a unique two-digit ordinal prefix; no two folders share a prefix; the operator can visually scan the vault in Obsidian and see a clean 00–09 sequence.
4. **Processed-inbox folder** — The processed-inbox folder exists in the vault on every synced device and is reachable via its registry marker.
5. **Agent integrity** — Every agent that references vault paths runs end-to-end successfully against the new folder names, verified by at least one smoke-test invocation per agent after the migration.
6. **Cron continuity** — The `felix-admin-capture` cron runs on its normal schedule after migration and processes the inbox correctly; no scheduled run is silently dropped.
7. **Wikilink integrity** — Opening the vault in Obsidian after the migration shows no new unresolved wikilinks attributable to this mission.
8. **Privacy boundary reinforcement** — The operator can confirm that placing a file under `_private/` in the second-brain repo now produces no change to `git status` in that repo; the path is gitignored by default.
9. **Documentation currency** — The operator can open any architecture JSON, markdown view, or runbook under `docs/` and find it consistent with the live system state; no stale path literals remain.
10. **Mission 027 unblocked** — The prerequisites for issue #149 (registry markers + physical folder) are in place; the next mission can start immediately.

---

## Key Entities

| Entity | Description |
|---|---|
| **Vault** | The operator's Obsidian knowledge store, synced across devices via Obsidian Sync. The vault's top-level folders are the subject of this mission. |
| **Vault path registry** | A structured data file mapping logical folder names to physical paths. Consumers resolve paths through this registry rather than hardcoding them. Introduced by mission 024. |
| **Template marker** | A placeholder like `{{VAULT_INBOX}}` that appears in source files and is replaced with a resolved path at deploy time. Not a runtime lookup. |
| **Agent workspace** | The set of files (standing orders, tools, identity, soul) that define an OpenClaw agent's behavior. Deployed to office2 at build time. |
| **Processed-inbox folder** | A new top-level vault folder that will receive inbox items more than 7 days old once the follow-on mission (issue #149) ships. Created empty by this mission. |
| **felix-admin-capture** | The OpenClaw agent that processes new items in the inbox. Runs on cron 4× per day. Paused during the risky window of this mission. |
| **Privacy boundary (`_private/`)** | A constitutionally-protected path under the Growth folder. No agent or script reads, writes, or enumerates it. Strengthened in this mission by adding a second-brain `.gitignore` rule. |
| **Second-brain repository** | A separate git repository from kg-automation, containing the vault's file content. FR-006 touches this repo, not kg-automation. |

---

## Dependencies and Assumptions

### Depended upon by

- **Issue #149** (Inbox pre-scan helper) — blocked until this mission merges. #149 requires the `{{VAULT_INBOX}}` and `{{VAULT_INBOX_PROCESSED}}` markers defined by FR-001 and the physical processed-inbox folder created by FR-003.

### Depends upon

- **Mission 024** (Vault path registry MVP, issue #150) — already complete. This mission extends the registry infrastructure that mission delivered. If the MVP infrastructure is in a broken state, this mission cannot proceed until it is repaired.

### Assumptions (to be validated in planning phase)

1. **Obsidian reliably auto-updates wikilinks on UI-driven folder renames.** Confirmed by the operator during discovery — treated as a validated assumption, not a risk to mitigate.
2. **The vault path registry infrastructure from mission 024 is currently functional on office2.** Planning phase verifies by running the existing deploy script before any mission work begins.
3. **The four registered OpenClaw agents (`felix-admin-capture`, `felix-admin-escalation`, `felix-admin-habits`, `felix-admin-tasker`) plus the `main`/`main-patches` support directories are the full set.** Planning phase confirms against `docs/constitution/AGENT-REGISTRY.md`. A missed agent means a missed migration target. Note: `ai-agents/` contains Claude instruction files (separate from OpenClaw agents) which are also in migration scope.
4. **The inbox frontmatter `status` field is stable.** Not strictly required for this mission (which doesn't read frontmatter) but noted because FR-007's runbook will describe the system state that the follow-on mission #149 will consume.
5. **`_private/` is empty today.** Confirmed by the operator during discovery. The cached-removal command in FR-006 is therefore a no-op but is kept for idempotent insurance.
6. **Obsidian Sync propagates folder renames from office2 to other devices within a reasonable window.** Planning phase confirms the sync cadence; the risky-window NFR-004 threshold (90 minutes) assumes sync is not the critical path.
7. **Spec-kitty merges create merge commits directly to main, not pull requests.** Verification automation must not depend on `pull_request` triggers. (Already a standing project reality.)

---

## Out of Scope

- The inbox pre-scan helper implementation (issue #149). That is a separate mission.
- Migrating non-vault paths (e.g., office2 filesystem paths for scripts, data drives) to the registry. The registry remains vault-only.
- Runtime path resolution for agents. Agents continue to get paths baked into their deployed files at build time.
- Scrubbing `_private/` content from git history. Not needed — `_private/` is empty today, and history scrubbing is a separate, deliberate operation.
- Refactoring or rewriting the mission-024 registry infrastructure beyond what is needed to support the new markers and folder names.
- Implementing monitoring or alerting for deploy failures beyond the existing error-surfacing behavior.
- Changing the `_private/` constitutional boundary in CLAUDE.md. That hardcoded absolute path stays exactly as it is.
- Adding additional paradigms, directives, or charter amendments to the project. The charter addition of the documentation-synchronization principle was made pre-mission by the operator; no further charter changes are part of this mission.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A hardcoded reference is missed during FR-002 migration and happens to still work pre-rename because it matches the current folder name — the defect is invisible until FR-004 rename, at which point the affected consumer breaks. | Medium | Medium | NFR-002 (zero hardcoded residue verification) and a repo-wide grep gate in the deploy script. |
| Deploy sync to office2 fails mid-run, leaving some agent files on new paths and others on old. | Low | High | C-005 (sequential-with-verification); rollback from known-good repo state rather than forced retry. |
| Cron fires during the risky window despite pause, or the pause mechanism itself fails. | Low | Medium | Pause verification step before proceeding to folder rename; the pause mechanism is itself tested as part of the pre-rename phase. |
| FR-006 cross-repo step is forgotten. | Medium | Low (today — `_private/` is empty) | FR-006 is a first-class requirement with its own explicit success criterion and a manual checkbox in mission close-out. |
| Obsidian Sync lags substantially during folder renames, causing office2 to see inconsistent state. | Low | Medium | NFR-004 (90-minute budget); if exceeded, operator pauses to reassess. |
| Spec-kitty or a related tool requires an upgrade mid-mission. | Low | High | C-004 (no mid-feature upgrades); mission pauses if an upgrade need is discovered. |
| Documentation synchronization (FR-007) is treated as an afterthought and missed at merge time. | Medium | Medium | FR-007 is a first-class functional requirement, not a cleanup item. NFR-006 enforces it at merge. New charter Project Directive #5 reinforces this at the governance layer. |

---

## Governance Notes

- **Paradigm:** `c4-incremental-detail-modeling`. This mission's deliverables map well to C4's progressive-zoom framing: the registry operates at the Container level (it's a deployable unit shared by multiple components), the agent migrations operate at the Component level, and the individual file edits operate at the Code level. The migration runbook created in FR-007 should carry a short C4 summary of what changed at each level.
- **Directive:** `DIRECTIVE_034` (Test-First Development). The verification FRs (FR-005, NFR-001, NFR-002, NFR-003, NFR-005, NFR-006) are written as acceptance tests that must pass before the mission is considered complete. The planning phase will expand these into per-stage test-first checkpoints.
- **Charter Project Directive #5** (documentation synchronization is a first-class mission requirement) is satisfied by FR-007.
- **Autonomy level:** Assisted (Level 1) for the Obsidian UI renames and the cross-repo operation; Observed (Level 2) for everything else. The operator is in the loop for every risky action.

---

## Notes for Planning

- Mission 024's deploy script is the starting point — extend, don't rewrite.
- Plan phase should run `spec-kitty charter sync` at the beginning as a sanity check since this mission's charter includes a recent amendment.
- Plan phase should identify the exact five registered agents and cross-reference against `docs/constitution/AGENT-REGISTRY.md` to catch any drift.
- The migration runbook created in FR-007 is itself a reusable asset — plan phase should consider it an output worth extra review effort.
- Cross-repo FR-006 needs its own work package structure because spec-kitty work packages assume edits inside the mission worktree.

---

## Clarifications

No `[NEEDS CLARIFICATION]` markers remain. Three discovery questions were answered during the specify phase:

1. **Obsidian wikilink auto-update on folder rename** → reliable (validated by operator).
2. **FR-006 cross-repo boundary handling** → keep in mission scope as a declared cross-repo operator task; include the idempotent cached-removal command even though it is a no-op today.
3. **Cron safety during the risky window** → pause `felix-admin-capture` before the rename, re-enable after verification.
