# Bug Report: Feature Merge Fails With Spurious --json Error

**Date**: 2026-04-04
**Spec-Kitty Version**: 3.0.3
**Reporter**: Kent Gale (via Claude Code)
**Priority**: TBD
**Status**: STUB — minimal reproduction captured, needs investigation

## Summary

`spec-kitty agent feature merge --feature 014-felix-core-digest` fails with
an error about `--json` not being supported outside dry-run mode, even though
`--json` was not passed on the command line.

## Reproduction

### Attempt 1: With --json

```bash
spec-kitty agent feature merge --feature 014-felix-core-digest --json
```

**Error:**
```text
Exit code 2
No such option: --json
```

This is expected — `--help` confirms `--json` is not a valid option.

### Attempt 2: Without --json

```bash
spec-kitty agent feature merge --feature 014-felix-core-digest
```

**Error:**
```text
Exit code 1
{"spec_kitty_version": "3.0.3", "error": "--json is currently supported with --dry-run only."}
{"error": "1", "success": false}
```

`--json` was not passed, but the error message references it. The command
may be internally adding `--json` or there is a code path that checks for
JSON output mode regardless of the CLI flags.

## Context

- Feature 014-felix-core-digest has 6 WPs, all in "done" lane
- All WP branches are already merged into main (via manual git merge —
  see session notes)
- 6 worktrees and 7 branches still exist (cleanup not performed)
- 68 commits ahead of origin (not pushed)

## Open Questions

1. Is the merge command detecting that branches are already integrated and
   erroring on a different code path?
2. Does the merge command require WPs to be in a specific lane state that
   differs from "done"?
3. Is there an internal `--json` flag being set by the `agent feature merge`
   wrapper vs. the underlying merge implementation?

## Environment

- OS: macOS Darwin 25.3.0
- Python: 3.13.12
- spec-kitty-cli: 3.0.3
- Feature: 014-felix-core-digest (6 WPs, all done, all merged to main)

## Discovered

2026-04-04 by Claude Code during F014 post-implementation cleanup
