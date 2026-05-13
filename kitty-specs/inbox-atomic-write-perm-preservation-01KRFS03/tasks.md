# Tasks: Inbox atomic-write permission preservation

**Mission**: `inbox-atomic-write-perm-preservation-01KRFS03`
**Source**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [quickstart.md](quickstart.md)
**Source issue**: [#254](https://github.com/kentonium3/kg-automation/issues/254)

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Modify `_atomic_write` in `scripts/inbox/inject_parse_error_marker.py` to preserve mode + add stderr log | WP01 | [P] | [D] |
| T002 | Modify `_atomic_write` in `scripts/inbox/strip_parse_error_marker.py` to preserve mode + add stderr log | WP01 | [D] |
| T003 | Create `tests/inbox/test_atomic_write_perms.py` with parameterized cases for both helpers | WP01 |  | [D] |
| T004 | Run local pytest suite, verify 85 existing + new tests pass | WP01 |  | [D] |
| T005 | Deploy to office2 via `scripts/deploy/deploy-149.sh --apply --backup-confirmed` | WP01 |  |
| T006 | Smoke test on office2 — verify mode preservation + stderr log via `/tmp` file | WP01 |  |
| T007 | End-to-end canary verification (SC-002 — fresh canary, sync round-trip within 5 min) | WP01 |  |

## Work Package WP01 — Preserve original file mode in inbox `_atomic_write` helpers

**Goal**: Fix the perm-orphaning bug in both inbox marker helper scripts. (End-to-end Obsidian Sync round-trip verification is post-merge operator work — see "Post-merge operator verification" below.)

**Priority**: P2 (per source issue #254).

**Independent test (WP01 review scope)**: Both `_atomic_write` helpers preserve original target mode (or apply 0o664 for new files) and emit a single stderr log line per write. Full `tests/inbox/` suite passes locally (85 existing + ~10 new = ~95+ passed, 0 failed).

**Included subtasks (review scope — T001–T004)**:

- [x] T001 Modify `_atomic_write` in `scripts/inbox/inject_parse_error_marker.py` (WP01) [P]
- [x] T002 Modify `_atomic_write` in `scripts/inbox/strip_parse_error_marker.py` (WP01) [P]
- [x] T003 Create `tests/inbox/test_atomic_write_perms.py` (WP01)
- [x] T004 Run local pytest suite (WP01)

**Post-merge operator verification (out of WP01 review scope — T005–T007)**:

- [ ] T005 Deploy to office2 via `scripts/deploy/deploy-149.sh --apply --backup-confirmed` (operator, on `main`)
- [ ] T006 Smoke test on office2 — verify mode preservation + stderr log via `/tmp` file (operator)
- [ ] T007 End-to-end canary verification (SC-002 — fresh canary, sync round-trip within 5 min) (operator)

**Why the split**: T005–T007 require office2 SSH against deployed code. Per `docs/design/architecture/change-control.md`, deploys must run against merged code on `main`, not from an unmerged lane branch. Folding them into the review-time WP DoD created a scoping conflict (the reviewer would block on operator-owned post-merge work). They are documented in detail inside the WP prompt file under "Post-Merge Operator Verification" so the operator runbook is preserved without blocking review.

**Implementation sketch**:

1. T001 and T002 are mechanically identical — apply the same `_atomic_write` block in both files. Mark `[P]` because they're separate files; an agent can do them in either order or in parallel.
2. T003 writes a single new test file using `pytest.mark.parametrize` over both helper modules — the spec defines 5 cases: 0o600/0o644/0o664 preserved, new-file default 0o664, atomic-replace invariant under exception.
3. T004 runs `python3 -m pytest tests/inbox/ -v` locally. Failure ends WP01.
4. After WP01 review approval and mission merge, the operator runs T005–T007 on `main` per the runbook embedded in the WP file (and `quickstart.md`).

**Parallel opportunities**: T001 and T002 are independent file edits.

**Dependencies**: None. This is a self-contained bug-fix WP.

**Risks (review-scope only)**:

- **`stat` race**: if the target file is unlinked between `os.stat(path)` and `os.replace(tmp_name, path)`, the call falls through to the `FileNotFoundError` branch and applies 0o664. Acceptable — the file was being deleted concurrently, so any mode is fine.
- **Post-merge T007 may surface unrelated Obsidian Sync issues**: if sync is broken for unrelated reasons (cf. the diagnosis 2026-05-13 in `reference_mission_185.md`), T007 may take >5 min. Operator disambiguates via heartbeat mtime comparison. This is operator-owned and not a WP01 review concern.

**Estimated prompt size**: ~320 lines (after the rescope; was ~400).

## MVP Scope

WP01 is the entire mission. No phase split necessary.

## Next Steps

After WP01 completes, the mission moves to review → merge. The follow-up mission for #253 (agent Step-6.2 autonomy) will start once #254 is merged.
