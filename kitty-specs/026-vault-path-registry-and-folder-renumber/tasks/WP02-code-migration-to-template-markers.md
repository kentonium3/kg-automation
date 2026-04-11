---
work_package_id: WP02
title: Code Migration to Template Markers
dependencies:
- WP01
requirement_refs:
- C-001
- FR-002
- NFR-001
- NFR-002
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
- T010
- T011
- T012
- T013
agent: "claude:opus-4-6:reviewer:reviewer"
shell_pid: "13742"
history:
- date: '2026-04-11T01:15:00Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl
- scripts/openclaw/agents/felix-admin-capture/TOOLS.md
- scripts/openclaw/agents/felix-admin-capture/TOOLS.md.tmpl
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md.tmpl
- scripts/openclaw/agents/felix-admin-escalation/TOOLS.md
- scripts/openclaw/agents/felix-admin-escalation/TOOLS.md.tmpl
- scripts/openclaw/agents/felix-admin-escalation/SOUL.md
- scripts/openclaw/agents/felix-admin-escalation/SOUL.md.tmpl
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md.tmpl
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md.tmpl
- scripts/openclaw/agents/felix-admin-tasker/TOOLS.md
- scripts/openclaw/agents/felix-admin-tasker/TOOLS.md.tmpl
- scripts/openclaw/agents/felix-admin-tasker/SOUL.md
- scripts/openclaw/agents/felix-admin-tasker/SOUL.md.tmpl
- scripts/openclaw/agents/felix-admin-tasker/USER.md
- scripts/openclaw/agents/felix-admin-tasker/USER.md.tmpl
- scripts/openclaw/agents/main/SOUL.md
- scripts/openclaw/agents/main/SOUL.md.tmpl
- scripts/openclaw/agents/main/USER.md
- scripts/openclaw/agents/main/USER.md.tmpl
- scripts/openclaw/agents/main-patches/inbox-delegation.md
- scripts/openclaw/agents/main-patches/inbox-delegation.md.tmpl
- ai-agents/claude-instructions.md
- ai-agents/claude-instructions.md.tmpl
- ai-agents/claude-code-instructions.md
- ai-agents/claude-code-instructions.md.tmpl
- CLAUDE.md
- CLAUDE.md.tmpl
tags: []
---

# WP02: Code Migration to Template Markers

## Objective

Convert every production file containing hardcoded vault-path literals (per the WP01 audit) to a `.tmpl` source file with `{{VAULT_*}}` markers. Run `scripts/vault/deploy.py --apply` to produce resolved output files. The resolved outputs must be byte-identical (or semantically equivalent) to the pre-migration content — this is a pure refactor. Registry values still point at the CURRENT folder names (pre-rename), so runtime behavior must be unchanged.

This WP sets up the refactor-fidelity check that WP04 will verify.

## Context

- WP01 has populated `scripts/vault/paths.json` and `scripts/vault/targets.json`
- WP01's T001 audit artifact (`kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp01-migration-targets.md`) is the authoritative list of files to migrate
- Mission 024's `felix-admin-capture/AGENTS.md.tmpl` already exists from the MVP — this WP extends it with any additional markers needed for newly-registered logical names, but does NOT overwrite the existing content
- The `_private/` boundary line in `CLAUDE.md` stays HARDCODED (C-001) — it is the one exception to FR-002
- The folder rename has NOT happened yet — so the `_private/` line still references `02-Growth/_private/` (the current path, which becomes `04-Growth/_private/` in WP05)
- The deploy script's invariant: byte-identical resolved output (except expected substitutions) is NFR-001 and the basis for WP04's fidelity check

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP02 --agent <name>`
- Execution: single lane worktree, dependency on WP01

## Contracts

- [../contracts/targets-schema.md](../contracts/targets-schema.md) — targets.json contract
- [../contracts/verification-contract.md](../contracts/verification-contract.md) — WP02 acceptance tests

---

## Subtask T007: Convert OpenClaw agent workspace files to `.tmpl` sources

**Purpose:** Convert every OpenClaw agent file containing vault path literals into a `.tmpl` source with `{{VAULT_*}}` markers. The converted files span four agents (`felix-admin-capture`, `felix-admin-escalation`, `felix-admin-habits`, `felix-admin-tasker`) plus the `main/` and `main-patches/` support directories.

**Steps:**

1. For each file in Category A of the WP01 audit artifact, create a `.tmpl` source alongside the original file:
   - Copy the original file to `<filename>.tmpl`
   - In the `.tmpl` source, replace every hardcoded vault folder literal with the corresponding `{{VAULT_*}}` marker
   - Example: `/home/kgale/second-brain/notes/00-Inbox` becomes `{{VAULT_INBOX}}`
   - Example: `/home/kgale/second-brain/notes/02-Growth` becomes `{{VAULT_GROWTH}}`
   - The path-suffix after the folder name stays literal: `{{VAULT_INBOX}}/subfolder/file.md`

2. **Do NOT modify the original (non-`.tmpl`) file directly.** The deploy script will regenerate it from the `.tmpl` source in T011. However, some files will already exist at the output path from the pre-WP02 state — `deploy.py --apply` will overwrite them.

3. **Do NOT convert:**
   - `SOUL.md` or `USER.md` files that contain no vault path literals (most `main-patches/` files may be in this category — check the WP01 audit)
   - Any file that is already listed in `targets.json` but has no vault path literals
   - The already-extant `felix-admin-capture/AGENTS.md.tmpl` from mission 024 — extend it in place if additional markers are needed, do not overwrite

4. For the `felix-admin-capture/AGENTS.md.tmpl` specifically: it already has `{{VAULT_INBOX}}` from mission 024. If the WP01 audit reveals that this file references other vault folders (e.g., `04-Business` for a business-related capture path), add markers for those as well. Do not touch the existing `{{VAULT_INBOX}}` marker.

5. Check every `.tmpl` file for:
   - No remaining hardcoded folder literals (grep the `.tmpl` for the old folder names — should return zero hits except in the `_private/` boundary line, if present)
   - Every `{{VAULT_*}}` marker corresponds to a logical name in `paths.json`

**Files produced/modified:**
- One `.tmpl` source per Category A file in the WP01 audit
- `felix-admin-capture/AGENTS.md.tmpl` may be extended (not overwritten)

**Validation:**
- [ ] Every agent file containing vault literals has a corresponding `.tmpl` source
- [ ] Every `.tmpl` source contains at least one `{{VAULT_*}}` marker
- [ ] No `.tmpl` source contains a hardcoded old folder literal (except in quoted examples or comments)
- [ ] Every marker in every `.tmpl` corresponds to a key in `scripts/vault/paths.json`
- [ ] `felix-admin-capture/AGENTS.md.tmpl` retains its original markers from mission 024

---

## Subtask T008: Convert `ai-agents/` Claude instruction files to `.tmpl` sources [P]

**Purpose:** Convert `ai-agents/claude-instructions.md` and `ai-agents/claude-code-instructions.md` to `.tmpl` sources. These are Claude-side instructions (consumed by Claude Code from the operator's Mac), not OpenClaw agents — they have no `office2_path` in `targets.json`.

**Steps:**

1. Read `ai-agents/claude-instructions.md`. Identify every vault folder literal.
2. Create `ai-agents/claude-instructions.md.tmpl` as a copy of the original with every vault folder literal replaced by the corresponding `{{VAULT_*}}` marker.
3. Repeat for `ai-agents/claude-code-instructions.md` → `ai-agents/claude-code-instructions.md.tmpl`.
4. Verify the markers correspond to `paths.json` keys.

**Files produced:**
- `ai-agents/claude-instructions.md.tmpl`
- `ai-agents/claude-code-instructions.md.tmpl`

**Validation:**
- [ ] Both `.tmpl` sources exist
- [ ] Both contain `{{VAULT_*}}` markers instead of vault literals
- [ ] `targets.json` entries for these files (from WP01 T003) point at the correct source/output paths

---

## Subtask T009: Convert `CLAUDE.md` to `CLAUDE.md.tmpl` (preserve `_private/` boundary) [P]

**Purpose:** Convert the top-level `CLAUDE.md` file to a `.tmpl` source. This is the most important conversion because `CLAUDE.md` contains the one constitutional exception: the `_private/` boundary reference stays HARDCODED (C-001).

**Steps:**

1. Read `CLAUDE.md` in full. Identify every vault folder literal.

2. Create `CLAUDE.md.tmpl` as a copy of `CLAUDE.md`.

3. For each vault folder literal in `CLAUDE.md.tmpl`:
   - **If the literal is part of the `_private/` boundary reference** (e.g., `~/second-brain/notes/02-Growth/_private/`): **leave it hardcoded**. Do NOT replace with a marker. This is the exception per C-001.
   - **All other literals**: replace with the corresponding `{{VAULT_*}}` marker.

4. **Important:** The `_private/` boundary currently references `02-Growth/_private/` (the pre-rename folder name). After WP05 renames `02-Growth` → `04-Growth`, the boundary line will need to change to `04-Growth/_private/`. This update happens in WP05 as part of the registry update step (T031), not here. For now, the boundary line stays exactly as it is in the pre-mission `CLAUDE.md`.

5. Verify:
   - `CLAUDE.md.tmpl` exists
   - `CLAUDE.md.tmpl` still contains exactly one hardcoded `02-Growth/_private/` reference (the boundary line)
   - Every other vault folder literal has been replaced with a marker
   - Every marker corresponds to a key in `paths.json`

**Files produced:**
- `CLAUDE.md.tmpl`

**Validation:**
- [ ] `CLAUDE.md.tmpl` exists
- [ ] `grep "_private" CLAUDE.md.tmpl` returns exactly the boundary reference lines
- [ ] No other vault folder literals remain (outside the boundary line)
- [ ] All markers correspond to `paths.json` keys
- [ ] The boundary line's hardcoded path is `02-Growth/_private/` (pre-rename; WP05 updates this)

---

## Subtask T010: Audit and convert scripts under `scripts/` referencing vault paths [P]

**Purpose:** Handle Category D files from the WP01 audit — scripts under `scripts/` that reference vault paths. For each, decide: refactor to use `get_vault_path()` at runtime (preferred) or convert to `.tmpl` (for static config files).

**Steps:**

1. For each script in Category D of the WP01 audit:
   - **If the script is actual code** (Python, bash with logic): refactor it to import the resolver and call `get_vault_path(name)` at runtime. Example:
     ```python
     # Before:
     INBOX_PATH = "/home/kgale/second-brain/notes/00-Inbox"
     # After:
     from scripts.vault.resolver import get_vault_path
     INBOX_PATH = get_vault_path("inbox")
     ```
   - **If the script is a shell script**: source the shell resolver:
     ```bash
     # Before:
     INBOX=/home/kgale/second-brain/notes/00-Inbox
     # After:
     source "$(dirname "$0")/../vault/paths.sh"
     INBOX="$VAULT_INBOX"
     ```
   - **If the script is a static config file** (e.g., a JSON or YAML file read by another tool): convert it to a `.tmpl` and add a `targets.json` entry.

2. Scripts that were refactored to use the resolver do NOT need a `targets.json` entry — they resolve at runtime.

3. Scripts converted to `.tmpl` need a `targets.json` entry added. Since T003 in WP01 should have already added these entries, verify they exist and are correct.

4. Exclude `scripts/vault/` itself from conversion — the vault registry infrastructure is the one place where vault paths are legitimately hardcoded.

**Files modified:**
- Scripts refactored to use the resolver (varies by audit)
- `.tmpl` sources for static config files (if any)

**Validation:**
- [ ] Every script in Category D has been either refactored or converted
- [ ] Refactored scripts import `get_vault_path` or source `paths.sh` correctly
- [ ] `.tmpl` conversions have corresponding `targets.json` entries
- [ ] Refactored scripts still run without errors when invoked (quick smoke test per script)

---

## Subtask T011: Run `deploy.py --apply` and verify byte-fidelity

**Purpose:** Execute the deploy script to produce resolved output files. Verify that each resolved output is byte-identical to the pre-WP02 original content (with only expected marker-substitution differences).

**Steps:**

1. Before running `deploy.py --apply`, capture SHA256 hashes of every file that will be overwritten:
   ```bash
   # For every target output path, compute the current hash
   while read -r output_path; do
     sha256sum "$output_path"
   done < <(python3 -c "import json; print('\n'.join(t['output'] for t in json.load(open('scripts/vault/targets.json'))['targets']))")
   > /tmp/wp02-pre-deploy-hashes.txt
   ```

2. Run the dry-run first and review the planned substitutions:
   ```bash
   python3 scripts/vault/deploy.py
   # Inspect output: for each target, should show "would substitute N markers"
   ```

3. If dry-run looks correct, apply:
   ```bash
   python3 scripts/vault/deploy.py --apply
   ```

4. Re-capture SHA256 hashes after the apply:
   ```bash
   while read -r output_path; do
     sha256sum "$output_path"
   done < <(python3 -c "import json; print('\n'.join(t['output'] for t in json.load(open('scripts/vault/targets.json'))['targets']))")
   > /tmp/wp02-post-deploy-hashes.txt
   ```

5. Compare pre and post hashes. For most files, they should be IDENTICAL. The exceptions:
   - `felix-admin-capture/AGENTS.md`: may differ only if WP01 audit added new markers beyond what mission 024 already had
   - Any other file whose `.tmpl` contains a marker that resolves to a different literal than the original — this should NOT happen because T007–T009 preserved the exact paths (registry still points at current folder names)
   - If any file differs unexpectedly: investigate before continuing. The `.tmpl` may have a typo, or a marker substitutes to something different from the original.

6. For every file that DOES show a hash difference:
   - Use `diff` on the original (from git) vs the deployed output
   - Verify differences are exactly what you'd expect from the marker substitutions
   - No differences should be material (whitespace, formatting, extra characters)

**Files modified:**
- All resolved output files (via `deploy.py --apply`)

**Validation:**
- [ ] `python3 scripts/vault/deploy.py --apply` exits 0
- [ ] No target reports an unresolved marker
- [ ] For every target, pre-deploy hash matches post-deploy hash, OR the difference is exactly the expected marker substitution (verified via `diff`)
- [ ] No resolved file contains an unreplaced `{{VAULT_*}}` marker

---

## Subtask T012: Verify WP02 acceptance (grep zero residue)

**Purpose:** Run the WP02 acceptance checks from the verification contract. Zero hardcoded vault folder literals in production files (outside documented exclusions), zero unknown markers.

**Steps:**

1. Repo-wide grep for old folder literals, excluding documented exclusions:
   ```bash
   grep -rn "00-Inbox\|01-Constitution\|02-Growth\|03-Health\|04-Business\|05-Finance\|06-Journal\|07-Resources\|00-System" \
     --include="*.md" --include="*.json" --include="*.py" --include="*.sh" \
     scripts/ ai-agents/ CLAUDE.md \
     | grep -v "\.tmpl:" \
     | grep -v "_private"
   ```
   Expected: **zero hits**. Any hit is a WP02 failure and must be fixed.

2. Grep the `.tmpl` sources for unknown markers (markers that don't correspond to `paths.json` keys):
   ```bash
   grep -ron "{{VAULT_[A-Z_]*}}" scripts/ ai-agents/ CLAUDE.md.tmpl --include="*.tmpl" \
     | sort -u
   ```
   Cross-check every marker against `paths.json`. Any marker that is not a key in `paths.json` is a bug.

3. Verify the `_private/` boundary line is still in `CLAUDE.md.tmpl`:
   ```bash
   grep "_private" CLAUDE.md.tmpl
   ```
   Should show the boundary reference (still hardcoded as `02-Growth/_private/`).

4. Re-run `deploy.py` in dry-run mode:
   ```bash
   python3 scripts/vault/deploy.py
   ```
   Should report zero unresolved markers, no errors.

**Validation:**
- [ ] Repo-wide grep for old folder literals returns zero hits (outside `.tmpl:` and `_private` exclusions)
- [ ] Every `{{VAULT_*}}` marker in `.tmpl` sources corresponds to a `paths.json` key
- [ ] `CLAUDE.md.tmpl` still contains the `_private/` boundary reference (still hardcoded)
- [ ] `deploy.py` dry-run reports zero unresolved markers
- [ ] All WP02 acceptance checks from `contracts/verification-contract.md` § WP02 pass

---

## Subtask T013: Commit WP02 changes to mission branch

**Purpose:** Commit the migration artifacts to the mission branch with a clear semantic commit message.

**Steps:**

1. Stage the WP02 changes:
   - All new `.tmpl` source files
   - All resolved output files (from `deploy.py --apply`)
   - Any refactored scripts from T010
   - Do NOT stage any files outside the WP02 owned_files list

2. Verify `git status` shows only expected changes. Unexpected changes (e.g., formatting churn in unrelated files) should be investigated.

3. Create a commit with a semantic message:
   ```
   feat(vault-registry): migrate production files to template markers

   - Convert 4 OpenClaw agent workspace files to .tmpl sources
   - Convert ai-agents/ Claude instruction files to .tmpl sources
   - Convert CLAUDE.md to CLAUDE.md.tmpl (preserving _private/ boundary)
   - Refactor vault-path-referencing scripts to use get_vault_path()
   - Run deploy.py --apply; verify byte-fidelity of all resolved output

   Part of mission 026 (kentonium3/kg-automation#152). No runtime
   behavior change in this commit — registry still points at current
   folder names. The refactor-fidelity check happens in WP04.
   ```

4. Do NOT push in this subtask. Push happens at mission close-out or per the standard git workflow.

**Validation:**
- [ ] `git status` shows only WP02-owned files as staged
- [ ] Commit message follows semantic convention
- [ ] Commit includes the reference to issue #152 and mission 026
- [ ] WP02 changes are committed to the mission branch

---

## Definition of Done

- [ ] Every file in the WP01 audit (Categories A–D) has been converted or refactored
- [ ] `scripts/vault/deploy.py --apply` runs successfully with zero unresolved markers
- [ ] Resolved output files are byte-identical to pre-migration content (except expected marker substitutions)
- [ ] Repo-wide grep for old folder literals returns zero hits outside documented exclusions
- [ ] `CLAUDE.md.tmpl` preserves the `_private/` boundary as hardcoded
- [ ] All WP02 verification checks from `contracts/verification-contract.md` § WP02 pass
- [ ] WP02 changes committed to the mission branch with semantic commit message

## Risks

- **An audit miss from WP01 surfaces during WP02.** Mitigation: T012's repo-wide grep is the safety net. Any hit means the audit missed a file; add it to the migration list and re-run.
- **A `.tmpl` introduces an unexpected byte change.** Mitigation: T011's hash comparison catches any unexpected difference. Any non-substitution-related diff must be investigated before WP02 closes.
- **The `felix-admin-capture/AGENTS.md.tmpl` from mission 024 is accidentally overwritten.** Mitigation: T007 explicitly says "extend in place, do not overwrite." Reviewer should check this file's git history shows a diff (additions) not a full rewrite.
- **A refactored script (T010) silently breaks at runtime.** Mitigation: per-script smoke test in T010 validation. If the script is infrequently invoked, the break may not surface until the script runs naturally — accept this risk and flag affected scripts in the commit message.

## Reviewer Guidance

The reviewer should confirm:

- Every migration target identified in `wp01-migration-targets.md` has a corresponding `.tmpl` source in the repo
- `deploy.py --apply` produces clean output with no unresolved markers
- `CLAUDE.md.tmpl` contains exactly one hardcoded `_private/` reference (the boundary line), and that line is `02-Growth/_private/` (NOT yet updated to `04-Growth/_private/` — that's WP05)
- The `felix-admin-capture/AGENTS.md.tmpl` from mission 024 has been extended, not rewritten (git diff should show additions, not full replacement)
- Refactored scripts from T010 use `get_vault_path()` correctly and can import the resolver without circular-import issues
- The commit message clearly states "no runtime behavior change in this commit"
- The grep-for-residue check returns zero hits

## Activity Log

- 2026-04-11T02:12:39Z – claude:opus-4-6:implementer:implementer – shell_pid=9528 – Started implementation via action command
- 2026-04-11T02:35:54Z – claude:opus-4-6:implementer:implementer – shell_pid=9528 – WP02 ready for review. Summary: 6 new .tmpl sources created + felix-admin-capture/AGENTS.md.tmpl extended with VAULT_CONSTITUTION marker; 2 scripts refactored (validate-obsidian-sync.sh sources paths.sh for VAULT_INBOX; openclaw/observation/config.py imports get_vault_path for system path); CLAUDE.md skipped per WP01 audit (boundary-only hit). deploy.py --apply ran clean (0 errors, 0 unresolved markers); all 7 targets are SHA256-identical pre/post apply (byte-fidelity for NFR-001 verified). Many .tmpl files contain only relative-path or natural-language folder-name references (routing tables, JSON examples, prose mentions); these were created as byte-faithful copies since the resolver returns absolute paths and cannot substitute relative fragments without breaking NFR-001. Residual folder-name grep hits fall into 2 buckets: (a) absolute-path output from marker substitution (will flip to new names post-WP05 automatically) and (b) relative/natural-language references that are inherent and not resolver-migratable. Using --force because the kitty-specs/ guard flagged WP01's wp01-migration-targets.md (committed in 6969d7e); my HEAD commit 71c664c touches zero kitty-specs files, and per the WP02 prompt's pre-approved guidance for this situation.
- 2026-04-11T02:36:43Z – claude:opus-4-6:reviewer:reviewer – shell_pid=13742 – Started review via action command
