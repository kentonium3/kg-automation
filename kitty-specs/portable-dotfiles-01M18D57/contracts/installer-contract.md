# Contract: `install.sh`

**Mission**: `portable-dotfiles-01M18D57` · revised after post-plan review (F1, F2, F7)

## Purpose

Make `$HOME` read its shell configuration from the local clone, **transactionally** and reversibly.

## Preconditions

- Clone present (default `~/repos/dotfiles`); `--source <path>` overrides.
- Platform resolvable, or supplied via `--platform kg_macbook_pro|kg_office4`.
- Write access to `$HOME`.

## Platform detection

`uname -s` plus hostname, as a **convenience only**. Hostname case, FQDN form, a rename, or a rebuild can all defeat it.

- `--platform <id>` always wins.
- Ambiguous or unrecognised detection → **refuse**, exit non-zero, change nothing. Never guess.
- On success, write a local untracked identity file so subsequent runs need no detection.

## Transaction

The critical property: **a failed install leaves the machine exactly as it was.** A partial install is more dangerous than no install, because it can produce a mixed old/new environment on the machine you are logged into — or on office4, reached only over the shell being replaced.

1. **Preflight.** Resolve every managed target and every directory to be written. Any problem → exit before touching anything.
2. **Manifest.** Record for each managed path: prior **type** (regular file / symlink / **absent**), symlink target if any, and mode. Write it into the backup directory. This is what makes rollback correct — a backup of existing files alone cannot describe a `.bashrc` that did not previously exist.
3. **Backup.** Copy every existing target into `~/.dotfiles-backup-<UTC timestamp>/`.
4. **Install under a trap.** `trap` restores from the manifest on any error or signal. Each entry is swapped by writing a temporary symlink and `mv`-ing it into place, so no entry is ever momentarily missing.
5. **Write `KG_PLATFORM`** into the selected override.
6. **Emit `restore.sh`** into the backup directory — a generated, self-contained rollback (see below).
7. **Report** every action and the backup path.

## Rollback — `restore.sh`

Generated per install, self-contained, and correct where `cp -a backup/. ~/` is not.

1. **Remove** each managed entry first. Copying over a live symlink follows it and writes through to the clone.
2. **Restore** entries whose prior type was file or symlink, with original mode.
3. **Delete** entries whose prior type was **absent**.
4. Never require the clone to be present.

## Postconditions

- Every managed `$HOME` entry is a symlink resolving inside the clone.
- Backup directory contains the manifest and `restore.sh`.
- Re-running changes nothing and creates no second backup (idempotent).

## Invariants

- **No network access** beyond the clone/pull of this repo (NFR-001).
- **No lifecycle scripts**, no package installation (directive 051).
- **Never commits a symlink**; never writes an absolute path into a tracked file (C-006).
- **Never touches** `~/.config/secrets` (C-002) or anything on office2 (C-001).
- **Never leaves a partial install** (NFR-005).

## Failure modes

| Condition | Behaviour |
|---|---|
| Ambiguous / unrecognised platform | exit non-zero, no change, suggest `--platform` |
| Preflight problem | exit non-zero **before** any modification |
| Failure mid-install | trap restores from manifest; machine returns to pre-install state |
| Backup dir not creatable | exit non-zero before any change |
| Clone missing | exit non-zero with the expected path |

## Exit status

`0` success (including a no-op re-run) · non-zero otherwise, reason on stderr.
