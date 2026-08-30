# Work Packages: Portable shell config across both machines

**Mission**: `portable-dotfiles-01M18D57` · **Branch**: `feat/portable-dotfiles`

10 work packages, 55 subtasks. The 8 implementation concerns do not map 1:1 — IC-05 (the helper, 14 assertions) splits across two WPs so neither prompt exceeds the size limit, and IC-06 (cutover) splits by machine because office4 must be proven before the MacBook, which is the machine executing this mission.

WP05 depends only on WP01, deliberately: the helper must exist before any config moves so it can capture the pre-change baseline (directive 034).

## Work Package 1 — Repository skeleton

- **Goal**: Fix the layout, override-selection convention, and README so later work packages build against a stable shape.
- **Priority**: P1
- **Independent test**: Tree matches plan.md Project Structure; `secrets.example` contains zero value-shaped strings.
- **Prompt**: [tasks/WP01-repository-skeleton.md](tasks/WP01-repository-skeleton.md)
- **Estimated prompt size**: ~250 lines
- **Dependencies**: none
- **Owned files**:
  - `dotfiles/README.md`
  - `dotfiles/secrets.example`
  - `dotfiles/.gitignore`
  - `dotfiles/core/`
  - `dotfiles/machines/`
  - `dotfiles/bin/`
- **Subtasks**:
  - T001 create `core/` `machines/` `bin/` tree
  - T002 `README.md` stating the symlink model and that GitHub is transport, not a symlink target
  - T003 machine override stubs
  - T004 `secrets.example`, names only
  - T005 `.gitignore`

## Work Package 2 — Shared core

- **Goal**: The platform-agnostic configuration: PATH composition, account router, direnv hook, bash parity.
- **Priority**: P1
- **Independent test**: `claude_account_for_path` correct for sampled paths; PATH has no duplicates; login shell emits 0 bytes stderr.
- **Prompt**: [tasks/WP02-shared-core.md](tasks/WP02-shared-core.md)
- **Estimated prompt size**: ~450 lines
- **Dependencies**: WP01
- **Owned files**:
  - `dotfiles/core/zshenv`
  - `dotfiles/core/zshrc`
  - `dotfiles/core/zprofile`
  - `dotfiles/core/bashrc`
- **Subtasks**:
  - T006 `zshenv` composes PATH from declared slots with `typeset -U path`
  - T007 `zshrc` router, patterns in an inspectable array, list stays a **glob**
  - T008 pure `claude_account_for_path <path>`
  - T009 direnv hook, interactive-only
  - T010 `zprofile`
  - T011 `bashrc` thin PATH parity
  - T012 tolerate missing `~/.config/secrets` silently

## Work Package 3 — Per-machine overrides

- **Goal**: Supply the platform-specific members the core deliberately omits.
- **Priority**: P1
- **Independent test**: Each override references only paths that exist on its own machine.
- **Prompt**: [tasks/WP03-machine-overrides.md](tasks/WP03-machine-overrides.md)
- **Estimated prompt size**: ~300 lines
- **Dependencies**: WP02
- **Owned files**:
  - `dotfiles/machines/kg_macbook_pro/local.zsh`
  - `dotfiles/machines/kg_office4/local.zsh`
- **Subtasks**:
  - T013 Mac override: Homebrew prefix, Cellar libexec, VS Code CLI, go/bin, npm-global
  - T014 office4 override: linuxbrew, uv shim, PATH in `.zshenv`
  - T015 document why they differ
  - T016 `KG_PLATFORM` written by installer, read by config

## Work Package 4 — Transactional installer

- **Goal**: `install.sh` — preflight, manifest, backup, trap-guarded swap, generated `restore.sh`.
- **Priority**: P1
- **Independent test**: Induced failure at 3 points leaves state byte-identical to baseline; rollback restores file, symlink and absent states.
- **Prompt**: [tasks/WP04-transactional-installer.md](tasks/WP04-transactional-installer.md)
- **Estimated prompt size**: ~500 lines
- **Dependencies**: WP02, WP03
- **Owned files**:
  - `dotfiles/install.sh`
- **Subtasks**:
  - T017 platform detection + `--platform`, refuse ambiguity
  - T018 preflight before any change
  - T019 manifest: prior type/target/mode/**absence**
  - T020 dated backup
  - T021 trap-guarded atomic swap
  - T022 generate self-contained `restore.sh`
  - T023 idempotency

## Work Package 5 — Assertion helper: local shell properties

- **Goal**: The helper skeleton plus every assertion needing no network or router API.
- **Priority**: P1
- **Independent test**: Exits 0 on a correct machine; non-zero naming the assertion for 5 deliberately broken properties.
- **Prompt**: [tasks/WP05-helper-local-assertions.md](tasks/WP05-helper-local-assertions.md)
- **Estimated prompt size**: ~450 lines
- **Dependencies**: WP01
- **Owned files**:
  - `dotfiles/bin/verify-shell-env`
- **Subtasks**:
  - T024 harness spawning `zsh -lic`/`-ic`/`-c`, PASS/FAIL/SKIP, `--verbose` baseline
  - T025 A1 managed entries are symlinks into the clone
  - T026 A2 `~/.local/bin` exactly once, correct precedence
  - T027 A3 three invocation types agree
  - T028 A4 intended interpreter
  - T029 A9 0 bytes stderr
  - T030 A11 bash/zsh agree

## Work Package 6 — Assertion helper: routing, remote, secrets, drift

- **Goal**: The assertions needing the router API, a real SSH probe, or filesystem state.
- **Priority**: P1
- **Independent test**: A5 correct for 100% of sampled paths; A13 distinguishes missing secrets from a routing failure; A12 genuinely invokes ssh.
- **Prompt**: [tasks/WP06-helper-routing-remote.md](tasks/WP06-helper-routing-remote.md)
- **Estimated prompt size**: ~450 lines
- **Dependencies**: WP02, WP05
- **Owned files**:
  - `dotfiles/bin/verify-shell-env`
- **Subtasks**:
  - T031 A5 router API over sampled paths incl. a not-yet-existing `spec-kitty-*`
  - T032 A6 patterns inspectable; bare literal duplicating a glob fails
  - T033 A7 `CODEX_HOME` per repo class
  - T034 A8 direnv fires on `cd`
  - T035 A10 clone clean and not behind origin
  - T036 A12 real `ssh office4-kgale` probe, explicit SKIP
  - T037 A13 secrets present, 600, names match
  - T041 A14 assert resolved paths; shadowing fails (moved from WP07: WP06 owns verify-shell-env)

## Work Package 7 — PATH-adjacent script inventory

- **Goal**: Decide per script whether it is managed or explicitly out of scope, and assert the outcome.
- **Priority**: P2
- **Independent test**: Every inventoried script classified with a rationale; A14 passes on both machines.
- **Prompt**: [tasks/WP07-script-inventory.md](tasks/WP07-script-inventory.md)
- **Estimated prompt size**: ~300 lines
- **Dependencies**: WP02
- **Owned files**:
  - `dotfiles/docs/script-inventory.md`
- **Subtasks**:
  - T038 inventory every PATH entry and shell-referenced helper
  - T039 classify: bring in or scope out with rationale
  - T040 migrate those in scope

## Work Package 8 — Cutover: office4

- **Goal**: Install from the repo on office4 and retire its five stopgap blocks.
- **Priority**: P1
- **Independent test**: All assertions pass; `git commit` succeeds in kg-automation on office4.
- **Prompt**: [tasks/WP08-cutover-office4.md](tasks/WP08-cutover-office4.md)
- **Estimated prompt size**: ~350 lines
- **Dependencies**: WP04, WP06, WP07
- **Owned files**:
  - `dotfiles/install.sh`
- **Subtasks**:
  - T042 capture `--verbose` baseline first
  - T043 install with a second session open
  - T044 remove five stopgaps, reconcile stale bash pair
  - T045 create secrets, mode 600, before verification
  - T046 full assertion run incl. SSH probe
  - T047 **measure** the dangling-symlink claim

## Work Package 9 — Cutover: MacBook Pro

- **Goal**: Install on the Mac, collapsing the triplicated PATH entries.
- **Priority**: P1
- **Independent test**: `~/.local/bin` appears once; both machines pass identically.
- **Prompt**: [tasks/WP09-cutover-macbook.md](tasks/WP09-cutover-macbook.md)
- **Estimated prompt size**: ~300 lines
- **Dependencies**: WP08
- **Owned files**:
  - `dotfiles/install.sh`
- **Subtasks**:
  - T048 capture baseline
  - T049 run installer
  - T050 verify `~/.local/bin` once (was 3x) and 5 prior-unaccounted entries in declared slots
  - T051 full run on both machines

## Work Package 10 — Bootstrap runbook and registration

- **Goal**: Document bringing up a machine from nothing, and register it.
- **Priority**: P2
- **Independent test**: `validate_docs.py` passes; runbook appears in both indexes.
- **Prompt**: [tasks/WP10-bootstrap-runbook.md](tasks/WP10-bootstrap-runbook.md)
- **Estimated prompt size**: ~300 lines
- **Dependencies**: WP09
- **Owned files**:
  - `docs/runbooks/new-machine-bootstrap.md`
  - `docs/INDEX.md`
  - `docs/DEVELOPER_PORTAL.md`
- **Subtasks**:
  - T052 write the runbook: auth before config, secrets before verification
  - T053 register in `docs/INDEX.md`
  - T054 register in `docs/DEVELOPER_PORTAL.md`
  - T055 document rollback via generated `restore.sh`, not `cp -a`
