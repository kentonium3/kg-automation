# Contract: `bin/verify-shell-env`

**Mission**: `portable-dotfiles-01M18D57`

## Purpose

Assert every property the shell configuration is supposed to guarantee. This is the mission's structural intervention against a recurring defect class (directive `040`): four defects survived because verification was ad-hoc and per-case.

## Design requirement

It **spawns** each shell invocation type rather than inspecting the one it runs in. A helper that checks only its own shell reproduces the exact blind spot it exists to close.

```
zsh -lic   interactive login
zsh -ic    interactive non-login   (VS Code terminal)
zsh -c     non-interactive         (what `ssh host 'cmd'` uses)
```

## Assertions

| # | Assertion | Defect it would have caught |
|---|---|---|
| A1 | Every managed `$HOME` entry is a symlink resolving inside the clone | — |
| A2 | `~/.local/bin` appears **exactly once**, ahead of the package-manager prefix, ahead of `/usr/bin` | 2 (`python3` capture) |
| A3 | All three invocation types resolve identical `python3`, `git`, `node` | 4 (PATH invisible to SSH) |
| A4 | `python3` matches the machine's intended interpreter | 2 |
| A5 | Work repos route to `.claude-work`; personal repos to the default tree — including `spec-kitty-end-to-end-testing` | 1 (silent misrouting) |
| A6 | The router's work-repo list is a glob, not an enumeration | 1 |
| A7 | `CODEX_HOME` resolves to `~/.codex-work` in work repos, unset in personal | — |
| A8 | direnv fires on `cd` into a directory with `.envrc` | 3 (hook in wrong shell) |
| A9 | Login shell emits **0 bytes** on stderr | NFR-004 |
| A10 | The clone is clean and not behind `origin` | drift (FR-008) |
| A11 | `#!/bin/bash` and interactive zsh resolve the same `python3` | 3 (bash/zsh divergence) |

## Output

One line per assertion — id, description, `PASS`/`FAIL`. On failure, expected versus actual. Summary line with counts.

`--verbose` shows resolved values for passing assertions too, so it doubles as the baseline capture required before cutover (directive `034`).

## Exit status

`0` only when **every** assertion passes. Non-zero otherwise. **Exit status is the contract** — it may gate an install or a commit (NFR-002).

## Platform requirement

Runs on macOS 26 (Intel) and Linux Mint 22.3. No dependency beyond zsh, git, and coreutils present by default on both. Notably **must not** assume GNU tools: `timeout` does not exist on macOS.
