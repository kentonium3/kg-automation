---
title: "Bug Report: `spec-kitty agent config add <agent>` silently strips `agents.selection` block from .kittify/config.yaml"
doc_type: diagnostic
status: active
---
# Bug Report: `spec-kitty agent config add <agent>` silently strips `agents.selection` block from .kittify/config.yaml

**Date**: 2026-05-21
**Spec-Kitty Version**: 3.1.8 (reported by `spec-kitty --version`; pip reports installed package as 3.1.1 — internal self-updater may be in play)
**Reporter**: Kent Gale (via Claude Code)
**Priority**: Medium — silent loss of user-authored config; deterministic reproduction; trivial to spot but easy to miss if no one looks at the diff after running the command
**Status**: READY TO FILE

## Summary

Running `spec-kitty agent config add <agent>` correctly appends the new agent to `agents.available` in `.kittify/config.yaml`, but the same write also silently removes the entire `agents.selection` sub-block (including `preferred_implementer` and `preferred_reviewer`). For users who explicitly set those values, the next mission falls back to spec-kitty's automatic agent selection without warning. The bug is data-loss-by-omission: nothing in the command's output indicates that selection routing was dropped, and there is no `--dry-run` or `--preview-diff` flag to catch it before commit.

## Reproduction

### Prerequisites

- Spec-kitty 3.1.8 installed
- A repo with `.kittify/config.yaml` that contains BOTH:
  - `agents.available:` (list of agent keys)
  - `agents.selection.preferred_implementer:` and/or `agents.selection.preferred_reviewer:` (any non-empty value)
- The target agent is one of spec-kitty's recognized "available but not configured" agents (e.g., `antigravity`)

### Steps

```bash
# Inspect before
cat .kittify/config.yaml

# Run the add command
spec-kitty agent config add antigravity

# Inspect after
git diff .kittify/config.yaml
```

### Expected Behavior

The command should produce a minimal, additive diff: one new line appended to `agents.available:` and no other changes. The `agents.selection:` block (and any sibling keys like `agents.auto_commit:`) must be preserved verbatim — the command is described as "Add agents to the project. Creates agent directories and updates config.yaml." (per `spec-kitty agent config add --help`), so its scope should be limited to the agent list, not the full `agents:` subtree.

Expected diff:

```diff
   - codex
+  - antigravity
   selection:
     preferred_implementer: claude
     preferred_reviewer: codex
```

### Actual Behavior

The diff strips the entire `agents.selection:` block while appending the new agent:

```diff
diff --git a/.kittify/config.yaml b/.kittify/config.yaml
index 94e2d205..a918bd95 100644
--- a/.kittify/config.yaml
+++ b/.kittify/config.yaml
@@ -6,9 +6,7 @@ agents:
   - claude
   - gemini
   - codex
-  selection:
-    preferred_implementer: claude
-    preferred_reviewer: codex
+  - antigravity
   auto_commit: true
```

The `agents.auto_commit:` key happened to survive in this reproduction (it sits at a different level in the YAML structure), but `agents.selection:` and both nested keys are gone. The command's stdout was:

```text
✓ Registered antigravity (global commands at ~/.agent/workflows/)

Updated config.yaml: added antigravity
```

No warning about the dropped subkeys.

### Root Cause

Unconfirmed without reading spec-kitty source, but the diff pattern is consistent with `agent config add` deserializing `agents:` into a partial in-memory model that recognizes `available:` and `auto_commit:` but not `selection:`, then re-serializing the model and overwriting the file. The unrecognized `selection:` subkey is dropped because the writer doesn't have a representation for it.

This is the classic "round-trip through an incomplete deserializer drops unknown fields" failure mode. A YAML round-trip that preserves the document tree (e.g., `ruamel.yaml` round-trip mode) instead of a plain `dict` round-trip would prevent it.

## Workaround Applied (post-#309 cycle)

Manually re-added the stripped block after running `spec-kitty agent config add antigravity` and confirming the diff:

```yaml
agents:
  available:
  - copilot
  - claude
  - gemini
  - codex
  - antigravity
  selection:                    # <-- restored manually
    preferred_implementer: claude
    preferred_reviewer: codex
  auto_commit: true
```

Total restoration time was under 30 seconds. The fix held — `spec-kitty agent config list` still parses correctly after the restoration.

## Suggested Fix

**Option A** (preferred): switch the YAML round-trip to a comment-and-unknown-field-preserving mode (e.g., `ruamel.yaml` in round-trip mode, or pyyaml with a custom representer). The serializer keeps every key the deserializer doesn't understand. This fixes the class of bug, not just the `selection:` case — `auto_commit`, custom user-added keys, and any future config additions all become safe.

**Option B** (defensive minimum): make `agent config add` perform a string-level append rather than a parse-then-rewrite. Locate the `agents.available:` list in the raw YAML and insert the new entry. Slower to maintain across schema changes but eliminates the round-trip-drop class entirely.

**Option C** (call-site mitigation): keep the current parse-then-rewrite but pre-load every known config subkey before re-serialization. Brittle (every new subkey is a future bug surface) but smallest patch surface.

A `--preview-diff` flag for `agent config add` would also be useful operator hygiene, regardless of which fix lands.

## Impact

- **Who hits this**: every user who has explicitly set `agents.selection.preferred_implementer` or `agents.selection.preferred_reviewer` in `.kittify/config.yaml` AND runs `agent config add` for any new agent. Users who rely on spec-kitty's default agent selection (no `selection:` block at all) are unaffected.
- **Frequency**: any time a new agent is added to an existing project. Antigravity activation is the immediate context (Antigravity is becoming the post-gemini-cli fallback reviewer), but `auggie`, `cursor`, `kilocode`, etc. would all reproduce the same way.
- **What breaks**: future missions silently start using spec-kitty's automatic agent selection instead of the user's preferred routing. The orchestrator-side `--agent <tool>:<model>:<profile>:<role>` argument still works, but the project's *default* routing is lost.
- **How it's caught**: only by inspecting `git diff` after running the command. There is no warning at command time and no validator that flags missing `selection:` against expected configuration shape.

## Environment

- OS: macOS Darwin 25.5.0
- Python: 3.13.x (system python3)
- spec-kitty-cli: 3.1.8 (per `spec-kitty --version`); 3.1.1 (per `pip show spec-kitty-cli`) — version mismatch is itself worth flagging upstream but is separate from this report
- Feature: post-#309 escalation-to-JSONL cutover (where Antigravity needed to be activated as the fallback reviewer after codex hit a usage limit)

## Open Questions

1. **Are other subkeys under `agents:` affected the same way?**
   Untested: `agents.auto_commit:` survived in this reproduction but it sits adjacent (not nested) to `available:`. Any user-added subkey under `agents:` (or under `agents.selection:`) might be silently dropped. Worth a parameterized test.

2. **Does `spec-kitty agent config remove` exhibit the same round-trip drop?**
   Untested. If yes, the bug is in the shared config-write path, not specific to `add`. Same class of fix would apply.

3. **What other config files use the same writer?**
   If `meta.json` or `lanes.json` go through the same code path, they may have similar unknown-field-drop vulnerabilities. Probably not (those are spec-kitty-managed and don't carry user-authored keys), but worth checking.

## Next Steps

- File this report with the spec-kitty maintainer
- Cross-reference with the implement-review SKILL.md "antigravity dispatch template" upstream gap noted in [`docs/diagnostics/agy-migration.md`](agy-migration.md) — both surfaced during the same workflow and would benefit from being fixed in one upstream release

## Discovered

2026-05-21 by Kent Gale via Claude Code during the post-#309 cycle. Mission #309 had just completed; we were activating Antigravity as a replacement fallback reviewer for the deprecating gemini-cli. The config diff showed the unexpected mutation immediately after the `agent config add antigravity` command ran. Documented during the same session in [`docs/diagnostics/agy-migration.md`](agy-migration.md) §"spec-kitty bug discovered during this resolution".
