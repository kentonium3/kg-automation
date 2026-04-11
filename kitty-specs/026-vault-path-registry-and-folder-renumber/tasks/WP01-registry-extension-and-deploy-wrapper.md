---
work_package_id: WP01
title: Registry Extension and Deploy Wrapper
dependencies: []
requirement_refs:
- C-001
- C-002
- FR-001
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-026-vault-path-registry-and-folder-renumber
base_commit: 60cc93f91087ac512e9d4535c62cbf9978063fec
created_at: '2026-04-11T01:44:17.736022+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
shell_pid: "4174"
agent: "claude:opus-4-6:implementer:implementer"
history:
- date: '2026-04-11T01:15:00Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/vault/
execution_mode: code_change
owned_files:
- scripts/vault/paths.json
- scripts/vault/targets.json
- scripts/deploy/deploy-f026.sh
tags: []
---

# WP01: Registry Extension and Deploy Wrapper

## Objective

Extend the mission-024 vault path registry from one logical name (`inbox`) to all ten top-level vault folders. Populate `scripts/vault/targets.json` with the complete list of files WP02 will migrate. Create `scripts/deploy/deploy-f026.sh` as a thin wrapper around `scripts/vault/deploy.py` that adds mission-specific orchestration (cron pause/resume, verification, smoke tests). Also audit `.kittify/charter/charter.md` for any non-`_private/` vault path references that need operator-driven handling via `spec-kitty charter sync`.

After this WP, the registry infrastructure is ready for WP02's code migration but no files have been converted yet — the system still runs exactly as it did before.

## Context

- This is the first WP of mission 026 (vault path registry full rollout and folder renumber)
- Mission 024 (MVP, kentonium3/kg-automation#150, already merged) built: `scripts/vault/paths.json`, `scripts/vault/resolver.py`, `scripts/vault/paths.sh`, `scripts/vault/deploy.py`, `scripts/vault/targets.json`, `scripts/vault/README.md`
- Mission 024 shipped with exactly one registry entry (`inbox`) and one target (`felix-admin-capture/AGENTS.md.tmpl`)
- The extension uses the same schema — no schema evolution in this WP
- The `scripts/deploy/deploy-f026.sh` wrapper is required for charter compliance (the Deployment Constraints rule). A separate issue (kentonium3/kg-automation#154) proposes amending the charter to recognize shared deploy primitives like `deploy.py`, but that amendment does not block this mission
- `.kittify/` is workflow-managed — direct edits to charter files are forbidden. Operator-driven charter edits flow through `spec-kitty charter sync`
- The `_private/` path is a constitutional privacy boundary — it is NEVER added to the registry (C-001, C-002)

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP01 --agent <name>`
- Execution: single lane worktree (created by `spec-kitty.implement`)

## Contracts

- [../contracts/registry-schema.md](../contracts/registry-schema.md) — paths.json contract
- [../contracts/targets-schema.md](../contracts/targets-schema.md) — targets.json contract
- [../contracts/deploy-wrapper-contract.md](../contracts/deploy-wrapper-contract.md) — deploy-f026.sh contract
- [../contracts/verification-contract.md](../contracts/verification-contract.md) — WP01 acceptance tests

---

## Subtask T001: Audit repo for files requiring migration

**Purpose:** Produce the complete, authoritative list of files that WP02 will convert to `.tmpl` template sources. This audit is the basis for every entry in `targets.json` (T003) and every `.tmpl` file created in WP02.

**Steps:**

1. Run a repo-wide grep for the current vault folder names:
   ```bash
   grep -rn "00-Inbox\|01-Constitution\|02-Growth\|03-Health\|04-Business\|05-Finance\|06-Journal\|07-Resources\|00-System" \
     scripts/ ai-agents/ CLAUDE.md \
     --include="*.md" --include="*.json" --include="*.py" --include="*.sh" \
     2>/dev/null
   ```
2. For each file in the output, categorize it:
   - **Category A: OpenClaw agent workspace file** (e.g., `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`). Has an office2 deployment target.
   - **Category B: Claude instruction file** (e.g., `ai-agents/claude-instructions.md`). Repo-only, no office2 deploy.
   - **Category C: Top-level project config** (`CLAUDE.md`). Repo-only.
   - **Category D: Script with vault path literals** (e.g., a helper under `scripts/`). Decide per-file: refactor to call `get_vault_path()` at runtime (preferred) OR convert to `.tmpl` (if it's a static config file).
3. Exclude from the migration list:
   - Files under `.claude/worktrees/` (ephemeral agent worktrees)
   - Files under `kitty-specs/` (mission history — never modified)
   - Files under `docs/archive/` and `docs/func-spec/` (historical archive)
   - `scripts/vault/paths.json` itself (the registry data file — contains the literal by design)
   - `scripts/vault/README.md` (contains example literals as documentation)
   - `CLAUDE.md`'s single `_private/` boundary line (constitutional, stays hardcoded)
4. Confirm the list against the four known OpenClaw agents: `felix-admin-capture`, `felix-admin-escalation`, `felix-admin-habits`, `felix-admin-tasker`, plus `main/` and `main-patches/`.
5. Cross-reference against `docs/constitution/AGENT-REGISTRY.md` to confirm no registered agents are missing from the file list.
6. Write the final audit list to a mission artifact at `kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp01-migration-targets.md`. Group by category. Include the file path, the vault folder literals present, and any notes about how to handle it.

**Files produced:**
- `kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp01-migration-targets.md` (new research artifact)

**Validation:**
- [ ] Audit artifact exists with at least one entry per category
- [ ] All four OpenClaw agents and both support directories (`main/`, `main-patches/`) are represented where applicable
- [ ] Both `ai-agents/` Claude instruction files are represented
- [ ] `CLAUDE.md` is listed with a note about the `_private/` boundary exception
- [ ] No files under excluded directories appear in the list

---

## Subtask T002: Extend `scripts/vault/paths.json` with all 10 logical names

**Purpose:** Populate the registry with every logical name consumers will reference. Initial values point at the **current** folder names — no renames happen in this WP.

**Steps:**

1. Edit `scripts/vault/paths.json`. Set `updated` to today's date. Replace the `paths` object with the following (all values use the PRE-RENAME folder names):

   ```json
   {
     "version": 1,
     "updated": "2026-04-11",
     "paths": {
       "system":          "/home/kgale/second-brain/notes/00-System",
       "inbox":           "/home/kgale/second-brain/notes/00-Inbox",
       "inbox_processed": "/home/kgale/second-brain/notes/02-Inbox-Processed",
       "constitution":    "/home/kgale/second-brain/notes/01-Constitution",
       "growth":          "/home/kgale/second-brain/notes/02-Growth",
       "health":          "/home/kgale/second-brain/notes/03-Health",
       "business":        "/home/kgale/second-brain/notes/04-Business",
       "finance":         "/home/kgale/second-brain/notes/05-Finance",
       "journal":         "/home/kgale/second-brain/notes/06-Journal",
       "resources":       "/home/kgale/second-brain/notes/07-Resources"
     }
   }
   ```

2. **Important:** `inbox_processed` points at the eventual-target path `02-Inbox-Processed` even though the physical folder does not exist yet. This is intentional — the registry entry is present so consumers can resolve the marker; no consumer actually dereferences `inbox_processed` until WP05 creates the physical folder and the `#149` follow-on mission ships. An early dereference would produce a "path does not exist" error, which is an acceptable failure mode for pre-WP05 state.

3. `_private` is NOT added. The path is deliberately unreachable through the registry (C-002).

**Files modified:**
- `scripts/vault/paths.json`

**Validation:**
- [ ] File parses as valid JSON: `python3 -m json.tool scripts/vault/paths.json > /dev/null`
- [ ] All 10 logical names present in `paths`
- [ ] No entry for `_private`
- [ ] `python3 scripts/vault/resolver.py inbox` returns the current inbox path
- [ ] `python3 scripts/vault/resolver.py inbox_processed` returns the target path (does not error even though folder doesn't exist yet — resolver doesn't check existence)
- [ ] `python3 scripts/vault/resolver.py _private` raises `UnknownPathError`
- [ ] `source scripts/vault/paths.sh && echo "$VAULT_INBOX_PROCESSED"` prints the target path

---

## Subtask T003: Extend `scripts/vault/targets.json` with migration target entries

**Purpose:** Populate the target manifest with one entry per file that WP02 will convert to a `.tmpl`. This manifest drives `scripts/vault/deploy.py`'s substitution loop.

**Steps:**

1. Using the T001 audit output, add one entry per migration target to `scripts/vault/targets.json`. Preserve the existing felix-admin-capture entry from mission 024.

2. For each OpenClaw agent file (Category A), the entry format is:

   ```json
   {
     "template": "scripts/openclaw/agents/<agent-dir>/<filename>.tmpl",
     "output":   "scripts/openclaw/agents/<agent-dir>/<filename>",
     "office2_path": "/data/services/openclaw/<office2-dir>/<filename>"
   }
   ```

   The `office2_path` follows the existing pattern from mission 024. Confirm the directory naming convention on office2 by examining the existing `felix-admin-capture` target (which deploys to `/data/services/openclaw/inbox-agent/`). Other agents follow the analogous naming — confirm via:

   ```bash
   ssh office2-claude 'ls /data/services/openclaw/'
   ```

3. For `ai-agents/` Claude instruction files (Category B), omit `office2_path`:

   ```json
   {
     "template": "ai-agents/claude-instructions.md.tmpl",
     "output":   "ai-agents/claude-instructions.md"
   }
   ```

4. For `CLAUDE.md` (Category C), the entry is:

   ```json
   {
     "template": "CLAUDE.md.tmpl",
     "output":   "CLAUDE.md"
   }
   ```

5. For scripts (Category D), add a target entry only if the script is being converted to a `.tmpl` rather than refactored to use the resolver. Prefer the resolver refactor for anything that is actual code.

6. **Do not create the `.tmpl` source files in this subtask** — that is WP02's job. This subtask only populates the manifest. `deploy.py` will fail if invoked against the manifest now because the `.tmpl` files don't exist; that's expected until WP02 completes.

**Files modified:**
- `scripts/vault/targets.json`

**Validation:**
- [ ] File parses as valid JSON
- [ ] Every entry has required fields (`template`, `output`)
- [ ] `template` and `output` differ for every entry
- [ ] Every `template` path ends in `.tmpl`
- [ ] Every `office2_path` (where present) is absolute
- [ ] The felix-admin-capture entry from mission 024 is preserved unchanged
- [ ] Entry count matches the T001 audit (one entry per migration target in categories A–D)

---

## Subtask T004: Create `scripts/deploy/deploy-f026.sh` wrapper [P]

**Purpose:** Create the mission-specific deploy wrapper that satisfies the charter's Deployment Constraints rule. The wrapper orchestrates the mission-specific sequence (cron pause/resume, verification, smoke tests) around `scripts/vault/deploy.py`.

**Steps:**

1. Create `scripts/deploy/deploy-f026.sh` with executable permissions. Use `scripts/deploy/deploy-f013.sh` as a reference implementation for the bash script conventions used in this repo.

2. The wrapper must implement the interface defined in [../contracts/deploy-wrapper-contract.md](../contracts/deploy-wrapper-contract.md). Key points:
   - Flags: `--dry-run`, `--apply`, `--mode pre-rename`, `--mode post-rename`, `--skip-smoke`, `--skip-cron`, `--help`
   - Default behavior without flags: dry-run
   - `--apply` requires a `--mode` flag
   - Invalid mode or missing required flag combination → exit non-zero with clear error

3. **Pre-rename mode** (for WP04):
   - Runs `python3 scripts/vault/deploy.py --apply`
   - Does NOT touch the cron (pre-rename is a pure refactor)
   - Runs smoke-test invocations of `felix-admin-capture` and `felix-admin-tasker` on office2 and captures their outputs for WP04 to diff against pre-deploy baselines
   - Exit 0 only if deploy succeeded and both smoke tests exited cleanly

4. **Post-rename mode** (for WP05):
   - Step 1: Tier 2 pre-flight — calls out to the backup-verification routine (operator may do this manually and pass `--backup-confirmed` if implementing the check inline is overkill)
   - Step 2: Pause `felix-admin-capture` cron on office2 via `ssh office2-claude` and crontab manipulation
   - Step 3: Run `python3 scripts/vault/deploy.py --apply`
   - Step 4: Repo-wide grep for stale literals; fail on any hit (excluding documented exclusions)
   - Step 5: Deployed-file grep for unreplaced `{{VAULT_*}}` markers; fail on any hit
   - Step 6: Smoke-test `felix-admin-capture` end-to-end
   - Step 7: Smoke-test `felix-admin-tasker` end-to-end
   - Step 8: Obsidian wikilink integrity check (mechanism: spot-check a known set of wikilinks, or query the Obsidian API if available)
   - Step 9: Re-enable `felix-admin-capture` cron
   - Step 10: Verify the cron fires correctly (trigger a one-shot manual run, or wait for the next natural tick)
   - Any failure halts the sequence with a loud error message and does NOT auto-resume the cron (operator must acknowledge)

5. **Invariants** (enforced by the script):
   - Idempotent re-runs produce the same result
   - Never silent — every action emits output
   - Non-zero exit on any failure
   - `--skip-smoke` and `--skip-cron` print loud warnings to stderr
   - On any failure in post-rename mode, the script prints `===== FAILURE =====` framing and states the current system state (including whether cron is still paused)

6. Reference implementation hint: `scripts/deploy/deploy-f013.sh` shows the bash conventions (shebang, set -euo pipefail, usage function, argument parsing, logging). Follow the same style.

**Files produced:**
- `scripts/deploy/deploy-f026.sh` (new, executable)

**Validation:**
- [ ] File exists and is executable: `test -x scripts/deploy/deploy-f026.sh`
- [ ] `bash scripts/deploy/deploy-f026.sh --help` prints usage and exits 0
- [ ] `bash scripts/deploy/deploy-f026.sh` (no flags) defaults to dry-run and exits 0
- [ ] `bash scripts/deploy/deploy-f026.sh --apply` (no mode) exits non-zero with clear error
- [ ] `bash scripts/deploy/deploy-f026.sh --apply --mode invalid` exits non-zero with clear error
- [ ] Script uses `set -euo pipefail` (matching repo convention)
- [ ] Script uses absolute or repo-rooted paths (no reliance on `$PWD`)

---

## Subtask T005: Audit `.kittify/charter/charter.md` for non-`_private/` vault path references [P]

**Purpose:** Determine whether the charter file contains vault path references beyond the `_private/` boundary, and if so, how to handle them without violating the `.kittify/` workflow-managed rule.

**Steps:**

1. Grep `.kittify/charter/charter.md` for vault folder literals:
   ```bash
   grep -n "00-Inbox\|01-Constitution\|02-Growth\|03-Health\|04-Business\|05-Finance\|06-Journal\|07-Resources\|00-System" \
     .kittify/charter/charter.md
   ```

2. For each hit, categorize:
   - **Hit is the `_private/` boundary reference** (`02-Growth/_private/`) → leave alone for now. This line will be updated in WP05 as part of the folder rename, but NOT via a `.tmpl` — it stays hardcoded per C-001.
   - **Hit is any other vault folder reference** → the operator must update `.kittify/charter/charter.md` manually and run `spec-kitty charter sync` to propagate the change.

3. If non-`_private/` hits exist:
   - Document them in the WP01 research artifact (from T001)
   - Flag them for operator attention in the WP01 completion report
   - **Do NOT edit `.kittify/charter/charter.md` from within an agent context** — per CLAUDE.md, `.kittify/` is workflow-managed
   - The operator performs the edit as a manual step and runs `spec-kitty charter sync`
   - After sync, the operator re-runs this audit to confirm zero non-boundary hits

4. If only the `_private/` boundary hit exists: document the single hit and confirm WP05 will update it via the hardcoded path rewrite (not via template markers).

**Files examined (read-only from the agent's perspective):**
- `.kittify/charter/charter.md`
- `.kittify/charter/directives.yaml`
- `.kittify/charter/library/user-project-profile.md`

**Validation:**
- [ ] Audit results documented in `kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp01-migration-targets.md` (appended or in a charter-files section)
- [ ] If non-boundary hits exist, the operator was flagged and resolved them before WP02 proceeds
- [ ] If only boundary hits exist, the WP01 report explicitly notes "charter files require no migration beyond the WP05 hardcoded-path update"

---

## Subtask T006: Verify WP01 acceptance

**Purpose:** Run all WP01 acceptance checks from the verification contract before closing the WP.

**Steps:**

1. Registry completeness:
   ```bash
   python3 scripts/vault/resolver.py system
   python3 scripts/vault/resolver.py inbox
   python3 scripts/vault/resolver.py inbox_processed
   python3 scripts/vault/resolver.py constitution
   python3 scripts/vault/resolver.py growth
   python3 scripts/vault/resolver.py health
   python3 scripts/vault/resolver.py business
   python3 scripts/vault/resolver.py finance
   python3 scripts/vault/resolver.py journal
   python3 scripts/vault/resolver.py resources
   ```
   All 10 must print a path.

2. Privacy boundary:
   ```bash
   python3 scripts/vault/resolver.py _private
   # Must exit non-zero with UnknownPathError
   ```

3. Shell resolver:
   ```bash
   source scripts/vault/paths.sh
   test -n "$VAULT_INBOX_PROCESSED"
   test -n "$VAULT_SYSTEM"
   echo "$VAULT_INBOX"
   ```

4. Deploy dry-run:
   ```bash
   python3 scripts/vault/deploy.py
   # Expected: "dry-run" mode output; will report missing .tmpl files because WP02 hasn't created them yet
   # This is expected behavior at WP01 — the command should still exit 0 in dry-run mode
   # if deploy.py exits non-zero due to missing .tmpl files, that's a WP02 prerequisite, not a WP01 failure
   ```
   Note: the exit code behavior for dry-run with missing .tmpl files may be implementation-dependent. If `deploy.py` exits non-zero in dry-run because `.tmpl` files are missing, document this in the WP01 completion note so WP02 knows to create the `.tmpl` files before running another dry-run.

5. Wrapper help:
   ```bash
   bash scripts/deploy/deploy-f026.sh --help
   bash scripts/deploy/deploy-f026.sh
   bash scripts/deploy/deploy-f026.sh --apply 2>&1 | grep -i error
   ```

6. Charter audit status:
   - Confirm the T005 audit is documented
   - If non-boundary hits existed, confirm the operator resolved them

**Validation:**
- [ ] All 10 resolver lookups succeed
- [ ] `_private` lookup fails with UnknownPathError
- [ ] Shell resolver exports all 10 variables
- [ ] `deploy-f026.sh --help` exits 0
- [ ] `deploy-f026.sh` (no flags) defaults to dry-run safely
- [ ] `deploy-f026.sh --apply` without mode errors out
- [ ] Charter audit documented; any non-boundary hits resolved
- [ ] WP01 acceptance checks from `contracts/verification-contract.md` § WP01 all pass

---

## Definition of Done

- [ ] `scripts/vault/paths.json` contains all 10 logical names pointing at current folder paths
- [ ] `scripts/vault/targets.json` contains one entry per file identified in the T001 audit
- [ ] `scripts/deploy/deploy-f026.sh` exists, is executable, and implements the contract
- [ ] `.kittify/charter/charter.md` audit documented; any non-boundary vault refs resolved
- [ ] All verification checks in `contracts/verification-contract.md` § WP01 pass
- [ ] `kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp01-migration-targets.md` exists with the full audit
- [ ] WP01 changes committed to the mission branch

## Risks

- **Charter file contains non-boundary vault refs.** Mitigation: T005 explicitly audits for this; operator handles via manual edit + sync.
- **Office2 directory naming for new agent targets is inconsistent.** Mitigation: T003 confirms via `ssh office2-claude 'ls /data/services/openclaw/'` before populating `targets.json`.
- **`deploy.py` behavior in dry-run mode with missing .tmpl files is undocumented.** Mitigation: T006 validation note documents the actual behavior so WP02 knows what to expect.
- **T001 audit misses a file containing vault path literals.** Mitigation: the WP02 grep check (NFR-002) will catch any missed literal before WP02 closes.

## Reviewer Guidance

The reviewer should confirm:

- `paths.json` contains exactly the 10 required logical names and no extras
- `_private` is not in `paths.json`
- `targets.json` entries match the T001 audit artifact — no phantom entries, no missing entries
- `deploy-f026.sh` is reviewable (not auto-generated glue with no logic); the flag handling, mode dispatch, and error-on-failure behavior are clearly implemented
- The T005 charter audit produced either zero non-boundary hits or a documented operator action
- No production files have been migrated yet — `grep` for old folder names still returns hits in exactly the files the audit identified (none have been converted to `.tmpl` yet)

## Activity Log

- 2026-04-11T01:44:18Z – claude:opus-4-6:implementer:implementer – shell_pid=4174 – Assigned agent via action command
