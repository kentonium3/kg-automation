---
title: office4 Work-Hat Environment
doc_type: runbook
audience: agents_and_humans
status: approved
last_updated: '2026-08-29'
---

# office4 Work-Hat Environment

**Read this if you are a work-account agent (`kent@spec-kitty.ai`) starting a session
on office4.** It records the environment as built on 2026-08-29 — what works, what is
deliberately different from the MacBook, and what is not set up yet.

It exists because a work-hat session on office4 starts with **no memory tree**:
`~/.claude-work/projects/` does not exist, so none of the setup context below is
inherited. This doc is the substitute.

> **Scope.** Environment mechanics only. The *behavioural* rules for the work hat —
> the upstream-contribution carve-out, spec-kitty source-contribution mode, per-action
> upstream approval — live in `~/.claude/CLAUDE.md` and are **already loaded** for you.
> See "Why you still read the personal CLAUDE.md" below.

## The machine

| | |
|---|---|
| Host | office4 — Framework Desktop (AMD Ryzen AI Max 300 Series) |
| OS | **Linux Mint 22.3** (Ubuntu 24.04 "noble" base) |
| Tailscale IP | `100.112.83.28` |
| Role | Kent's primary development machine — **attended, unmanaged peer** |

⚠ **`uname` lies about the OS here.** The kernel build string reads `#28~24.04.1-Ubuntu`,
which is the Ubuntu *base*, not the distribution. `/etc/os-release` is the standard of
proof. A prior session recorded "Ubuntu 24.04 LTS" from `uname` and was wrong.

office4 is **not** a deploy target and holds no managed services. The three-machine model
and the placement test are in
[ADR-0008](../design/architecture/adr/0008-three-machine-model.md); read it before
proposing that anything run here.

## Hat routing — how you got the work account

Each work repo carries an `.envrc` that direnv loads on `cd`-in:

```bash
export CODEX_HOME="$HOME/.codex-work"
export CLAUDE_CONFIG_DIR="$HOME/.claude-work"
```

All five `~/repos/spec-kitty*` clones have both. Without the `CLAUDE_CONFIG_DIR` line,
`claude` in a work repo **silently uses the personal `~/.claude` tree** — it does not
warn. If you are ever unsure which hat you are on, check `echo $CLAUDE_CONFIG_DIR`.

### Why you still read the personal CLAUDE.md

Claude Code resolves user memory from the literal path `~/.claude/CLAUDE.md`
**regardless of `CLAUDE_CONFIG_DIR`**. `~/.claude-work/CLAUDE.md` does not exist and
would not be read if it did. This is why that one file is section-scoped by hat rather
than split into two files — and why the work-hat rules are already in your context.

`~/.claude-work/` symlinks `commands` and `skills` back to `~/.claude/`, so slash
commands and skills are shared across hats. Only credentials, sessions, settings, and
project memory are separate.

### Per-clone state that does NOT survive `git clone`

Each `.envrc` is registered in that clone's `.git/info/exclude` (not `.gitignore` —
these are Kent's local files and must not enter the work repos' history).
`.git/info/exclude` is **per-clone**: a fresh clone starts empty and the entry must be
re-added, along with `direnv allow`. Tracked as kg-automation#911 (dotfiles split).

## Reaching office2

| Alias | Path | Auth |
|---|---|---|
| `office2-claude` / `office2-codex` / `office2-kgale` | tailnet `100.92.197.90` | Tailscale SSH |
| `office2-kgale-lan` | LAN `192.168.1.158` | SSH key (`~/.ssh/id_ed25519_office4`) |

🔑 **The fact that surprises everyone.** With Tailscale SSH `action: "accept"`,
**tailscaled terminates the connection itself** and authorises on *tailnet device
identity*. It does **not** pass through to sshd — so `authorized_keys` and
`PermitRootLogin` are **never consulted** on the tailnet path. An `IdentityFile` on a
tailnet `Host` block is silently inert. Keys still apply on the **LAN** path, which is a
real sshd.

Full model in
[security-posture.md](../design/architecture/security-posture.md) (Path A / Path B) and
`docs/design/architecture/data/network-topology.json`.

**Account discipline is unchanged on office4:** each agent uses its own account. Never
`ssh office2-kgale` from an agent session — that account is for human use only. Neither
agent account has passwordless sudo.

## Python environments

Built 2026-08-29. Nothing was migrated from the MacBook — venvs are gitignored, so the
clones carried none and these were created from scratch.

| Repo | Python | Built with | Notes |
|---|---|---|---|
| `spec-kitty` | 3.11.15 | `uv sync` | has `uv.lock`; CLI reports `spec-kitty-cli 3.2.6` |
| `spec-kitty-telescope` | 3.13.15 | `uv sync` | has `uv.lock` |
| `spec-kitty-saas` | 3.12.3 | `uv sync` | has `uv.lock`; Django 6.0 |
| `spec-kitty-qa` | 3.13.15 | **not uv** — see below | full suite: 2717 passed, 6 skipped |
| `spec-kitty-analyzer` | — | — | **Go project**, no venv |

direnv activates each venv on `cd`-in; do **not** `source .venv/bin/activate` manually.

Toolchain present: `uv` 0.12.7, `node` v26.7.0, `npm` 11.19.0, `/usr/bin/python3` 3.12.3.

### spec-kitty-qa is the special case

It has **no lockfile**, pins `requires-python = ">=3.13,<3.14"`, and is **deliberately
not installable** — it declares a PEP 735 dependency group instead. Rebuild it with:

```bash
uv venv --python 3.13 --seed
```

```bash
.venv/bin/python -m pip install --group test -c constraints.txt
```

Three constraints, all measured and documented in its own `pyproject.toml`:

- `--group` requires **pip ≥ 26.1**. `--seed` supplied 26.2.1.
- The install **must run from the repository root**, or it fails with
  `pyproject.toml not found. Cannot resolve '--group' option.`
- The repo **refuses narrowed pytest runs by design.** A subset invocation exits without
  running any tests. `QA_ALLOW_NARROWED_RUN=1` is the deliberate override, and per the
  repo's own comment the workflow must never set it. Run the whole suite (~90s).

### Python is not the whole environment

`spec-kitty-qa`'s suite still failed two tests with a correct venv — both on a missing
`node_modules/.bin/tsc`. `npm install` fixed it and the suite went fully green.

⚠ **`spec-kitty` and `spec-kitty-saas` also carry a `package.json` with `node_modules`
still absent.** Their suites have never been run on office4, so this is *unverified*,
not *fine*. If a test fails on a missing JS tool, run `npm install` before debugging.

## Codex on the work hat

`CODEX_HOME=$HOME/.codex-work` is set by the same `.envrc`. The
`spec-kitty-review` profile **is loadable from the work hat** — the sidecar
`~/.codex-work/spec-kitty-review.config.toml` exists and loads. (Codex CLI v0.135.0
deprecated `[profiles.<name>]` blocks in favour of these sidecars.)

**Availability is not permission.** That profile is a single line —
`sandbox_mode = "danger-full-access"` — and exists only so Codex can record a WP verdict
itself. It must **not** be used for the post-plan or post-merge review checkpoints, which
are read-only. Never `--full-auto`, which overrides the profile. Full rule in
`~/.claude/CLAUDE.md`.

## Not set up yet

- **MCP servers** need re-approval on this machine: `filesystem` (npx), `postgres`
  (uvx + PG:5432), `playwright` (Node + browsers).
- **`core.hooksPath .githooks`** is not configured per clone. Use that, **not**
  `scripts/install-hooks.sh` — the script installs the *legacy* secret-scan hook.
- **No Obsidian vault.** `~/second-brain` does not exist on office4 and the vault is not
  synced here (Mac, iPhone, and office2 only). Anything that assumes a local vault will
  fail.
- **No work-hat memory.** `~/.claude-work/projects/` is empty; this doc is the handoff.

Tracking: kg-automation#914 (repo/tooling migration), #912 (credentials and connectors),
#911 (dotfiles split), #917 (the `codex` account's purpose).
