# Work Packages: Portable shell config across both machines

**Mission**: `portable-dotfiles-01M18D57` · **Branch**: `feat/portable-dotfiles`

10 work packages, 51 subtasks. Sizing follows the 3–7 subtask target; none exceeds 7.

Decomposition note: the 8 implementation concerns do not map 1:1 to WPs. IC-05 (the assertion helper, 14 assertions) splits into two WPs so neither prompt exceeds the size limit; IC-06 (cutover) splits by machine because office4 must be proven before the Mac — the Mac is the machine this mission executes on, so its cutover is last.

## Dependency graph

```
WP01 skeleton
 ├─▶ WP02 core ──┬─▶ WP03 overrides ─┐
 │               └─▶ WP07 inventory ─┤
 ├─▶ WP05 helper: local assertions ──┤
 │        └─▶ WP06 helper: routing/remote/secrets
 └─▶ WP04 installer ─────────────────┤
                                     ▼
                            WP08 cutover office4
                                     │
                            WP09 cutover MacBook
                                     │
                            WP10 runbook + registration
```

WP05 depends only on WP01 (the contract), not on WP02/03 — deliberate, so the helper exists to capture the pre-change baseline before any config moves (directive 034).

---

## WP01 — Repository skeleton

**Goal**: Fix the layout, override-selection convention, and README so later WPs build against a stable shape.  
**Priority**: P1 · Dependencies: none · **Estimated prompt**: ~250 lines

**Subtasks**: T001 create `core/` `machines/` `bin/` tree · T002 `README.md` stating the symlink model and that GitHub is transport, not a symlink target · T003 `machines/kg_macbook_pro/` and `machines/kg_office4/` stubs · T004 `secrets.example` with variable names only · T005 `.gitignore` (identity file, local artefacts)

**Test criteria**: tree matches plan.md Project Structure; `secrets.example` contains zero value-shaped strings.

**Requirements**: FR-001, FR-002, FR-012, C-002, C-004

---

## WP02 — Shared core

**Goal**: The platform-agnostic configuration — PATH composition, account router, direnv hook, bash parity.  
**Priority**: P1 · Dependencies: WP01 · **Estimated prompt**: ~450 lines

**Subtasks**: T006 `core/zshenv` composing PATH from declared slots with `typeset -U path` · T007 `core/zshrc` account router, ported verbatim, patterns in an **inspectable array** · T008 expose pure `claude_account_for_path <path>` (FR-016) · T009 direnv hook in `zshrc`, interactive-only · T010 `core/zprofile` login-only concerns · T011 `core/bashrc` thin PATH parity (FR-013) · T012 tolerate missing `~/.config/secrets` silently (FR-015)

**Implementation notes**: The work-repo list **must stay a glob**; converting it to an enumeration is what caused the silent misrouting. Its explanatory comment is load-bearing. PATH must be *composed*, never accumulated — `~/.local/bin` currently appears 3× on the MacBook.

**Test criteria**: `claude_account_for_path` returns correct trees for sampled paths; PATH has no duplicates; login shell emits 0 bytes on stderr.

**Requirements**: FR-002, FR-004, FR-005, FR-007, FR-013, FR-015, FR-016, C-005

---

## WP03 — Per-machine overrides

**Goal**: Supply the platform-specific members the core deliberately omits.  
**Priority**: P1 · Dependencies: WP02 · **Estimated prompt**: ~300 lines

**Subtasks**: T013 `kg_macbook_pro/local.zsh` — Homebrew `/usr/local`, `python@3.13` and `node` libexec, VS Code CLI, `~/go/bin`, `~/.npm-global/bin` · T014 `kg_office4/local.zsh` — linuxbrew prefix, uv shim, **PATH in `.zshenv`** for remote invocation · T015 document why the two differ, so neither is "tidied" into the core · T016 `KG_PLATFORM` written by the installer, read by the config

**Implementation notes**: Same `python3` version (3.13.15) on both, different *mechanism* — Cellar libexec on the Mac, uv shim on office4. Normalising this breaks one machine.

**Test criteria**: each override references only paths that exist on its own machine.

**Requirements**: FR-002, FR-006

---

## WP04 — Transactional installer

**Goal**: `install.sh` — preflight, manifest, backup, trap-guarded swap, generated `restore.sh`.  
**Priority**: P1 · Dependencies: WP02, WP03 · **Estimated prompt**: ~500 lines

**Subtasks**: T017 platform detection + `--platform` override, refusing ambiguity (F7) · T018 preflight all targets and dirs, exit before any change · T019 manifest recording prior **type/target/mode/absence** (F2) · T020 backup to `~/.dotfiles-backup-<ts>/` · T021 trap-guarded atomic swap per entry (F1) · T022 generate self-contained `restore.sh` · T023 idempotency — re-run changes nothing, no nested backup

**Implementation notes**: A partial install is worse than none — it can leave a mixed environment on the machine you are logged into, or on office4 reached only through the shell being replaced. `restore.sh` must **remove** managed symlinks before restoring; `cp -a` copies *through* them into the clone.

**Test criteria**: induced failure at 3 distinct points leaves state byte-identical to baseline (SC-012); rollback restores all 3 prior states — file, symlink, **absent** (SC-013).

**Requirements**: FR-003, FR-014, NFR-001, NFR-003, NFR-005, C-006

---

## WP05 — Assertion helper: local shell properties

**Goal**: `verify-shell-env` skeleton plus the assertions that need no network or router API.  
**Priority**: P1 · Dependencies: WP01 · **Estimated prompt**: ~450 lines

**Subtasks**: T024 harness — spawn `zsh -lic`, `zsh -ic`, `zsh -c`; PASS/FAIL/SKIP reporting; `--verbose` baseline mode · T025 A1 managed entries are symlinks into the clone · T026 A2 `~/.local/bin` exactly once, correct precedence · T027 A3 three invocation types agree on `python3`/`git`/`node` · T028 A4 `python3` matches intended interpreter · T029 A9 login shell emits 0 bytes stderr · T030 A11 bash and zsh agree on `python3`

**Implementation notes**: Spawn, never introspect — a helper checking only its own shell reproduces the blind spot it exists to close. No GNU-only tools: `timeout` does not exist on macOS.

**Test criteria**: exits 0 on a correct machine; non-zero naming the assertion for each of 5 deliberately broken properties.

**Requirements**: FR-008, NFR-002, NFR-004

---

## WP06 — Assertion helper: routing, remote, secrets, drift

**Goal**: The assertions that need the router API, a real SSH probe, or filesystem state.  
**Priority**: P1 · Dependencies: WP05, WP02 · **Estimated prompt**: ~450 lines

**Subtasks**: T031 A5 `claude_account_for_path` over sampled paths incl. a `spec-kitty-*` repo that does not exist yet · T032 A6 patterns are an inspectable array; a bare literal duplicating an existing glob **fails** · T033 A7 `CODEX_HOME` correct per repo class · T034 A8 direnv fires on `cd` · T035 A10 clone clean and not behind `origin` · T036 A12 real `ssh office4-kgale` probe, explicit SKIP when unreachable · T037 A13 secrets present, mode 600, names match `secrets.example` — its **own** failure class

**Implementation notes**: `zsh -c` is not `ssh host 'cmd'` — same shell mode, but not sshd, PAM, login-shell selection, or non-TTY. A12 must genuinely invoke ssh. A SKIP is never a silent pass.

**Test criteria**: A5 correct for 100% of sampled paths; A13 distinguishes missing secrets from a routing failure.

**Requirements**: FR-008, FR-015, FR-016

---

## WP07 — PATH-adjacent script inventory

**Goal**: Decide per script — managed or explicitly out of scope — and assert the outcome.  
**Priority**: P2 · Dependencies: WP02 · **Estimated prompt**: ~300 lines

**Subtasks**: T038 inventory every PATH entry and shell-referenced helper on both machines · T039 classify: bring into `dotfiles/bin`, or scope out with rationale · T040 migrate those brought in-scope · T041 A14 — assert resolved paths; an unmanaged entry shadowing a managed one **fails**

**Implementation notes**: `~/bin/claim_and_run.sh` already reads `KG_PLATFORM`; `codex-review*.sh` serve the mandatory review checkpoints. Scoping out is acceptable; scoping out *silently* is not.

**Test criteria**: every inventoried script is classified; A14 passes on both machines.

**Requirements**: FR-017

---

## WP08 — Cutover: office4

**Goal**: Install from the repo on office4 and retire its five stopgap blocks.  
**Priority**: P1 · Dependencies: WP04, WP06, WP07 · **Estimated prompt**: ~350 lines

**Subtasks**: T042 capture `--verbose` baseline **before** any change · T043 run installer with a second session open · T044 remove the five stopgap blocks and reconcile the stale `.bashrc`/`.profile` pair · T045 create `~/.config/secrets` from the template, mode 600 · T046 full assertion run incl. the real SSH probe · T047 **measure** the dangling-symlink claim rather than assuming it

**Implementation notes**: office4 goes first precisely because it is not the machine executing this mission. T047 tests an assumption stated as fact during planning and never verified.

**Test criteria**: all assertions pass; `git commit` succeeds in kg-automation on office4 (SC-008).

**Requirements**: FR-009, FR-010, C-001, C-002

---

## WP09 — Cutover: MacBook Pro

**Goal**: Install on the Mac, collapsing the triplicated PATH entries.  
**Priority**: P1 · Dependencies: WP08 · **Estimated prompt**: ~300 lines

**Subtasks**: T048 capture baseline · T049 run installer · T050 verify `~/.local/bin` now appears **once** (was 3×) and the 5 previously unaccounted entries are placed in declared slots · T051 full assertion run on both machines, confirming parity

**Implementation notes**: Last, because it is the machine executing the mission. A shell broken here stops the arc.

**Test criteria**: SC-005 satisfied; both machines pass identically.

**Requirements**: FR-009, FR-010, FR-005

---

## WP10 — Bootstrap runbook and registration

**Goal**: Document bringing up a machine from nothing, and register it.  
**Priority**: P2 · Dependencies: WP09 · **Estimated prompt**: ~300 lines

**Subtasks**: T052 write `docs/runbooks/new-machine-bootstrap.md` — auth **before** config, secrets **before** verification · T053 register in `docs/INDEX.md` · T054 register in `docs/DEVELOPER_PORTAL.md` · T055 document rollback via generated `restore.sh`, not `cp -a`

**Implementation notes**: Document what was actually done in WP08/WP09, not what was intended. The ordering constraints are the part that makes it usable on a genuinely fresh machine.

**Test criteria**: `validate_docs.py` passes; runbook appears in both indexes.

**Requirements**: FR-011, FR-015

---

## Parallel opportunities

- WP05 runs alongside WP02/WP03 — it depends only on the contract.
- WP03 and WP07 both follow WP02 and are independent of each other.
- WP08 and WP09 are strictly sequential: office4 must be proven before the Mac.
