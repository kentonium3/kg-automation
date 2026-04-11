# Tasks: Vault Path Registry and Folder Renumber

**Mission:** `026-vault-path-registry-and-folder-renumber`
**Branch:** `main` → `main`
**Date:** 2026-04-11
**Spec:** [spec.md](./spec.md)
**Plan:** [plan.md](./plan.md)
**Source issue:** [kentonium3/kg-automation#152](https://github.com/kentonium3/kg-automation/issues/152)

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Audit repo for files requiring migration (complete target list) | WP01 | | [D] |
| T002 | Extend `scripts/vault/paths.json` with all 10 logical names | WP01 | | [D] |
| T003 | Extend `scripts/vault/targets.json` with all migration target entries | WP01 | | [D] |
| T004 | Create `scripts/deploy/deploy-f026.sh` wrapper | WP01 | [D] |
| T005 | Audit `.kittify/charter/charter.md` for non-`_private/` vault path refs | WP01 | [D] |
| T006 | Verify WP01 acceptance (resolver, dry-run, wrapper help) | WP01 | | [D] |
| T007 | Convert OpenClaw agent workspace files to `.tmpl` sources | WP02 | | [D] |
| T008 | Convert `ai-agents/` Claude instruction files to `.tmpl` | WP02 | [D] |
| T009 | Convert `CLAUDE.md` to `CLAUDE.md.tmpl` (preserve `_private/` boundary) | WP02 | [D] |
| T010 | Audit and convert scripts under `scripts/` referencing vault paths | WP02 | [D] |
| T011 | Run `deploy.py --apply` and verify byte-fidelity of resolved output | WP02 | | [D] |
| T012 | Verify WP02 acceptance (grep zero stale literals, zero unknown markers) | WP02 | | [D] |
| T013 | Commit WP02 changes to mission branch | WP02 | | [D] |
| T014 | Audit `docs/` for vault path references, produce update list | WP03 | | [D] |
| T015 | Update architecture JSON data files (`service-inventory.json`, `data-flows.json`) | WP03 | | [D] |
| T016 | Regenerate markdown views in `docs/design/architecture/` to match JSON | WP03 | | [D] |
| T017 | Update runbooks under `docs/runbooks/` referencing vault paths | WP03 | [D] |
| T018 | Create new runbook `docs/runbooks/vault-path-registry-migration.md` with C4 summary | WP03 | [D] |
| T019 | Update `docs/INDEX.md` with new runbook entry | WP03 | [D] |
| T020 | Update `docs/design/felix-capability-roadmap.md` (registry MVP→full) | WP03 | [D] |
| T021 | Verify WP03 acceptance (`validate_docs.py`, grep zero hits in docs) | WP03 | | [D] |
| T022 | Capture pre-deploy baseline (agent outputs, resolved file hashes) | WP04 | |
| T023 | Run `deploy-f026.sh --apply --mode pre-rename` | WP04 | |
| T024 | Verify resolved files byte-match pre-deploy snapshots | WP04 | |
| T025 | Re-invoke `felix-admin-capture` and `felix-admin-tasker`, diff vs baseline (NFR-001) | WP04 | |
| T026 | Record WP04 fidelity checkpoint + operator authorization gate for WP05 | WP04 | |
| T027 | Tier 2 pre-flight (Restic backup verification) | WP05 | |
| T028 | Pause `felix-admin-capture` cron on office2 + verify paused | WP05 | |
| T029 | Create `02-Inbox-Processed/` folder on disk | WP05 | |
| T030 | Rename vault folders via Obsidian UI (one-at-a-time with inter-rename wikilink verification) | WP05 | |
| T031 | Update `paths.json` and `CLAUDE.md` `_private/` boundary line to new folder names | WP05 | |
| T032 | Run `deploy-f026.sh --apply --mode post-rename` (deploy + greps + smoke tests + wikilink + cron resume) | WP05 | |
| T033 | Record WP05 runlog + operator authorization gate for WP06 | WP05 | |
| T034 | Execute cross-repo operation in `~/second-brain/` (`.gitignore`, `git rm --cached`, commit, push) | WP06 | |
| T035 | Verify `_private/` gitignore effectiveness via `git check-ignore` | WP06 | |
| T036 | Final mission verification — walk through all 10 Success Criteria from `spec.md` | WP06 | |
| T037 | Close GitHub issue #152 with merge commit reference | WP06 | |

**Total:** 37 subtasks across 6 work packages.

**Parallel marker note:** The `[P]` marker in the index table is a reference indicator only — it signals which subtasks could theoretically run concurrently if this mission supported multi-lane execution. In practice, mission 026 is executed as a single lane by a single operator because the dependency chain between WPs is tight and the risky-window gating in WP05 requires human coordination.

---

## Work Packages

### WP01: Registry Extension and Deploy Wrapper

**Goal:** Extend `scripts/vault/paths.json` with all 10 logical vault names (pointing at *current* folder names — no renames yet), populate `scripts/vault/targets.json` with every file that WP02 will migrate, create the `scripts/deploy/deploy-f026.sh` wrapper script per the deploy-wrapper contract, and audit `.kittify/charter/charter.md` for any non-`_private/` vault path references that need operator-driven handling.

**Priority:** P0 — foundation for all subsequent WPs.

**Dependencies:** None (first WP in sequence).

**Prompt file:** [WP01-registry-extension-and-deploy-wrapper.md](tasks/WP01-registry-extension-and-deploy-wrapper.md)

**Subtasks:**
- [x] T001: Audit repo for files requiring migration (complete target list)
- [x] T002: Extend `scripts/vault/paths.json` with all 10 logical names
- [x] T003: Extend `scripts/vault/targets.json` with all migration target entries
- [x] T004: Create `scripts/deploy/deploy-f026.sh` wrapper
- [x] T005: Audit `.kittify/charter/charter.md` for non-`_private/` vault path refs
- [x] T006: Verify WP01 acceptance (resolver, dry-run, wrapper help)

**Estimated prompt size:** ~420 lines

---

### WP02: Code Migration to Template Markers

**Goal:** Convert every in-scope production file to a `.tmpl` source file with `{{VAULT_*}}` markers, run `scripts/vault/deploy.py --apply` to produce resolved output files, and verify the resolved output is byte-identical to pre-migration content (except for expected marker substitutions). This is the pure refactor — registry still points at current folder names, so runtime behavior should be unchanged.

**Priority:** P0 — enables WP03 and WP04.

**Dependencies:** WP01 (uses the populated `paths.json` and `targets.json`).

**Prompt file:** [WP02-code-migration-to-template-markers.md](tasks/WP02-code-migration-to-template-markers.md)

**Subtasks:**
- [x] T007: Convert OpenClaw agent workspace files to `.tmpl` sources
- [x] T008: Convert `ai-agents/` Claude instruction files to `.tmpl`
- [x] T009: Convert `CLAUDE.md` to `CLAUDE.md.tmpl` (preserve `_private/` boundary)
- [x] T010: Audit and convert scripts under `scripts/` referencing vault paths
- [x] T011: Run `deploy.py --apply` and verify byte-fidelity of resolved output
- [x] T012: Verify WP02 acceptance (grep zero stale literals, zero unknown markers)
- [x] T013: Commit WP02 changes to mission branch

**Estimated prompt size:** ~480 lines

---

### WP03: Documentation Synchronization

**Goal:** Update every documentation artifact affected by the vault path registry extension and folder renumber — architecture JSON data files, their markdown views, runbooks under `docs/runbooks/`, `docs/INDEX.md`, and `docs/design/felix-capability-roadmap.md`. Create the new runbook `docs/runbooks/vault-path-registry-migration.md` with a C4-style summary per the charter paradigm. This WP satisfies FR-007 and charter Project Directive #5 (documentation sync is a first-class mission requirement).

**Priority:** P1 — must complete before mission merge but does not block WP04/WP05 runtime verification.

**Dependencies:** WP02 (doc sync references the new markers and migration pattern).

**Prompt file:** [WP03-documentation-synchronization.md](tasks/WP03-documentation-synchronization.md)

**Subtasks:**
- [x] T014: Audit `docs/` for vault path references, produce update list
- [x] T015: Update architecture JSON data files with new folder names and `updated_by: #152`
- [x] T016: Regenerate markdown views in `docs/design/architecture/` to match JSON
- [x] T017: Update runbooks under `docs/runbooks/` referencing vault paths
- [x] T018: Create new runbook `docs/runbooks/vault-path-registry-migration.md` with C4 summary
- [x] T019: Update `docs/INDEX.md` with new runbook entry
- [x] T020: Update `docs/design/felix-capability-roadmap.md` (registry MVP→full)
- [x] T021: Verify WP03 acceptance (`validate_docs.py`, grep zero hits in docs)

**Estimated prompt size:** ~470 lines

---

### WP04: Pre-Rename Deploy and Refactor-Fidelity Checkpoint

**Goal:** Prove that WP01–WP03 is a pure refactor — zero runtime behavior change. This is the explicit DIRECTIVE_034 test-first checkpoint. Capture agent output baselines, run the pre-rename deploy via `deploy-f026.sh --apply --mode pre-rename`, then re-invoke `felix-admin-capture` and `felix-admin-tasker` and diff against the baselines. Zero semantic differences required. This WP exists specifically to gate the risky WP05 entry.

**Priority:** P0 — required gate before the risky window opens.

**Dependencies:** WP02, WP03 (all template markers and doc sync must be complete and deployed for the fidelity check to be meaningful).

**Prompt file:** [WP04-pre-rename-deploy-and-fidelity-checkpoint.md](tasks/WP04-pre-rename-deploy-and-fidelity-checkpoint.md)

**Subtasks:**
- [ ] T022: Capture pre-deploy baseline (agent outputs, resolved file hashes)
- [ ] T023: Run `deploy-f026.sh --apply --mode pre-rename`
- [ ] T024: Verify resolved files byte-match pre-deploy snapshots
- [ ] T025: Re-invoke `felix-admin-capture` and `felix-admin-tasker`, diff vs baseline (NFR-001)
- [ ] T026: Record WP04 fidelity checkpoint + operator authorization gate for WP05

**Estimated prompt size:** ~320 lines

---

### WP05: Folder Rename and Post-Rename Deploy

**Goal:** Execute the risky window — the only WP that changes runtime state in an operator-visible way. Verify Tier 2 backup, pause the cron, create `02-Inbox-Processed/`, rename vault folders via Obsidian UI, update the registry, run the post-rename deploy (which internally does verification and smoke tests), and re-enable the cron. 90-minute total duration budget per NFR-004. **This WP has an explicit operator review gate at entry and at exit.**

**Priority:** P0 — the risky window; the mission's heart.

**Dependencies:** WP04 (refactor fidelity must be proven before changing runtime state).

**Prompt file:** [WP05-folder-rename-and-post-rename-deploy.md](tasks/WP05-folder-rename-and-post-rename-deploy.md)

**Subtasks:**
- [ ] T027: Tier 2 pre-flight (Restic backup verification)
- [ ] T028: Pause `felix-admin-capture` cron on office2 + verify paused
- [ ] T029: Create `02-Inbox-Processed/` folder on disk
- [ ] T030: Rename vault folders via Obsidian UI with inter-rename wikilink verification
- [ ] T031: Update `paths.json` and `CLAUDE.md` `_private/` boundary line
- [ ] T032: Run `deploy-f026.sh --apply --mode post-rename`
- [ ] T033: Record WP05 runlog + operator authorization gate for WP06

**Estimated prompt size:** ~450 lines

---

### WP06: Cross-Repo Privacy Boundary and Mission Close-Out

**Goal:** Complete the cross-repo privacy boundary reinforcement by adding `_private/` to `~/second-brain/.gitignore`, run the idempotent `git rm --cached` as future-proofing insurance, commit and push in the second-brain repo. Then perform final mission verification against all 10 Success Criteria from `spec.md` and close GitHub issue #152. **This is an operator-only WP — no agent touches the second-brain repo.**

**Priority:** P1 — mission close-out; blocks merge.

**Dependencies:** WP05 (final verification happens after the risky window closes).

**Prompt file:** [WP06-cross-repo-and-mission-closeout.md](tasks/WP06-cross-repo-and-mission-closeout.md)

**Subtasks:**
- [ ] T034: Execute cross-repo operation in `~/second-brain/`
- [ ] T035: Verify `_private/` gitignore effectiveness via `git check-ignore`
- [ ] T036: Final mission verification — walk through all 10 Success Criteria
- [ ] T037: Close GitHub issue #152 with merge commit reference

**Estimated prompt size:** ~280 lines

---

## Dependency Graph

```
WP01 (registry + wrapper)
  ↓
WP02 (code migration)
  ↓
WP03 (doc sync) ────┐
  ↓                 │
WP04 (pre-rename deploy + fidelity checkpoint) ← OPERATOR GATE
  ↓
WP05 (rename + post-rename deploy) ← OPERATOR GATE (enter) + OPERATOR GATE (exit)
  ↓
WP06 (cross-repo + close-out)
```

Sequential execution. WP03 technically could run in parallel with WP04 preparation (WP03 has no runtime side effects), but the single-operator nature of this mission means it's executed sequentially in practice.

## Parallel Opportunities

Within each WP, several subtasks are marked `[P]` (parallel-safe per file/concern) but the single-lane execution model means the operator completes them in file-convenient order rather than true parallelism.

Cross-WP parallelism is limited by the strict dependency chain — every WP gates on the previous one's verification.

## MVP Scope

**There is no sub-MVP for this mission.** It is an atomic infrastructure refactor — partial completion would leave the system in a broken state. All six WPs must complete to declare the mission done.

The closest thing to an "MVP" is the completion of WP04 — at that point, the code migration is done and proven to be a pure refactor. If the risky window (WP05) cannot be executed for any reason (e.g., Obsidian Sync is in a bad state, Restic backup unavailable), the mission can pause at the end of WP04 and resume WP05 later without losing work. WP01–WP04 are all non-destructive and independently committable.

## Size Distribution Summary

| WP | Subtasks | Est. Lines |
|---|---|---|
| WP01 | 6 | ~420 |
| WP02 | 7 | ~480 |
| WP03 | 8 | ~470 |
| WP04 | 5 | ~320 |
| WP05 | 7 | ~450 |
| WP06 | 4 | ~280 |
| **Total** | **37** | **~2,420** |

**Validation:** All WPs within the ideal 200–500 line range. No WP exceeds the 700-line maximum. No WP has more than 10 subtasks. ✅

## Next Commands

1. `/spec-kitty.implement` — begin WP01 execution (or per-agent implementation loop)
2. After all WPs complete: `/spec-kitty.review`
3. After review: `/spec-kitty.merge`
