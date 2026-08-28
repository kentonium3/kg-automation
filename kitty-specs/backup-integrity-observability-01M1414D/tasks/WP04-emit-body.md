---
work_package_id: WP04
title: Crontab recovery without a hand-written strip
dependencies: []
requirement_refs:
- FR-006
planning_base_branch: feat/backup-integrity-observability
merge_target_branch: feat/backup-integrity-observability
branch_strategy: Planning artifacts for this mission were generated on feat/backup-integrity-observability. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/backup-integrity-observability unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-backup-integrity-observability-01M1414D
base_commit: 7c7a443258232f05c31b22ae225de9462b40f0cb
created_at: '2026-08-28T12:22:54.025858+00:00'
subtasks:
- T014
- T015
- T016
phase: Phase 2 - Detect divergence, fix recovery
history:
- at: '2026-08-28T11:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/office2/crontab_capture.py
create_intent: []
execution_mode: code_change
owned_files:
- scripts/office2/crontab_capture.py
- tests/office2/crontab_capture/**
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP04 — Crontab recovery without a hand-written strip

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load`
(profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope,
and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch at prompt creation**: `feat/backup-integrity-observability`
- **Final merge target**: `feat/backup-integrity-observability`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates `base_branch`.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch.

---

## Objectives & Success Criteria

The documented crontab recovery strips the provenance header with a hand-written
pattern:

```
grep -v "^# captured-\|^# source-\|^# NOTE:\|^#       "
```

That predates the sentinel-delimited header and no longer matches two of its
lines. Verified live: the documented *verification* reports a false failure, and
the documented *recovery* installs a crontab carrying two stray comments that the
next hourly capture absorbs as body — so the header grows on every recovery
cycle.

The defect is not the stale pattern. It is that header removal is **implemented
twice** — once in code, once in prose — with nothing binding them. Correcting the
pattern re-arms the same trap for the next header change.

**Done when**: the body can be obtained from the helper that wrote the header,
there is exactly one implementation, and a header-format change that breaks the
round trip fails the suite.

**Maps to**: FR-006; NFR-003; C-004.

---

## ⚠ Why "just reuse `strip_header()`" is not enough

Today's `strip_header()` returns its input **unchanged** in two different
situations: when the first line does not match, and when the first line matches
but the sentinel is missing. That tolerance is correct for the capture path — a
foreign or headerless file is body, whole and unmodified.

But the function's signature loses the one fact the emitter needs: *was a
well-formed header recognised?* An emitter built on it would happily emit a
headerless or truncated artifact as though verified — and during recovery that
installs wrong content silently, which is the failure mode this whole mission is
about.

---

## Subtasks

### T014 — Refactor to one parser that reports recognition

**Steps**:

1. Introduce a single parser — e.g.
   `split_header(data: bytes) -> (recognized: bool, body: bytes)` — that both
   callers use. Keep it bytes-native; the capture path is bytes end to end and
   byte identity is the contract.
2. Recognition means: first line equals `HEADER_FIRST_LINE` **and** the
   `HEADER_SENTINEL` line is present. Anything else is `recognized=False` with
   the whole input as body.
3. Re-express `strip_header()` in terms of it so the **capture path's behaviour
   is unchanged** — foreign content still passes through untouched. All existing
   crontab_capture tests must still pass without modification.
4. **Do not** add a second recogniser in the CLI path. One implementation is the
   entire point; a `startswith` check in the emitter recreates the coupling being
   removed.

**Validation**:
- [ ] Existing `tests/office2/crontab_capture/` passes unchanged
- [ ] Exactly one place computes where the header ends

### T015 — `--emit-body`, failing closed

**Steps**:

1. Add `--emit-body`: read the artifact, parse, write the body to stdout, exit 0.
2. **Writes nothing.** It runs during recovery, when the artifact must not be
   disturbed. No pointer update, no artifact rewrite.
3. Fail closed, with `ERROR:` to stderr and a non-zero exit, when:
   - the artifact does not exist;
   - the artifact is empty;
   - `recognized` is False (headerless, foreign, or first line matches but the
     sentinel is missing).
   Emitting a partial or headerless body would install wrong content silently.
4. Body goes to stdout **raw** — no `SUMMARY:` line, no `INFO:` prefix — because
   the output is piped to `crontab -`. Diagnostics go to stderr. This is a
   deliberate, documented exception to the stdout convention; say so in a comment.
5. `--emit-body` is mutually exclusive with `--dry-run`/`--force`.

**Validation**:
- [ ] `--emit-body` on a good artifact emits only the body
- [ ] Missing / empty / headerless / sentinel-less all exit non-zero and emit nothing to stdout

### T016 — Round-trip test that fails when the format drifts

**Steps**:

Extend `tests/office2/crontab_capture/test_crontab_capture.py`:

1. **Round trip**: capture an injected `crontab -l` input, emit the body, assert
   byte-identical to the *original input* — not to the emitter's own output.
2. **Format-drift guard (SC-005)**: monkeypatch `build_header` to emit a header
   without the sentinel, capture, then assert `--emit-body` **fails** rather than
   returning something plausible. This is the test that would have caught the
   original regression.
3. Body containing the sentinel string mid-file still round-trips.
4. CRLF, missing trailing newline, and non-UTF-8 bodies round-trip.
5. Missing artifact, empty artifact, and foreign file each exit non-zero.
6. `--emit-body` leaves the artifact's mtime and the pointer untouched.

**Validation**:
- [ ] Test 2 fails if the emitter is made tolerant
- [ ] `python3 -m pytest tests/office2/crontab_capture/ -q` green

---

## Definition of Done

- [ ] One parser; capture behaviour unchanged; existing tests pass untouched
- [ ] `--emit-body` fails closed on every unrecognised input
- [ ] Round trip asserted against the original input
- [ ] Format-drift guard in place
- [ ] `make test` at or above the 6216 floor
- [ ] No file outside `owned_files` modified

## Out of scope

- The runbook that documents the new recovery command — **WP05**.
- The stale `quickstart.md` in the merged #895 mission: `kitty-specs/` is
  workflow-owned and must not be edited. The new runbook supersedes it.
- Changing the header format itself. It is fine; the coupling was the problem.

## Reviewer guidance

Check that `strip_header()`'s tolerant behaviour survives for the capture path —
a stricter capture would refuse to back up a crontab whose first line happens to
look like a header, which would be a worse bug than the one being fixed. Then
confirm the emitter is strict where capture is tolerant, and that both derive
from the same parser. Finally, verify test 2 actually fails when the emitter is
loosened; a drift guard that passes either way is decoration.
