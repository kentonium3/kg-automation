# Mission Specification: Portable shell config across both machines

**Mission Branch**: `feat/portable-dotfiles`  
**Created**: 2026-08-30  
**Status**: Draft  
**Input**: kg-automation#911 — extract shell configuration into the private `kentonium3/dotfiles` repo so the MacBook Pro and office4 read one versioned source, and add a helper that asserts the shell environment rather than trusting it.

## User Scenarios & Testing *(mandatory)*

Kent operates two development machines — a MacBook Pro (Intel, macOS 26) and office4 (Linux Mint 22.3) — and drives office4 both at its keyboard and remotely over SSH. Agents run on both. The shell configuration decides which Anthropic account a session authenticates as, which Python interpreter runs, and whether the commit gate can execute at all.

### User Story 1 - One versioned source of shell truth (Priority: P1)

As Kent, I want both machines' shell configuration to come from one versioned repo, so that a fix made once applies everywhere and cannot silently drift.

**Why this priority**: The account router decides whether work runs as `kent@spec-kitty.ai` or `kent@intentional.biz`. It currently exists in exactly two untracked files with no backup and no history. A clobber or a careless port silently reverts work sessions to the personal account — this already happened once and produced no error.

**Independent Test**: Change a shared setting in the repo, run the installer on both machines, and confirm both reflect the change and neither retains a hand-edited copy.

**Acceptance Scenarios**:

1. **Given** a shared setting changed in the repo, **When** the installer runs on both machines, **Then** both reflect it and `git status` in the dotfiles repo is clean.
2. **Given** a work repo on either machine, **When** `claude-whoami` runs there, **Then** it reports `kent@spec-kitty.ai`; in a personal repo it reports `kent@intentional.biz`.
3. **Given** the router's work-repo list, **When** it is inspected, **Then** it is a glob over the employer namespace, not an enumeration.

### User Story 2 - Assert the environment instead of trusting it (Priority: P1)

As Kent or an agent, I want a single command that asserts the whole shell environment, so that a misconfiguration is caught deliberately rather than discovered by a failure hours later.

**Why this priority**: All four motivating defects survived because verification was ad-hoc and per-case — each was "it works in the shell I happened to test". Versioning the files without adding assertion leaves the blind spot intact.

**Independent Test**: Deliberately break one property (reorder PATH, unset the direnv hook), run the helper, and confirm it exits non-zero and names the failed assertion.

**Acceptance Scenarios**:

1. **Given** a correctly configured machine, **When** `verify-shell-env` runs, **Then** it exits 0.
2. **Given** PATH reordered so brew precedes `~/.local/bin`, **When** it runs, **Then** it exits non-zero and names the ordering assertion.
3. **Given** office4, **When** it runs under an interactive login shell, an interactive non-login shell, and `ssh office4-kgale 'cmd'`, **Then** all three are exercised and reported separately.

### User Story 3 - Bring up a new machine from the repo (Priority: P2)

As Kent, I want a documented bootstrap path, so that a third machine — or a rebuild of either existing one — starts from the same source rather than by copying files by hand.

**Why this priority**: office4 was built by hand over one session and accumulated five undocumented blocks. Repeating that is the failure this mission exists to prevent, but it is a lower priority than protecting the identity control already in production.

**Independent Test**: On a scratch account or container, clone the repo, run the installer, run the helper, and confirm a working shell without manual edits.

**Acceptance Scenarios**:

1. **Given** a machine with only git and a shell, **When** the runbook is followed, **Then** the shell is configured and `verify-shell-env` passes.
2. **Given** the bootstrap runbook, **When** `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md` are checked, **Then** it is registered in both.

### Edge Cases

- What happens when the dotfiles repo is absent or unreachable at rollback time? The dated backup must restore the prior state without it.
- What happens when a machine-specific path (Homebrew prefix, Cellar libexec) does not exist on the other machine? The core must not reference it; the per-machine override supplies it.
- What happens when a shell starts non-interactively over SSH? PATH must still resolve on office4, which reads only `.zshenv` in that case.
- What happens when a transitive package dependency installs a competing `python3`? PATH precedence must be explicit, so the intended interpreter wins regardless of install order.
- What happens when a future repo joins the employer namespace? The glob must route it without an edit.
- What happens when the installer runs twice? It must be idempotent and must not stack duplicate PATH entries.
- What happens when the dotfiles clone is deleted or moved? `$HOME` symlinks dangle and zsh starts with defaults — a degraded but usable shell, recoverable from the dated backup without the repo.
- What happens when a local edit is never pushed, or the other machine is never pulled? The helper must fail, because the clone is dirty or behind `origin`.
- What happens when the installer fails partway — after `.zshenv` is swapped but before `.zshrc`? The trap must restore every entry, not leave a mixed environment.
- What happens when `.bashrc` did not exist before install? Rollback must **delete** it, not leave an orphan the backup cannot describe.
- What happens when `~/.config/secrets` is absent on a fresh machine? Startup must stay silent; the helper reports it as a distinct failure rather than a routing failure.
- What happens when hostname case, FQDN form, or a rebuild changes detection? `--platform` must override, and ambiguous detection must refuse rather than guess.
- What happens when an unmanaged `~/bin` script shadows a managed one? Either it is in scope, or its resolved path is asserted.
- What happens on a new machine with no git credentials? The repo is private, so bootstrap must authenticate before it can fetch shell config at all.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status |
|----|-------|------------|----------|--------|
| FR-001 | Versioned source | As Kent, I want shell config held in the private `kentonium3/dotfiles` repo so that it is versioned, reviewable, and backed up. | High | Open |
| FR-002 | Core plus per-machine override | As Kent, I want a shared core and a per-machine override keyed on `KG_PLATFORM` so that legitimate machine differences do not fork the whole config. | High | Open |
| FR-003 | Transactional symlink install | As Kent, I want the installer to preflight every target, write a backup **manifest**, then swap entries with a trap that restores on any failure, so that a partial failure cannot leave a mixed old/new environment on the machine I am logged into. It must accept `--platform` to override auto-detection and refuse to proceed on ambiguous detection. | High | Open |
| FR-004 | Account router preserved | As Kent, I want the router carried over with its globbed work-repo list and explanatory comment intact so that work sessions cannot silently use the personal account. | High | Open |
| FR-005 | Composed, deduplicated PATH | As Kent, I want PATH composed from documented slots and deduplicated so that precedence is declared rather than an artifact of append order. | High | Open |
| FR-006 | Per-invocation-type placement | As Kent, I want office4's PATH in `.zshenv` so that shells driven by `ssh host 'cmd'` resolve tools identically to interactive ones. | High | Open |
| FR-007 | direnv hook placement | As Kent, I want the direnv hook in `.zshrc` so that it loads for interactive shells, which is the only context `precmd` hooks apply to. | Medium | Open |
| FR-008 | Environment assertion helper | As Kent or an agent, I want `bin/verify-shell-env` to assert routing, PATH order, interpreter version, direnv, all three local invocation types, **a real end-to-end `ssh office4-kgale 'cmd'` probe** (local `zsh -c` simulates the shell mode but not sshd, PAM, login-shell selection, or non-TTY behaviour), the router API over sampled paths, and that the dotfiles clone is clean and not behind `origin` — so that misconfiguration, untested remote behaviour, and unpushed drift are all caught deliberately. | High | Open |
| FR-009 | Retire stopgap blocks | As Kent, I want office4's five stopgap blocks removed and the stale `.bashrc`/`.profile` pair reconciled so that no machine carries undocumented config. | High | Open |
| FR-010 | Drop non-portable items | As Kent, I want macOS-only scripts, the launchd job, the unguarded brew eval, and three dangling paths dropped or replaced so that the core runs cleanly on both platforms. | Medium | Open |
| FR-011 | Bootstrap runbook | As Kent, I want a new-machine bootstrap runbook registered in `INDEX.md` and `DEVELOPER_PORTAL.md` so that a rebuild does not repeat office4's hand-built history. | Medium | Open |
| FR-014 | Manifest-based rollback | As Kent, I want rollback driven by a manifest recording each managed path's prior **type, target, mode, and absence**, so that restore removes managed symlinks first, restores what existed, and deletes what did not — rather than copying over a live symlink. | High | Open |
| FR-015 | Secrets contract | As Kent, I want startup to tolerate a missing `~/.config/secrets` silently, and the helper to assert its presence, mode 600, and required variable names, so that a fresh machine does not emit errors before the file exists and routing is never silently degraded by its absence. | High | Open |
| FR-016 | Router observable API | As an agent, I want the router to expose a pure `claude_account_for_path <path>` function and to hold its work-repo patterns in an inspectable array, so that routing can be asserted over sampled paths rather than inferred from a banner. | High | Open |
| FR-017 | PATH-adjacent script inventory | As Kent, I want every PATH entry and shell-referenced helper inventoried, and each either brought into the repo or explicitly scoped out with its resolved path asserted, so that unmanaged `~/bin` and `~/helper-scripts` cannot shadow managed ones or diverge between machines. | Medium | Open |
| FR-013 | Minimal bash parity | As Kent, I want a thin `~/.bashrc` setting the same PATH as zsh so that `#!/bin/bash` scripts and `bash -lc` resolve the same interpreters an interactive session does. | Medium | Open |
| FR-012 | Secrets shape documented | As Kent or an agent, I want a `secrets.example` naming the variables `~/.config/secrets` must define, with no values, so that a new machine knows what to create and an agent knows what to look for. | Medium | Open |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Offline installer | The installer performs zero network fetches beyond cloning or pulling the dotfiles repo itself; count of other network calls is 0. | Security | High | Open |
| NFR-002 | Cross-platform helper | `verify-shell-env` runs on macOS 26 (Intel) and Linux Mint 22.3; exit status is the contract — 0 when every assertion passes, non-zero naming the first failure otherwise. | Portability | High | Open |
| NFR-003 | Repo-independent rollback | The dated backup restores the previous shell config in a single command with the dotfiles repo absent from disk. | Reliability | High | Open |
| NFR-005 | Install atomicity | A failed install leaves the machine in exactly its pre-install state: 0 managed entries changed, verified by running the installer with an induced mid-run failure and confirming `verify-shell-env` output is byte-identical to the pre-run baseline. | Reliability | High | Open |
| NFR-004 | Silent login | A login shell on either machine emits 0 bytes on stderr — no Homebrew error on Linux, no missing-path noise on macOS. | Reliability | Medium | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | office2 untouched | No file on office2 changes. It is a managed host; both target machines are unmanaged peers per ADR-0008. | Technical | High | Open |
| C-002 | Secrets stay out | `~/.config/secrets` is never committed and retains mode 600; only its variable names are documented. | Security | High | Open |
| C-003 | No new package sources | No brew tap, pip index, npm registry, or MCP plugin is introduced. | Security | High | Open |
| C-004 | Repo stays private | `kentonium3/dotfiles` remains private; kg-automation is public and must not gain shell config. | Security | High | Open |
| C-005 | Routing unchanged | No change to which repos map to which account beyond the glob fix already applied on 2026-08-29. | Technical | High | Open |
| C-006 | Local symlinks, never committed | Installation creates symlinks from `$HOME` into the **local** clone. It must never commit a symlink, nor create one with an absolute path baked into a tracked file — 144 committed absolute symlinks broke on office4 during this migration with no supported recovery path. Locally-created symlinks into a local clone are a different mechanism and are the point: one file, so the repo cannot go stale. | Technical | High | Open |

### Key Entities

- **Shared core**: platform-agnostic shell configuration — the account router, PATH composition rules, aliases, and guards. Read by both machines unchanged.
- **Per-machine override**: the file supplying platform-specific members — Homebrew prefix, Cellar libexec paths, VS Code CLI path, and the `.zshenv` versus `.zprofile` placement decision. Selected by `KG_PLATFORM`.
- **Installer**: copies core plus the matching override into `$HOME`, taking a timestamped backup first. Idempotent.
- **Environment assertion helper**: `bin/verify-shell-env`. Exercises every property across every shell invocation type and exits non-zero on any failure.
- **Secrets template**: `secrets.example` — variable names only, no values. Documents the shape of a file that is never committed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Both machines' shell config derives entirely from the repo — 0 hand-maintained blocks remain, verified by diffing installed files against installer output.
- **SC-002**: `verify-shell-env` exits 0 on both machines and non-zero for each of at least 5 deliberately broken properties.
- **SC-003**: Account routing is correct for 100% of repos tested, covering both accounts and including `spec-kitty-end-to-end-testing` — the repo that previously misrouted.
- **SC-004**: All 3 shell invocation types on office4 — interactive login, interactive non-login, non-interactive over SSH — resolve the same `python3`, `git`, and `node`.
- **SC-005**: `~/.local/bin` appears exactly once in PATH on both machines, ahead of the package manager prefix, which is ahead of `/usr/bin`. It currently appears 3 times on the MacBook.
- **SC-006**: A login shell emits 0 bytes on stderr on both machines.
- **SC-007**: Rollback restores the prior config in 1 command with the dotfiles repo deleted from disk.
- **SC-008**: `git commit` succeeds in kg-automation on office4, exercising the `.githooks` gate that requires the direnv-provided venv.
- **SC-009**: Editing an installed file and running `git status` in the dotfiles clone shows the change with 0 extra steps — no copy, sync, or re-install required.
- **SC-010**: `verify-shell-env` exits non-zero when the clone is dirty or behind `origin`, and 0 when it is clean and current.
- **SC-011**: `#!/bin/bash` scripts and interactive zsh resolve the same `python3` on both machines.
- **SC-012**: An install failure induced at any of 3 distinct points leaves `verify-shell-env --verbose` output byte-identical to the pre-install baseline.
- **SC-013**: Rollback correctly restores 3 prior states — file present, symlink present, and file **absent** — verified per managed entry.
- **SC-014**: `verify-shell-env` run from the Mac performs a real `ssh office4-kgale` probe and reports it as a distinct assertion from the local shell-mode checks.
- **SC-015**: `claude_account_for_path` returns the correct tree for 100% of sampled paths, including a `spec-kitty-*` repo that does not yet exist.
