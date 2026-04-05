---
title: "Bug Report: finalize-tasks strips LLM-authored dependencies from WP frontmatter"
doc_type: diagnostic
status: active
---
# Bug Report: finalize-tasks strips LLM-authored dependencies from WP frontmatter

**Date**: 2026-04-05
**Spec-Kitty Version**: 3.0.3
**Reporter**: Kent Gale (via Claude Code)
**Priority**: CRITICAL — silently destroys the dependency DAG that `/spec-kitty.implement` relies on for correct WP sequencing
**Status**: READY TO FILE

## Summary

The `/spec-kitty.tasks` slash-command prompt explicitly instructs the LLM to parse dependencies from `tasks.md` and write them to each WP prompt file's `dependencies` frontmatter field. The subsequent (mandatory) `spec-kitty agent feature finalize-tasks` call then **re-parses `tasks.md` with a narrower regex** and silently **overwrites** the LLM-authored `dependencies` field with its own (usually-empty) parsed result. The JSON output reports `updated_wp_count: 0` even though files were modified.

This corrupts the execution DAG: downstream `/spec-kitty.implement` calls have no dependency information and all WPs look parallel-startable, breaking sequencing.

## Reproduction

### Prerequisites

- spec-kitty 3.0.3 project with a feature that has multi-WP dependencies
- Dependencies declared in `tasks.md` sections using bullet-list format:
  ```markdown
  ### Dependencies
  - WP01 (cite Divio standard)
  - WP02 (new path known)
  ```

### Steps

1. Run `/spec-kitty.tasks` slash-command.
2. During step 7 ("Generate prompt files"), write each WP file with `dependencies: [WP01, WP02]` in the frontmatter — exactly as the slash-command prompt instructs.
3. Run the mandatory final step: `spec-kitty agent feature finalize-tasks --feature <slug> --json`.
4. Check the generated WP files' frontmatter `dependencies` field.

### Expected Behavior

Either (a) `finalize-tasks` honors the LLM-authored `dependencies` values, OR (b) it re-parses `tasks.md` successfully and matches what the LLM wrote. In both cases, the execution DAG is preserved.

### Actual Behavior

`finalize-tasks` runs to success (`result: success`, `commit_created: true`) but **silently strips** the `dependencies` field to `[]` on most WPs. Only WP sections whose `tasks.md` text contains the literal phrase "depends on WP##" (as opposed to the bullet-list format the slash-command prompt describes) get parsed correctly.

**Evidence from F015 (13 FRs, 11 WPs)**:

```
WP  | LLM-authored (in tasks.md + frontmatter)   | After finalize-tasks
----|---------------------------------------------|----------------------
WP03| [WP01, WP02]                                | []            ❌
WP04| [WP02]                                      | []            ❌
WP06| [WP01]                                      | []            ❌
WP07| [WP01, WP02, WP03, WP04, WP05, WP06]        | []            ❌
WP08| [WP07]                                      | []            ❌
WP09| [WP07]                                      | []            ❌
WP11| [WP02, WP07]                                | [WP01, WP02, WP07]  ⚠️
```

10 of 11 WPs had frontmatter overwritten. Only WP11 survived parsing AND gained a spurious `WP01` that was not in its `tasks.md` Dependencies section.

The WP11 parsing appears to match on a single line elsewhere in `tasks.md` with the phrase "WP11 (depends on WP07 + WP02)" in the Work Package Execution Order section — NOT from WP11's own `### Dependencies` subsection.

### Root Cause

`finalize-tasks`'s dependency parser uses a regex that matches phrases like `depends on WP##` or `Dependencies: WP##`, but the slash-command prompt (`/spec-kitty.tasks`) tells the LLM to generate bullet-list style:

```markdown
### Dependencies
- WP01 (reason)
- WP02 (reason)
```

When the parser finds no match for its narrower regex, it writes `dependencies: []` to the frontmatter — destroying the LLM's work without warning.

Additionally, the JSON output reports `updated_wp_count: 0` even though the frontmatter WAS modified, making the destruction harder to detect.

## Workaround Applied (F015)

Per user directive ("option 2: manually patch the frontmatter"), the LLM-authored dependencies were manually restored via `Edit` tool after the strip, then committed before any subsequent `finalize-tasks` run. Preserved across all subsequent `implement/review/approved` transitions.

```bash
# After finalize-tasks completed with stripped dependencies:
# Manually edit each affected WP file to restore the dependencies array.
# Commit immediately (spec-kitty's auto_commit doesn't cover the repair).
git add kitty-specs/<feature>/tasks/WP*.md
git commit -m "fix: restore dependencies after finalize-tasks stripped them"
```

Further complication: running `spec-kitty agent feature finalize-tasks --validate-only --json` after the repair **also strips** the restored dependencies (see separate bug report: `validate-only-mutates-frontmatter.md`). The repair only survives if NO subsequent finalize-tasks call happens.

## Suggested Fix

Option A: **Harmonize slash-command and parser formats.** Update the
slash-command prompt to instruct the LLM to use the "depends on WP##" phrase
the parser recognizes, OR update the parser to recognize the bullet-list
format the slash-command prompt describes. The current mismatch is the root
cause.

Option B: **Preserve existing frontmatter.** When `finalize-tasks` parses
`tasks.md` and finds no dependencies but the WP file already has a non-empty
`dependencies` field in frontmatter, preserve the existing value rather than
overwriting with `[]`.

Option C: **Fail loudly.** When the parser's result disagrees with existing
frontmatter, emit a warning or error instead of silently overwriting. The
current `updated_wp_count: 0` report is misleading.

Option D: **Single source of truth.** Decide whether `tasks.md` OR the WP
frontmatter owns dependency declarations. Currently both claim ownership,
and they disagree.

## Impact

- Every multi-WP feature that follows the documented `/spec-kitty.tasks`
  workflow hits this.
- Dependency DAG is silently corrupted; `/spec-kitty.implement` no longer
  knows which WPs depend on which.
- Multi-parent merge-base creation (which relies on dependencies) still
  happens to work because it uses a different code path, but any agent
  checking `dependencies` frontmatter for sequencing decisions gets wrong
  information.
- Manual repair is fragile — next `finalize-tasks` call (including
  `--validate-only`) re-strips.

## Environment

- OS: macOS Darwin 25.3.0
- Python: 3.13.12
- spec-kitty-cli: 3.0.3
- Feature: 015-documentation-architecture-rationalization (11 WPs, 13 FRs,
  documentation mission)

## Open Questions

1. **What exact regex does the parser use?** Understanding the pattern would
   clarify whether the slash-command prompt could be updated to produce
   matching text, and whether WP11's partial success reveals a specific
   match form.

2. **Why did WP11 get a spurious `WP01`?** WP11's `tasks.md` Dependencies
   section lists `- WP07` and `- WP02`, not WP01. The spurious `WP01` may
   reveal a parser bug where it matches across WP sections.

3. **Is `updated_wp_count: 0` report a separate bug?** The count is wrong —
   files WERE modified. Either the counter is incrementing in the wrong
   place or it's measuring something else (e.g., metadata field additions,
   not modifications).

## Next Steps

- Inspect `spec-kitty-cli` source to confirm the parser regex
- Confirm the JSON `updated_wp_count` counter logic
- File upstream with this report and a minimal reproduction

## Discovered

2026-04-05 by Claude Code during F015 WP03-WP11 implementation. Entry in
running journal: `../spec-kitty-workflow-journal.md` (2026-04-04 entry:
"finalize-tasks overwrote LLM-authored dependency frontmatter").
