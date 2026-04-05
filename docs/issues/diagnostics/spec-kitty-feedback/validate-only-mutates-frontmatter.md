---
title: "Bug Report: finalize-tasks --validate-only mutates WP frontmatter (flag contract violation)"
doc_type: diagnostic
status: active
---
# Bug Report: finalize-tasks --validate-only mutates WP frontmatter

**Date**: 2026-04-05
**Spec-Kitty Version**: 3.0.3
**Reporter**: Kent Gale (via Claude Code)
**Priority**: HIGH — violates the "--validate-only" flag contract, silently destroys user edits
**Status**: READY TO FILE

## Summary

`spec-kitty agent feature finalize-tasks --validate-only` is expected to be a
read-only dry-run (validate state, do not modify files). It is instead
destructive: it runs the same bootstrap step as the non-validate invocation,
which re-parses `tasks.md` and **rewrites WP frontmatter** (stripping
`dependencies` fields, rewriting `branch_strategy`, etc.). The command returns
`"result": "validation_passed"` while silently overwriting files on disk. Users
who use `--validate-only` to confirm that a manual repair is correct end up
with their repair destroyed.

## Reproduction

### Prerequisites

- spec-kitty 3.0.3 feature with at least one WP that has dependencies
- Manually patch a WP file's `dependencies` frontmatter (e.g., restore it
  after a previous `finalize-tasks` strip)
- Do NOT commit the patch yet

### Steps

```bash
# Manually edit WP03's frontmatter to set dependencies: [WP01, WP02]
# Verify the patch is in place:
grep -A3 "^dependencies:" kitty-specs/<feature>/tasks/WP03-*.md

# Run the supposedly-read-only validation:
spec-kitty agent feature finalize-tasks --feature <slug> --validate-only --json

# Check the file again:
grep -A3 "^dependencies:" kitty-specs/<feature>/tasks/WP03-*.md
```

### Expected Behavior

A flag named `--validate-only` should be a pure dry-run: read files, validate
state, emit a report, exit without mutations. Convention across CLI tooling
universally treats `--validate-only` / `--dry-run` / `--check` as
read-only.

### Actual Behavior

`--validate-only` runs the bootstrap step unconditionally, which re-parses
`tasks.md` and rewrites WP frontmatter on disk. The patched `dependencies`
field is stripped back to `[]`. The JSON output returns
`"result": "validation_passed"` and the bootstrap block reports:

```json
{
  "result": "validation_passed",
  "bootstrap": {"total_wps": 11, "newly_seeded": 0, "already_initialized": 11},
  ...
}
```

The mutation is silent in the JSON output — no field signals that files
were modified.

**F015 evidence**: after manually patching 7 WP files to restore stripped
`dependencies` arrays, running `finalize-tasks --validate-only` reverted all
7 patches. `git status` showed no changes because the patched state now
matched the previous committed state (which contained the stripped values).

### Root Cause

The bootstrap step inside `finalize-tasks` runs unconditionally, before
the validate/commit fork. Bootstrap re-parses `tasks.md` and writes
frontmatter based on the parser's output. The `--validate-only` flag only
suppresses the final commit step — it does NOT skip the mutation-inducing
bootstrap.

## Workaround Applied (F015)

After discovering the silent revert during F015:

```bash
# Re-apply the 7 frontmatter patches via Edit tool
# Immediately commit via git (do not run finalize-tasks again)
git add kitty-specs/<feature>/tasks/WP*.md
git commit -m "fix: restore dependencies after validate-only revert"
```

**Critical caveat**: the repair is fragile. Any subsequent `finalize-tasks`
invocation — including `--validate-only` — will strip the dependencies
again. The F015 repair survived because no further `finalize-tasks` calls
were made.

## Suggested Fix

Option A: **Skip bootstrap under --validate-only.** The flag name and
convention require read-only behavior. Bootstrap should not run when the
user is asking for validation only.

Option B: **Make bootstrap idempotent.** When bootstrap encounters WP
frontmatter with a non-empty `dependencies` field, it should preserve
the existing value rather than overwriting with its own (potentially
empty) parse result.

Option C: **Rename the flag.** If bootstrap truly must run unconditionally,
rename `--validate-only` to something honest like `--no-commit` or
`--preview-effects`. The current name violates the CLI convention.

## Impact

- Any manual repair to WP frontmatter is fragile — next `finalize-tasks`
  call (including validate-only) destroys it
- Users cannot safely inspect the state of their feature using
  `--validate-only` without risking data loss
- Cross-references to [finalize-tasks-strips-dependencies.md](finalize-tasks-strips-dependencies.md)
  — this bug compounds that one: manual recovery from the dependency strip
  is possible but only if validate-only is never run again

## Environment

- OS: macOS Darwin 25.3.0
- Python: 3.13.12
- spec-kitty-cli: 3.0.3
- Feature: 015-documentation-architecture-rationalization

## Open Questions

1. **What else does bootstrap mutate?** Besides stripping dependencies,
   bootstrap rewrites `branch_strategy` (expanded to a longer paragraph).
   What other frontmatter fields does it overwrite?

2. **Is there a `--dry-run` or other read-only alternative?** If not, how
   do users safely inspect feature state?

3. **Does the same issue apply to other spec-kitty commands that run
   bootstrap?** (e.g., `check-prerequisites`, `setup-plan`)

## Next Steps

- Inspect spec-kitty-cli source to map bootstrap's full mutation surface
- Confirm other bootstrap-invoking commands have the same issue
- File upstream with this report

## Discovered

2026-04-05 by Claude Code during F015 WP dependency repair. Running journal
entry: `../spec-kitty-workflow-journal.md` (2026-04-04 entry:
"finalize-tasks --validate-only is NOT actually read-only").
