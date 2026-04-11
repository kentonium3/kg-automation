---
work_package_id: WP03
title: Deploy Wrapper deploy-149.sh
dependencies:
- WP01
- WP02
requirement_refs:
- FR-014
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
- T015
- T016
- T017
agent: "claude:opus-4-6:shell-implementer:implementer"
shell_pid: "56005"
history:
- date: '2026-04-11'
  event: created
authoritative_surface: scripts/deploy/
execution_mode: code_change
mission_slug: 027-inbox-pre-scan-helper
owned_files:
- scripts/deploy/deploy-149.sh
tags: []
---

# WP03: Deploy Wrapper `deploy-149.sh`

## Objective

Build the one-shot deploy wrapper that pushes the helper (WP01), the updated agent workspace (WP02), and the openclaw cron payload edits to office2 in a single safe sequence. The wrapper supports `--dry-run` (read-only preview) and `--apply` (execute). It halts on any step failure and prints manual rollback instructions rather than auto-reverting.

This WP is the bridge from the repo to live production. WP05 exercises it against real office2.

## Context

Read these first:
- `kitty-specs/027-inbox-pre-scan-helper/spec.md` — FR-014
- `kitty-specs/027-inbox-pre-scan-helper/plan.md` — "Deploy Wrapper Contract" section (8-step ordered flow)
- `kitty-specs/027-inbox-pre-scan-helper/quickstart.md` — Reference paths table and common failure modes
- `scripts/deploy/` — look for any surviving deploy wrapper patterns from prior missions (note: mission 026's `deploy-f026.sh` was deleted in that mission's merge, but the pattern can be reconstructed from `kitty-specs/026-vault-path-registry-and-folder-renumber/research/` artifacts if needed)
- `docs/runbooks/governance/pre-flight-checklist.md` — Tier 2 + Tier 3 pre-flight requirements (this mission is Tier 2 + Tier 3)
- `docs/runbooks/governance/post-change-verification.md` — post-flight requirements
- `docs/design/architecture/data/change-risk-taxonomy.json` — tier definitions

**Critical bug to avoid**: closed issue #162 documented a silent-failure bug in mission 026's wrapper where "pause cron" fell back to editing the system crontab, which is unrelated to openclaw's cron scheduler. **This wrapper MUST NOT use the system crontab for anything.** All cron interactions must go through `openclaw cron list`, `openclaw cron edit`, and `openclaw cron run`.

**Key design insight from planning**: because this WP's architecture (option B, agent runs helper as Step 1) does not disable or recreate any cron jobs — it only edits their payload messages — the wrapper does NOT need pause/resume logic at all. The worst-case mid-deploy cron fire runs the legacy Step 1 (scan the inbox) harmlessly. This is a major simplification compared to mission 026's wrapper.

## Branch Strategy

- **Planning base**: main
- **Final merge target**: main
- **Execution worktree**: assigned by `spec-kitty agent action implement WP03 --agent <name>`.
- **Dependencies**: WP01 (for the helper file to rsync) + WP02 (for the agent workspace files to rsync) must be approved before WP03 implementation begins. Use `spec-kitty next --agent <name> --mission 027-inbox-pre-scan-helper` to confirm.

## Subtasks

### T011 — Create `deploy-149.sh` skeleton

**Purpose**: Establish the shell script with safe defaults, flag parsing, and structured output.

**Steps**:
1. Create `scripts/deploy/deploy-149.sh` with:
   - Shebang: `#!/usr/bin/env bash`
   - `set -euo pipefail` (fail on any error, unset var, or pipe error)
   - Argparse for `--dry-run` and `--apply` (mutually exclusive; default is to print usage and exit)
   - A `STEP` function that prints `[deploy-149] Step N/M: <description>` to stderr before each phase
   - A `HALT` function that prints an error message and exits 1
   - Structured output so the operator can follow along: each step prints its own header + result
2. Define constants at the top of the script:
   - `SSH_HOST="office2-claude"`
   - `REMOTE_HELPER_PATH="/home/claude/kg-automation/scripts/inbox/prescan.py"`
   - `REMOTE_AGENT_WORKSPACE="/home/claude/.openclaw/agents/felix-admin-capture/"`
   - `INBOX_CRON_NAMES=("inbox-7am" "inbox-noon" "inbox-5pm" "inbox-10pm")` — names, not UUIDs. UUIDs are resolved at runtime via `openclaw cron list --json`.
3. Print a summary of what the wrapper will do (`--dry-run` and `--apply` show the same summary at the top)
4. In `--dry-run` mode, each step prints what it WOULD do but performs no remote mutations. Read-only probes (ssh true, restic query, cron list) are allowed in dry-run.

**Files**:
- `scripts/deploy/deploy-149.sh` (new, ~80 lines at this stage)

**Validation**:
- [ ] `./scripts/deploy/deploy-149.sh` without flags prints usage and exits 1
- [ ] `./scripts/deploy/deploy-149.sh --dry-run` runs cleanly and prints each step's intent
- [ ] `./scripts/deploy/deploy-149.sh --apply` runs cleanly against current state (assuming WP01 + WP02 are in place in the repo)

### T012 — Implement pre-flight checks

**Purpose**: Halt early on any precondition failure so nothing touches office2 until everything is verified.

**Steps**:
1. Pre-flight checks to run (in order):
   - **Restic backup age ≤24h**: query `restic snapshots --latest 1 --json` (via `ssh office2-claude`, since Restic runs on office2) and compare the latest snapshot's timestamp to `date -u +%s - 86400`. If the latest backup is older than 24h, halt with a message like "Tier 2 pre-flight failed: no Restic snapshot in the last 24 hours. Run `restic backup` first."
   - **office2 reachable**: `ssh office2-claude true` must return exit 0. If not, halt with "Cannot reach office2 via `ssh office2-claude`. Check Tailscale and SSH key."
   - **Helper source exists in repo**: `test -f scripts/inbox/prescan.py`. Halt on missing.
   - **Agent workspace source files exist in repo**: `test -f` for each expected file (confirmed by WP02's outputs). Halt on missing.
   - **Registry resolvable**: `python3 -c "import json; json.load(open('scripts/vault/paths.json'))"`. Halt on malformed.
2. Each check prints `[OK]` or `[FAIL]` and the first failure halts.
3. In `--dry-run` mode, all pre-flight checks run (they are read-only).

**Files**:
- `scripts/deploy/deploy-149.sh` (extend, ~60 more lines)

**Validation**:
- [ ] With Restic older than 24h (simulate by checking against a synthetic date), wrapper halts with the right message
- [ ] With office2 unreachable (simulate by unsetting SSH config), wrapper halts with the right message
- [ ] With missing helper file, wrapper halts with the right message
- [ ] Happy path (all pre-flight passes), wrapper proceeds to the next step

### T013 — Step 2 copy helper + Step 3 verify helper

**Purpose**: Push `scripts/inbox/` to office2 and confirm the helper can self-check.

**Steps**:
1. **Step 2 (copy helper)**: use `rsync -avz --delete scripts/inbox/ office2-claude:/home/claude/kg-automation/scripts/inbox/`. Dry-run mode: use `--dry-run` flag on rsync and print the result.
2. **Step 3 (verify helper)**: `ssh office2-claude 'python3 /home/claude/kg-automation/scripts/inbox/prescan.py --self-check'`. Expect exit 0 and JSON output containing `"self_check": "ok"`. Parse the JSON with a one-liner Python and confirm. Halt on any failure.
3. If Step 3 fails, the rollback instruction is: `ssh office2-claude 'git -C /home/claude/kg-automation checkout HEAD -- scripts/inbox/'` (or a reference to the prior state).
4. In `--dry-run`, Step 2 uses rsync `--dry-run`; Step 3 runs `--self-check` anyway because it's read-only. If the remote helper is already present and self-check passes, that's informational only.

**Files**:
- `scripts/deploy/deploy-149.sh` (extend, ~50 more lines)

**Validation**:
- [ ] `--dry-run` shows rsync diff without applying
- [ ] `--apply` copies files and runs self-check
- [ ] Self-check failure halts the wrapper with a clear message

### T014 — Step 4 copy agent workspace + Step 5 verify

**Purpose**: Push the updated `ai-agents/felix-admin-capture/` files (or their rendered output) to `/home/claude/.openclaw/agents/felix-admin-capture/` on office2 and confirm they deployed cleanly.

**Steps**:
1. **Step 4 (copy workspace)**: Determine what to rsync:
   - If WP02 edited the `.tmpl` files under `scripts/openclaw/agents/felix-admin-capture/`, then this step must render those `.tmpl` files using the vault path registry's substitution logic (same pattern mission 026 established) and rsync the rendered output to office2.
   - If the render tool is a Python script, invoke it here: `python3 scripts/vault/render.py scripts/openclaw/agents/felix-admin-capture/ --output /tmp/render-felix-admin-capture/` and then `rsync -avz /tmp/render-felix-admin-capture/ office2-claude:/home/claude/.openclaw/agents/felix-admin-capture/`
   - If no render tool exists yet, the WP03 implementation must call out the gap and either (a) build a minimal render step inline in the wrapper, or (b) file a follow-on issue and handcraft the render for this mission. Prefer option (a).
2. **Step 5 (verify workspace)**: `ssh office2-claude 'md5sum /home/claude/.openclaw/agents/felix-admin-capture/*.md'` and compare to local `md5sum` of the rendered files. Halt on mismatch.
3. In `--dry-run`, use rsync `--dry-run` and skip the md5 diff (there's nothing to diff yet).

**Files**:
- `scripts/deploy/deploy-149.sh` (extend, ~60 more lines)

**Validation**:
- [ ] `--dry-run` shows file-by-file diff without applying
- [ ] `--apply` copies files and verifies via md5sum match
- [ ] Mismatch halts the wrapper

### T015 — Step 6 edit cron payloads + Step 7 verify

**Purpose**: Update the 4 inbox cron payload messages to point at the new Step 1 contract, and verify the update landed.

**Steps**:
1. **Step 6 (edit crons)**:
   - Resolve the 4 UUIDs by name: `ssh office2-claude 'openclaw cron list --json'` returns a JSON object with a `jobs` array; parse it and extract the UUID for each name in `INBOX_CRON_NAMES`. Halt if any name is missing.
   - Define the new payload message:
     ```
     "Process the inbox now. Begin with your Step 1 pre-scan per your standing orders. If the helper reports no unprocessed files, reply with IDLE only. If the helper returns unprocessed paths, process each file per your routing rules. If the helper exits non-zero, report its error and stop."
     ```
   - For each UUID, run `ssh office2-claude "openclaw cron edit <uuid> --message '<new message>'"`. Halt on any failure.
2. **Step 7 (verify crons)**: `ssh office2-claude 'openclaw cron list --json'` again, parse the JSON, and for each inbox-* cron confirm the payload message matches the new string. Halt on any mismatch.
3. In `--dry-run`, perform the UUID lookup (read-only), print the current payload for each inbox cron, print the intended new payload, do NOT call `openclaw cron edit`.
4. Note: `openclaw cron edit` may require the message as JSON. Test the exact syntax in advance. The wrapper should call `openclaw cron edit --help` once during implementation to confirm.

**Files**:
- `scripts/deploy/deploy-149.sh` (extend, ~80 more lines)

**Validation**:
- [ ] `--dry-run` shows current and intended payloads for all 4 crons without applying
- [ ] `--apply` edits all 4 cron payloads and verifies they match
- [ ] If any UUID is missing (e.g., a cron was renamed), wrapper halts with the name that wasn't found
- [ ] If `openclaw cron edit` fails for any cron, wrapper halts and prints which one

### T016 — Step 8 post-flight smoke test

**Purpose**: Trigger one cron manually and confirm the new deploy works end-to-end.

**Steps**:
1. **Step 8 (smoke test)**: `ssh office2-claude 'openclaw cron run <inbox-noon-uuid>'` (or any of the 4; noon is a reasonable default because it's unlikely to collide with a natural fire). This is a debug trigger that runs the cron immediately.
2. Wait for completion. `openclaw cron run` may return synchronously with the result, or may be async — the wrapper needs to poll `openclaw cron runs <uuid>` for up to 60 seconds waiting for the latest run to show `status: ok` or `status: error`.
3. After the run completes, fetch the latest helper log: `ssh office2-claude 'ls -t /home/claude/second-brain/agents/logs/inbox-prescan-*.md | head -1 | xargs cat'`. Confirm a new run entry was written.
4. Fetch the openclaw run history: `ssh office2-claude 'openclaw cron runs <uuid> 2>&1 | head -20'` and confirm the latest run's outcome.
5. If the run succeeded AND the helper log was updated, Step 8 passes. Otherwise halt with the failing detail.
6. In `--dry-run`, skip Step 8 entirely (it's a mutation — it actually triggers an agent run).

**Files**:
- `scripts/deploy/deploy-149.sh` (extend, ~70 more lines)

**Validation**:
- [ ] `--dry-run` skips Step 8 cleanly
- [ ] `--apply` triggers the smoke test, waits for completion, confirms via log file and run history
- [ ] Failing smoke test halts the wrapper with actionable detail

### T017 — Rollback-instruction printer on failure

**Purpose**: On any failure, print a clear manual rollback recipe so the operator can restore prior state.

**Steps**:
1. Add a `trap` on ERR that, on any failure (via `set -e`), invokes a `ROLLBACK_INSTRUCTIONS` function that prints:
   - The step that failed (captured in a global `LAST_STEP` variable updated by the `STEP` function)
   - The manual recovery commands for each step that had already completed before the failure:
     - Step 2 (helper rsync): "To revert, run `ssh office2-claude 'rm /home/claude/kg-automation/scripts/inbox/prescan.py'` or restore the previous version via `git` on office2."
     - Step 4 (workspace rsync): "To revert, restore the prior files from `ssh office2-claude 'git -C /home/claude/kg-automation checkout HEAD -- scripts/openclaw/agents/felix-admin-capture/'` and re-run the render step manually."
     - Step 6 (cron edit): "To revert, run `ssh office2-claude 'openclaw cron edit <uuid> --message \"Process the inbox now.\"'` for each of the 4 inbox cron UUIDs."
   - A final line: "Rollback is NOT automatic. Review the commands above and apply them manually if needed."
2. **Do NOT auto-execute rollback.** The operator's judgment is the rollback mechanism — the wrapper only surfaces the right recipe.

**Files**:
- `scripts/deploy/deploy-149.sh` (extend, ~50 more lines; final total ~450 lines)

**Validation**:
- [ ] Inject a failure at each step and verify the rollback instructions printed are correct for the state reached
- [ ] `--dry-run` never triggers rollback instructions (because it never mutates anything)

## Definition of Done

- [ ] `scripts/deploy/deploy-149.sh` exists and is executable
- [ ] `--dry-run` runs cleanly against current state, prints each step's intent
- [ ] `--apply` runs cleanly against current state (during WP03 it is exercised by the implementer against their current local/office2 state, not against prod state — that's WP05's job)
- [ ] All 8 ordered steps are present and halt-on-error
- [ ] Zero system-crontab usage anywhere in the script (grep proves it)
- [ ] UUIDs are resolved at runtime, not hardcoded
- [ ] Rollback instructions print on any failure
- [ ] Conventional commit: `feat(WP03): deploy-149.sh one-shot deploy wrapper`

## Risks

- **openclaw cron edit syntax**: the exact flag syntax (`--message`, `--payload`, etc.) must be verified against `openclaw cron edit --help` before writing the command. Mission 026 had an openclaw-specific bug here (see closed #162).
- **Rendering `.tmpl` files**: if no render tool exists in `scripts/vault/`, the wrapper must either build one inline or the WP02 deliverable must be plain `.md` files with no substitution needed. T014 calls this out explicitly.
- **Smoke test timing**: `openclaw cron run` may not be perfectly synchronous. The polling loop in T016 must have a sensible timeout (60s is generous) and fail loud if the run never completes.
- **Restic query syntax**: if `restic snapshots --latest 1 --json` is not the exact command, check `docs/runbooks/` for the canonical Restic invocation on office2.
- **SSH agent locked**: `ssh office2-claude` may prompt for a passphrase interactively. The wrapper should detect this (timeout on ssh commands, or use `ssh -o BatchMode=yes`) and halt early with a clear message.

## Reviewer Guidance

- **Critical**: grep for `crontab` anywhere in the script. If found, reject the WP. The only valid cron interaction is via `openclaw cron *`.
- Verify all UUIDs come from `openclaw cron list --json`, not hardcoded strings
- Verify the 8 ordered steps match plan.md's "Deploy Wrapper Contract" section exactly
- Verify `--dry-run` mode is read-only: no `rsync` without `--dry-run`, no `openclaw cron edit`, no `openclaw cron run`
- Verify rollback instructions are printed on failure (trap on ERR exists)
- Verify the smoke test waits for completion before declaring success
- Verify pre-flight checks include Restic age, office2 reachability, and repo file presence
- Verify `set -euo pipefail` is present at the top
- The wrapper should not itself require WP01 and WP02 to be "correct" — it should do its job regardless of whether the files it rsyncs are semantically right. WP05 validates the end-to-end semantics. WP03's job is to move files and edit crons safely.

## Implementation command

```bash
spec-kitty agent action implement WP03 --mission 027-inbox-pre-scan-helper --agent <tool>:<model>:<profile>:<role>
```

## Activity Log

- 2026-04-11T19:04:43Z – claude:opus-4-6:shell-implementer:implementer – shell_pid=56005 – Started implementation via action command
