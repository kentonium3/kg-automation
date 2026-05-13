# Spec: Inbox atomic-write permission preservation

**Mission**: `inbox-atomic-write-perm-preservation-01KRFS03`
**Source issue**: [#254](https://github.com/kentonium3/kg-automation/issues/254)
**Mission type**: `software-dev`
**Status**: draft
**Target branch**: `main`

## Summary

Inbox marker helper scripts (`inject_parse_error_marker.py`, `strip_parse_error_marker.py`) silently break Obsidian Sync for any note they touch. After they write to a note, the file's permissions are reset to the writing agent's restrictive defaults instead of the original note's permissions. The Obsidian Sync daemon on office2 then cannot read the file and stops propagating cloud updates to it.

This mission restores the invariant that the original note's access permissions survive a marker injection or strip operation, and that newly created notes use a permission mode compatible with shared access on office2.

## User Scenarios & Testing

### Primary scenario — parse-failure marker injection

**As** the Felix inbox automation,
**when** I detect a parse failure on an inbox note and inject a callout marker referencing the GitHub issue,
**then** the note remains readable and writable by other members of the `secondbrain` group on office2,
**so that** Obsidian Sync continues to propagate cloud edits to and from the note.

**Acceptance**:
- After `inject_parse_error_marker.py` runs as `claude` against a `kgale`-owned note in `01-Inbox/`, the resulting file's mode is identical to the pre-call mode (or `0o664` if the file did not previously exist).
- A subsequent edit made on the Mac side (via Obsidian) propagates to office2 within Obsidian Sync's normal latency.

### Secondary scenario — parse-failure marker stripping

**As** the Felix inbox automation,
**when** I detect that an inbox note's parse error has been resolved and strip the callout marker,
**then** the note's mode is unchanged from before the strip,
**so that** Obsidian Sync continues to operate on it.

**Acceptance**:
- After `strip_parse_error_marker.py` runs as `claude` against a `claude:secondbrain 0664` note (the typical state after a prior `inject_*` call with the fix in place), the resulting mode is `0664`.

### Edge cases

- **New file write** (target does not exist): result has mode `0o664` (group-readable and group-writable), not the umask-derived `0600`.
- **Read-only original** (mode `0o444`): preserved as `0o444`. Mission does not "upgrade" perms; it preserves what was there.
- **Concurrent writes**: atomic-replace guarantee preserved (rename remains the final operation).

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | `_atomic_write` in `scripts/inbox/inject_parse_error_marker.py` shall preserve the mode of an existing target file when replacing it. | proposed |
| FR-002 | `_atomic_write` in `scripts/inbox/strip_parse_error_marker.py` shall preserve the mode of an existing target file when replacing it. | proposed |
| FR-003 | Both `_atomic_write` helpers shall assign mode `0o664` to a newly created target when the target did not previously exist. | proposed |
| FR-004 | Both `_atomic_write` helpers shall continue to provide atomic replace semantics (no partial-state file visible at the target path). | proposed |
| FR-005 | Unit tests shall cover mode-preservation for existing files at modes `0o600`, `0o644`, and `0o664` for both scripts. | proposed |
| FR-006 | Unit tests shall cover the `0o664` default for new files for both scripts. | proposed |

### Non-Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-001 | Mode-preservation step shall add no more than 5 ms to a single `_atomic_write` invocation on office2-class hardware. | proposed |
| NFR-002 | Fix shall not require elevated privileges (no `sudo`, no `root`). | proposed |

### Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | UID preservation is out of scope: `chown` to a different uid requires `CAP_CHOWN` (root only on Linux), and the writing agent runs as the unprivileged `claude` user. The mission preserves mode only; UID will remain the writer's. | accepted |
| C-002 | Fix is duplicated verbatim in both helper scripts. No shared module is introduced. | accepted |
| C-003 | The mission does not change the behavior of the Obsidian Sync daemon (`ob`). Once perms are no longer orphaned, the daemon's existing behavior is sufficient. | accepted |
| C-004 | The mission does not address `ob`'s per-file error caching (files already stuck require manual recovery — documented separately). | accepted |

## Success Criteria

- **SC-001**: After deploying the fix to office2, running `inject_parse_error_marker.py` as `claude` on a `kgale`-owned note leaves the file group-readable to users in the `secondbrain` group. (Verifiable by `stat` showing mode preserved or set to `0o664`.)
- **SC-002**: An end-to-end canary — inject a marker to a fresh inbox note, then edit the same note on Mac side via Obsidian — confirms the office2 copy receives the cloud update within 5 minutes, with no manual permission or deletion intervention required.
- **SC-003**: All 85 existing `tests/inbox/` tests continue to pass. New unit tests for `_atomic_write` mode handling pass.

## Assumptions

- The parent directory of inbox notes (`/home/kgale/second-brain/notes/01-Inbox/`) retains its setgid bit (`drwxrwsr-x kgale:secondbrain`), so group inheritance for new files works automatically. (Verified 2026-05-13.)
- Both helper scripts will continue to run as the `claude` user under the inbox-processing OpenClaw agent. No change to agent identity is required by this mission.
- The `claude` and `kgale` accounts on office2 will both remain members of the `secondbrain` group. (Verified 2026-05-13.)

## Dependencies

- None on other open work. This is a self-contained bug fix.
- Follow-up to #185 (mission delivered the affected helpers) and prerequisite to end-to-end verification of #253 (agent autonomy gap on Step 6.2).

## Out of Scope

- Refactoring `_atomic_write` into a shared module (declined per discovery choice A; would be a separate refactor mission).
- UID preservation across writes (impossible without root).
- Recovery tooling for files already stuck in the orphaned state (manual `rm` of the file unsticks it; no broader migration is needed).
- Changing the OpenClaw agent's identity or filesystem capabilities.
- Any change to Obsidian Sync configuration or the `ob` daemon's retry behavior.
