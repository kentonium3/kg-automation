---
work_package_id: WP02
title: Wire portal + validation drift check
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-009
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T009
- T010
- T011
- T012
agent: "claude:opus-4-7:implementer:implementer"
shell_pid: "15027"
history:
- date: '2026-05-26'
  note: WP authored by spec-kitty.tasks (mission documentation-developer-portal-01KSJ75K)
authoritative_surface: docs/DEVELOPER_PORTAL.md
execution_mode: code_change
mission_slug: documentation-developer-portal-01KSJ75K
owned_files:
- docs/DEVELOPER_PORTAL.md
- tooling/scripts/validate_docs.py
- tests/tooling/test_validate_docs_portal_drift.py
tags: []
---

# WP02 — Wire portal + validation drift check

## Objective

Author the portal markdown (Quick-Start, Execution Loop, Verification
Quick-Reference, plus the marker pair for the auto-generated filter),
populate the filter section by running the helper script delivered in
WP01, and extend `validate_docs.py` so CI fails when the embedded block is
stale.

## Branch strategy

- Planning/base branch: **main**
- Merge target: **main**
- Single-lane mission; this WP runs in the same lane worktree as WP01 and
  WP03 once allocated by `finalize-tasks`.

## Context

WP01 delivered `tooling/scripts/build_runbook_filter.py`. This WP creates
the portal that the script populates, and wires the drift check into
`validate_docs.py` so contributors can't accidentally let the embedded
block go stale.

**Hard constraints** (from spec):
- Execution Loop section is **≤ 3 paragraphs** and links to existing
  runbooks; do not duplicate their content.
- Portal frontmatter must pass `validate_docs.py`'s schema (use
  `doc_type: index`).
- The drift-check hook must be a no-op when the portal does not exist, so
  it doesn't break older branches or CI workflows that scan multiple refs.

**Key references**:
- `kitty-specs/documentation-developer-portal-01KSJ75K/spec.md` — full FR list
- `kitty-specs/documentation-developer-portal-01KSJ75K/plan.md` — portal layout decisions
- `docs/INDEX.md` — pattern for navigation markdown in this repo
- `docs/runbooks/agent-workspace-reconciliation.md` — execution-loop TL;DR source A (link, do not paraphrase)
- `docs/runbooks/openclaw-agent-setup.md` — execution-loop TL;DR source B (link, do not paraphrase)

## Subtasks

### T009 — Author `docs/DEVELOPER_PORTAL.md` body

**Purpose**: Create the portal with valid frontmatter and four sections plus the marker pair.

**Steps**:

1. Create `docs/DEVELOPER_PORTAL.md` with YAML frontmatter:
   ```yaml
   ---
   title: kg-automation Developer Portal
   doc_type: index
   status: approved
   owners: [kgale]
   audience: agents_and_humans
   last_validated: 2026-05-26
   version: "1.0"
   ---
   ```
   (Use the current date for `last_validated`. `version` starts at `"1.0"`.)

2. Opening orientation paragraph (~3 sentences): one-line statement of what the file is, who it's for, and a sentence linking back to `docs/INDEX.md` as the flat catalog. Use relative link `./INDEX.md`.

3. **Quick-Start Onboarding Sequences** — three named paths, each an ordered checklist of files to read. Use this exact structure:
   ```markdown
   ## Quick-Start Onboarding

   Pick the path that matches what you're about to do.

   ### Feature Development
   1. [link 1]
   2. [link 2]
   ...

   ### Runbook Execution
   1. ...

   ### Bug Fix
   1. ...
   ```
   For each path, list 3-6 files in the order to read them. Examples of files to consider per path:
   - **Feature Development**: `CLAUDE.md` § "Feature Development Workflow", `docs/constitution/FELIX-CONSTITUTION.md`, `docs/design/felix-capability-roadmap.md`, `docs/design/architecture/README.md`
   - **Runbook Execution**: `CLAUDE.md` § "Server Access", `docs/runbooks/agent-workspace-reconciliation.md`, target runbook, `docs/runbooks/governance/post-change-verification.md`
   - **Bug Fix**: `CLAUDE.md` § "Issue-First Habit", the affected `docs/runbooks/*.md`, related `docs/design/architecture/*` for context

4. **The Execution Loop Explained** — at most 3 paragraphs covering:
   - Para 1: Local workspace → commit → GitHub push (mention spec-kitty merges create commits directly to main, not PRs — per existing CLAUDE.md text)
   - Para 2: GitHub → `office2` reconciliation. **Link** to `docs/runbooks/agent-workspace-reconciliation.md` for the daemon mechanics; do not duplicate.
   - Para 3: `office2` → OpenClaw run lifecycle. **Link** to `docs/runbooks/openclaw-agent-setup.md` for IDENTITY.md/SOUL.md/AGENTS.md and registration; do not duplicate.

   Hard cap: 3 paragraphs. Each paragraph ≤ 6 sentences. No code blocks in this section — it is purely orientation.

5. **Verification Command Quick-Reference** — a single table:
   ```markdown
   | Command | What it checks | Run from |
   |---|---|---|
   | `python -m pytest` | Repo-wide test suite | repo root |
   | `python tooling/scripts/validate_docs.py` | Markdown frontmatter schema + portal drift | repo root |
   | `python tooling/scripts/sync_mermaid_views.py` | `.view.md` files match source diagrams | repo root |
   | `python tooling/scripts/build_runbook_filter.py` | Portal runbook-filter block is current | repo root |
   | `python tooling/scripts/build_runbook_filter.py --write` | Refresh portal runbook-filter block | repo root |
   ```
   Verify each script path exists in the repo before listing it. If `sync_mermaid_views.py` does not exist, omit that row.

6. **Virtual Runbook Filter** — section header, one-sentence description, then the marker pair (the contents inside the markers will be populated by T010):
   ```markdown
   ## Virtual Runbook Filter

   Runbooks under `docs/runbooks/` grouped by their `audience:`
   frontmatter. This section is auto-generated; run
   `python tooling/scripts/build_runbook_filter.py --write` after adding
   or changing a runbook's audience.

   <!-- begin:runbook-filter (generated; do not edit) -->
   <!-- end:runbook-filter -->
   ```
   Leave the marker pair empty — T010 will populate it.

7. Keep the overall file ≤ 25 KB (NFR-001). Spot-check after writing.

**Files**:
- `docs/DEVELOPER_PORTAL.md` (new)

**Validation**:
- `python tooling/scripts/validate_docs.py` exits 0 for this file (drift hook from T011 is still being added in parallel — pre-drift-hook validation suffices here).
- Manual read: each section is present with the names above.

### T010 — Populate filter section

**Purpose**: Run the helper script to fill in the marker pair contents.

**Steps**:
1. From the lane worktree root, run: `python tooling/scripts/build_runbook_filter.py --write`
2. Verify the script exits 0 and the portal now contains entries between the markers.
3. Spot-check: every file under `docs/runbooks/**/*.md` appears in exactly one bucket. Files at deeper paths (e.g., `docs/runbooks/governance/*.md`) appear with their relative path from the portal.
4. Commit the resulting portal change.

**Files**:
- `docs/DEVELOPER_PORTAL.md` (the marker-pair content is updated in place)

**Validation**:
- `python tooling/scripts/build_runbook_filter.py` (without `--write`) exits 0.

### T011 — Extend `validate_docs.py` with portal drift check

**Purpose**: Wire the helper script's drift check into the existing `validate_docs.py` umbrella.

**Steps**:
1. At the bottom of `tooling/scripts/validate_docs.py` (after existing checks complete), add a new check section. Guard it: skip if `docs/DEVELOPER_PORTAL.md` does not exist on disk (lets older branches and CI on unrelated refs pass).
2. If the portal exists, call the helper script's drift-check function. Two clean ways to do this:
   - **Preferred**: import the function from `build_runbook_filter` (both files live in `tooling/scripts/`, so a relative import works). Add `tooling/scripts/` to `sys.path` if needed.
   - **Alternative**: subprocess call to `python tooling/scripts/build_runbook_filter.py` and inspect exit code + stdout.
   Implementer chooses; document the choice with a one-line comment.
3. On drift detected, emit a clear error (consistent with the existing `err(...)` helper in `validate_docs.py`) that includes the line `run: python tooling/scripts/build_runbook_filter.py --write`. Treat drift as a blocker (matches the strictness of other schema checks).
4. Confirm `validate_docs.py` still exits 0 when the portal block is fresh; non-zero when stale.

**Files**:
- `tooling/scripts/validate_docs.py`

**Validation**:
- Manual: tamper the portal block (e.g., delete one entry), re-run `validate_docs.py`, observe non-zero exit with the `run:` hint. Restore the block via `--write`, re-run, observe exit 0.

### T012 — Smoke test for the drift hook

**Purpose**: Lock the drift-check integration with an automated test.

**Steps**:
1. Create `tests/tooling/test_validate_docs_portal_drift.py`.
2. Test 1: fresh portal block, validation passes. Use a synthetic temp dir like T006's setup; invoke `validate_docs.py` as a subprocess with `cwd=tmp_path` and assert exit 0.
3. Test 2: tamper the block, validation fails non-zero, stderr/stdout includes the `run:` hint.
4. Test 3: no portal file present in the temp tree → validation still passes (drift check is gated).

**Files**:
- `tests/tooling/test_validate_docs_portal_drift.py` (new)

**Validation**:
- `python -m pytest tests/tooling/test_validate_docs_portal_drift.py -v` exits 0.

## Test Strategy

- T012 covers integration. WP01's tests cover the helper script itself.
- Run from repo root: `python -m pytest tests/tooling -v` (covers both WP01 and WP02 tests).

## Definition of Done

- [ ] `docs/DEVELOPER_PORTAL.md` exists, frontmatter passes schema, file ≤ 25 KB
- [ ] All four required sections present in the order specified
- [ ] Execution Loop section is **≤ 3 paragraphs** and contains explicit links (not duplicated content) to `agent-workspace-reconciliation.md` and `openclaw-agent-setup.md`
- [ ] Virtual Runbook Filter is populated; every runbook file appears in exactly one bucket
- [ ] `python tooling/scripts/build_runbook_filter.py` exits 0 against the populated portal
- [ ] `python tooling/scripts/validate_docs.py` exits 0 overall (including the new drift hook)
- [ ] Tampering the block makes `validate_docs.py` exit non-zero with the `run:` hint
- [ ] `tests/tooling/test_validate_docs_portal_drift.py` passes
- [ ] No edits outside the three `owned_files` paths

## Reviewer guidance

- **Critical**: read the Execution Loop section and count paragraphs. Reject if > 3, or if any paragraph paraphrases the linked runbooks rather than pointing at them.
- Verify the marker-pair contents match a fresh run of `build_runbook_filter.py` (i.e., re-run the script during review and `git diff docs/DEVELOPER_PORTAL.md` should be empty).
- Verify the drift hook is gated on the portal existing — read the new code in `validate_docs.py` and confirm there's a clear conditional.
- Verify the smoke tests use synthetic fixtures, not the live `docs/runbooks/`.

## Implementation command

```
spec-kitty agent action implement WP02 --agent <name>
```

## Activity Log

- 2026-05-26T13:58:56Z – claude:opus-4-7:implementer:implementer – shell_pid=15027 – Started implementation via action command
