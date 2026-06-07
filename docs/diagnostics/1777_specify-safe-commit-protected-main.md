# Bug: /spec-kitty.specify safe-commit refuses spec.md commit on protected main — class symptom of #1619/#1666, not covered by closed #1348/#1386 fixes

**Filed upstream**: [Priivacy-ai/spec-kitty#1777](https://github.com/Priivacy-ai/spec-kitty/issues/1777) (2026-06-07). Internal tracking: [kentonium3/kg-automation#559](https://github.com/kentonium3/kg-automation/issues/559).

## Summary

The `/spec-kitty.specify` runbook (3.2.0rc37) instructs the operator to commit `spec.md` via `spec-kitty safe-commit --message "Add spec for <slug>" <feature_dir>/spec.md` from the repository root checkout. On any repo whose target branch is protected (default for `main`), the safe-commit refuses:

```
Error: Refusing to create commit 'Add spec for <slug>' on protected branch 'main' in <repo>. Run status commit operations from the mission lane branch/worktree.
```

The error advises switching to a lane branch/worktree, but **during specify there is no lane branch yet** — lanes materialize at `/spec-kitty.implement` per the git-workflow skill. The coord branch exists but the specify runbook explicitly says specify stays in the repository root checkout. The runbook and the CLI guard are mutually incompatible for fresh missions.

## Reproduction

```bash
cd <fresh repo on 3.2.0rc37, on protected main>

spec-kitty agent mission create "minimal-repro" \
  --friendly-name "Minimal repro" \
  --purpose-tldr "Reproduce specify safe-commit failure" \
  --purpose-context "Minimal repro." \
  --json

# Populate spec.md with substantive content (real FR rows, etc.).

spec-kitty safe-commit \
  --message "Add spec for minimal-repro" \
  kitty-specs/minimal-repro-<mid8>/spec.md

# → Error: Refusing to create commit on protected branch 'main' ...
```

`coordination_branch_created: true` in the `create --json` output, but the coord worktree does NOT exist at `.worktrees/<slug>-<mid8>-coord/` (worktree materialization is lazy, on first `BookkeepingTransaction.acquire()` write). The runbook's commit step never runs through that write path.

## Why this is fresh

Two closed tickets addressed the implement-phase analogue of this class:

- [Priivacy-ai/spec-kitty#1348](https://github.com/Priivacy-ai/spec-kitty/issues/1348) (closed by [#1361](https://github.com/Priivacy-ai/spec-kitty/pull/1361)) — protected-branch guard during `agent action implement`
- [Priivacy-ai/spec-kitty#1386](https://github.com/Priivacy-ai/spec-kitty/issues/1386) (closed by [#1387](https://github.com/Priivacy-ai/spec-kitty/pull/1387)) — protected-branch guard during status transitions / `move-task`

Neither covered the specify-phase `safe-commit ... spec.md` chain. The exception list at `src/specify_cli/git/commit_helpers.py` (`_PROTECTED_BRANCH_COMMIT_EXCEPTIONS`) carries `"chore: apply spec-kitty upgrade changes"`, `"chore: release "`, and `"release: "` — none match the specify-phase commit message documented in the runbook.

## Local workaround applied

Switched the repository root checkout from `main` to the coordination branch `kitty/mission-<slug>-<mid8>` (per the CLI's explicit recommendation), then `spec-kitty safe-commit --to-branch kitty/mission-<...>` to commit `spec.md` on the coord branch. Branch switch is reversible — return to `main` after the mission lands.

Sibling first-symptom (decision open failure during specify) workaround: resolve all `[NEEDS CLARIFICATION]` upfront, since Decision Moment Protocol is unusable on 3.2.0rc37. Documented in `kentonium3/kg-automation#559`.

## Class context

This bug sits inside the coord-vs-primary execution-context authority split-brain class. Parent and sibling tickets:

- [Priivacy-ai/spec-kitty#1619](https://github.com/Priivacy-ai/spec-kitty/issues/1619) — Epic: unify mission execution context across coord/main/lane topology (P0, launch-blocker)
- [Priivacy-ai/spec-kitty#1666](https://github.com/Priivacy-ai/spec-kitty/issues/1666) — Execution-state & context domain-boundary redesign (blocks #1619)
- [Priivacy-ai/spec-kitty#1672](https://github.com/Priivacy-ai/spec-kitty/issues/1672) — Strangler step 1: e2e parity ratchet (the proof gate)
- [Priivacy-ai/spec-kitty#1764](https://github.com/Priivacy-ai/spec-kitty/issues/1764) — implement-loop coord/primary read/write split
- [Priivacy-ai/spec-kitty#1765](https://github.com/Priivacy-ai/spec-kitty/issues/1765) — dependent-lane base coord/primary split
- [Priivacy-ai/spec-kitty#1589](https://github.com/Priivacy-ai/spec-kitty/issues/1589) — original coord/mission branch status desync (closed; class redesign in flight)

## Environment

- `spec-kitty-cli`: 3.2.0rc37 (pipx-managed; upgraded from 3.1.8 on 2026-06-06)
- Host: macOS (darwin 25.5.0), Python 3.13
- Downstream repo: `kentonium3/kg-automation` (default branch protected `main`)
- Date observed: 2026-06-07
- Affected mission: `inbox-calendar-and-aspiration-routing-01KTHHXS` (tracking [#558](https://github.com/kentonium3/kg-automation/issues/558))
