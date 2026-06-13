# Tasks: OpenClaw Auth Verifier

**Mission**: `openclaw-auth-verifier-01KV0Y9E`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Issue**: kentonium3/kg-automation#597
**Branch contract**: planning/base `main` → merge target `main` (branch_matches_target=true).

---

## Subtask Index

| Task | Description | Work Package | Parallel |
|---|---|---|---|
| T001 | Build `tests/security/fixtures/` with healthy / shadow / drift SQLite + plaintext fixtures | WP01 | |
| T002 | Author `scripts/security/anthropic_verify/findings.py` (Finding dataclass + sanitization) | WP01 | |
| T003 | Author `scripts/security/anthropic_verify/core.py` (discover, sqlite read, sha256, drift compare) | WP01 | |
| T004 | Add Anthropic ping to `core.py` (urllib + 5s/15s timeouts; HTTP 200 / 4xx / network classification) | WP01 | |
| T005 | Author `scripts/security/anthropic-verify.sh` (bash entry; argparse; `--check` dispatch; lazy `--repair` import) | WP01 | |
| T006 | Author `tests/security/test_anthropic_verify_core.py` (fixture-driven topology + drift + mocked-ping tests) | WP01 | |
| T007 | Author `tests/security/test_anthropic_verify_output.py` (C-005 sentinel-grep + NFR-003 fs-snapshot tests) | WP01 | |
| T008 | Author `scripts/security/anthropic_verify/repair.py` (backup + shadow clear + atomic plaintext rewrite) | WP02 | |
| T009 | Wire repair dispatch into `__init__.py` (lazy import; FR-009 gateway-restart hint print) | WP02 | |
| T010 | Author `tests/security/test_anthropic_verify_repair.py` (backup invariants + mutation contract tests) | WP02 | |
| T011 | Extend `scripts/security/anthropic-rotate.sh` with Step 6 verify gate + per-rotation manifest write | WP03 | |
| T012 | Extend `anthropic-rotate.sh` with `--rollback <ts>` argparse + restore logic + manifest read | WP03 | |
| T013 | Author `tests/security/test_anthropic_rotate_gate.py` (gate behavior + rollback restore tests) | WP03 | |
| T014 | `docs/runbooks/openclaw-ops.md` — § _Known upgrade gotchas_ addendum (shadow + drift modes + verifier) | WP04 | [P] |
| T015 | `docs/runbooks/credential-rotation-ops.md` — § _anthropic_ addendum referencing verifier + rollback | WP04 | [P] |
| T016 | `tests/security/test_runbook_anchors.py` — assert runbook section anchors exist (prevents doc drift) | WP04 | |

---

## Work Packages

### WP01 — Detection core + bash entrypoint

**Goal**: Build the verifier's read-only `--check` surface: enumerate sub-agents, count per-agent auth rows, compute sha256[:8] fingerprints for drift detection, ping Anthropic, emit structured `Finding` objects with the no-key-in-output invariant enforced. Includes the bash entry script that operators will invoke.

**Priority**: P0 — foundational. Nothing in WP02/03/04 can land without this.

**Independent test**: Against fixture SQLite databases under `tests/security/fixtures/`, `anthropic-verify --check` produces deterministic output and exit codes that match the spec's exit-code mapping (FR-011). Sentinel-grep test confirms no test-key value appears in stdout/stderr.

**Estimated prompt size**: ~480 lines (7 subtasks).

**Dependencies**: none.

**Included subtasks**:

- [x] T001 Build `tests/security/fixtures/` healthy / shadow / drift fixtures
- [x] T002 `findings.py` — `Finding` dataclass + sanitization invariant
- [x] T003 `core.py` — discovery, sqlite read, AgentAuthState / PlaintextFileState, sha256, drift compare
- [x] T004 `core.py` — Anthropic ping with timeouts and error classification
- [x] T005 `anthropic-verify.sh` — bash entry with argparse, `--check` dispatch, lazy `--repair` import
- [x] T006 `test_anthropic_verify_core.py` — topology + drift + mocked-ping tests
- [x] T007 `test_anthropic_verify_output.py` — sentinel-grep + fs-snapshot tests

**Risks**:
- The Finding sanitization invariant (no `sk-ant-...` substring in evidence or suggested_action) MUST be enforced in `__post_init__` and verified by a sentinel-grep test that runs the verifier against a fixture whose key value is a known test sentinel.
- urllib's default connect timeout interacts with NFR-001's 30 s budget. Set explicit 5 s connect / 15 s total.
- SQLite `store_json` schema navigation must tolerate missing keys (emit `main_empty` finding, not crash).

---

### WP02 — Repair surface

**Goal**: Land the `--repair` mode that mutates state behind a backup invariant. Cleans shadow rows from a sub-agent's SQLite, atomically rewrites the plaintext file from main's SQLite on drift. Print the gateway-restart command after a shadow repair; never auto-restart.

**Priority**: P0 — together with WP01 forms the operator-facing diagnostic+remediation surface.

**Independent test**: Against the shadow fixture, `anthropic-verify --repair` produces a `.pre-repair.<ts>.bak` sibling, then DELETE on both `auth_profile_store` and `auth_profile_state`, leaves the sub-agent with zero rows, and prints the systemctl restart command. Against the drift fixture, the plaintext file is rewritten atomically and its sha256[:8] matches main's afterward.

**Estimated prompt size**: ~310 lines (3 subtasks).

**Dependencies**: WP01 (uses `Finding`, `AgentAuthState`, `PlaintextFileState` types; relies on bash entry's lazy-import dispatch).

**Included subtasks**:

- [x] T008 `repair.py` — backup + clear shadow rows + atomic plaintext rewrite
- [x] T009 Wire repair dispatch in `__init__.py` (lazy import; FR-009 hint print)
- [x] T010 `test_anthropic_verify_repair.py` — backup invariants + mutation tests

**Risks**:
- The atomic-rename pattern (`<file>.tmp` → rename → `<file>`) must preserve mode 0600 and owner. `shutil.copy2` + `os.rename` is the safe sequence.
- The backup-before-mutate invariant (NFR-004) must be enforced even when the mutation itself fails; tests check both halves.

---

### WP03 — Rotation-script integration + rollback

**Goal**: Make `anthropic-rotate.sh` invoke the verifier as a fail-closed gate at the end of a successful rotation, and add `--rollback <ts>` with per-rotation manifest backing. Emit the copy-pasteable rollback command on verify failure; never auto-undo.

**Priority**: P1 — operationally critical (the `#596` recurrence prevention rests here) but depends on WP01 + WP02 being green first.

**Independent test**: A simulated rotation that ends in a clean state passes `--check` and exits 0 with green report. A simulated rotation that ends with an injected shadow row triggers `--check` exit 2, the rotate script prints the rollback hint, and exits non-zero. The `--rollback <ts>` flow restores all three artifacts from per-step backups and verifies their integrity by sha256 prefix.

**Estimated prompt size**: ~360 lines (3 subtasks).

**Dependencies**: WP01 + WP02.

**Included subtasks**:

- [x] T011 `anthropic-rotate.sh` — Step 6 verify gate + per-rotation manifest at `~/.cache/anthropic-rotate/manifest.<ts>.json`
- [x] T012 `anthropic-rotate.sh` — `--rollback <ts>` argparse + restore logic
- [x] T013 `test_anthropic_rotate_gate.py` — gate + rollback tests (bash-driven; mock the verifier output)

**Risks**:
- The existing rotate script's self-update-from-main re-exec pattern must not break when new flags are added; the `argparse` extension goes BEFORE the re-exec.
- The manifest format must be discoverable by future tooling; document at the top of `anthropic-rotate.sh` and in `data-model.md` (already done).

---

### WP04 — Runbook addenda + anti-drift test

**Goal**: Document both failure modes (shadow + drift) and the verifier as the canonical post-`doctor --fix` and post-rotation gate. Add a smoke test that asserts the runbook section anchors exist, so future doc edits don't silently drop the section.

**Priority**: P1 — documentation must land in the same merge as the helper so the discoverability story is single-commit-coherent.

**Independent test**: `grep -F "anthropic-verify"` finds the verifier referenced in both runbooks. The anchor-existence test passes against the merged runbook state.

**Estimated prompt size**: ~240 lines (3 subtasks).

**Dependencies**: WP01 + WP02 + WP03.

**Included subtasks**:

- [ ] T014 `docs/runbooks/openclaw-ops.md` § _Known upgrade gotchas_ addendum
- [ ] T015 `docs/runbooks/credential-rotation-ops.md` § _anthropic_ addendum
- [ ] T016 `test_runbook_anchors.py` — assert section anchors exist in both runbooks

**Risks**:
- Minor — runbook drift if a future PR removes the sections. The anchor-existence test guards against that.
- The merge commit MUST record `Rebaseline: completed at <ts>` per spec FR-017 and #557. The operator runs the rebaseline post-merge — this is a MERGE-TIME action, not a WP-level file change.

---

## Implementation sequence

```
WP01 (foundation)
  → WP02 (repair, depends on WP01)
    → WP03 (rotation integration, depends on WP02)
      → WP04 (runbook + anti-drift, depends on WP03)
```

All four are sequential — no genuine parallelism opportunity exists because each WP depends on the previous one's surfaces. Runbooks (T014/T015) within WP04 are marked `[P]` because they touch different files and can be authored in parallel by a single implementer; that's intra-WP parallelism, not WP-level.

## MVP scope

WP01 alone is sufficient for an operator to detect both failure modes manually (no `--repair`, no rotation integration). For the full incident-recurrence-prevention from #596/#597, WP01 + WP02 deliver the operator UX, and WP03 + WP04 close out the lifecycle integration and discoverability.

The mission's acceptance criteria (spec SC-001 through SC-010) require all four WPs to be merged.

## Next command

`/spec-kitty.analyze` for the optional consistency-check pass, then `/spec-kitty.implement` (or the implement-review skill) to execute WP01 → WP04.
