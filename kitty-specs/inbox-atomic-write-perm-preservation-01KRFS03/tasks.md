# Tasks: Inbox atomic-write permission preservation

**Mission**: `inbox-atomic-write-perm-preservation-01KRFS03`
**Source**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [quickstart.md](quickstart.md)
**Source issue**: [#254](https://github.com/kentonium3/kg-automation/issues/254)

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Modify `_atomic_write` in `scripts/inbox/inject_parse_error_marker.py` to preserve mode + add stderr log | WP01 | [P] |
| T002 | Modify `_atomic_write` in `scripts/inbox/strip_parse_error_marker.py` to preserve mode + add stderr log | WP01 | [P] |
| T003 | Create `tests/inbox/test_atomic_write_perms.py` with parameterized cases for both helpers | WP01 |  |
| T004 | Run local pytest suite, verify 85 existing + new tests pass | WP01 |  |
| T005 | Deploy to office2 via `scripts/deploy/deploy-149.sh --apply --backup-confirmed` | WP01 |  |
| T006 | Smoke test on office2 — verify mode preservation + stderr log via `/tmp` file | WP01 |  |
| T007 | End-to-end canary verification (SC-002 — fresh canary, sync round-trip within 5 min) | WP01 |  |

## Work Package WP01 — Preserve original file mode in inbox `_atomic_write` helpers

**Goal**: Fix the perm-orphaning bug in both inbox marker helper scripts and verify end-to-end that Obsidian Sync continues to round-trip files after they've been touched.

**Priority**: P2 (per source issue #254).

**Independent test**: After deploy, a marker-injected note on office2 remains group-readable, and an edit on Mac side propagates to office2 within 5 minutes.

**Included subtasks**:

- [ ] T001 Modify `_atomic_write` in `scripts/inbox/inject_parse_error_marker.py` (WP01) [P]
- [ ] T002 Modify `_atomic_write` in `scripts/inbox/strip_parse_error_marker.py` (WP01) [P]
- [ ] T003 Create `tests/inbox/test_atomic_write_perms.py` (WP01)
- [ ] T004 Run local pytest suite (WP01)
- [ ] T005 Deploy to office2 (WP01)
- [ ] T006 Smoke test on office2 (WP01)
- [ ] T007 End-to-end canary verification (WP01)

**Implementation sketch**:

1. T001 and T002 are mechanically identical — apply the same `_atomic_write` block in both files. Mark `[P]` because they're separate files; an agent can do them in either order or in parallel.
2. T003 writes a single new test file using `pytest.mark.parametrize` over both helper modules (or two test functions, one per module) — the spec defines 5 cases: 0o600/0o644/0o664 preserved, new-file default 0o664, atomic-replace invariant under exception.
3. T004 runs `python3 -m pytest tests/inbox/ -v` locally. Failure ends WP01.
4. T005 runs the deploy script. The script handles rsync + perms; agent watches for any non-zero exit.
5. T006 is an ad-hoc smoke test directly on office2 using a `/tmp` file (see quickstart.md §3-4). Verifies the change in the actual runtime environment without touching the real inbox.
6. T007 is the end-to-end canary (quickstart.md §5). This is SC-002 verification.

**Parallel opportunities**: T001 and T002 are independent file edits. The rest is strictly sequential (tests depend on impl; deploy depends on tests; verification depends on deploy).

**Dependencies**: None. This is a self-contained bug-fix WP.

**Risks**:

- **`stat` race**: if the target file is unlinked between `os.stat(path)` and `os.replace(tmp_name, path)`, the call falls through to the `FileNotFoundError` branch and applies 0o664. Acceptable — the file was being deleted concurrently, so any mode is fine.
- **Deploy step requires office2 access**: agent must use `ssh office2-claude`. If SSH fails, T005 onward cannot run; report and stop rather than improvising.
- **End-to-end canary requires Obsidian Sync working bidirectionally**: if sync is broken for unrelated reasons (cf. the previous diagnosis 2026-05-13), T007 may take >5 min. Distinguish "fix didn't work" from "sync unrelated issue" by checking the heartbeat file mtime on both sides — same epoch = sync healthy.

**Estimated prompt size**: ~400 lines.

## MVP Scope

WP01 is the entire mission. No phase split necessary.

## Next Steps

After WP01 completes, the mission moves to review → merge. The follow-up mission for #253 (agent Step-6.2 autonomy) will start once #254 is merged.
