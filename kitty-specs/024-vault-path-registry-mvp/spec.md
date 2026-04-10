# Vault Path Registry MVP

**Feature**: 024-vault-path-registry-mvp
**Mission**: software-dev
**Source**: GitHub issue #150
**Target Branch**: main

---

## Executive Summary

Vault folder paths are hardcoded across agent standing orders, TOOLS.md files, CLAUDE.md, scripts, and documentation. Renaming a folder requires coordinated edits across many files — fragile and error-prone. This feature introduces a path registry infrastructure that centralizes path definitions and eliminates hardcoded references, starting with a minimal proof of concept.

**Scope deliberately narrow**: build the registry, Python resolver, shell resolver, and deploy script. Migrate exactly ONE hardcoded reference (the inbox path in one agent file) to prove the methodology end-to-end. Once proven, a follow-up feature extends the registry to all vault paths and includes folder renumbering.

Current gaps:
- ❌ Vault paths hardcoded in multiple agent and script files
- ❌ No single source of truth for where folders live
- ❌ Folder moves require multi-file coordinated edits

---

## Problem Statement

**Current State:**
```
Hardcoded paths scattered across files
├─ Agent AGENTS.md files (each reference path independently)
├─ TOOLS.md files
├─ Scripts that touch vault content
├─ Documentation
└─ Any new consumer adds another hardcoded reference
```

**Target State:**
```
Path registry as single source of truth
├─ paths.json (human-editable, version-controlled)
├─ Python resolver (importable by scripts)
├─ Shell resolver (sourceable by shell scripts)
├─ Deploy script (resolves templates and writes target files)
└─ Target files use {{VAULT_*}} template markers in .tmpl source
```

---

## Study These Files First

1. **Current hardcoded inbox references**
   - Find: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (repo copy)
   - Find: `/data/services/openclaw/inbox-agent/AGENTS.md` (on office2)
   - Note: how many times the inbox path appears, what surrounding context looks like

2. **Existing scripts directory structure**
   - Find: `scripts/` in the repo — organization and conventions
   - Note: where new scripts typically live, how they are invoked

3. **Existing JSON config patterns**
   - Find: `docs/constitution/agent-registry.json`, spec-kitty `meta.json` files
   - Note: schema conventions, whether version fields are used

4. **Existing shell scripts in repo**
   - Find: any `.sh` files in `scripts/`
   - Note: shebang conventions, how they handle paths, whether they use existing helpers

---

## Assumptions

- The registry JSON lives in the repo at `scripts/vault/paths.json` (or similar) — version-controlled, editable, small
- The Python resolver is a module importable by other scripts in the repo
- The shell resolver is sourceable: `source scripts/vault/paths.sh` exports `VAULT_*` environment variables
- Template markers use a double-brace syntax: `{{VAULT_INBOX}}` — unlikely to collide with markdown or code content
- Source files with template markers use a `.tmpl` suffix or are otherwise clearly distinguishable from resolved output
- The deploy script is idempotent: running it multiple times produces the same result
- The deploy script has a dry-run mode that shows what would change without writing
- After deploy, target files contain resolved concrete paths, not template markers
- `jq` is available on office2 and Mac for shell resolver implementation (to be verified in planning)

---

## Functional Requirements

### FR-001: Path Registry Data File

| Field | Value |
|---|---|
| **ID** | FR-001 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Create a JSON file at a canonical location in the repo
- The JSON contains a map of logical names to physical paths
- MVP contents: exactly one entry for `inbox` mapping to the current inbox path
- Schema supports future extension (additional entries, optional metadata fields)
- Schema is documented — either inline or in a README alongside the JSON

**Business rules:**
- Logical names are lowercase, underscore-separated (e.g., `inbox`, `inbox_processed`)
- Physical paths are absolute
- The file must be valid JSON (parseable by both Python's `json` module and `jq`)

**Success criteria:**
- [ ] JSON file exists and is valid
- [ ] Contains exactly one entry for the inbox path
- [ ] Schema is documented
- [ ] File is committed to the repo

---

### FR-002: Python Resolver Library

| Field | Value |
|---|---|
| **ID** | FR-002 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Provide a Python function that accepts a logical name and returns the resolved physical path
- Read the registry from the canonical location
- Raise a clear, specific error when the logical name is not found
- Be importable by other Python scripts in the repo
- Be testable: the lookup function can be called with a known registry and produce expected results

**Business rules:**
- Lookup is case-sensitive (logical names are exact matches)
- Missing logical names raise an exception with a helpful message listing what is available
- Missing or malformed registry file raises a distinct exception so callers can distinguish the two

**Success criteria:**
- [ ] Function returns the correct path for `inbox`
- [ ] Unknown logical name raises a clear exception
- [ ] Another script in the repo can import and use the resolver
- [ ] The function has no runtime dependencies outside the standard library

---

### FR-003: Shell Resolver

| Field | Value |
|---|---|
| **ID** | FR-003 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Provide a sourceable shell script that reads the registry and exports environment variables
- After sourcing, `$VAULT_INBOX` contains the resolved path for the inbox logical name
- Works in bash and zsh
- Handles the case where the registry file is missing with a clear error

**Business rules:**
- Environment variable names follow the pattern `VAULT_<UPPERCASE_LOGICAL_NAME>`
- Sourcing is silent on success (no output to stdout/stderr unless error)
- If the registry is missing or malformed, source produces an error message and a non-zero return
- Uses `jq` or a small Python helper to parse JSON — no hand-rolled JSON parsing

**Success criteria:**
- [ ] `source scripts/vault/paths.sh` sets `$VAULT_INBOX` correctly
- [ ] Works in bash and zsh
- [ ] Missing registry produces a clear error
- [ ] A downstream shell script can use `$VAULT_INBOX` after sourcing

---

### FR-004: Build-Time Deploy Script

| Field | Value |
|---|---|
| **ID** | FR-004 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Read the registry
- Find template source files (files with `.tmpl` suffix or similar convention) in a defined set of locations
- For each template file, replace `{{VAULT_<NAME>}}` markers with the corresponding resolved path
- Write the resolved content to the corresponding non-`.tmpl` target file
- Support a dry-run mode that shows what would change without writing
- Report what files were processed and what was changed

**Business rules:**
- Only markers corresponding to entries in the registry are replaced — unknown markers produce a clear error
- The script is idempotent: running it twice produces the same result
- The script handles both repo-side files and files on office2 (the mechanism — direct write via SSH, SCP, or other — is chosen in planning)
- Dry-run is the default for safety; applying changes requires an explicit flag

**Success criteria:**
- [ ] Script reads registry and finds template files
- [ ] Dry-run mode shows changes without writing
- [ ] Apply mode writes resolved files to targets
- [ ] Unknown markers produce a clear error
- [ ] Running twice produces identical output (idempotent)

---

### FR-005: Migrate Inbox Path in One Agent File

| Field | Value |
|---|---|
| **ID** | FR-005 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Identify ONE target file to migrate: the felix-admin-capture agent standing orders (repo copy and deployed counterpart on office2)
- Create a `.tmpl` version of the file with `{{VAULT_INBOX}}` in place of the hardcoded inbox path
- Run the deploy script to produce the resolved output
- Verify the resolved file is functionally identical to the original
- Confirm the inbox agent continues to function normally after the change

**Business rules:**
- The original hardcoded path is replaced only in places where the inbox path appears as a standalone reference — not partial matches inside other paths
- The `.tmpl` file is committed to the repo as the authoritative source
- The inbox agent is triggered at least once post-migration to verify no behavioral regression

**Success criteria:**
- [ ] `.tmpl` file exists with template marker
- [ ] Deploy script produces the resolved file correctly
- [ ] Diff between resolved file and original shows only expected changes (if any)
- [ ] Inbox agent runs successfully after migration

---

## Non-Functional Requirements

### NFR-001: Zero Runtime Cost for Agents

| Field | Value |
|---|---|
| **ID** | NFR-001 |
| **Status** | Proposed |
| **Priority** | High |

Agents consuming the resolved files have zero additional work compared to the hardcoded version. The resolved files contain concrete paths — agents do not call the resolver at runtime. This is a build-time concern, not a runtime concern. Token cost for agents is unchanged.

---

### NFR-002: Dry-Run Safety

| Field | Value |
|---|---|
| **ID** | NFR-002 |
| **Status** | Proposed |
| **Priority** | High |

The deploy script's default behavior is dry-run. Applying changes requires an explicit flag. This prevents accidental overwrites during development or when running the script to inspect what it would do.

---

## Constraints

### C-001: Limited Migration Scope

| Field | Value |
|---|---|
| **ID** | C-001 |
| **Status** | Active |
| **Priority** | High |

Only ONE file is migrated in this feature. The goal is to prove the methodology, not to migrate everything. Additional migrations are follow-up work (#152).

### C-002: No Privacy Path

| Field | Value |
|---|---|
| **ID** | C-002 |
| **Status** | Active |
| **Priority** | High |

The `_private/` path is never added to the registry. Autonomous agents discover paths only through the registry — keeping `_private` out means they cannot reference it even accidentally. The policy boundary in standing orders remains hardcoded for defense in depth.

---

## Out of Scope

- ❌ Migrating other hardcoded vault path references (#152)
- ❌ Adding more logical names beyond `inbox` to the registry (#152)
- ❌ Folder renumbering (#152)
- ❌ Runtime registry access by agents (defeats the point of build-time resolution)
- ❌ Gitignoring `_private/` in second-brain repo (#152)
- ❌ Web UI or CLI for registry management (YAGNI for MVP)

---

## User Scenarios & Testing

### Scenario 1: Developer Adds a New Logical Name

**Actor:** Kent (or Claude) editing the registry in a future extension
**Flow:** Edit `paths.json` to add a new entry → run deploy script in dry-run → review changes → run with apply flag
**Expected outcome:** Deploy script shows what would change in dry-run; applying writes the resolved files
**Acceptance:** Adding a new entry and running the script does not break existing migrated files

### Scenario 2: Deploy Script Detects Unknown Marker

**Actor:** Developer who added `{{VAULT_NEW_PATH}}` to a `.tmpl` file but forgot to add it to `paths.json`
**Flow:** Run deploy script → script finds the marker → script reports an error listing the unknown marker
**Expected outcome:** Clear error message, no files written, non-zero exit code
**Acceptance:** Developer can add the missing registry entry and re-run successfully

### Scenario 3: Inbox Agent Runs Post-Migration

**Actor:** felix-admin-capture on its next scheduled run after migration
**Flow:** Cron triggers agent → agent reads its AGENTS.md (which now has the resolved path baked in) → processes inbox as normal
**Expected outcome:** Agent behavior is identical to before migration
**Acceptance:** Inbox agent runs successfully, session log shows normal processing, no errors

### Scenario 4: Idempotent Deploy

**Actor:** Developer running the deploy script twice in a row
**Flow:** Run deploy with apply flag → run deploy with apply flag again → compare target files
**Expected outcome:** Target files are identical after both runs
**Acceptance:** No changes on the second run, script reports nothing to update

---

## Key Entities

| Entity | Description |
|---|---|
| Path Registry | JSON file mapping logical names to physical paths — single source of truth |
| Logical Name | A symbolic identifier for a vault path (e.g., `inbox`) used in template markers and API calls |
| Template Marker | A placeholder in source files like `{{VAULT_INBOX}}` that the deploy script replaces |
| Template File | A `.tmpl` source file containing template markers, committed to the repo |
| Target File | The resolved output file that replaces markers with concrete paths |
| Deploy Script | The build-time tool that reads the registry, processes templates, and writes targets |
| Python Resolver | A library function that returns resolved paths for Python consumers |
| Shell Resolver | A sourceable shell script that exports `VAULT_*` environment variables |

---

## Success Criteria

- A JSON registry file exists with the inbox path entry
- Python code can import the resolver and look up the inbox path
- Shell scripts can source the resolver and use `$VAULT_INBOX`
- A deploy script processes template files and writes resolved output
- At least one file has been migrated from hardcoded to template-driven
- The migrated file's resolved output is functionally identical to the original
- The inbox agent continues to function normally post-migration
- The methodology is documented well enough for follow-up migrations (#152) to proceed mechanically

---

## Risk Considerations

**Risk: Template marker syntax collides with existing file content**
- Using `{{VAULT_*}}` with a distinctive `VAULT_` prefix makes collision unlikely
- Mitigation: scan existing files for `{{VAULT_` patterns before adopting the convention; document the chosen pattern

**Risk: Deploy script corrupts a target file during partial rollout**
- Mitigation: dry-run by default; write to a temp file and rename atomically; back up the target before overwriting

**Risk: Resolved files drift from `.tmpl` sources if someone edits the resolved copy directly**
- Mitigation: document that `.tmpl` is authoritative; add a header comment to resolved files warning against direct edits

**Risk: Shell resolver requires `jq` but office2 or Mac does not have it**
- Mitigation: verify `jq` availability before assuming it; fall back to Python helper if needed

---

## Notes for Implementation

**Pattern Discovery (Planning Phase):**
- Study existing scripts in `scripts/` to understand organization conventions
- Study existing JSON config files for schema patterns
- Check if `jq` is available on office2 and Mac
- Decide: commit resolved files to the repo, or regenerate on deploy only?

**Key Patterns to Establish:**
- The `.tmpl` + deploy + resolved pattern becomes the canonical way to manage path references in this repo
- Future features (#152 and beyond) will use this pattern without inventing new approaches

---

**END OF SPECIFICATION**
