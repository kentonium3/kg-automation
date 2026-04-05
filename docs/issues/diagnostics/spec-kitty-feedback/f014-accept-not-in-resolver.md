---
title: "Bug Report: Accept Action Not Registered in Context Resolver"
doc_type: diagnostic
status: active
---
# Bug Report: Accept Action Not Registered in Context Resolver

**Date**: 2026-04-04
**Spec-Kitty Version**: 3.0.3
**Reporter**: Kent Gale (via Claude Code)
**Priority**: Low — cosmetic inconsistency, easy workaround
**Status**: OPEN

## Summary

The `spec-kitty agent shim accept` command successfully resolves a context
token (e.g., `ctx-01KNCP...`), but `spec-kitty agent context resolve
--action accept` returns an error saying "accept" is not a valid action.
The shim and resolver disagree on what actions are valid.

## Reproduction

### Step 1: Shim succeeds

```bash
spec-kitty agent shim accept --agent claude --raw-args "WP01 --feature 014-felix-core-digest"
```

**Output:**
```text
✓ accept context resolved: ctx-01KNCPET0TN0GE5GFGXVGM8K1W
  Feature: 014-felix-core-digest
  WP:      WP01
  Agent:   claude
```

### Step 2: Resolver rejects the action

```bash
spec-kitty agent context resolve --action accept --feature 014-felix-core-digest --wp-id WP01 --json
```

**Output:**
```json
{
  "success": false,
  "error_code": "INVALID_ACTION",
  "error": "Invalid action 'accept'. Expected one of: tasks, tasks_outline, tasks_packages, tasks_finalize, implement, review."
}
```

### Expected Behavior

Either:
- `accept` is registered as a valid resolver action (consistent with the shim), or
- The shim doesn't generate accept contexts if the resolver can't consume them

### Actual Behavior

The shim generates a context token for `accept`, but the resolver can't use
it. The accept workflow works through `move-task --to approved` instead,
making the shim-generated context token unused.

## Impact

Minor — the accept workflow works through `move-task` commands. The
inconsistency is confusing for agents trying to follow the shim's output
instructions but doesn't block the workflow.

## Suggested Fix

Register `accept` as a valid action in the context resolver, or remove
the accept shim if it's not intended to be used with the resolver.

## Environment

- OS: macOS Darwin 25.3.0
- Python: 3.13.12
- spec-kitty-cli: 3.0.3
- Feature: 014-felix-core-digest

## Discovered

2026-04-04 by Claude Code during F014 acceptance phase
