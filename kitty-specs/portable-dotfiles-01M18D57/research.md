# Research: Portable shell config across both machines

**Mission**: `portable-dotfiles-01M18D57` · **Phase 0**

All findings below were established **empirically on the two target machines** during the office4 migration (2026-08-28/29), not from documentation. That distinction matters: every one of them contradicted a reasonable prior assumption.

## R-001 — Which startup files each shell invocation actually reads

**Question**: Where must PATH live so that every way a shell starts resolves the same tools?

**Finding**:

| Invocation | Files read | Occurs when |
|---|---|---|
| Interactive login | `.zshenv` `.zprofile` `.zshrc` `.zlogin` | sitting at the machine |
| Interactive non-login | `.zshenv` `.zshrc` | VS Code integrated terminal |
| Non-interactive non-login | **`.zshenv` only** | `ssh office4-kgale 'cmd'` |

**Evidence**: with `brew shellenv` in `.zprofile` only, `ssh office4-kgale 'command -v git'` resolved `/usr/bin/git` 2.43.0 while an interactive shell resolved brew's 2.55.0. Moving PATH to `.zshenv` made all three agree.

**Decision**: PATH lives in `.zshenv` on office4. Not required on the Mac, which is never driven remotely — a genuine per-machine difference, recorded in the override rather than normalised away.

## R-002 — Copy-on-install versus symlink *(decision reversed during planning)*

**Question**: Should the installer copy files into `$HOME`, or symlink them into the clone?

**Initial position**: copy. Justified by the observation that 144 committed symlinks with absolute `/Users/kentgale/…` targets were **100% broken** on office4, with no supported CLI path to restore them (upstream #2748, open).

**Reversal, and why**: that reasoning conflated two different mechanisms.

| | Committed absolute symlinks | Locally-created symlinks |
|---|---|---|
| Created by | a tool, then committed to git | the installer, at install time |
| Target | absolute path from the originating machine | local path on the same disk |
| Shared across machines | yes, via git | no — created per machine |
| Failure mode observed | 144/144 broken on the second machine | not applicable |

**The decisive argument was not symlink safety but drift.** Copy-on-install has **no feedback path**: editing `~/.zshrc` — which is what one does when something breaks — leaves the repo unaware, and the next install silently overwrites the fix. That is precisely how a dotfiles repo becomes stale fiction, and it is the failure this mission exists to prevent. Symlinks make `$HOME` and the repo the same inode, so `git status` sees every edit with no extra step.

**Residual risk accepted**: a deleted or moved clone leaves dangling symlinks and zsh starts with defaults — a degraded but usable shell, recoverable from the dated backup without the repo (NFR-003). Weighed against certain drift, this is the better trade.

**Disposition**: `changed`. Constraint C-006 was rewritten from "copy, not symlink" to "local symlinks, never committed".

## R-003 — The `KG_PLATFORM` circular dependency

**Question**: How does the installer know which machine override to select?

**Finding**: `KG_PLATFORM` is *exported by* the shell configuration, so at install time — before any config exists — it is unset. It cannot select the configuration that defines it.

**Decision**: the installer detects the platform independently via `uname -s` plus hostname (`Darwin` → `kg_macbook_pro`; `Linux` + `Office4` → `kg_office4`) and **writes** `KG_PLATFORM` into the selected override. Downstream consumers — including `~/bin/claim_and_run.sh`, which already reads it — are unchanged.

**Alternative rejected**: prompting at install time. It makes the installer non-idempotent and unusable unattended.

## R-004 — PATH is accumulated, not composed

**Question**: What is the actual PATH on each machine, and does the intended precedence hold?

**Finding**:

| | MacBook | office4 |
|---|---|---|
| Head | `~/go/bin` | `~/.local/bin` |
| `~/.local/bin` occurrences | **3** (positions 3, 4, 13) | 1 |
| `/usr/bin` position | 20 | 5 |

office4 matches the intended precedence exactly — it was built deliberately after the `python@3.14` capture. The Mac's is sediment: `~/.local/bin` is prepended four separate times across `.zprofile:5`, `.zprofile:9`, `.zshrc:69` and `.zshrc:74`.

The Mac additionally carries five entries the original constraint did not account for — `~/go/bin` (gopls, mage), `~/.npm-global/bin` (clasp, pnpm), Homebrew's `node` and `python@3.13` libexec paths, and the VS Code CLI. The last two are **load-bearing on the Mac with no office4 equivalent**: office4 gets `python3` from a uv shim in `~/.local/bin`, not a Cellar libexec. Same resulting version (3.13.15), different mechanism.

**Decision**: the core declares an ordered list of **slots** (user-local → language toolchains → package manager → system) and applies `typeset -U path` so duplicates collapse. Overrides supply the platform-specific members of each slot.

## R-005 — Bash parity: manage or drop

**Question**: office4's login shell is zsh. Should bash config be managed at all?

**Finding**: bash remains reachable via `#!/bin/bash` scripts and `bash -lc`. With no bash config, those inherit the system default PATH while interactive zsh gets the composed one — so a script calling `python3` can get a different interpreter than the operator does, silently. This is the shape of both defect 2 (`python3` capture) and defect 3 (direnv hooked into bash while the login shell was zsh, breaking every commit).

**Decision**: manage bash **minimally** — a thin `core/bashrc` that sets PATH identically and does nothing else (FR-013). Roughly ten lines, closing a failure mode already hit twice.

**Alternative considered**: drop bash config entirely. Simpler and smaller surface, but accepts a silent script-versus-interactive interpreter mismatch. Rejected on that basis; the simplicity saving is not worth a class of bug we have already paid for.

## R-006 — Supply-chain assessment *(directive 051)*

**Finding**: this mission introduces **no third-party dependency**. No brew tap, pip index, npm registry, or MCP plugin. The one new source is `kentonium3/dotfiles` — Kent's own private repo, fetched over authenticated HTTPS.

Registry authenticity, package freshness, lifecycle-script discipline, and Node Active LTS awareness are all **not applicable**: no package is installed and no lifecycle script runs. The installer's only network access is the clone or pull of that repo (NFR-001).

**Consequence recorded**: because the repo is private, a machine needs git credentials **before** it can fetch shell configuration. The bootstrap runbook must sequence authentication first, or it is unusable on a genuinely fresh machine (FR-011).

## Adversarial evidence

No security-impacting *dependency* decision was made, so the dependency-focused adversarial pass is **not applicable**. Two design decisions were nonetheless challenged during planning, both by Kent, and both changed the design:

| Challenge | Disposition |
|---|---|
| "There's no mechanism for updating the repo copies if a local version changes" — identified the copy model's missing feedback path | **changed** — C-006 reversed to symlinks (R-002) |
| "Simpler is better, but it also needs to be resilient" — probed whether bash management earns its complexity | **accepted** — manage minimally, with the two prior failures as justification (R-005) |

No contested finding was dropped.

## R-007 — Post-plan Codex review dispositions

Read-only adversarial pass over spec, plan, research, data-model and both contracts (2026-08-30, `codex exec --sandbox read-only`, no profile). Seven findings — five High, two Medium. **All seven changed the design**; none was deferred or dropped.

| # | Finding | Disposition |
|---|---|---|
| F1 | **Installer reversible but not transactional.** Backup-then-replace-one-at-a-time can leave a mixed old/new environment if it fails between entries — on the machine you are logged into, or on office4 reached only through the shell being replaced. | **changed** — FR-003 rewritten to require preflight, manifest, and a restoring trap; NFR-005 and SC-012 added; installer-contract rewritten around a transaction. |
| F2 | **Rollback underspecified and probably wrong.** `cp -a backup/. ~/` copies *through* a live symlink into the clone, and cannot delete an entry that did not exist before install (`.bashrc`). A backup of existing files cannot describe absence. | **changed** — FR-014 added: manifest records prior type/target/mode/**absence**; a generated `restore.sh` removes managed entries first, restores, then deletes what was absent. quickstart's incorrect command replaced. |
| F3 | **Secrets ordering makes a fresh machine fail verification for the wrong reason.** quickstart ran `verify-shell-env` before `~/.config/secrets` existed; the contract for missing secrets was undefined. | **changed** — FR-015 added: startup tolerates absence silently; A13 asserts presence, mode 600, and required names as its **own** failure class. quickstart resequenced. |
| F4 | **`zsh -c` is a simulation, not the acceptance scenario.** The spec names `ssh office4-kgale 'cmd'`; local `zsh -c` shares the shell mode but not sshd, PAM, login-shell selection, or non-TTY behaviour. | **changed** — A12 added as a real remote probe, reported separately, with explicit SKIP (never a silent pass) when unreachable. FR-008 amended. |
| F5 | **A5/A6 were fakeable.** Observing a banner or env var does not prove which account `claude` authenticates as, and "is a glob, not an enumeration" is not mechanically checkable unless the representation is constrained. Written aspirationally. | **changed** — FR-016 added: router exposes a pure `claude_account_for_path`; work-repo patterns held in an inspectable array. A6 now fails a bare literal duplicating an existing glob. |
| F6 | **`~/bin` and `~/helper-scripts` remain unmanaged** while on PATH, holding load-bearing scripts (`claim_and_run.sh` reads `KG_PLATFORM`; `codex-review*.sh` serve the review checkpoints). An unmanaged copy can shadow a managed one and diverge. | **changed** — FR-017 and IC-08 added: inventory each, bring in or scope out **explicitly**, and assert the resolved path either way (A14). Scoping out is fine; doing so silently is not. |
| F7 | **Machine detection brittle.** Hostname case, FQDN form, rename, or rebuild can select the wrong override. | **changed** — `--platform` override required; ambiguous detection must refuse rather than guess; a local untracked identity file is written on success. |

**Also noted and accepted**: the claim that dangling symlinks "degrade gracefully" is an assumption, not a measurement, and must be *tested* on both zsh builds rather than asserted. Folded into IC-06's verification rather than left as prose.

The reviewer judged the `.zshenv` placement and the bash-parity scope sound, and the local-symlink decision defensible for drift prevention.

## Open questions

None. All clarifications raised during specify and plan were resolved before this document was written; `spec.md` contains no `[NEEDS CLARIFICATION]` markers.
