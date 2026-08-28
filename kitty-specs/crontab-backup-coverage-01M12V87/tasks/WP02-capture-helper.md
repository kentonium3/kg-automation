---
work_package_id: WP02
title: Crontab capture helper
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-003
- FR-004
- FR-005
planning_base_branch: feat/crontab-backup-coverage
merge_target_branch: feat/crontab-backup-coverage
branch_strategy: Planning artifacts for this mission were generated on feat/crontab-backup-coverage. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/crontab-backup-coverage unless the human explicitly redirects the landing branch.
created_at: '2026-08-28T00:37:21Z'
subtasks:
- T006
- T007
- T008
- T009
- T010
- T011
phase: Phase 1 - Make the crontab recoverable
history:
- at: '2026-08-28T00:37:21Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/office2/crontab_capture.py
create_intent:
- scripts/office2/crontab_capture.py
- tests/office2/crontab_capture/__init__.py
- tests/office2/crontab_capture/test_crontab_capture.py
execution_mode: code_change
owned_files:
- scripts/office2/crontab_capture.py
- tests/office2/crontab_capture/**
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP02 — Crontab capture helper

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load`
(profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope,
and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch at prompt creation**: `feat/crontab-backup-coverage`
- **Final merge target**: `feat/crontab-backup-coverage`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates `base_branch` when
  the worktree is created.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch.

---

## Objectives & Success Criteria

Build `scripts/office2/crontab_capture.py`: a system-pipeline helper that copies
the `claude` user's crontab into `/data/services/`, which the restic backup
already covers. It runs unattended on an hourly timer (installed by WP03).

The subtlety worth internalising before writing code: **this helper runs during
the same incidents it protects against.** If the crontab is being destroyed at
13:21 and the capture fires at 13:22, a naive implementation overwrites the good
artifact with an empty one and the backup faithfully preserves the emptiness.
The refusal rules in T008 and T009 are therefore the core of the work, not
defensive garnish.

**Done when**: the helper captures, refuses to destroy good state, writes a
health signal on every run, and is covered by tests that inject the crontab
reader rather than touching a real crontab.

**Maps to**: FR-001, FR-003, FR-004, FR-005, NFR-003, NFR-005.

---

## Required reading

- `docs/design/helper-script-conventions.md` — §1 storage location (this is a
  "System pipeline", hence `scripts/office2/`), §2 CLI contract, §3 stdout
  convention, §4 atomic state mutation, §5 idempotency, §8 testing.
- `kitty-specs/crontab-backup-coverage-01M12V87/data-model.md` — the exact
  artifact and pointer shapes. Follow it; do not invent field names.
- `scripts/openclaw/deploy/deploy_agent_prompts.py` — `write_last_tick()` around
  line 395 is the canonical freshness-pointer writer. Match its shape.

---

## Subtasks

### T006 — Scaffold the CLI

**Purpose**: A stable, testable entry point that follows the repo's helper
contract.

**Steps**:

1. Create `scripts/office2/crontab_capture.py` with a module docstring stating
   what it captures, where it writes, and why (reference #895).
2. argparse CLI — **no** `sys.argv` hand-parsing. Flags:
   - `--artifact-path` (default `/data/services/host-state/crontabs/claude.crontab`)
   - `--state-path` (default `/data/services/host-state/last-tick.json`)
   - `--force` — bypass the shrink guard only (never the empty guard)
   - `--dry-run` — compute and report, write nothing
3. Exit codes per §2 of the conventions: `0` success, `1` operational error,
   `2` usage error.
4. Final stdout line is always `SUMMARY: key=value ...` — include at minimum
   `captured=`, `changed=`, `bytes=`, `refused=`.
5. `INFO:` / `WARN:` prefixes on stdout; `ERROR:` to **stderr**.

**Validation**:
- [ ] `python3 scripts/office2/crontab_capture.py --help` works
- [ ] Invalid flag exits 2

### T007 — Read the crontab and compose the artifact

**Purpose**: Produce a file that a human can reinstall verbatim during an
incident.

**Steps**:

1. Read via `crontab -l` as a **subprocess**, wrapped in an injectable callable
   (e.g. a module-level `_read_crontab()` default that tests replace). Do not
   call `subprocess` directly from the write path — that is what makes T011
   testable without a real crontab.
2. Compose the artifact exactly as `data-model.md` specifies: a provenance header
   of `#`-comments (`captured-by`, `captured-at-utc`, `source-user`,
   `source-host`, and the reinstall note), then the verbatim `crontab -l` body.
3. The body below the header must be **byte-identical** to `crontab -l` output.
   The whole file is deliberately not byte-identical — the header is what makes a
   file found in a months-old snapshot self-describing.
4. Header comments are safe: cron ignores leading `#` lines, so
   `crontab <file>` works on the artifact as written.

**Validation**:
- [ ] Body below the header round-trips byte-for-byte
- [ ] `artifact_bytes` in the pointer reflects the body size

### T008 — Refuse empty or failed reads

**Purpose**: FR-004. The destruction-window case.

**Steps**:

1. If `crontab -l` exits non-zero, **or** returns empty/whitespace-only output:
   - do **not** touch the artifact;
   - write the pointer with `status: "error"` and a non-zero `exit_code`;
   - emit `WARN:` explaining the refusal and `ERROR:` to stderr;
   - exit `1`.
2. Preserving the old artifact is the right *data* outcome but is **not** a
   healthy run and must not be reported as one. A silent "nothing to do" here
   would hide exactly the condition worth alerting on.
3. `--force` must **not** override this guard. It exists only for T009.

**Validation**:
- [ ] Empty read leaves an existing artifact byte-identical
- [ ] Empty read produces `status: error`, non-zero `exit_code`, process exit 1
- [ ] `--force` does not bypass this rule

### T009 — Shrink guard

**Purpose**: A non-empty but truncated read is still destructive, and
`artifact_bytes` alone is diagnostic, not protective.

**Steps**:

1. When an artifact already exists, compare the new body length against the
   stored body length (exclude the header from both sides).
2. If the new body is **more than 50% smaller**, refuse exactly as T008 does:
   preserve the artifact, `status: "error"`, non-zero exit, `WARN:` naming both
   sizes.
3. `--force` bypasses **this** guard only, and its use must be logged at `WARN:`
   so a forced shrink is visible in the record.
4. **First run** — no existing artifact — is not a shrink. Never refuse it.

**Rationale to preserve in a comment**: `crontab -l` reading a local spool file is
unlikely to return a partial success. "Unlikely" is not an invariant, and the
cost of the guard is one integer comparison against a failure mode that silently
destroys the artifact this whole mission exists to create.

**Validation**:
- [ ] 60% shrink is refused; 10% shrink is accepted
- [ ] `--force` allows the 60% shrink and logs a `WARN:`
- [ ] First run with no prior artifact is never refused

### T010 — Freshness pointer

**Purpose**: FR-005. Make a dead capture visible instead of assumed-working.

**Steps**:

1. Write the pointer on **every** run — success, refusal, and error alike.
2. Fields exactly per `data-model.md`: `status`, `exit_code`,
   `completed_at_utc`, `artifact_path`, `artifact_bytes`, `artifact_changed`,
   `source_user`.
3. `completed_at_utc` must be present and ISO-8601 UTC — it is the canary's
   preferred timestamp key, and a pointer without it is judged *unknown*, never
   healthy.
4. Write atomically: `tempfile.mkstemp` in the destination directory, then
   `os.replace`. Same for the artifact in T007.
5. A pointer-write failure must not crash the run — losing the freshness signal
   is preferable to losing the capture. Match the `except OSError: pass`
   discipline in `deploy_agent_prompts.py:420`.

**Validation**:
- [ ] Pointer written on success, refusal, and error paths
- [ ] Atomic: a simulated mid-write failure leaves no partial file
- [ ] `completed_at_utc` always present

### T011 — Tests

**Purpose**: These behaviours are load-bearing during incidents and must not
regress.

**Steps**:

Create `tests/office2/crontab_capture/test_crontab_capture.py` covering:

1. **Happy path** — injected crontab text produces an artifact whose body matches
   byte-for-byte, and a `status: success` pointer.
2. **Reinstallability** — the written file parses as a crontab: header lines all
   start with `#`, body lines are unmodified.
3. **Empty refusal** — pre-existing artifact survives unchanged; pointer says
   error; exit 1.
4. **Failed-read refusal** — non-zero `crontab -l` exit behaves as above.
5. **Shrink refusal and `--force` override**, plus the first-run carve-out.
6. **Idempotency (NFR-003)** — two runs over unchanged input leave artifact
   content *and* mtime untouched while the pointer timestamp advances.
7. **Atomicity** — simulate a failure during write; assert no partial artifact
   and no partial pointer.

Use `tmp_path`; never read or write a real crontab or a real `/data` path.

**Validation**:
- [ ] `python3 -m pytest tests/office2/crontab_capture/ -v` passes
- [ ] Tests do not invoke the real `crontab` binary

---

## Definition of Done

- [ ] All six subtasks complete with their validation boxes checked
- [ ] `python3 -m pytest tests/office2/crontab_capture/ -v` green
- [ ] Full suite still at or above the 6177 floor: `make test`
- [ ] Helper honours the CLI, stdout, atomic-write, and idempotency conventions
- [ ] No file outside `owned_files` modified

## Out of scope

- The systemd unit, timer, deploy entrypoint, and manifest — **WP03**.
- Registering the component in `service-inventory.json` — **WP05**.
- Capturing the `kgale` or `root` crontabs. Both return permission-denied to an
  unprivileged reader (verified), so covering them needs sudo, which is Tier 0.
  Do not add a `sudo` call path.

## Reviewer guidance

Read T008 and T009 first — a capture that cannot refuse is worse than no capture,
because it manufactures a confident empty backup. Confirm `--force` bypasses only
the shrink guard. Confirm the pointer is written on the refusal path with an
error status, not skipped: a refusal that reports healthy is the #891 defect
class reappearing. Finally, confirm the tests inject the reader rather than
shelling out to `crontab`.
