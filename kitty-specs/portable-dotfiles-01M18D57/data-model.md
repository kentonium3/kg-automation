# Data Model: Portable shell config across both machines

**Mission**: `portable-dotfiles-01M18D57` · **Phase 1**

No database. The "data" is a set of files, the symlink relation between `$HOME` and the clone, and the platform-selection key that binds them.

## Entities

### Shared core
Platform-agnostic configuration read by both machines unchanged. Members: `zshenv` (PATH composition), `zshrc` (router, direnv hook, aliases, completion), `zprofile` (login-only), `bashrc` (PATH parity only).
**Invariant**: contains no path that exists on only one machine.

### Per-machine override
Supplies the platform-specific members the core deliberately omits. Selected by `KG_PLATFORM`. One directory per machine under `machines/`.
**Invariant**: exactly one override is active per machine; overrides are never read by the machine they do not belong to.

### Platform key — `KG_PLATFORM`
Values: `kg_macbook_pro`, `kg_office4`. Already consumed by `~/bin/claim_and_run.sh`.
**Invariant**: written *by* the installer, read *by* the configuration. Never both in the same direction — see the circularity in research R-003.

### Installed entry
A path in `$HOME` (`.zshenv`, `.zshrc`, `.zprofile`, `.bashrc`) that is a **symlink** into the local clone.
**Invariant**: every installed entry is a symlink, its target is inside the clone, and the target path is **relative to the machine** — never a committed absolute path (C-006).

### Backup set
A timestamped copy of every file the installer is about to replace, taken before any change.
**Invariant**: restorable with the clone absent from disk (NFR-003).

### Secrets template — `secrets.example`
Variable names only, no values. Documents the shape of `~/.config/secrets`, which is never committed and stays mode 600 (C-002, FR-012).
**Invariant**: contains zero credential values. A value appearing here is a defect, not a convenience.

## Relationships

```
KG_PLATFORM ──selects──▶ per-machine override
                              │
                              ├──sourced by──▶ shared core
                              ▼
$HOME entry ──symlink──▶ clone file ──git──▶ github.com/kentonium3/dotfiles (private)
     │
     └──backed up to──▶ backup set (independent of clone)
```

GitHub is **transport between machines**, not a symlink target. The symlink is always local.

## State transitions

| From | Event | To | Notes |
|---|---|---|---|
| Unmanaged | `install.sh` | Managed | Backup taken first; entries replaced by symlinks |
| Managed | `install.sh` (again) | Managed | **Idempotent** — no stacked PATH entries, no nested backups |
| Managed | clone deleted/moved | Degraded | Dangling symlinks; zsh starts with defaults. Usable, recoverable |
| Managed / Degraded | restore from backup set | Unmanaged | Works without the clone |
| Managed | local edit | Managed, **dirty** | Same inode, so `git status` sees it immediately |
| Managed, dirty | commit + push | Managed, clean | Other machine still stale until it pulls |

## Externally visible events

- **Assertion failure** — `verify-shell-env` exits non-zero naming the failed property. The only intended machine-readable signal.
- **Clone drift** — clone dirty or behind `origin`. Asserted, not merely observed (FR-008).
- **Account routing outcome** — the cyan `▸ work account` banner. Its **absence** is the tell, which is why absence must be asserted rather than watched for.

## Validation rules

1. Every `$HOME` entry is a symlink whose target resolves inside the clone.
2. `~/.local/bin` appears exactly once in PATH, ahead of the package-manager prefix, ahead of `/usr/bin`.
3. All three invocation types resolve identical `python3`, `git`, `node`.
4. Work repos route to `.claude-work`; personal repos to the default tree.
5. The router's work-repo list is a **glob**, not an enumeration.
6. The clone is clean and not behind `origin`.
7. `secrets.example` contains no value-shaped strings.
