---
work_package_id: WP03
title: Register portal and update CLAUDE.md
dependencies:
- WP02
requirement_refs:
- FR-006
- FR-007
- FR-008
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T013
- T014
- T015
history:
- date: '2026-05-26'
  note: WP authored by spec-kitty.tasks (mission documentation-developer-portal-01KSJ75K)
authoritative_surface: CLAUDE.md
execution_mode: code_change
mission_slug: documentation-developer-portal-01KSJ75K
owned_files:
- docs/INDEX.md
- CLAUDE.md
tags: []
---

# WP03 — Register portal and update CLAUDE.md

## Objective

Link the portal from `docs/INDEX.md` (the established master index) and add
exactly one additive pointer line to `CLAUDE.md` under the existing
"Architecture Documentation" section. Run the full local verification
suite. This WP closes the loop so readers find the portal from established
entry points.

## Branch strategy

- Planning/base branch: **main**
- Merge target: **main**
- Single-lane mission; this WP runs in the same lane worktree as WP01 and
  WP02.

## Context

**Load-bearing constraint** (the entire mission's main risk):
> `CLAUDE.md` is the authoritative, self-contained runtime instruction
> book for AI sessions. Any change beyond a single additive pointer line
> fails review.

Specifically: do **not** rephrase, reorder, remove, or relocate any
existing line. The diff on `CLAUDE.md` must be purely additive. The
reviewer will inspect `git diff CLAUDE.md` line by line.

**Key references**:
- `kitty-specs/documentation-developer-portal-01KSJ75K/spec.md` — FR-006, FR-007, C-001
- `CLAUDE.md` — read the existing "Architecture Documentation" section before editing
- `docs/INDEX.md` — pattern for index entries

## Subtasks

### T013 — Add portal entry to `docs/INDEX.md`

**Purpose**: Make the portal discoverable from the master index.

**Steps**:
1. Open `docs/INDEX.md`. Read the existing structure to find the most natural placement. Likely options:
   - As a new top-level section "Onboarding & Navigation" near the top (best signal-to-noise for new readers)
   - As an entry under an existing section if one fits cleanly (e.g., near the top under "Constitution & Governance")
2. Add a single bullet pointing at the portal. Format consistent with the file's existing pattern:
   ```markdown
   - [Developer Portal](<./DEVELOPER_PORTAL.md>) — guided onboarding sitemap (start here for new agents and contributors)
   ```
3. Update the `last_validated:` frontmatter field on `docs/INDEX.md` to today's date.
4. Do not reorganize or rewrite any existing INDEX entries. Only add the new entry and update `last_validated`.

**Files**:
- `docs/INDEX.md`

**Validation**:
- `python tooling/scripts/validate_docs.py` exits 0.
- `git diff docs/INDEX.md` shows the new bullet line and the frontmatter date change, nothing else.

### T014 — Add additive pointer line to `CLAUDE.md`

**Purpose**: Wire the portal into the AI session entry point with the minimum possible change.

**Steps**:
1. Open the project-root `CLAUDE.md`. Locate the existing section titled "Architecture Documentation". (In the current file it begins with `## Architecture Documentation` near the top.)
2. Read the entire section, including its existing bullet list of pointers.
3. **Edit strategy** — this is critical:
   - Use a single `Edit` tool operation.
   - The `old_string` is the last existing line of the bulleted list within that section, captured exactly as it appears on disk (including any trailing punctuation or italics).
   - The `new_string` is the same line, plus a newline, plus the new pointer line.
   - This guarantees no other line is touched.
4. The new line content:
   ```markdown
   - **[Developer Portal](docs/DEVELOPER_PORTAL.md)** — guided onboarding sitemap (start here for orientation; complements `docs/INDEX.md`).
   ```
   (Use whatever bullet style matches the surrounding lines. If the surrounding lines use `**Bold**:` prefixes for the link, match that.)
5. Do not change any other line. Do not add a section header. Do not move anything.

**Files**:
- `CLAUDE.md`

**Validation**:
- `git diff CLAUDE.md` is purely additive (only `+` lines, zero `-` lines).
- Read the surrounding 10 lines before and after the change in the new file; verify they are byte-identical to the original.

### T015 — Run full local verification

**Purpose**: Confirm acceptance criteria across the whole mission.

**Steps**:
1. From repo root, run:
   ```
   python -m pytest tests/tooling -v
   ```
   Expect: all WP01 and WP02 tests pass. Exit 0.

2. Run:
   ```
   python tooling/scripts/validate_docs.py
   ```
   Expect: exit 0. (If this fails because of unrelated pre-existing issues on `main`, capture the failing entries and flag them in the WP comment — do not silence the validator.)

3. Run:
   ```
   python tooling/scripts/build_runbook_filter.py
   ```
   Expect: exit 0 (portal block is in sync).

4. Run:
   ```
   git diff CLAUDE.md
   ```
   Expect: **only added lines**. Zero `-` lines, zero modified lines. Visually inspect to confirm.

5. Run:
   ```
   git diff docs/INDEX.md
   ```
   Expect: the new bullet line plus optionally the `last_validated:` frontmatter change. Nothing else.

6. Run:
   ```
   wc -c docs/DEVELOPER_PORTAL.md
   ```
   Expect: ≤ 25600 bytes (NFR-001).

7. Compile a one-paragraph verification report in the WP comment summarizing the results.

**Files**:
- (none — verification only)

**Validation**:
- All seven checks above exit cleanly. Report attached.

## Test Strategy

This WP is verification-heavy. No new code, no new tests — but the
verification step exercises the whole stack including WP01 and WP02
outputs.

## Definition of Done

- [ ] `docs/INDEX.md` references the new portal
- [ ] `CLAUDE.md` has exactly one new line added (verified via `git diff`)
- [ ] `python -m pytest tests/tooling` exits 0
- [ ] `python tooling/scripts/validate_docs.py` exits 0
- [ ] `python tooling/scripts/build_runbook_filter.py` exits 0
- [ ] `wc -c docs/DEVELOPER_PORTAL.md` ≤ 25600
- [ ] Verification report attached as a WP comment
- [ ] No edits outside the two `owned_files` paths

## Reviewer guidance

- **Inspect `git diff CLAUDE.md` line by line** before approving. Any line that is not net-new is grounds for rejection — there is no acceptable rephrasing within this WP's scope.
- Confirm `docs/INDEX.md`'s diff is also additive (one new bullet, optional frontmatter date refresh).
- Run the verification commands from T015 yourself; do not trust the report alone.
- If T015's `validate_docs.py` flagged pre-existing issues on `main`, those are out of scope for this mission — confirm they are pre-existing (not introduced) before approving.

## Implementation command

```
spec-kitty agent action implement WP03 --agent <name>
```
