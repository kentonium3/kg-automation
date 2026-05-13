# Research / Alignment: Inbox atomic-write permission preservation

**Mission**: `inbox-atomic-write-perm-preservation-01KRFS03`
**Date**: 2026-05-13

This document records the planning-phase decisions for this mission. There were no open `[NEEDS CLARIFICATION]` markers in the spec; this file captures the rationale behind each non-trivial choice so future readers can audit the reasoning.

---

## Decision 1: Logging sink and rotation strategy

**Decision**: Use `print(..., file=sys.stderr)` for the new per-write log line. No `logging` module, no new log file, no `RotatingFileHandler`.

**Rationale**:
- Every existing script in `scripts/inbox/` uses `print(...)` and `print(..., file=sys.stderr)` exclusively. None imports `logging`. Matching the existing pattern keeps the change minimal and avoids introducing a new convention for a single one-line log.
- The OpenClaw agent runtime captures stdout/stderr from the script into its own transcript files and applies its own rotation/retention policy. Using stderr therefore inherits the existing bounded-size guarantee without code changes here.
- Manual invocations (canary verification, ad-hoc) emit to the operator's terminal — appropriate scope.

**Alternatives considered**:
- `logging.RotatingFileHandler` writing to `~/second-brain/agents/state/inbox-atomic-write.log`: introduces a new file sink and rotation config. Rejected as scope creep for a single log line.
- Silent (no logging change at all): rejected — the original bug took hours to diagnose precisely because the failure was silent. One log line per write makes future perm regressions visible on first occurrence (Kent: A).

## Decision 2: Default mode for new files

**Decision**: `0o664` (owner rw, group rw, world r).

**Rationale**:
- The parent directory of inbox notes (`/home/kgale/second-brain/notes/01-Inbox/`) has the setgid bit set (`drwxrwsr-x kgale:secondbrain`). Files created within inherit the `secondbrain` group automatically.
- Both `claude` (the writer) and `kgale` (the `ob` daemon's user) are members of `secondbrain`. Mode `0o664` is the minimal mode that lets both of them read AND write the file.
- World-read is consistent with existing notes (most are `kgale:secondbrain 0664`).

**Alternatives considered**:
- `0o644` (group r, no group w): would still let `ob` read, satisfying the immediate bug. But strip operations from kgale's tooling (if any future agent runs as kgale) would need write — `0o664` is more future-proof at no cost.
- `0o600` (current broken behavior): rejected — this is the bug.

## Decision 3: No shared `_atomic_write` module

**Decision**: Duplicate the fix in both `inject_parse_error_marker.py` and `strip_parse_error_marker.py`. No new shared module.

**Rationale**: Locked in via discovery (Kent: A). Minimizes blast radius; only two files change. A future refactor can extract a shared helper if more inbox-write scripts are added.

## Decision 4: No UID preservation

**Decision**: Mode preservation only. UID after write will remain the writer's (e.g., `claude` for agent-driven writes).

**Rationale**: `chown` to a different uid requires `CAP_CHOWN`, which only root has on Linux. The writer is the unprivileged `claude` user. Mode preservation alone is sufficient to keep the file group-readable to `secondbrain` members, which solves the sync bug.

## Decision 5: Test strategy

**Decision**: Single new file `tests/inbox/test_atomic_write_perms.py` using `pytest`'s `tmp_path` fixture, parameterized over both helper modules. End-to-end verification (sync round-trip) is covered by the SC-002 manual canary, not by automated integration tests.

**Rationale**:
- The bug lives in a single function (`_atomic_write`) in two files. Unit-testing the function directly with `tmp_path` is the most precise test surface.
- Higher-level regression assertions in `test_callout_marker.py` etc. would duplicate coverage at the cost of additional test runtime. Trade-off rejected.
- End-to-end sync verification requires the actual office2 filesystem and `ob` daemon — not suitable for the unit-test suite. The SC-002 manual canary is the appropriate verification level.

## Decision 6: Deploy mechanism

**Decision**: Reuse `scripts/deploy/deploy-149.sh --apply --backup-confirmed` from mission #185.

**Rationale**: That deploy script already handles the rsync + permissions + symlink dance for `scripts/inbox/`. No new deploy code needed; the only thing landing on office2 is updated `.py` files in the same directory.

---

## Open questions

None. All technical decisions are locked.
