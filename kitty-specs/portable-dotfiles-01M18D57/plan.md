# Implementation Plan: Portable shell config across both machines

**Mission**: `portable-dotfiles-01M18D57`  
**Branch**: `feat/portable-dotfiles`  
**Spec**: `kitty-specs/portable-dotfiles-01M18D57/spec.md`  
**Created**: 2026-08-30

## Summary

Move the shell configuration of two developer machines out of loose untracked files in `$HOME` and into the private `kentonium3/dotfiles` repo, installed by **symlink** so there is exactly one copy of each file. Add `bin/verify-shell-env`, which asserts every property the configuration is supposed to guarantee — account routing, PATH composition, interpreter identity, direnv, behaviour across all three shell invocation types, and the clone's own git state.

The verification helper is not an accessory. All four motivating defects survived because verification was ad-hoc and per-case; versioning the files without adding assertion would leave that blind spot exactly as it is.

## Technical Context

**Language/Version**: zsh 5.9 (Linux Mint 22.3) / zsh 5.9 (macOS 26) — core, overrides, installer and helper are all zsh
**Primary Dependencies**: none beyond git and coreutils present by default on both machines. No package is installed.
**Storage**: plain files in a git repository; no database
**Testing**: `bin/verify-shell-env` — 11 assertions spawned across three shell invocation types; exit status is the contract
**Target Platform**: macOS 26.5.2 (Intel x86_64) and Linux Mint 22.3 (Ubuntu 24.04 base, x86_64)
**Project Type**: single
**Performance Goals**: `.zshenv` runs on every zsh invocation including scripts — no subprocess per shell; PATH set by static assignment, not `eval $(brew shellenv)`
**Constraints**: zero network access beyond cloning this repo; no GNU-only tools (`timeout` is absent on macOS); rollback must work with the clone deleted
**Scale/Scope**: 2 machines, 4 managed `$HOME` entries, 11 assertions, 7 implementation concerns

**Language rationale**: zsh for the core, overrides, installer, and helper. The helper asserts *zsh* behaviour, so writing it in bash or Python would test a shell other than the one being used. zsh is the login shell on both machines and is present by default on macOS.

**Target machines**:

| | MacBook Pro | office4 |
|---|---|---|
| OS | macOS 26.5.2, Intel `x86_64` | Linux Mint 22.3 (Ubuntu 24.04 base) |
| Package manager prefix | `/usr/local` (Intel Homebrew) | `/home/linuxbrew/.linuxbrew` |
| `python3` source | Homebrew `python@3.13` libexec | uv-managed shim in `~/.local/bin` |
| Driven remotely | no | **yes** — `ssh office4-kgale 'cmd'` |
| Login shell | zsh | zsh (`chsh`, 2026-08-28) |

**Install mechanism**: symlink from `$HOME` into the local clone at `~/repos/dotfiles`, created by the installer, never committed. A dated backup is taken first and is the repo-independent rollback path (NFR-003).

**Machine detection**: `KG_PLATFORM` is *set by* the configuration, so it cannot select the configuration — a circular dependency. The installer breaks it by detecting the platform independently (`uname -s` plus hostname) and writing `KG_PLATFORM` into the selected override. Downstream consumers keep using the variable exactly as today.

**Shell invocation types** — the axis that produced two of the four defects:

| Type | Files read | Where it occurs |
|---|---|---|
| Interactive login | `.zshenv` `.zprofile` `.zshrc` `.zlogin` | sitting at either machine |
| Interactive non-login | `.zshenv` `.zshrc` | the VS Code integrated terminal |
| **Non-interactive non-login** | **`.zshenv` only** | `ssh office4-kgale 'cmd'` — how agents drive office4 |

PATH must therefore live in `.zshenv` on office4. On the Mac it need not, because the Mac is never driven remotely. This is a legitimate per-machine difference and belongs in the override, not the core.

**Supply chain** (directive `051-supply-chain-install-safety`): this mission introduces **no third-party dependency** — no brew tap, pip index, npm registry, or MCP plugin. The single new source is `kentonium3/dotfiles`, Kent's own private repo, fetched over authenticated HTTPS via `gh`. The installer performs no network access beyond that clone or pull (NFR-001), and runs no lifecycle scripts. Registry authenticity, package freshness, and Node LTS considerations do not apply because no package is installed.

**Testing**: `bin/verify-shell-env` is the test surface. Per directive `034-test-first-development` it is written **before** the cutover of either machine, so the pre-change state is captured as a baseline and the post-change state is compared against it rather than eyeballed.

## Charter Check

| Directive | Status | Note |
|---|---|---|
| `001-architectural-integrity-standard` | Pass | One source of truth replacing per-machine copies. |
| `003-decision-documentation-requirement` | Pass | The copy-versus-symlink reversal and its reasoning are recorded in `research.md` (R-002). |
| `010-specification-fidelity-requirement` | Pass | Every IC traces to FR/NFR/C ids. |
| `024-locality-of-change` | Pass | Changes confined to the dotfiles repo plus one runbook; no office2 surface. |
| `025-boy-scout-rule` | Pass | Five stopgap blocks and six dangling or non-portable items retired as part of the work. |
| `030-test-and-typecheck-quality-gate` | Pass | `verify-shell-env` exit status is the gate; non-zero fails. |
| `031-context-aware-design` | Pass | Per-machine differences preserved deliberately rather than normalised away. |
| `033-targeted-staging-policy` | Pass | Scoped `git add`; no bulk staging. |
| `034-test-first-development` | Pass | Helper precedes cutover; baseline captured first. |
| `037-living-documentation-sync` | Pass | Bootstrap runbook registered in `INDEX.md` and `DEVELOPER_PORTAL.md` (FR-011). |
| `040-recurring-bug-structural-intervention` | **Central** | Four defects of one class — "it works in the shell I happened to test". The structural intervention is the assertion helper, not the repo. |
| `051-supply-chain-install-safety` | Pass | No third-party dependency introduced; see Technical Context. |

No violations. Complexity Tracking is therefore empty.

## Project Structure

### Documentation (this mission)

```
kitty-specs/portable-dotfiles-01M18D57/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    ├── installer-contract.md
    └── verify-shell-env-contract.md
```

### Source Code

Primary artifact is a **separate repository**, `kentonium3/dotfiles` (private), cloned to `~/repos/dotfiles` on each machine:

```
dotfiles/
├── core/
│   ├── zshenv            # PATH composition; read by every invocation type
│   ├── zshrc             # interactive: router, direnv hook, aliases, completion
│   ├── zprofile          # login-only concerns
│   └── bashrc            # thin: PATH parity only (FR-013)
├── machines/
│   ├── kg_macbook_pro/local.zsh
│   └── kg_office4/local.zsh
├── bin/
│   └── verify-shell-env
├── secrets.example       # variable names only, never values (FR-012, C-002)
├── install.sh
└── README.md
```

In **this** repository (kg-automation), the only change is documentation:

```
docs/runbooks/new-machine-bootstrap.md   # new (FR-011)
docs/INDEX.md                            # register
docs/DEVELOPER_PORTAL.md                 # register
```

## Complexity Tracking

*No Charter Check violations. Section intentionally empty.*

## Implementation Concern Map

> Implementation concerns are not work packages. `/spec-kitty.tasks` translates these into executable WPs.

### IC-01 — Repository skeleton and contracts

- **Purpose**: Establish the layout, the `KG_PLATFORM` override-selection convention, and the two behavioural contracts so later concerns build against a fixed shape.
- **Relevant requirements**: FR-001, FR-002, C-004
- **Affected surfaces**: `dotfiles/` root, `core/`, `machines/`, `README.md`
- **Sequencing/depends-on**: none
- **Risks**: Layout churn later is expensive because the installer and helper both encode paths. Fix the shape before writing either.

### IC-02 — Shared core

- **Purpose**: The platform-agnostic configuration — account router, PATH composition rules, direnv hook, aliases, guards.
- **Relevant requirements**: FR-002, FR-004, FR-005, FR-007, C-005
- **Affected surfaces**: `core/zshenv`, `core/zshrc`, `core/zprofile`
- **Sequencing/depends-on**: IC-01
- **Risks**: **The router's work-repo list must stay a glob.** Converting it back to an explicit list is what caused the silent misrouting; the explanatory comment is load-bearing and must survive. PATH must be *composed* from declared slots and deduplicated (`typeset -U path`), not accumulated — `~/.local/bin` currently appears three times on the MacBook.

### IC-03 — Per-machine overrides

- **Purpose**: Supply the platform-specific members the core deliberately does not name.
- **Relevant requirements**: FR-002, FR-006
- **Affected surfaces**: `machines/kg_macbook_pro/local.zsh`, `machines/kg_office4/local.zsh`
- **Sequencing/depends-on**: IC-02
- **Risks**: The Mac needs Homebrew Cellar libexec paths for `python3` and `node`, plus the VS Code CLI path; office4 needs none of those and instead needs PATH in `.zshenv` for remote invocation. Normalising these into the core would break one machine or the other.

### IC-04 — Installer

- **Purpose**: Symlink `$HOME` entries into the clone after a dated backup, detect the platform, and write `KG_PLATFORM`.
- **Relevant requirements**: FR-003, FR-013, NFR-001, NFR-003, C-006
- **Affected surfaces**: `install.sh`
- **Sequencing/depends-on**: IC-02, IC-03
- **Risks**: Must be idempotent — a second run must not stack PATH entries or nest backups. Must never create a symlink with an absolute path inside a tracked file. Must refuse to clobber an existing non-symlink without backing it up first.

### IC-05 — Environment assertion helper

- **Purpose**: Assert every guaranteed property, including the clone's own git state. This is the mission's structural intervention.
- **Relevant requirements**: FR-008, NFR-002, NFR-004
- **Affected surfaces**: `bin/verify-shell-env`
- **Sequencing/depends-on**: IC-01 (contract only) — deliberately **not** blocked on IC-02/03, so it can capture the pre-change baseline per directive 034
- **Risks**: Must spawn all three invocation types rather than inspecting the current one; must run on both platforms; exit status is the contract. A helper that only checks the shell it is running in reproduces the exact blind spot this mission exists to close.

### IC-06 — Cutover of both machines

- **Purpose**: Install from the repo on the Mac and office4, retire the five stopgap blocks, reconcile the stale `.bashrc`/`.profile` pair, and drop the non-portable items.
- **Relevant requirements**: FR-009, FR-010, FR-012, C-001, C-002
- **Affected surfaces**: `$HOME` on both machines; `secrets.example` in the repo
- **Sequencing/depends-on**: IC-04, IC-05
- **Risks**: Highest-risk concern — it changes live shells. Run the helper *before* to capture baseline and *after* to prove parity. office4 must be done with a second session open. The Mac is the machine the mission is executing on, so its cutover is last.

### IC-07 — Bootstrap runbook and registration

- **Purpose**: Document bringing up a machine from nothing, including the private-repo authentication step that must precede fetching any config.
- **Relevant requirements**: FR-011
- **Affected surfaces**: `docs/runbooks/new-machine-bootstrap.md`, `docs/INDEX.md`, `docs/DEVELOPER_PORTAL.md`
- **Sequencing/depends-on**: IC-06 (document what was actually done, not what was intended)
- **Risks**: The auth-before-config ordering is easy to omit and makes the runbook unusable on a genuinely fresh machine.
