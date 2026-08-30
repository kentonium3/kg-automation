# Contract: `install.sh`

**Mission**: `portable-dotfiles-01M18D57`

## Purpose

Make `$HOME` read its shell configuration from the local clone, reversibly.

## Preconditions

- Clone present (default `~/repos/dotfiles`); `--source <path>` overrides.
- Platform resolvable via `uname -s` + hostname.
- Write access to `$HOME`.

## Behaviour

1. **Detect platform** independently of `KG_PLATFORM` (which does not yet exist — research R-003). Unrecognised platform → exit non-zero, change nothing.
2. **Back up** every target that exists, to `~/.dotfiles-backup-<UTC timestamp>/`, before any modification.
3. **Link** each managed entry: `$HOME/<name>` → `<clone>/core/<name>`. Replace an existing symlink; back up and replace a regular file; **never** silently clobber.
4. **Write `KG_PLATFORM`** into the selected override.
5. **Report** each action taken and the backup location.

## Postconditions

- Every managed `$HOME` entry is a symlink resolving inside the clone.
- The backup set restores the prior state **with the clone absent** (NFR-003).
- Re-running changes nothing and creates no second backup (idempotent).

## Invariants

- **No network access** beyond the clone/pull of this repo (NFR-001).
- **No lifecycle scripts**, no package installation (directive 051).
- **Never commits a symlink**, and never writes an absolute path into a tracked file (C-006).
- **Never touches** `~/.config/secrets` (C-002) or anything on office2 (C-001).

## Failure modes

| Condition | Behaviour |
|---|---|
| Unrecognised platform | exit non-zero, no change |
| Target exists and is not a symlink | back up, then replace |
| Backup directory not creatable | exit non-zero **before** any change |
| Clone missing | exit non-zero with the expected path |

## Exit status

`0` success (including a no-op re-run) · non-zero otherwise, with the reason on stderr.
