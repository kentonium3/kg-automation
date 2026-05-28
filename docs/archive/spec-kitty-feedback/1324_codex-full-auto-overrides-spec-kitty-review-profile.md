---
title: "Bug Report: spec-kitty implement-review skill dispatches codex with deprecated `--full-auto`, which overrides the `spec-kitty-review` profile and blocks `.git/` writes (move-task fails)"
doc_type: diagnostic
status: active
---
# Bug Report: spec-kitty implement-review skill dispatches codex with deprecated `--full-auto`, which overrides the `spec-kitty-review` profile and blocks `.git/` writes (move-task fails)

**Date**: 2026-05-24
**Spec-Kitty Version**: 3.1.8 (reported by `spec-kitty --version`; pip reports installed package as 3.1.1 — internal self-updater may be in play)
**Reporter**: Kent Gale (via Claude Code)
**Priority**: High — every codex review in spec-kitty 3.1.8 + codex 0.133.0 fails its terminal `move-task` step; the orchestrator must compensate manually, which inflates review-cycle counters and risks state divergence
**Status**: FILED https://github.com/Priivacy-ai/spec-kitty/issues/1324

## Summary

The `spec-kitty-implement-review` skill dispatches codex with `codex exec --full-auto -C <dir> -`. In codex CLI 0.133.0, `--full-auto` is deprecated and is implemented as a shorthand for `--sandbox workspace-write`, which blocks writes to `.git/` (where spec-kitty stores per-mission lock files and frontmatter commits). Even when the orchestrator adds `-p spec-kitty-review` per the documented workaround (a profile that sets `sandbox = "danger-full-access"`), the explicit `--full-auto` flag overrides the profile's sandbox setting. The result: codex completes the review/implementation work but fails its terminal `spec-kitty agent tasks move-task` call with a `.git/index.lock` write error, forcing the orchestrator to commit status updates from the main repo manually after every codex action.

## Reproduction

### Prerequisites

- Spec-kitty 3.1.8 (or any version where `spec-kitty-implement-review/SKILL.md` still dispatches codex with `--full-auto`)
- codex CLI ≥ 0.133.0 (where `--full-auto` is deprecated to `--sandbox workspace-write`)
- A `~/.codex/config.toml` with a `spec-kitty-review` profile defined per the established workaround:
  ```toml
  [profiles.spec-kitty-review]
  sandbox = "danger-full-access"
  ```
- An active mission with a work package in `for_review` lane

### Steps

```bash
# Trigger a codex review of WP## using spec-kitty's own dispatch shape
OUTPUT=$(spec-kitty agent action review WP## --mission <slug> --agent codex:gpt-5:spec-kitty-review:reviewer 2>&1)
REVIEW_PROMPT=$(echo "$OUTPUT" | grep -o '/var/folders[^ ]*/spec-kitty-review-WP[0-9]*.md')
WORKTREE=$(echo "$OUTPUT" | grep 'Workspace: cd ' | sed 's/.*Workspace: cd //')

# Build the combined prompt
printf 'IMPORTANT: After reviewing, you MUST execute the appropriate spec-kitty agent tasks move-task command shown at the bottom of this prompt.\n---\n' > /tmp/review-prompt-WP##.md
cat "$REVIEW_PROMPT" >> /tmp/review-prompt-WP##.md

# Dispatch using the skill's documented command shape
cat /tmp/review-prompt-WP##.md | codex exec --full-auto \
  -C "$WORKTREE" --add-dir "$(pwd)" \
  -o "/tmp/review-result-WP##.md" -
```

### Expected Behavior

Codex completes the review and runs `spec-kitty agent tasks move-task WP## --to approved --note "Review passed: <summary>"` (or `--to planned --force --review-feedback-file <path>` on rejection). The lane transition succeeds and spec-kitty's status event log records the verdict.

### Actual Behavior

Codex completes the review work and produces the verdict, then attempts `move-task`. The transition fails because spec-kitty cannot acquire its per-mission lock file inside `.git/`:

```text
warning: `--full-auto` is deprecated; use `--sandbox workspace-write` instead.
... [review proceeds] ...
PermissionError: [Errno 13] Permission denied: '.git/index.lock'
spec-kitty: failed to write lock file; transition aborted
```

The orchestrator (Claude Code in this session) then has to manually run `move-task` from the main repo and commit the status transition. Each manual compensation cycle:

- Increments the spec-kitty `review-cycle-N.md` counter (the prior mission #403 ended at cycle 6 on WP02 for a single real rejection)
- Forces the orchestrator to make explicit status-only commits, which fall outside the safe-commit pattern
- Adds friction that violates the global "no manual workflow workarounds" rule

### Root Cause

In codex CLI 0.133.0:

```text
$ echo "test" | codex exec --full-auto -C /tmp -
warning: `--full-auto` is deprecated; use `--sandbox workspace-write` instead.
```

`--full-auto` is now a deprecated alias for `--sandbox workspace-write`. The `workspace-write` sandbox blocks writes to `.git/`. This is documented in the `~/.codex/config.toml` comment that introduces the `spec-kitty-review` profile (Kent's existing manual workaround):

```toml
# workspace-write blocks writes to .git/ (where spec-kitty stores its
# per-mission lock files) and to ~/.spec-kitty/ (state dir outside the
# workspace). Both are required for `spec-kitty agent tasks move-task`
# to complete. danger-full-access lifts both restrictions for this
# profile only; codex CLI continues to use workspace-write by default
# for any non-profile invocation.
```

Explicit CLI flags on `codex exec` override profile defaults from `config.toml`. So when the user combines `--full-auto` with `-p spec-kitty-review`, the profile's `sandbox = "danger-full-access"` is silently overridden by `--full-auto`'s implicit `--sandbox workspace-write`. The user-facing workaround (configuring the profile) is bypassed by the skill itself.

Affected files in the spec-kitty distribution (all under `spec-kitty/skills/spec-kitty-implement-review/`):

- `SKILL.md` line 64 — agent capability matrix entry
- `SKILL.md` line 220 — implementation dispatch command
- `SKILL.md` line 340 — review dispatch command
- `references/agent-dispatch-matrix.md` line 13 — quick-reference matrix entry

## Workaround Applied (post-#403 cycle)

Two-layer workaround:

**Layer 1 — codex config** (already in place, from kentonium3/kg-automation#330):

```toml
# ~/.codex/config.toml
[profiles.spec-kitty-review]
sandbox = "danger-full-access"
```

**Layer 2 — local skill patch** (applied 2026-05-24): replaced all 16 `--full-auto` occurrences with `-p spec-kitty-review` across all four agent homes that host the skill (`~/.claude/`, `~/.agents/`, `~/.qwen/`, `~/.kilocode/`). The skill files are normally read-only; `chmod +w` then patched with `Edit` (replace_all). The local patches will be reverted next time spec-kitty refreshes the skills directory (e.g., on upgrade), at which point they will need to be re-applied until the upstream fix lands.

```bash
# Locate every copy of the skill
find ~ -name "spec-kitty-implement-review" -type d 2>/dev/null

# Patch all 16 occurrences (in each SKILL.md and references/agent-dispatch-matrix.md)
chmod +w <skill files>
# Replace `--full-auto` with `-p spec-kitty-review` in each file (codex contexts only)
```

After the patch, codex's `move-task` call succeeded on its own and the orchestrator no longer had to compensate by committing status updates from main.

## Suggested Fix

**Option A** (preferred): replace `--full-auto` with `--sandbox danger-full-access` directly in the skill. This is portable across all users (no profile setup required) and matches what codex actually needs for spec-kitty workflows. The trade-off is that `danger-full-access` is the most permissive sandbox setting; users who want narrower codex permissions for other invocations can still configure them at the codex-level (codex's other invocations are unaffected because the skill's dispatch is a self-contained command line). Add a short comment in the skill explaining why this sandbox mode is required (so the next maintainer doesn't tighten it without understanding the consequence).

```bash
# In SKILL.md and references/agent-dispatch-matrix.md
codex exec --sandbox danger-full-access -C <dir> -
```

**Option B**: ship a documented codex profile (e.g., `spec-kitty-review`) as part of spec-kitty's setup flow and dispatch with `-p spec-kitty-review`. Users without the profile would see a clear error from codex (`profile not found in config.toml`) rather than a sandbox permission error. This matches the local patch applied as the immediate workaround, but it requires spec-kitty to take a hard dependency on a user-installable codex profile.

**Option C** (minimal patch): leave the dispatch as-is but suppress codex's terminal `move-task` call, instead having the orchestrator always run `move-task` on behalf of codex (the "Tier 2 — Workaround Required" pattern already used for `cursor`). This eliminates the failure path entirely but loses the "codex can complete its own move-task" capability — a regression compared to today's behavior in profile-configured environments.

Independent of which option lands, the skill should also remove the deprecated `--full-auto` flag — it emits a warning on every codex invocation today.

## Impact

- **Who hits this**: every spec-kitty user who dispatches codex for either implementation or review on codex CLI ≥ 0.133.0 (where `--full-auto` deprecation took effect).
- **Frequency**: every codex action on every spec-kitty mission. Implementation dispatch and review dispatch both fail their terminal `move-task` call.
- **What breaks**: codex completes the review/implementation work successfully, but cannot transition the WP. The orchestrator (a Claude Code or other driver) must compensate by:
  - Running `move-task` manually from the main repo
  - Making a manual status commit (`chore(kitty): WP## approval status (codex sandbox required manual status commit)`) outside the safe-commit pattern
  - Tolerating an inflated `review-cycle-N.md` counter (mission #403 hit cycle 6 on WP02 for a single real rejection)
- **Severity**: not data-loss (the verdict still lands), but adds material friction to every codex-driven mission and violates the global "workflow systems are authoritative" rule. Manual compensation increases the chance of state divergence in long missions.

## Environment

- OS: macOS Darwin 25.5.0
- Python: 3.13.x (system python3)
- spec-kitty-cli: 3.1.8 (per `spec-kitty --version`); 3.1.1 (per `pip show spec-kitty-cli`)
- codex CLI: 0.133.0
- Feature: post-#403 (drift-ledger retry-count hardening mission); first observed during the same mission's WP02 review cycle

## Open Questions

1. **Does this affect codex CLI < 0.133.0 the same way?**
   Untested. Earlier codex versions may have implemented `--full-auto` as a self-contained sandbox preset that allowed `.git/` writes (matching its earlier documentation). If so, this bug is a regression introduced by codex's deprecation of `--full-auto`, not a long-standing spec-kitty issue. Worth confirming the cutover version before filing — if the regression is owned by codex, the fix may instead belong on that side (e.g., preserve `--full-auto`'s historical sandbox behavior under the new flag shape).

2. **Are other agents in the dispatch matrix affected by similar sandbox-mode deprecations?**
   The matrix lists `gemini --yolo`, `qwen --yolo`, `kilocode -a --yolo -j`, `auggie --acp`, etc. Each CLI's sandbox/permission model has its own evolution. Worth a parameterized verification pass to catch the next "deprecated convenience flag overrides explicit user config" issue before it lands in production.

3. **Should spec-kitty install codex's `spec-kitty-review` profile as part of its setup?**
   Currently the profile is user-installed (per kentonium3/kg-automation#330's documentation). If Option B is chosen, spec-kitty's setup flow could write the profile to `~/.codex/config.toml` on first run, removing the manual-installation step. Trade-off: spec-kitty modifying a sibling tool's config file.

## Next Steps

- File this report with the spec-kitty maintainer
- After upstream fix lands, verify by:
  1. Removing the local skill patches (let spec-kitty's upgrade restore the upstream version)
  2. Running a mission with a codex-dispatched review
  3. Confirming codex's own `move-task` call succeeds with no orchestrator compensation
- Cross-reference with [`docs/diagnostics/agy-migration.md`](<./agy-migration.md>) since the dispatch matrix was last touched during the post-#309 antigravity activation work and both issues live in the same skill

## Discovered

2026-05-24 by Kent Gale via Claude Code during the mission #403 (`drift-ledger-retry-count-hardening-01KSC6AJ`) WP02 review cycle. Codex consistently hit `.git/index.lock` write errors during `move-task`, even with `-p spec-kitty-review` passed. The orchestrator (Claude Code) compensated by committing status updates from main after each codex action, inflating the `review-cycle-N.md` counter to 6 for a single real rejection of WP02. Documented in [`docs/temp/context-continuity-2026-05-24-mission403.md`](<../temp/context-continuity-2026-05-24-mission403.md>) under "Spec-kitty issues observed during mission #403". Root cause isolated 2026-05-24 in the post-mission session by checking `codex exec --help` (which revealed the deprecation warning) and tracing the explicit-flag-overrides-profile interaction.
