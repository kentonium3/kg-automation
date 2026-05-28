---
title: "Bug Report: Spec-Kitty configures incorrect wrapper directory for Google Antigravity (~/.agent/workflows/ vs. actual ~/.gemini/extensions/)"
doc_type: diagnostic
status: inactive
---
# Bug Report: Spec-Kitty configures incorrect wrapper directory for Google Antigravity (~/.agent/workflows/ vs. actual ~/.gemini/extensions/)

**Date**: 2026-05-24
**Spec-Kitty Version**: 3.1.8
**Reporter**: Kent Gale (via Antigravity)
**Priority**: Low — System operating as designed; global slash commands are bypassed in favor of workspace-local programmatic skills.
**Status**: CLOSED - OPERATING AS DESIGNED (REVERTED)

## Summary

The Spec-Kitty CLI identifies Google Antigravity (`antigravity`) as an agent with a global wrapper root directory of `~/.agent/workflows/`. While running `spec-kitty verify-setup` succeeds because the files are present in `~/.agent/workflows/`, the Antigravity CLI executable (`agy`) actually loads its plugins/extensions from the legacy Gemini CLI directory `~/.gemini/extensions/`. Because of this directory mismatch, none of the Spec-Kitty slash commands (such as `/spec-kitty.checklist` or `/spec-kitty.specify`) are registered or available in `agy` sessions.

## Reproduction

### Prerequisites

- Spec-Kitty version 3.1.8+
- Google Antigravity CLI (`agy`) installed and configured
- Spec-Kitty initialized in the active repository with `antigravity` configured under `agents.available` in `.kittify/config.yaml`.

### Steps

1. Run the Spec-Kitty verify setup command:
   ```bash
   spec-kitty verify-setup
   ```
   Note that all 112 skills and wrapper files are reported as intact and verified.
2. Launch an Antigravity interactive CLI session:
   ```bash
   agy --prompt-interactive
   ```
3. Type `/` to show available slash commands.

### Expected Behavior

The `/[spec-kitty-skill]` slash commands (e.g., `/spec-kitty.checklist`, `/spec-kitty.specify`) should be visible and selectable within the `agy` session.

### Actual Behavior

Only the default built-in commands of the Antigravity CLI are available (e.g., `/goal`, `/schedule`, `/grill-me`). The Spec-Kitty workflow slash commands are entirely absent.

The Antigravity CLI startup logs (`~/.gemini/antigravity-cli/log/cli-*.log`) show that it only searches for custom extensions inside `~/.gemini/extensions/`:

```text
I0524 22:41:17.401854 56717 gemini_extensions.go:28] Detecting Gemini extensions in /Users/kentgale/.gemini/extensions
I0524 22:41:17.402018 56717 gemini_extensions.go:49] No extensions found
```

### Root Cause

Inside the Spec-Kitty package, the `antigravity` command configurations are defined with `.agent/workflows/` as their wrapper root. For example, in `specify_cli/core/config.py`:

```python
AGENT_COMMAND_CONFIG: dict[str, dict[str, str]] = {
    ...
    "antigravity": {"dir": ".agent/workflows", "ext": "md", "arg_format": "$ARGUMENTS"},
}
```

And in `specify_cli/cli/commands/init.py` / `specify_cli/gitignore_manager.py`:
```python
"antigravity": ".agent/",
```

However, the Google Antigravity (`agy`) CLI continues to load external commands, plugins, and legacy Gemini extensions from `~/.gemini/extensions/`.

Because `agy` never reads from `~/.agent/workflows/`, the generated commands are completely unreachable.

## Workaround Applied (kg-automation)

### Initial Workaround
To bypass the path mismatch, we initially executed a manual workaround to copy the `.md` command files from `~/.agent/workflows/` into `~/.gemini/extensions/` (where the `agy` binary detects extensions). This made the slash commands available in active `agy` sessions.

### Reversal & Permanent Resolution
This workaround was subsequently **reverted and deleted** (`rm -f ~/.gemini/extensions/spec-kitty.*.md`). 

**Rationale for Reversal**:
1. **Maintenance and Drift Risk**: There is no automated upgrade or sync mechanism to detect when Spec-Kitty skills are updated and propagate those changes to the global `~/.gemini/extensions/` directory. Allowing globally copied command files introduces a high risk of version mismatch and silent configuration drift.
2. **Operating as Designed**: In modern developer environments, customized agent workflows are designed to be run programmatically or locally via workspace-level files (`.agents/skills/`), which are correctly tracked in version control and updated automatically via Spec-Kitty's workflow managers.
3. **No Global Bloat**: Reverting the global copy ensures the host system remains clean and does not accumulate stale custom command definitions across different projects.

Instead of global shell-level slash commands, the team will utilize workspace-local programmatic skills programmatically within active `agy` sessions.

## Suggested Fix

Update Spec-Kitty's core configuration and directory mappings for `antigravity` to use `~/.gemini/extensions/` as its wrapper root:

### In [specify_cli/core/config.py](file:///Users/kentgale/Library/Python/3.13/lib/python/site-packages/specify_cli/core/config.py):
```python
AGENT_COMMAND_CONFIG: dict[str, dict[str, str]] = {
    ...
    # Correct the wrapper directory to point to ~/.gemini/extensions
    "antigravity": {"dir": ".gemini/extensions", "ext": "md", "arg_format": "$ARGUMENTS"},
}
```

Similarly, align the `gitignore_manager.py` and `init.py` mappings so that Spec-Kitty installs `antigravity` commands directly into `~/.gemini/extensions`.

## Impact

- **Target Audience**: All developers migrating from Gemini CLI (`gemini`) to Google Antigravity (`agy`) ahead of the June 18, 2026 deprecation.
- **Consequences**: Out-of-the-box Spec-Kitty workflow slash commands fail silently during `agy` sessions. The orchestrator cannot run automated tasks or trigger spec/review workflows without manually creating symlinks/copies.

## Environment

- OS: macOS Darwin 25.3.0
- Python: 3.13
- spec-kitty-cli: 3.1.8 (reports 3.1.1 package on pip)
- Feature: F000-global-diagnostics

## Open Questions

1. **Does `agy` support loading commands from a project-local directory (analogous to `.gemini/extensions` or `.claude/commands`)?**
   No, our diagnostic tests confirm that `agy`'s Go codebase lacks workspace-level slash command detection. It only scans the global `~/.gemini/extensions/` directory during startup. Therefore, installing them globally is the only viable path to integrate custom slash commands into the `agy` interactive shell UI.
2. **Is there any leakage risk with globally registered commands?**
   No. All Spec-Kitty slash commands are natively "context-locked" via internal prerequisite checks (e.g., `spec-kitty agent mission check-prerequisites`). If run in a workspace where Spec-Kitty is not initialized, the commands fail and exit immediately.
3. **Should the extension folder be `.gemini/extensions` or does `agy` also plan to support `.antigravitycli/` or `.agent/` natively in future releases?**
   Currently, the production `agy` executable specifically checks `~/.gemini/extensions`.

## Next Steps

- **No Action Required**: This issue is closed and will not be filed upstream. The global slash command mismatch is deemed a legacy artifact of CLI shell integrations. Programmatic use of workspace-local skills (`.agents/skills/`) is the correct, maintainable pattern.

## Discovered

2026-05-24 by Antigravity during post-migration system diagnostic check.
