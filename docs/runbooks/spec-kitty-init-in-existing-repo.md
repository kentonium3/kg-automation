---
title: Spec-Kitty — Install, Initialize, Upgrade
doc_type: runbook
audience: humans
status: active
last_validated: 2026-06-23
---

# Spec-Kitty — Install, Initialize, Upgrade

Operational runbook for the three lifecycle moments of spec-kitty on this Mac:

1. **Install** — first-time install of the global `spec-kitty-cli` binary.
2. **Initialize** — set up spec-kitty in a new (or existing) git repository.
3. **Upgrade** — bump the CLI and roll the new version through every spec-kitty-initialized repo.

Authoritative paths and versions on Kent's Mac (as of 2026-06-14):

- pipx venv: `/Users/kentgale/.local/pipx/venvs/spec-kitty-cli/`
- binary: `/Users/kentgale/.local/bin/spec-kitty`
- PyPI package name: `spec-kitty-cli` (NOT `spec-kitty`; the latter 404s)
- Spec-kitty-initialized repos: `metalbox`, `bake-planner`, `intentional`, `bake-tracker`, `kg-automation`, `spec-kitty-analyzer-harness`, `vikunja-harness`
  - **The list grows.** Rather than trust this line, discover the live set on demand:
    `for d in /Users/kentgale/repos/*/; do [ -d "$d/.kittify" ] && [ -d "$d/.git" ] && basename "$d"; done`
    (excludes the spec-kitty **source** repo only if you filter it out — it has `.kittify/` because it dogfoods, but is **not** a consumer; never run `upgrade --project` on it).

---

## 1. Install (first time only)

Spec-kitty is installed via pipx. Do **not** use brew, npm, or `uv tool install` — pipx is the canonical channel.

```bash
pipx install spec-kitty-cli --pip-args="--pre"
```

`--pre` allows release-candidate versions (`3.2.0rcNN`). Drop it once stable `3.2.0` ships.

Verify:

```bash
spec-kitty --version
```

If the binary isn't on `PATH`, run `pipx ensurepath` and open a new shell.

### ⚠️ Which `spec-kitty` binary am I running? (matters while 3.2.2 is main-only)

There can be **two** `spec-kitty` binaries on this Mac:

| Install | Path | What it is | Use for |
|---|---|---|---|
| **pipx (canonical)** | `~/.local/bin/spec-kitty` | Frozen build; currently 3.2.2 from upstream `main@aeb8dfc31` (no PyPI 3.2.2 yet) | **Managing these consumer repos** |
| **editable dev** | `~/repos/spec-kitty/.venv/bin/spec-kitty` | Runs live from the spec-kitty **source** working tree; reflects whatever branch is checked out | **Developing spec-kitty itself** |

When the source `.venv` is **activated**, it sits *first* on `PATH` and shadows pipx — so a bare `spec-kitty` runs the **dev build off the current branch**, not clean main. Both currently report `3.2.2`, so you can't tell them apart by `--version`.

**Rule until a real 3.2.2 release lands:** for consumer-repo work, run from a shell where the source `.venv` is **not** active (or call `~/.local/bin/spec-kitty` by full path, or `deactivate` first). Confirm with `type -a spec-kitty` (first line wins) or `command -v spec-kitty`.

---

## 2. Initialize in a repo

For a brand-new repo or an existing one that hasn't been spec-kitty-initialized. Init creates `.kittify/`, `kitty-specs/`, and harness files (`.claude/CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`).

### Pre-flight

1. Confirm you're at the repo root (`.git/` present).
2. Confirm none of `.kittify/`, `kitty-specs/`, `.worktrees/` already exist.
3. Confirm `.gitignore` has (or will be updated to have) `.worktrees/` ignored — required for spec-kitty 3.2.x mission worktrees.

### Steps

```bash
cd /path/to/repo
spec-kitty init . --force --ai claude
```

- `--force` allows install into a non-empty directory.
- `--ai claude` installs the `/spec-kitty.*` slash commands for Claude Code. Substitute `codex`, `gemini`, etc. for other harnesses.

Post-init, verify and commit:

```bash
spec-kitty check
grep -E '^\.worktrees/' .gitignore || echo '.worktrees/' >> .gitignore
git add .kittify/ kitty-specs/ .gitignore .claude/ AGENTS.md .github/
git commit -m "feat: initialize spec-kitty"
```

Then run the charter interview to establish governance:

```
/spec-kitty.charter
```

---

## 3. Upgrade

A spec-kitty upgrade is two layers:

- **Global CLI** — one pipx binary serves every repo.
- **Per-repo project state** — `.kittify/metadata.yaml` + harness files are versioned independently per repo. The CLI bump does NOT auto-bump these; `spec-kitty upgrade --agent-check --json` reports `up_to_date` even when projects have drifted.

### 3.1 Pre-flight: no missions in flight

Spec-kitty migrations applied mid-mission can permanently break that mission's accept/merge gates (see `feedback_no_mid_feature_upgrades.md`).

The authoritative signal is git worktrees — an active mission always has a coord/target worktree:

```bash
for repo in metalbox bake-planner intentional bake-tracker kg-automation vikunja-harness; do
  d=/Users/kentgale/repos/$repo
  echo "=== $repo ==="
  (cd "$d" && git worktree list 2>/dev/null | grep -v "^$d ")
done
```

Empty output = safe to upgrade. (Do NOT rely on `status.json` frontmatter `lane:` fields — in 3.0.x+ those are stale; the event log is authoritative.)

### 3.2 Upgrade the CLI

```bash
pipx upgrade spec-kitty-cli --pip-args="--pre"
spec-kitty --version
```

To pin to a specific RC:

```bash
pipx install --force "spec-kitty-cli==3.2.0rc44"
```

### 3.2b Upgrade off `main` (unreleased change)

When a merged upstream PR you need is on `main` but **not yet in any tagged release** (e.g. a doctrine
directive that hasn't shipped in a `vX.Y.Z` tag), install the CLI directly from upstream `main`:

```bash
pipx install --force "git+https://github.com/Priivacy-ai/spec-kitty.git@main"
```

**Capture the build SHA.** `main` moves and the version string (e.g. `3.2.6`) is **not granular** — the
exact commit is the real build ID. pip records it in the package's `direct_url.json`; take the **9-char
short SHA** (the reporting convention — see `spec-kitty-bug-reporting.md § Build-ID convention`):

```bash
python3 -c "import glob,json; f=glob.glob('$HOME/.local/pipx/venvs/spec-kitty-cli/lib/python*/site-packages/spec_kitty_cli-*.dist-info/direct_url.json')[0]; print(json.load(open(f))['vcs_info']['commit_id'][:9])"
```

Record it in any bug/tracking report as `X.Y.Z (main build, SHA <9char>)`.

**Verify the change actually landed** (a version bump alone doesn't prove the doctrine is present):
`grep -rl "<new DIRECTIVE_ID or wording>" "$(dirname "$(python3 -c 'import spec_kitty_cli,os;print(os.path.dirname(spec_kitty_cli.__file__))')")/../doctrine" 2>/dev/null` — or list `…/site-packages/doctrine/directives/built-in/`.

**Caveat:** installing off `main` reverses the pinned-official-release posture (daily-driving-main).
Prefer waiting for the next tagged release unless the change is needed now. Roll back with
`pipx install --force spec-kitty-cli==<last-good-tag>`. Note new builtin directives are **available** in
the CLI but not auto-activated in a project's charter — adopting one is a separate charter update.

Then run §3.3 (per-repo `--project --yes`) as normal.

### 3.3 Roll the bump into each repo

Dry-run first to inspect the plan:

```bash
for repo in metalbox bake-planner intentional bake-tracker kg-automation vikunja-harness; do
  echo "=== $repo ==="
  (cd /Users/kentgale/repos/$repo && spec-kitty upgrade --project --dry-run 2>&1 | tail -15)
done
```

Then apply per repo:

```bash
for repo in metalbox bake-planner intentional bake-tracker kg-automation vikunja-harness; do
  echo "=== $repo ==="
  (cd /Users/kentgale/repos/$repo && spec-kitty upgrade --project --yes 2>&1 | tail -10)
done
```

Each successful upgrade auto-commits a `chore: apply spec-kitty upgrade changes (X -> Y)` commit and stamps `version:` + `last_upgraded_at:` in `.kittify/metadata.yaml`.

Verify the version stamp in every repo:

```bash
for repo in metalbox bake-planner intentional bake-tracker kg-automation vikunja-harness; do
  v=$(grep -E '^  version:' /Users/kentgale/repos/$repo/.kittify/metadata.yaml | head -1 | tr -d ' ')
  echo "$repo: $v"
done
```

### 3.4 Known soft-blockers

**TeamSpace SNAPSHOT_DRIFT** — bake-tracker and kg-automation carry pre-existing missions with missing `status.events.jsonl` (data debt from pre-3.0.x). Upgrade WARNS but still stamps the version. To audit or clear:

```bash
spec-kitty doctor mission-state --audit --fail-on teamspace-blocker
spec-kitty doctor mission-state --fix --mission <slug>
```

Operator decides whether to clear; leaving these unfixed is fine for solo work.

**Dirty `kitty-specs/` paths** — if a stale mission has uncommitted `meta.json` edits, mission-state repair refuses. Investigate the dirty file before stashing — it's likely the residue of an abandoned mission. Pass `--allow-dirty` only if you've verified the change is safe to skip.

**Per-repo upgrade is non-negotiable** — the CLI's `--agent-check` does NOT detect project-vs-CLI drift. Always run the per-repo dry-run+apply pass after any CLI bump. (See `feedback_speckitty_per_repo_upgrade_ritual.md`.)

---

## Troubleshooting

**`spec-kitty: command not found`** — `pipx ensurepath` then open a new shell.

**PyPI says "not found"** — the package is `spec-kitty-cli`, not `spec-kitty`. Both `pip index versions spec-kitty` and `curl https://pypi.org/pypi/spec-kitty/json` will 404.

**`curl https://pypi.org/pypi/spec-kitty-cli/json | jq -r '.releases | keys[]' | tail -10`** — list the most recent versions available on PyPI.

**Dashboard port conflict** — `spec-kitty dashboard --kill` then `spec-kitty dashboard --port 3001`.

**Reset a stuck worktree** — `git worktree list` then `git worktree remove <path>` from the main repo directory. Never `rm -rf` a `.worktrees/<slug>/` by hand.

---

## References

- `feedback_speckitty_per_repo_upgrade_ritual.md` — why per-repo `--yes` is required after every CLI bump.
- `feedback_no_mid_feature_upgrades.md` — never upgrade during an active mission.
- `reference_speckitty_version_history.md` — historical version log + upgrade procedure.
- `reference_speckitty_3_2_worktree_gitignore.md` — `.worktrees/` MUST be gitignored before any 3.2.x mission.
