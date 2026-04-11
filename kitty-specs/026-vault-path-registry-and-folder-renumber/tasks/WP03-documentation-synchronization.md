---
work_package_id: WP03
title: Documentation Synchronization
dependencies:
- WP02
requirement_refs:
- C-007
- FR-007
- NFR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T014
- T015
- T016
- T017
- T018
- T019
- T020
- T021
agent: "claude:opus-4-6:implementer:implementer"
shell_pid: "14489"
history:
- date: '2026-04-11T01:15:00Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: docs/
execution_mode: code_change
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data-flows.md
- docs/design/architecture/security-posture.md
- docs/design/architecture/glossary.md
- docs/design/felix-capability-roadmap.md
- docs/runbooks/inbox-ops.md
- docs/runbooks/habits-ops.md
- docs/runbooks/goals-ops.md
- docs/runbooks/escalation-ops.md
- docs/runbooks/obsidian-sync-ops.md
- docs/runbooks/openclaw-agent-setup.md
- docs/runbooks/felix-governance.md
- docs/runbooks/vault-path-registry-migration.md
- docs/constitution/FELIX-CONSTITUTION.md
- docs/INDEX.md
tags: []
---

# WP03: Documentation Synchronization

## Objective

Update every documentation artifact affected by the vault path registry extension and the coming folder renumber — architecture JSON data files, their markdown views, runbooks, `docs/INDEX.md`, and `docs/design/felix-capability-roadmap.md`. Create the new runbook `docs/runbooks/vault-path-registry-migration.md` with a C4-style summary per the charter paradigm. This WP satisfies FR-007 and charter Project Directive #5 — documentation synchronization is a first-class mission deliverable, not a post-hoc cleanup.

**Important:** This WP updates docs to reflect the POST-RENAME folder state (`01-Inbox`, `03-Constitution`, etc.) even though the physical rename hasn't happened yet. This is intentional: docs describe intended state, and by the time the mission merges, WP05 will have completed the rename. If the mission is halted before WP05, these doc updates need to be reverted as part of the rollback.

## Context

- WP02 is complete: all production files now use `.tmpl` markers (except the `_private/` boundary)
- The folder rename has NOT happened yet — that's WP05
- This WP updates documentation to describe the **post-rename** folder state because docs will be merged to main alongside the code changes and will be in effect after WP05
- The charter paradigm is `c4-incremental-detail-modeling`; the new migration runbook must include a C4-style summary
- `docs/func-spec/` and `docs/archive/` are frozen historical archives and MUST NOT be modified by this mission
- `validate_docs.py` is the CI gate for docs — all modified docs must pass it

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP03 --agent <name>`
- Execution: single lane worktree, dependency on WP02

## Contracts

- [../contracts/verification-contract.md](../contracts/verification-contract.md) — WP03 acceptance tests

---

## Subtask T014: Audit `docs/` for vault path references

**Purpose:** Produce the complete list of documentation files that need updates in this WP.

**Steps:**

1. Run the grep audit:
   ```bash
   grep -rn "00-Inbox\|01-Constitution\|02-Growth\|03-Health\|04-Business\|05-Finance\|06-Journal\|07-Resources\|00-System" \
     docs/ \
     | grep -v "docs/archive/" \
     | grep -v "docs/func-spec/"
   ```

2. Categorize each hit:
   - **Architecture JSON data** (`docs/design/architecture/data/*.json`) — authoritative per project directive #4, must be updated first
   - **Architecture markdown views** (`docs/design/architecture/*.md`) — regenerated from JSON
   - **Runbooks** (`docs/runbooks/*.md`) — updated individually per content
   - **Constitution** (`docs/constitution/FELIX-CONSTITUTION.md`) — check for vault path references; the privacy boundary may be mentioned
   - **Capability roadmap** (`docs/design/felix-capability-roadmap.md`) — update registry capability status
   - **Other** — any unexpected location

3. Write the audit to `kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp03-doc-updates.md`.

**Files produced:**
- `kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp03-doc-updates.md` (audit artifact)

**Validation:**
- [ ] Audit artifact exists with categorized file list
- [ ] Every hit from the grep output is categorized
- [ ] Files under `docs/archive/` and `docs/func-spec/` are excluded

---

## Subtask T015: Update architecture JSON data files

**Purpose:** Update `docs/design/architecture/data/service-inventory.json` and any other JSON files under `data/` that reference vault paths. Set `updated_by: #152` per project convention.

**Steps:**

1. Start with `service-inventory.json`. Search for every vault folder literal. Update each to the new name per the rename table:

   | Old | New |
   |---|---|
   | `00-Inbox` | `01-Inbox` |
   | `01-Constitution` | `03-Constitution` |
   | `02-Growth` | `04-Growth` |
   | `03-Health` | `05-Health` |
   | `04-Business` | `06-Business` |
   | `05-Finance` | `07-Finance` |
   | `06-Journal` | `08-Journal` |
   | `07-Resources` | `09-Resources` |

   `00-System` stays unchanged.

2. Add `02-Inbox-Processed` where appropriate — the service inventory should reference the new folder if any service (e.g., the future inbox pre-scan helper) will consume it.

3. Set the `updated_by` field to `"#152"` (or `"kentonium3/kg-automation#152"` per whatever convention existing entries use).

4. Update `updated_at` or similar timestamp fields to today's date.

5. Repeat for `data-flows.json` and any other JSON files in `data/` that the audit identified.

6. Validate each JSON file:
   ```bash
   python3 -m json.tool docs/design/architecture/data/service-inventory.json > /dev/null
   python3 -m json.tool docs/design/architecture/data/data-flows.json > /dev/null
   ```

**Files modified:**
- `docs/design/architecture/data/service-inventory.json`
- `docs/design/architecture/data/data-flows.json`
- Any other JSON files from the audit

**Validation:**
- [ ] Every modified JSON file parses
- [ ] Every in-scope JSON file has `updated_by: #152` (or equivalent)
- [ ] Every vault folder literal has been updated to the new name
- [ ] `02-Inbox-Processed` is represented where it belongs
- [ ] `00-System` is unchanged

---

## Subtask T016: Regenerate markdown views in `docs/design/architecture/`

**Purpose:** Update every markdown view under `docs/design/architecture/` to match its JSON source. Per project directive #4, JSON is authoritative and markdown narrative must match.

**Steps:**

1. For each markdown view in the audit (e.g., `service-inventory.md`, `data-flows.md`, `security-posture.md`, `glossary.md`):
   - Read the file
   - Identify the sections that reference vault paths
   - Update each reference to the new folder name per the rename table above
   - Verify narrative text reads coherently after the update (no "Inbox folder (00-Inbox)" becoming "Inbox folder (01-Inbox)" mid-sentence-that-doesn't-make-sense)

2. For markdown views that are mechanically generated from JSON (if any such tooling exists in this repo): re-run the generator. Otherwise: hand-edit.

3. Spot-check each view against its JSON source after editing:
   - Line count delta is within ±10% of pre-update
   - No broken markdown formatting (tables still render, links still work)
   - No orphan references to old folder names

4. Run `validate_docs.py`:
   ```bash
   python3 tooling/scripts/validate_docs.py docs/design/architecture/
   ```

**Files modified:**
- Every in-scope markdown file under `docs/design/architecture/`

**Validation:**
- [ ] Every markdown view that referenced vault paths has been updated
- [ ] Narrative still reads coherently
- [ ] `validate_docs.py` passes on `docs/design/architecture/`
- [ ] No hits for old folder names remain in `docs/design/architecture/*.md`

---

## Subtask T017: Update runbooks under `docs/runbooks/` [P]

**Purpose:** Update every runbook in `docs/runbooks/` that references vault paths. Runbooks are operator-facing — accuracy matters for incident response and routine operations.

**Steps:**

1. For each runbook in the audit (e.g., `inbox-ops.md`, `habits-ops.md`, `goals-ops.md`, `escalation-ops.md`, `obsidian-sync-ops.md`, `openclaw-agent-setup.md`, `felix-governance.md`):
   - Read the runbook
   - Update every vault folder reference to the new name
   - If the runbook references the pre-rename folder structure for historical reasons (e.g., "the original layout was..."), leave historical references alone but add a note about the post-#152 state

2. Spot-check runbooks for operational accuracy — the commands in the runbook must still work against the post-rename vault.

3. For runbooks referencing `felix-admin-capture` cron, add a note about the cron pause procedure used in this mission (as a forward reference for future similar operations). Don't expand into a full procedure — just a pointer to the new migration runbook (T018).

**Files modified:**
- Every in-scope runbook under `docs/runbooks/`

**Validation:**
- [ ] Every runbook that referenced vault paths has been updated
- [ ] Commands in runbooks are operationally valid post-rename
- [ ] `validate_docs.py` passes on `docs/runbooks/`

---

## Subtask T018: Create new runbook `docs/runbooks/vault-path-registry-migration.md` [P]

**Purpose:** Create a reusable playbook for future vault-path-registry migrations. Include a C4-style summary per the charter paradigm (`c4-incremental-detail-modeling`).

**Steps:**

1. Create `docs/runbooks/vault-path-registry-migration.md` with frontmatter and structure matching other runbooks in the repo.

2. Structure:
   - **Frontmatter**: title, doc_type (runbook), status, level, owners, last_validated, version
   - **Purpose**: why this runbook exists, who uses it
   - **When to use this runbook**: scenarios where a vault path migration is the right move
   - **C4 Summary** (per paradigm requirement):
     - Level 1 (System Context): the Felix system and its knowledge-store boundary
     - Level 2 (Containers): `scripts/vault/` as the deployable registry container
     - Level 3 (Components): the resolver, deploy script, and deploy wrapper components
     - Level 4 (Code): `.tmpl` files and marker substitution
   - **Prerequisites**: what must be true before starting
   - **Procedure**: the 10-step migration sequence (extracted from this mission's plan.md and quickstart.md)
   - **Verification**: the acceptance checks that must pass before declaring the migration done
   - **Rollback**: how to recover if the migration fails at each stage
   - **Post-migration**: what to do after successful completion
   - **References**: links to the mission 024 and 026 artifacts, the vault path registry README, and the deploy contracts

3. Use mission 026 as the canonical example throughout. Link back to `kitty-specs/026-vault-path-registry-and-folder-renumber/` where appropriate.

4. Length target: 300–500 lines. Not a one-pager, but not a full spec either.

5. Run `validate_docs.py` on the new runbook.

**Files produced:**
- `docs/runbooks/vault-path-registry-migration.md` (new)

**Validation:**
- [ ] File exists with proper frontmatter
- [ ] All sections populated
- [ ] C4 summary includes all four levels
- [ ] Procedure covers the 10 steps from mission 026's plan.md
- [ ] `validate_docs.py` passes

---

## Subtask T019: Update `docs/INDEX.md` with new runbook entry [P]

**Purpose:** Ensure the new migration runbook is discoverable through the master documentation index.

**Steps:**

1. Read `docs/INDEX.md`.

2. Find the runbooks section. Add an entry for `vault-path-registry-migration.md` in the appropriate category (likely under "Infrastructure runbooks" or similar — match the existing categorization scheme).

3. Include the Divio type annotation per the INDEX conventions (e.g., "How-to guide" or "Reference" — check how other runbooks are annotated).

4. Preserve alphabetical or structural ordering per the INDEX's existing convention.

5. Run `validate_docs.py` on `docs/INDEX.md`.

**Files modified:**
- `docs/INDEX.md`

**Validation:**
- [ ] New runbook entry present in INDEX
- [ ] Entry follows the same categorization and annotation conventions as existing entries
- [ ] `validate_docs.py` passes

---

## Subtask T020: Update `docs/design/felix-capability-roadmap.md` [P]

**Purpose:** Reflect the vault path registry capability as "full" rather than "MVP" after mission 026 closes.

**Steps:**

1. Read `docs/design/felix-capability-roadmap.md`.

2. Find the section that lists the vault path registry capability. Mission 024 likely marked it as "MVP" or "Phase 1" or similar.

3. Update the status to reflect the post-#152 state:
   - Capability state: "Full" (or equivalent phrasing per existing roadmap style)
   - Add a reference to mission 026 (kentonium3/kg-automation#152) alongside the existing #150 reference
   - Note the new logical names added
   - Note that the `02-Inbox-Processed` folder now exists, unblocking the `#149` follow-on mission

4. If the roadmap has a "Next steps" or "Open decisions" section, remove any items that this mission resolves (e.g., "extend registry to all paths" should no longer be open).

5. Run `validate_docs.py`.

**Files modified:**
- `docs/design/felix-capability-roadmap.md`

**Validation:**
- [ ] Registry capability status updated
- [ ] Mission 026 (#152) referenced
- [ ] Resolved open items removed from "Next steps" or similar
- [ ] `validate_docs.py` passes

---

## Subtask T021: Verify WP03 acceptance

**Purpose:** Run the WP03 acceptance checks from the verification contract.

**Steps:**

1. Repo-wide grep in `docs/` for old folder literals:
   ```bash
   grep -rn "00-Inbox\|01-Constitution\|02-Growth\|03-Health\|04-Business\|05-Finance\|06-Journal\|07-Resources" \
     docs/ \
     | grep -v "docs/archive/" \
     | grep -v "docs/func-spec/" \
     | grep -v "_private"
   ```
   Expected: zero hits (excluding archive and func-spec, and any intentional `_private/` references).

2. Verify every modified JSON file has `updated_by: #152`:
   ```bash
   grep -l '"updated_by"' docs/design/architecture/data/*.json | \
     xargs grep -l '"#152"' | \
     wc -l
   # Compare to the count of files modified in T015
   ```

3. Run `validate_docs.py` on the full `docs/` tree:
   ```bash
   python3 tooling/scripts/validate_docs.py docs/
   ```

4. Confirm the new migration runbook exists and is indexed:
   ```bash
   test -f docs/runbooks/vault-path-registry-migration.md
   grep "vault-path-registry-migration" docs/INDEX.md
   ```

5. Confirm the capability roadmap reflects the new status:
   ```bash
   grep -A 3 "vault-path-registry" docs/design/felix-capability-roadmap.md
   ```

**Validation:**
- [ ] Repo-wide doc grep for old folder literals returns zero hits outside documented exclusions
- [ ] All modified JSON files have `updated_by: #152`
- [ ] `validate_docs.py` passes on `docs/` tree
- [ ] New migration runbook exists and is indexed in `docs/INDEX.md`
- [ ] `felix-capability-roadmap.md` reflects registry as "full"
- [ ] All WP03 verification checks from `contracts/verification-contract.md` § WP03 pass

---

## Definition of Done

- [ ] Every architecture JSON data file in scope has been updated with new folder names and `updated_by: #152`
- [ ] Every markdown view in `docs/design/architecture/` matches its JSON source
- [ ] Every runbook referencing vault paths has been updated
- [ ] New runbook `docs/runbooks/vault-path-registry-migration.md` exists with C4 summary
- [ ] `docs/INDEX.md` includes the new runbook entry
- [ ] `docs/design/felix-capability-roadmap.md` reflects the registry capability as "full"
- [ ] `validate_docs.py` passes on the full `docs/` tree
- [ ] Zero hits for old folder literals in `docs/` outside documented exclusions
- [ ] WP03 changes committed to the mission branch

## Risks

- **Doc updates reflect post-rename state but folder rename hasn't happened.** Mitigation: if WP05 is halted before completion, rollback includes reverting these doc updates. This is called out explicitly in the plan.
- **A markdown view is mechanically generated from JSON and hand-editing creates drift.** Mitigation: investigate whether any views have generator tooling. If yes, use the generator. If no, hand-edit carefully.
- **`validate_docs.py` is strict about frontmatter and catches unrelated issues.** Mitigation: run it early (after T015) and fix any frontmatter issues incrementally.
- **The C4 summary in the new runbook (T018) is a first-of-its-kind artifact for this repo.** Mitigation: keep it concise and focused on the migration's own C4 shape, not a system-wide C4 model.

## Reviewer Guidance

The reviewer should confirm:

- All in-scope JSON data files have `updated_by: #152` (spot-check several)
- Markdown views match their JSON sources (spot-check one view against its source)
- The new migration runbook is genuinely reusable — a future similar migration should be able to follow it without reading mission 026's spec
- The C4 summary in the new runbook covers all four levels, not just one
- `docs/INDEX.md` includes the new runbook in the right section
- No drift introduced into `docs/archive/` or `docs/func-spec/` (those are frozen)
- `validate_docs.py` output is clean (no warnings, no errors)

## Activity Log

- 2026-04-11T02:40:19Z – claude:opus-4-6:implementer:implementer – shell_pid=14489 – Started implementation via action command
- 2026-04-11T02:56:37Z – claude:opus-4-6:implementer:implementer – shell_pid=14489 – WP03 ready for review: architecture JSON/markdown updated with post-rename folder names and updated_by: #152, runbooks synced, new vault-path-registry-migration runbook created with C4 summary (Levels 1-4) and 10-step playbook, INDEX.md and felix-capability-roadmap.md updated, validate_docs.py passes. --force per spec-kitty #589 (research artifacts under kitty-specs/research/ are legitimate WP audit deliverables)
