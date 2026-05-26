---
work_package_id: WP01
title: Build runbook-filter helper script
dependencies: []
requirement_refs:
- FR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-documentation-developer-portal-01KSJ75K
base_commit: 84dabc8724dfe6f2d151e50144717abbe5a2bc38
created_at: '2026-05-26T13:35:23.312258+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
- T008
shell_pid: "8164"
agent: "claude:opus-4-7:implementer:implementer"
history:
- date: '2026-05-26'
  note: WP authored by spec-kitty.tasks (mission documentation-developer-portal-01KSJ75K)
authoritative_surface: tooling/scripts/build_runbook_filter.py
execution_mode: code_change
mission_slug: documentation-developer-portal-01KSJ75K
owned_files:
- tooling/scripts/build_runbook_filter.py
- tests/tooling/test_build_runbook_filter.py
tags: []
---

# WP01 — Build runbook-filter helper script

## Objective

Deliver `tooling/scripts/build_runbook_filter.py` exactly per
`contracts/build_runbook_filter.md`, with unit tests covering every contract
row. After this WP the helper script is runnable from a fresh checkout; the
portal itself does not yet exist (WP02 creates it).

## Branch strategy

- Planning/base branch: **main**
- Merge target: **main**
- Execution lane is allocated by `finalize-tasks` (single-lane mission). All
  three WPs share one lane worktree; this WP's commits go to that lane
  branch via `spec-kitty agent action implement WP01 --agent <name>`.

## Context

The portal will contain an auto-generated section listing every runbook
grouped by its `audience:` frontmatter value (`agents` / `humans` /
`agents_and_humans`). This script is the generator. It supports both a
default drift-check mode (so CI can fail when the embedded block is stale)
and a `--write` mode (so contributors can refresh the block locally).

The contract document is authoritative. If anything in this prompt appears
to conflict with `contracts/build_runbook_filter.md`, trust the contract
and surface the discrepancy in the WP comment.

**Key references** (read before starting):
- `kitty-specs/documentation-developer-portal-01KSJ75K/contracts/build_runbook_filter.md` — full behavior contract
- `kitty-specs/documentation-developer-portal-01KSJ75K/data-model.md` — input/output schema
- `tooling/scripts/validate_docs.py` — existing frontmatter-parsing pattern and the canonical `ALLOWED_VALUES['audience']` enum

## Subtasks

### T001 — Frontmatter reader + audience bucket assignment

**Purpose**: Walk `docs/runbooks/**/*.md`, parse YAML frontmatter, and assign each file to a bucket.

**Steps**:
1. Add a `read_runbook_frontmatter(root)` helper that yields `(path, frontmatter_dict)` for every `.md` file under `docs/runbooks/`. Skip non-`.md` files silently. Files without a frontmatter block (no leading `---` … `---`) emit a stderr warning and are excluded from buckets.
2. Implement bucket assignment using the same `ALLOWED_VALUES['audience']` set that `validate_docs.py` exposes. Prefer `from validate_docs import ALLOWED_VALUES` if it doesn't introduce circular imports; otherwise replicate `{'agents', 'humans', 'agents_and_humans'}` literally with a comment that points back to `validate_docs.py` as the source of truth.
3. Buckets:
   - `agents` → `Agent-executable`
   - `humans` → `Human-only`
   - `agents_and_humans` → `Dual-audience`
   - missing `audience:` → `Unclassified`
   - any other value → raise/return an error (handled in T005)
4. Missing `title:` frontmatter → error (T005).

**Files**:
- `tooling/scripts/build_runbook_filter.py` (new file)

**Validation**:
- Manually invoking against the live `docs/runbooks/` returns one entry per existing runbook, all routed to a real bucket.

### T002 — Block emitter (sort, format, marker semantics)

**Purpose**: Build the deterministic markdown block per the contract.

**Steps**:
1. Add `build_block(buckets) -> str` that emits the fixed bucket order: `Agent-executable` → `Dual-audience` → `Human-only` → `Unclassified`.
2. Within each bucket, sort entries alphabetically by lowercased title.
3. Format each entry as `- [<title>](<relative-path>)` where `<relative-path>` is computed relative to `docs/DEVELOPER_PORTAL.md` (i.e., `runbooks/foo.md`). Use `pathlib.PurePosixPath.relative_to`.
4. The `Unclassified` bucket appends `— missing \`audience:\` frontmatter` to each entry line.
5. Empty buckets render as the header followed by `- _(none)_`.
6. Exactly one blank line between buckets. Trailing newline before the end marker.
7. Wrap the inner content with the two HTML comment markers: `<!-- begin:runbook-filter (generated; do not edit) -->` and `<!-- end:runbook-filter -->`. Surround the markers themselves with a blank line on the outside of each so the surrounding markdown stays well-formed.

**Files**:
- `tooling/scripts/build_runbook_filter.py`

**Validation**:
- Unit tests in T007 exercise sort and empty-bucket behavior.

### T003 — Default mode (drift check, exit 0/1 with diff)

**Purpose**: Implement the default invocation that compares the embedded block to what would be generated, fails non-zero with a diff if they differ.

**Steps**:
1. Add `def check_drift(portal_path) -> int` that:
   - Locates the marker pair in `portal_path` (T005 handles error cases for missing/duplicate markers).
   - Extracts the current block including markers.
   - Builds the expected block from the runbook input.
   - Normalizes line endings to `\n` on both sides before comparison.
   - Returns 0 if identical, 1 with a unified diff on stdout if not.
2. The last line of stdout in the drift case is literally: `run: python tooling/scripts/build_runbook_filter.py --write` so contributors can copy/paste.
3. CLI entry point: argparse with `--write`, `--check-only` (default behavior alias), `--help`. No positional args.

**Files**:
- `tooling/scripts/build_runbook_filter.py`

**Validation**:
- T006 happy-path test exercises both clean-and-stale states.

### T004 — `--write` mode

**Purpose**: Rewrite the block in place when the contributor wants to refresh.

**Steps**:
1. Add `def write_block(portal_path) -> int`. Same setup as `check_drift`: locate marker pair, build expected block.
2. Replace the content between the markers with the new block. Preserve every line outside the markers byte-for-byte.
3. If the file is already up to date, do not rewrite — print `up to date` and exit 0.
4. After writing, exit 0.

**Files**:
- `tooling/scripts/build_runbook_filter.py`

**Validation**:
- T006 regenerates a stale block and verifies the new content matches the expected block.

### T005 — Error paths

**Purpose**: Every error case in the contract has an exit code and an actionable message on stderr.

**Steps**:
1. Exit 2: portal file missing — `error: docs/DEVELOPER_PORTAL.md not found`
2. Exit 3: marker pair missing — `error: marker pair not found in portal`
3. Exit 3: marker pair duplicated — `error: duplicate marker pair in portal`
4. Exit 4: invalid `audience:` value — `error: invalid audience '<value>' in <path>`
5. Exit 4: missing `title:` field — `error: missing title in <path>`
6. Use `sys.exit(code)` from the CLI wrapper. The internal helpers return the code so tests can capture without subprocess.

**Files**:
- `tooling/scripts/build_runbook_filter.py`

**Validation**:
- T008 covers all five error cases.

### T006 — Happy-path tests

**Purpose**: Exercise the contract's primary flow against synthetic fixtures (do not read the live `docs/runbooks/`).

**Steps**:
1. Create `tests/tooling/test_build_runbook_filter.py` (new file; create `tests/tooling/__init__.py` if needed for discovery).
2. Use `pytest`'s `tmp_path` fixture to materialize a synthetic tree:
   ```
   tmp_path/
   ├── docs/
   │   ├── DEVELOPER_PORTAL.md     (with the marker pair)
   │   └── runbooks/
   │       ├── a.md  (audience: agents)
   │       ├── b.md  (audience: humans)
   │       └── c.md  (audience: agents_and_humans)
   └── tooling/scripts/             (imported, not invoked as subprocess)
   ```
3. Test cases:
   - Drift check against a clean portal → exit 0, no output
   - Drift check against a portal with a stale block (e.g., the wrong path) → exit 1, diff on stdout contains the new file's title, last line is the `run:` hint
   - `--write` against a stale portal → file now matches the expected block, exit 0
   - `--write` against an already-clean portal → prints `up to date`, exit 0

**Files**:
- `tests/tooling/test_build_runbook_filter.py` (new)
- `tests/tooling/__init__.py` (new if not present)

**Validation**:
- `pytest tests/tooling/test_build_runbook_filter.py -k happy` passes.

### T007 — Bucket / sort / empty-bucket tests

**Purpose**: Verify the deterministic ordering rules.

**Steps**:
1. Test: bucket order is fixed `Agent-executable → Dual-audience → Human-only → Unclassified` regardless of input file discovery order.
2. Test: within-bucket alphabetization is case-insensitive (e.g., `apple.md` before `Banana.md`).
3. Test: when no file lands in `Unclassified`, the bucket still renders with `- _(none)_`.
4. Test: when no file lands in `Agent-executable`, same behavior.
5. Test: relative paths in entries are correctly computed for files at deeper nesting (e.g., `docs/runbooks/governance/pre-flight-checklist.md`).

**Files**:
- `tests/tooling/test_build_runbook_filter.py`

**Validation**:
- `pytest tests/tooling/test_build_runbook_filter.py -k 'bucket or sort or empty'` passes.

### T008 — Error-case tests

**Purpose**: Verify exit codes 2/3/4 and the corresponding stderr messages.

**Steps**:
1. Test: portal file absent → exit 2, stderr contains `not found`
2. Test: portal exists but has no marker pair → exit 3, stderr contains `marker pair not found`
3. Test: portal exists with two marker pairs → exit 3, stderr contains `duplicate marker pair`
4. Test: a runbook has `audience: bogus` → exit 4, stderr contains `invalid audience 'bogus'` and the file path
5. Test: a runbook is missing `title:` → exit 4, stderr contains `missing title` and the file path

**Files**:
- `tests/tooling/test_build_runbook_filter.py`

**Validation**:
- `pytest tests/tooling/test_build_runbook_filter.py -k error` passes.

## Test Strategy

`pytest` against synthetic fixtures only. Do not let the test suite walk the
real `docs/runbooks/` tree — that couples tests to repo state.

Run from repo root: `python -m pytest tests/tooling/test_build_runbook_filter.py -v`

## Definition of Done

- [ ] `tooling/scripts/build_runbook_filter.py` exists, is executable from the repo root, and implements every contract row
- [ ] `tests/tooling/test_build_runbook_filter.py` exists with at least the 12 cases listed across T006/T007/T008
- [ ] `python -m pytest tests/tooling/test_build_runbook_filter.py` exits 0
- [ ] Manual smoke: `python tooling/scripts/build_runbook_filter.py` (with no portal yet) exits 2 with the expected message
- [ ] No new dependencies added to the repo's Python requirements files
- [ ] No edits outside the two `owned_files` paths

## Reviewer guidance

- Verify the script's audience enum is sourced from `validate_docs.py` rather than re-declared in isolation (or re-declared with a clear pointer comment).
- Verify the `Unclassified` bucket appears even when empty, with the `_(none)_` placeholder.
- Verify the `run:` hint is the literal last line of stdout in drift mode, with no trailing whitespace or color codes.
- Spot-check that the script's argparse setup rejects extra positional args.
- Reject the WP if any owned-file path is touched outside this list.

## Implementation command

```
spec-kitty agent action implement WP01 --agent <name>
```

## Activity Log

- 2026-05-26T13:35:25Z – claude:opus-4-7:implementer:implementer – shell_pid=8164 – Assigned agent via action command
