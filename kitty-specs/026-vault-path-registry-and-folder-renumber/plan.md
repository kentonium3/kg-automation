# Implementation Plan: Vault Path Registry and Folder Renumber

**Mission:** `026-vault-path-registry-and-folder-renumber`
**Target branch:** `main`
**Current branch:** `main`
**Date:** 2026-04-11
**Spec:** [spec.md](./spec.md)
**Source issue:** [kentonium3/kg-automation#152](https://github.com/kentonium3/kg-automation/issues/152)

## Summary

Extend the vault path registry from mission 024 (single path: inbox) to cover every top-level vault folder. Create a new `02-Inbox-Processed/` folder. Renumber existing folders to eliminate the `00-` collision and establish a clean 00–09 ordinal sequence. Migrate every hardcoded vault-path reference across OpenClaw agents, Claude instructions, CLAUDE.md, architecture JSON/markdown, runbooks, and scripts to `{{VAULT_*}}` template markers resolved by `scripts/vault/deploy.py` at build time. Add `_private/` to the second-brain repo's `.gitignore`. Update all architecture documentation to reflect the new state as a first-class deliverable (per charter Project Directive #5). Execute the migration in 6 phase-aligned work packages with an explicit test-first fidelity checkpoint (WP04) before the risky rename window (WP05) opens.

## Technical Context

| Aspect | Value |
|---|---|
| **Language / runtime** | Python 3.11+ (extends existing `scripts/vault/deploy.py`, `scripts/vault/resolver.py`); Bash (new `scripts/deploy/deploy-f026.sh` wrapper) |
| **Primary dependencies** | Existing mission-024 infrastructure: `scripts/vault/paths.json`, `scripts/vault/targets.json`, `scripts/vault/resolver.py`, `scripts/vault/paths.sh`, `scripts/vault/deploy.py` |
| **Storage** | JSON registry + manifest, markdown `.tmpl` templates, resolved markdown deliverables |
| **Testing** | Grep-based verification (zero stale literals, zero unreplaced markers), smoke-test invocations of `felix-admin-capture` and `felix-admin-tasker`, Obsidian wikilink integrity check, pre-vs-post-migration behavioral equivalence check for WP04 (DIRECTIVE_034 test-first checkpoint) |
| **Target platform** | office2 (Ubuntu 24.04 LTS); vault is synced via Obsidian Sync to office2 from the operator's Mac |
| **Project type** | Infrastructure refactor + operational reconfiguration — no new user-facing features |
| **Performance goals** | NFR-004: risky-window (cron pause → cron resume) completes within 90 minutes under nominal conditions |
| **Constraints** | NFR-001 (refactor fidelity, zero behavior change pre-rename); NFR-002 (zero stale literals post-migration); NFR-003 (zero unreplaced markers post-deploy); NFR-005 (zero new unresolved wikilinks); NFR-006 (doc sync enforced at merge) |
| **Scale / scope** | 4 OpenClaw agents (`felix-admin-capture`, `felix-admin-escalation`, `felix-admin-habits`, `felix-admin-tasker`) + `main/` + `main-patches/` support; 2 Claude instruction files in `ai-agents/`; 1 CLAUDE.md; ≥7 runbooks under `docs/runbooks/`; multiple architecture docs and JSON files; 10 vault folders total |

## Charter Check

**Governance posture loaded from `.kittify/charter/charter.md`:**
- Template set: `software-dev-default`
- Paradigm: `c4-incremental-detail-modeling`
- Directive: `DIRECTIVE_034` (Test-First Development)

### Paradigm alignment (c4-incremental-detail-modeling)

This mission's deliverables map cleanly to the C4 zoom levels:

| C4 level | Mission artifact |
|---|---|
| **Level 1: System Context** | No change — the system boundary stays the same. Felix still composes the same services. |
| **Level 2: Containers** | `scripts/vault/` remains a container (deployable shared infrastructure). `paths.json` and `targets.json` grow to cover all vault paths — this is a capacity expansion of an existing container, not a new one. |
| **Level 3: Components** | New component: the `scripts/deploy/deploy-f026.sh` wrapper (a named, versioned deploy orchestrator for this mission). Existing components (agent workspaces) are updated to reference paths via marker instead of literal — same component interface, new internal representation. |
| **Level 4: Code** | Every `.tmpl` file is a Level 4 artifact. The deploy script's marker-substitution logic is Level 4. These are the most detailed level and are exercised by the verification checks in WP04 and WP05. |

The mission runbook created in FR-7 (`docs/runbooks/vault-path-registry-migration.md`) will carry a short C4 summary at each zoom level so future similar migrations have a progressive-detail reference.

**No paradigm violations.** ✅

### Directive alignment (DIRECTIVE_034 — Test-First Development)

Test-first for an infrastructure refactor means writing the *verification checks* before the work they verify, not traditional unit-tests-before-code. For this mission:

- **Before WP01 (registry extension):** Write the registry completeness check — "every logical name the mission will introduce is resolvable via `scripts/vault/resolver.py` after WP01 closes."
- **Before WP02 (code migration):** Write the stale-literal check — "repo-wide grep for `00-Inbox`, `01-Constitution`, etc., in production files returns zero hits (excluding `_private/` boundary and archive) after WP02 closes."
- **Before WP04 (pre-rename deploy):** Write the refactor-fidelity check — "post-deploy output of `felix-admin-capture` and `felix-admin-tasker` is byte-for-byte identical to pre-deploy output when invoked against the same inbox state." This is the explicit DIRECTIVE_034 checkpoint; WP04 exists specifically to prove this test passes.
- **Before WP05 (rename + post-rename deploy):** Write the unreplaced-marker check, the wikilink integrity check, and the smoke-test acceptance criteria for `felix-admin-capture` and `felix-admin-tasker`.
- **Before WP06 (cross-repo FR-6):** Write the acceptance test — "after the second-brain edit, `git status` in `~/second-brain/` shows no `_private/` content as modified/untracked when a file is placed there."

Every verification is defined before the corresponding work package enters the in-progress state. The verifications become the WP exit criteria.

**No directive violations.** ✅

### Project Directive alignment

| Directive | How this mission complies |
|---|---|
| #1 — Apply doctrine directive `DIRECTIVE_034` | Covered above (test-first as verification-first) |
| #2 — `_private/` constitutional boundary | C-001, C-002 enforce. FR-006 strengthens with gitignore. `_private/` deliberately unreachable through registry. |
| #3 — Keep documentation synchronized | FR-007 is first-class, NFR-006 enforces at merge |
| #4 — Documentation standards (JSON authoritative) | All JSON data files in `docs/design/architecture/data/` updated in WP03; markdown views regenerated to match |
| #5 — Every mission includes doc-sync requirement | FR-007 satisfies — this is the first mission applying the new directive |

**No project directive violations.** ✅

### Charter Check: PASS — proceed to Phase 0.

## Project Structure

### Mission artifact layout

```
kitty-specs/026-vault-path-registry-and-folder-renumber/
├── spec.md                               # WHAT and WHY (already complete)
├── meta.json                             # Mission identity
├── plan.md                               # THIS FILE — HOW at a planning level
├── research.md                           # Phase 0 — audit findings and decision records
├── data-model.md                         # Phase 1 — entities and schemas
├── contracts/                            # Phase 1 — interface contracts
│   ├── registry-schema.md                # paths.json contract
│   ├── targets-schema.md                 # targets.json contract
│   ├── deploy-wrapper-contract.md        # deploy-f026.sh inputs/outputs/side effects
│   └── verification-contract.md          # Acceptance tests for each WP
├── quickstart.md                         # Phase 1 — condensed operator runbook
├── checklists/
│   └── requirements.md                   # Spec quality checklist (already complete)
└── tasks/                                # Phase 2 — created by /spec-kitty.tasks, NOT by plan
```

### Repository paths touched by this mission

```
scripts/vault/
├── paths.json                            # WP01 — extend with 10 logical names
├── targets.json                          # WP01 — extend with all .tmpl → resolved mappings
├── resolver.py                           # No change (already generic)
├── paths.sh                              # Regenerated by deploy.py (already generic)
├── deploy.py                             # WP01 — may need minor extension if targets grow enough
│                                         #        to require batching; probably no changes
└── README.md                             # WP03 — update examples and path list

scripts/openclaw/agents/                  # WP02 — convert all to .tmpl with markers
├── felix-admin-capture/                  #   AGENTS.md.tmpl already exists (mission 024)
│   ├── AGENTS.md.tmpl                    #   update/extend with new markers
│   ├── TOOLS.md  → TOOLS.md.tmpl         #   create
│   ├── SOUL.md                           #   (may not need migration — check in WP02)
│   └── USER.md                           #   (may not need migration — check in WP02)
├── felix-admin-escalation/
│   ├── AGENTS.md  → AGENTS.md.tmpl
│   ├── TOOLS.md   → TOOLS.md.tmpl
│   └── SOUL.md    (as above)
├── felix-admin-habits/
│   └── AGENTS.md  → AGENTS.md.tmpl
├── felix-admin-tasker/
│   ├── AGENTS.md  → AGENTS.md.tmpl
│   ├── TOOLS.md   → TOOLS.md.tmpl
│   ├── SOUL.md
│   └── USER.md
├── main/
│   ├── SOUL.md    (migrate if path refs present)
│   └── USER.md
└── main-patches/
    └── inbox-delegation.md               # grep hit — migrate

ai-agents/                                # WP02
├── claude-instructions.md                # convert to .tmpl
└── claude-code-instructions.md           # convert to .tmpl

CLAUDE.md                                 # WP02 — migrate all except _private/ boundary line
                                          #        (CLAUDE.md is itself a .tmpl source)

docs/
├── constitution/FELIX-CONSTITUTION.md    # WP03 — update path references
├── design/
│   ├── architecture/
│   │   ├── data/
│   │   │   ├── service-inventory.json    # WP03 — update folder names, set updated_by: #152
│   │   │   ├── data-flows.json           # WP03 — check and update
│   │   │   └── (other JSON files)        # WP03 — audit and update as needed
│   │   ├── service-inventory.md          # WP03 — regenerate narrative from JSON
│   │   ├── data-flows.md                 # WP03 — same
│   │   ├── security-posture.md           # WP03 — check and update
│   │   └── glossary.md                   # WP03 — check and update
│   └── felix-capability-roadmap.md       # WP03 — mark vault-path-registry capability "full"
├── runbooks/
│   ├── inbox-ops.md                      # WP03 — update path references
│   ├── habits-ops.md                     # WP03 — same
│   ├── goals-ops.md                      # WP03 — same
│   ├── escalation-ops.md                 # WP03 — same
│   ├── obsidian-sync-ops.md              # WP03 — same
│   ├── openclaw-agent-setup.md           # WP03 — same
│   ├── felix-governance.md               # WP03 — same
│   └── vault-path-registry-migration.md  # WP03 — NEW runbook documenting this migration
└── INDEX.md                              # WP03 — include the new runbook

scripts/deploy/
└── deploy-f026.sh                        # WP01 — NEW thin wrapper; see contracts/deploy-wrapper-contract.md

.kittify/charter/                         # NOT directly edited — see research.md finding on charter file handling
├── charter.md                            # If contains non-_private/ vault paths, edit via operator
│                                         # then run `spec-kitty charter sync`
├── directives.yaml                       # Regenerated by sync
└── library/user-project-profile.md       # Regenerated by sync
```

**Structure decision:** This is a single-project infrastructure refactor. No new top-level directories are introduced. All work happens inside existing directories (`scripts/`, `ai-agents/`, `docs/`, `kitty-specs/`). The one new file in a new location is `scripts/deploy/deploy-f026.sh`, which joins the existing `deploy-f013.sh` and `deploy-f014.sh` in that directory per the charter rule.

## Work Package Strategy

Six phase-aligned work packages. Execution is primarily sequential — true parallelism is limited because most steps gate on the previous one's verification. Each WP has a clear entry condition, exit condition, and rollback point.

### WP01 — Registry extension and deploy wrapper

**Goal:** Extend `paths.json` and `targets.json` to cover every vault path and every file requiring migration. Create `scripts/deploy/deploy-f026.sh` wrapper.

**Inputs:**
- Current `scripts/vault/paths.json` (one entry: `inbox`)
- Current `scripts/vault/targets.json` (one entry: felix-admin-capture `AGENTS.md.tmpl`)
- Complete file-migration-target list from the repo audit (see research.md)

**Deliverables:**
- `paths.json` contains all 10 logical names (`system`, `inbox`, `inbox_processed`, `constitution`, `growth`, `health`, `business`, `finance`, `journal`, `resources`), each pointing at the current folder name at mission start. `inbox_processed` points at the soon-to-be-created folder path (the registry entry exists even though the physical folder is created in WP05).
- `targets.json` contains one entry per file to be migrated across all 4 agents, `ai-agents/`, `CLAUDE.md`, and any scripts.
- `scripts/deploy/deploy-f026.sh` exists and is executable.

**Verification (test-first, define before implementing):**
- `python3 scripts/vault/resolver.py inbox_processed` returns a path without error
- `python3 scripts/vault/resolver.py _private` raises an error
- `source scripts/vault/paths.sh && echo "$VAULT_INBOX_PROCESSED"` prints a non-empty path
- `python3 scripts/vault/deploy.py` (dry-run) reports planned substitutions for every new target entry
- `bash scripts/deploy/deploy-f026.sh --help` prints usage without error

**Exit gate:** All verification checks pass. Registry is complete and consistent. No migration yet — files are still in their pre-WP01 state.

**Rollback:** `git revert` the WP01 commit. No runtime state touched.

### WP02 — Code migration to template markers

**Goal:** Convert every in-scope file to a `.tmpl` source with `{{VAULT_*}}` markers. Resolved output is deployed via `deploy.py` and is byte-identical to the pre-migration file content.

**Inputs:**
- WP01 complete (registry and targets populated)
- Audit list of files containing hardcoded vault-path literals

**Deliverables:**
- Every OpenClaw agent file containing vault path literals is converted to a `.tmpl` source.
- Every Claude instruction file in `ai-agents/` is converted to a `.tmpl` source.
- `CLAUDE.md.tmpl` exists and contains markers for everything except the `_private/` boundary line (which remains hardcoded).
- Any script under `scripts/` containing vault path literals is converted or modified to use the resolver API.
- `scripts/vault/deploy.py --apply` resolves all markers, producing output files byte-identical (or formatting-equivalent) to their pre-migration content.

**Verification (test-first):**
- Repo-wide `grep -r "00-Inbox" scripts/ ai-agents/ CLAUDE.md` returns zero hits after `deploy.py --apply` (excluding `.tmpl` sources which may contain old names in comments, and archive files).
- For each `.tmpl` → resolved file pair, `diff` against a pre-migration backup shows only expected differences.
- `python3 scripts/vault/deploy.py` dry-run reports zero unresolved markers.

**Exit gate:** All verifications pass. Deployed files match pre-migration content. Still no behavior change — registry still points at current folder names.

**Rollback:** `git revert` WP02 commit. No runtime state touched.

### WP03 — Documentation synchronization

**Goal:** Update all documentation artifacts (architecture JSON, markdown views, runbooks, INDEX, capability roadmap) to reflect the new folder names and the expanded registry. Create the new migration runbook. Flows in time alongside WP02 but tracked separately to prevent doc sync from being skipped at merge (per Project Directive #5).

**Inputs:**
- WP01 complete
- WP02 in progress or complete
- Audit list of doc files referencing vault paths

**Deliverables:**
- `docs/design/architecture/data/service-inventory.json` and other in-scope JSON files updated with new folder names, `updated_by: #152`.
- Markdown views under `docs/design/architecture/` regenerated from JSON to match.
- All runbooks under `docs/runbooks/` updated to reference new folder names (or leave as historical if the runbook documents legacy state).
- New runbook `docs/runbooks/vault-path-registry-migration.md` documents the 10-step migration procedure in full — written as a reusable playbook for future similar migrations. Includes a C4 summary per charter paradigm.
- `docs/INDEX.md` includes the new migration runbook.
- `docs/design/felix-capability-roadmap.md` updated to reflect the vault-path-registry capability as "full" rather than "MVP".

**Verification (test-first):**
- Repo-wide `grep -r "00-Inbox" docs/` returns zero hits (excluding archive and historical specs, and `docs/func-spec/` which is frozen history).
- Every JSON file in `docs/design/architecture/data/` modified by this mission has its `updated_by` field set.
- `docs/INDEX.md` includes an entry for the new runbook.
- Markdown view line count for each updated architecture doc is within ±10% of the pre-update version (sanity check against truncation).

**Exit gate:** All verifications pass. Documentation is consistent with the (still pre-rename) registry state.

**Rollback:** `git revert` WP03 commit. No runtime state touched.

### WP04 — Pre-rename deploy + refactor-fidelity checkpoint

**Goal:** Prove the WP01–WP03 work has zero runtime effect. This is the explicit DIRECTIVE_034 test-first checkpoint — the test ("no behavior change") is defined in the spec (NFR-001) and this WP exists to prove it.

**Inputs:**
- WP01, WP02, WP03 all complete
- Registry points at current folder names (no physical folder changes yet)
- `felix-admin-capture` and `felix-admin-tasker` baseline outputs captured before WP04 begins (from a pre-WP04 invocation against the current inbox state)

**Deliverables:**
- `scripts/vault/deploy.py --apply` executed successfully
- Resolved files in repo and on office2 match pre-migration files byte-for-byte (or within whitespace tolerance)
- `felix-admin-capture` produces output indistinguishable from the WP04-entry baseline when invoked against the same inbox state
- `felix-admin-tasker` produces output indistinguishable from the WP04-entry baseline under the same input condition

**Verification (test-first):**
- Pre-deploy baseline capture: invoke `felix-admin-capture` and `felix-admin-tasker` once each, record outputs (logs, file state, any vault writes)
- Post-deploy re-invocation: same invocation, same input state, outputs compared via `diff`
- Zero differences attributable to the migration itself (ignore timestamps and any other inherently-nondeterministic fields)

**Exit gate:** Refactor fidelity confirmed. Byte-equivalent (or semantically-equivalent) behavior. This is the proof that WP01–WP03 were a pure refactor.

**Rollback:** If behavior differs from baseline, `git revert` WP01–WP04 commits in reverse order, re-run `deploy.py --apply` to restore the pre-mission state on office2. Investigate root cause before proceeding.

**CRITICAL:** Operator review gate required before exit. WP04 exit authorizes WP05 entry, which opens the risky window.

### WP05 — Folder rename + post-rename deploy + smoke tests

**Goal:** Execute the risky window — physical folder creation, vault folder renames, registry update, redeploy, verification, smoke tests, cron resume.

**Inputs:**
- WP04 complete (refactor fidelity confirmed)
- Operator has authorized WP05 entry
- Tier 2 pre-flight: Restic backup verified (≤ 24 hours old) per `docs/runbooks/governance/pre-flight-checklist.md`
- `felix-admin-capture` cron currently enabled and running on its normal schedule

**Deliverables (executed in order):**
1. Tier 2 backup verification confirmed (or new backup triggered)
2. `felix-admin-capture` cron paused on office2
3. `02-Inbox-Processed/` folder created on disk at its final target name, with placeholder file for sync reliability
4. Vault folders renamed via Obsidian UI one at a time, with wikilink integrity verified between each rename
5. `scripts/vault/paths.json` updated to new folder names
6. `scripts/deploy/deploy-f026.sh --apply` executed — internally calls `scripts/vault/deploy.py --apply` plus performs verification orchestration
7. Repo-wide grep for stale literals returns zero hits (NFR-002)
8. Deployed files grep for unreplaced markers returns zero hits (NFR-003)
9. `felix-admin-capture` smoke test — full invocation, end-to-end, against the new inbox path
10. `felix-admin-tasker` smoke test — full invocation, end-to-end
11. Obsidian wikilink integrity verified — no new unresolved links (NFR-005)
12. `felix-admin-capture` cron re-enabled on office2
13. Verify the cron fires correctly on its next scheduled tick (or trigger a manual run-once and observe)

**Verification (test-first — every check in the list above is itself a test):**
- Each step has a pass/fail outcome; any failure halts the WP immediately
- Total risky-window duration (step 2 → step 12) must complete within 90 minutes (NFR-004) or operator reassesses

**Exit gate:** All 13 steps complete successfully. System is running on the new paths with the cron re-enabled and verified.

**Rollback:** The most complex rollback in the mission.
- If failure at steps 3–5 (pre-redeploy): Obsidian UI rename folders back to original names, revert `paths.json`, re-enable cron. No office2 state was changed yet.
- If failure at step 6 (redeploy): re-run `deploy.py --apply` with `paths.json` reverted to old folder names; this restores old-state agent files on office2. Then Obsidian UI rename folders back.
- If failure at steps 7–11 (verification): same as step 6 rollback.
- If failure is catastrophic and manual recovery is not viable: fall back to Restic restore of the vault to the pre-migration state per `docs/runbooks/governance/post-change-verification.md` Tier 2 fallback.
- After any rollback, operator confirms system is back to pre-mission state, re-enables cron, and declares mission halted. Rollback itself is a reviewable event — do not retry automatically.

**CRITICAL:** Operator review gate required before exit.

### WP06 — Cross-repo FR-6 + mission close-out

**Goal:** Complete the cross-repository privacy boundary reinforcement and final mission verification. Operator-only — no agent touches this WP.

**Inputs:**
- WP05 complete, all success criteria verified
- Operator has access to the `~/second-brain/` repository

**Deliverables:**
- Detailed operator runbook embedded in the WP description — step-by-step commands, verification checks, rollback steps
- `_private/` added to `~/second-brain/.gitignore`
- `git rm --cached -r _private/` executed in second-brain (no-op today — `_private/` is empty)
- Second-brain repo committed and pushed
- Final mission verification: every success criterion from spec.md § Success Criteria checked off by the operator
- Final mission verification: every FR confirmed satisfied

**Verification (test-first):**
- After the edit, `git check-ignore -v <test-path-under-_private>` in `~/second-brain/` confirms the ignore rule matches
- After the edit, placing a test file under `~/second-brain/_private/` produces no change to `git status` output in that repo
- All 10 success criteria from spec.md are explicitly confirmed by the operator (checklist embedded in the WP)

**Exit gate:** Operator confirms completion via the WP checklist.

**Rollback:** Trivial — `git revert` in second-brain repo.

## Risk & Rollback Summary

See spec.md § Risk Register for the full register. Mission-level rollback posture:

- **WP01–WP04:** git revert is sufficient. Runtime state unchanged.
- **WP05:** Multi-step rollback per the WP05 rollback section. Restic is the last-resort fallback for vault state corruption beyond manual recovery.
- **WP06:** git revert in second-brain repo.
- **Any WP:** Operator may halt the mission at any point between WPs. Halting during a WP requires completing or explicitly rolling back that WP first.

## Complexity Tracking

No Charter Check violations. This section is intentionally empty per the IMPL_PLAN template.

## Phase 0 and Phase 1 artifacts

Phase 0 (research) is documented in `research.md`. Phase 1 (design) is documented in `data-model.md`, `contracts/`, and `quickstart.md`. See those files for the findings and decisions behind this plan.

## Branch contract (restated)

- **Current branch:** `main`
- **Planning/base branch:** `main`
- **Merge target:** `main`
- **Matches target:** ✅ yes

All mission work happens in worktrees under `.worktrees/026-vault-path-registry-and-folder-renumber-lane-*` (created later by `/spec-kitty.implement`, not by this plan command). Merges land on `main`.

---

**Next command:** `/spec-kitty.tasks` — generates work package files under `kitty-specs/026-vault-path-registry-and-folder-renumber/tasks/` based on this plan. Must be invoked explicitly by the operator.
