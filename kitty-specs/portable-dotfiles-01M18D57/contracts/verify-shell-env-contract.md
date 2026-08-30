# Contract: `bin/verify-shell-env`

**Mission**: `portable-dotfiles-01M18D57` · revised after post-plan review (F3, F4, F5, F6)

## Purpose

Assert every property the configuration is supposed to guarantee. The structural intervention against a recurring defect class (directive `040`): four defects survived because verification was ad-hoc and per-case.

## Design requirements

**Spawn, don't introspect.** A helper that checks only its own shell reproduces the blind spot it exists to close.

```
zsh -lic   interactive login
zsh -ic    interactive non-login   (VS Code terminal)
zsh -c     non-interactive shell mode
```

⚠ **`zsh -c` is not `ssh host 'cmd'`.** It exercises the same *shell mode*, but not sshd, PAM, login-shell selection, remote hostname resolution, or non-TTY behaviour. The spec's acceptance scenario names ssh, so a **real remote probe** is required — not a local approximation (F4).

**Assert routing through an API, not a banner.** Observing the cyan banner or an env var does not prove which account `claude` will authenticate as. The router must expose a pure function (F5).

## Assertions

| # | Assertion | Defect it would have caught |
|---|---|---|
| A1 | Every managed `$HOME` entry is a symlink resolving inside the clone | — |
| A2 | `~/.local/bin` appears **exactly once**, ahead of the package-manager prefix, ahead of `/usr/bin` | 2 |
| A3 | All three local invocation types resolve identical `python3`, `git`, `node` | 4 |
| A4 | `python3` matches the machine's intended interpreter | 2 |
| A5 | `claude_account_for_path` returns the correct tree for every sampled path — work, personal, and a `spec-kitty-*` repo that does not yet exist | 1 |
| A6 | The router's work-repo patterns are an **inspectable array**, and every entry either contains a glob metacharacter or is a deliberate exact-match exception; a bare literal that duplicates an existing glob **fails** | 1 |
| A7 | `CODEX_HOME` resolves to `~/.codex-work` in work repos, unset in personal | — |
| A8 | direnv fires on `cd` into a directory with `.envrc` | 3 |
| A9 | Login shell emits **0 bytes** on stderr | NFR-004 |
| A10 | The clone is clean and not behind `origin` | drift |
| A11 | `#!/bin/bash` and interactive zsh resolve the same `python3` | 3 |
| A12 | **`ssh office4-kgale 'cmd'` resolves the same `python3`, `git`, `node`** as local shells. Reported separately; skipped with an explicit SKIP (not a pass) when the host is unreachable | 4 |
| A13 | `~/.config/secrets` exists, is mode 600, and defines every name in `secrets.example`. Absence is its **own** failure, never reported as a routing failure | F3 |
| A14 | Every PATH-adjacent helper in scope resolves to its expected path; unmanaged entries that shadow a managed one **fail** | F6 |

## Output

One line per assertion — id, description, `PASS`/`FAIL`/`SKIP`. On failure, expected versus actual. Summary with counts.

`--verbose` prints resolved values for passing assertions, so it doubles as the **baseline capture** required before cutover (directive `034`) and as the comparison target for install-atomicity (NFR-005, SC-012).

## Exit status

`0` only when every assertion passes or is an explicit SKIP. Non-zero otherwise. **Exit status is the contract** — it may gate an install or a commit (NFR-002).

## Platform requirement

Runs on macOS 26 (Intel) and Linux Mint 22.3. No dependency beyond zsh, git, and default coreutils. **Must not assume GNU tools** — `timeout` does not exist on macOS.
