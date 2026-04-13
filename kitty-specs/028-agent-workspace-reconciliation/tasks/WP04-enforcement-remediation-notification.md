---
work_package_id: WP04
title: Enforcement script — remediation and notification
dependencies:
- WP03
requirement_refs:
- FR-008
- FR-009
- FR-010
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T013
- T014
- T015
- T016
- T017
- T018
agent: "codex:gpt-4o:reviewer:reviewer"
shell_pid: "93091"
history:
- date: '2026-04-13'
  action: created
  agent: claude-opus-4-6
authoritative_surface: scripts/openclaw/enforcement/
execution_mode: code_change
owned_files:
- scripts/openclaw/enforcement/remediation.py
- scripts/openclaw/enforcement/notification.py
- tests/openclaw/enforcement/test_remediation.py
- tests/openclaw/enforcement/test_notification.py
tags: []
---

# WP04: Enforcement Script — Remediation and Notification

## Objective

Implement the action layer of the enforcement script: auto-deploy (repo→office2), auto-capture (office2→repo), conflict notification via WhatsApp, and GitHub issue creation for conflicts and factory-default transitions.

## Context

WP03 built the detection engine. This WP adds what happens when drift is detected:

| DriftState | Action | Module |
|---|---|---|
| `REPO_CHANGED` | Auto-deploy: SCP repo file → office2, update manifest | `remediation.py` |
| `OFFICE2_CHANGED` | Auto-capture: SCP office2 file → repo, git commit, update manifest | `remediation.py` |
| `CONFLICT` | File GitHub issue + send WhatsApp alert | `notification.py` |
| Factory-default transition | File GitHub issue + send WhatsApp alert | `notification.py` |

The enforcement script (`drift_check.py`) calls detection → remediation → notification in sequence.

## Branch Strategy

- Planning base branch: `main`
- Merge target branch: `main`
- Execution worktree: allocated by spec-kitty lane assignment per `lanes.json`

## Detailed Guidance

### T013: Implement auto-deploy action (repo→office2 via SCP)

**Purpose**: When the repo has a newer version of a tracked file (repo changed, office2 unchanged), deploy it to office2.

**Steps**:
1. Create `scripts/openclaw/enforcement/remediation.py`:
   ```python
   import subprocess
   import logging

   logger = logging.getLogger(__name__)

   def deploy_to_office2(
       repo_file: str,
       office2_path: str,
       ssh_host: str = "office2-claude",
       dry_run: bool = False,
   ) -> bool:
       """SCP a repo file to office2. Returns True on success."""
       if dry_run:
           logger.info(f"DRY RUN: would deploy {repo_file} → {ssh_host}:{office2_path}")
           return True
       # 1. SCP the file
       result = subprocess.run(
           ["scp", repo_file, f"{ssh_host}:{office2_path}"],
           capture_output=True, text=True, timeout=30,
       )
       if result.returncode != 0:
           logger.error(f"SCP failed: {result.stderr}")
           return False
       # 2. Verify hash matches
       # ...compute remote hash and compare to local...
       return True
   ```

2. After successful deploy, the function should return enough info to update the baseline manifest (new office2 hash = repo hash).

**Files**: `scripts/openclaw/enforcement/remediation.py` (new, ~60 lines initially)

### T014: Implement auto-capture action (office2→repo + git commit)

**Purpose**: When office2 has a newer version (office2 changed, repo unchanged), capture it to the repo and commit.

**Steps**:
1. Add to `remediation.py`:
   ```python
   def capture_from_office2(
       office2_path: str,
       repo_file: str,
       ssh_host: str = "office2-claude",
       dry_run: bool = False,
       repo_root: str = ".",
   ) -> bool:
       """SCP an office2 file to the repo and git commit."""
       if dry_run:
           logger.info(f"DRY RUN: would capture {ssh_host}:{office2_path} → {repo_file}")
           return True
       # 1. SCP from office2
       result = subprocess.run(
           ["scp", f"{ssh_host}:{office2_path}", repo_file],
           capture_output=True, text=True, timeout=30,
       )
       if result.returncode != 0:
           logger.error(f"SCP failed: {result.stderr}")
           return False
       # 2. Git add + commit
       agent_name = ...  # extract from path
       filename = ...    # extract from path
       commit_msg = f"chore: drift-reconcile {agent_name}/{filename} (office2→repo)"
       subprocess.run(["git", "-C", repo_root, "add", repo_file], check=True)
       subprocess.run(
           ["git", "-C", repo_root, "commit", "-m", commit_msg],
           check=True,
       )
       return True
   ```

2. The commit message uses the `chore: drift-reconcile` prefix for auditability (plan.md D1).

3. After successful capture, return enough info to update the baseline manifest (new repo hash = office2 hash).

**Files**: `scripts/openclaw/enforcement/remediation.py` (updated, ~120 lines total)

**Edge cases**:
- Git working tree is dirty (uncommitted changes) → log warning but proceed (the drift-reconcile commit is independent)
- Multiple files captured in one run → each gets its own commit for auditability

### T015: Implement conflict detection and notification routing

**Purpose**: When both sides changed since the last baseline (CONFLICT state), route to notification.

**Steps**:
1. Add to `remediation.py` or create a new routing function in `drift_check.py`:
   ```python
   def process_drift_results(
       results: list[DriftResult],
       config: dict,
       dry_run: bool = False,
   ) -> dict:
       """Process all drift results: remediate or notify as appropriate."""
       actions_taken = {"deployed": [], "captured": [], "conflicts": [], "factory_transitions": []}
       for result in results:
           if result.state == DriftState.REPO_CHANGED:
               deploy_to_office2(...)
               actions_taken["deployed"].append(result)
           elif result.state == DriftState.OFFICE2_CHANGED:
               capture_from_office2(...)
               actions_taken["captured"].append(result)
               if result.is_factory_default == False:  # was factory, now customized
                   actions_taken["factory_transitions"].append(result)
           elif result.state == DriftState.CONFLICT:
               actions_taken["conflicts"].append(result)
       # Notify for conflicts and factory transitions
       if actions_taken["conflicts"] or actions_taken["factory_transitions"]:
           notify(actions_taken, config, dry_run)
       return actions_taken
   ```

2. The routing logic must also detect the factory-default→customized transition:
   - Check the baseline: was this file previously `factory_default: true`?
   - Check current: is `is_factory_default` now `false`?
   - If yes → add to `factory_transitions` list

**Files**: `scripts/openclaw/enforcement/remediation.py` (updated)

### T016: Implement WhatsApp notification via openclaw agent --deliver

**Purpose**: Send drift alerts to Kent via WhatsApp using the established OpenClaw CLI pattern.

**Steps**:
1. Create `scripts/openclaw/enforcement/notification.py`:
   ```python
   import subprocess
   import logging

   logger = logging.getLogger(__name__)

   def send_whatsapp(
       message: str,
       config: dict,
       dry_run: bool = False,
   ) -> bool:
       """Send a WhatsApp message via openclaw agent --deliver."""
       if dry_run:
           logger.info(f"DRY RUN: would send WhatsApp: {message[:100]}...")
           return True
       recipient = config["notification"]["recipient"]
       agent = config["notification"].get("openclaw_agent", "main")
       result = subprocess.run(
           [
               "openclaw", "agent",
               "--agent", agent,
               "--message", message,
               "--deliver",
               "--channel", "whatsapp",
               "--to", recipient,
           ],
           capture_output=True, text=True, timeout=60,
       )
       return result.returncode == 0
   ```

2. Compose alert messages with clear structure:
   ```
   🔔 Agent Workspace Drift Alert

   Conflicts (both sides changed):
   • felix-admin-capture/AGENTS.md

   Factory transitions (newly customized):
   • main/IDENTITY.md (was factory default)

   Action required: review and resolve manually.
   Issue filed: #<number>
   ```

3. Only send one consolidated message per enforcement run, not one per file.

**Files**: `scripts/openclaw/enforcement/notification.py` (new, ~80 lines)

### T017: Implement GitHub issue creation for conflicts/factory transitions

**Purpose**: File a GitHub issue when drift requires human attention (conflicts or factory-default transitions).

**Steps**:
1. Add to `notification.py`:
   ```python
   def create_drift_issue(
       actions: dict,
       config: dict,
       dry_run: bool = False,
   ) -> str | None:
       """Create a GitHub issue for unresolved drift. Returns issue URL or None."""
       if dry_run:
           logger.info("DRY RUN: would create drift-alert issue")
           return None
       repo = config["notification"]["issue_repo"]
       labels = ",".join(config["notification"]["issue_labels"])

       title = f"Drift alert: {len(actions['conflicts'])} conflicts, {len(actions['factory_transitions'])} factory transitions"
       body = compose_issue_body(actions)

       result = subprocess.run(
           ["gh", "issue", "create",
            "--repo", repo,
            "--title", title,
            "--body", body,
            "--label", labels],
           capture_output=True, text=True, timeout=30,
       )
       if result.returncode == 0:
           return result.stdout.strip()  # issue URL
       logger.error(f"Issue creation failed: {result.stderr}")
       return None
   ```

2. The issue body should include:
   - Which files have conflicts (both sides changed)
   - Which files transitioned from factory default to customized
   - Current hashes on both sides for each affected file
   - Suggested resolution steps

3. Labels from config: `["drift-alert", "area/felix-core"]`

**Files**: `scripts/openclaw/enforcement/notification.py` (updated, ~150 lines total)

### T018: Write pytest tests for remediation and notification

**Purpose**: Test remediation actions and notification dispatch with mocked subprocess calls.

**Steps**:
1. Create `tests/openclaw/enforcement/test_remediation.py`:
   - Test `deploy_to_office2` with mocked SCP (success and failure)
   - Test `capture_from_office2` with mocked SCP + git (success and failure)
   - Test `process_drift_results` routing for each drift state
   - Test factory-default transition detection in routing

2. Create `tests/openclaw/enforcement/test_notification.py`:
   - Test `send_whatsapp` with mocked openclaw CLI
   - Test `create_drift_issue` with mocked gh CLI
   - Test message composition (verify all fields present)
   - Test dry-run mode produces no subprocess calls

3. Use `unittest.mock.patch` for subprocess calls — no actual SSH/SCP/CLI calls in tests.

**Files**:
- `tests/openclaw/enforcement/test_remediation.py` (new)
- `tests/openclaw/enforcement/test_notification.py` (new)

**Validation**:
- [ ] All remediation paths (deploy, capture, routing) tested
- [ ] Notification dispatch tested for WhatsApp and GitHub issue
- [ ] Dry-run mode tested (no side effects)
- [ ] Error handling tested (SCP failure, git failure, CLI failure)
- [ ] `pytest tests/openclaw/enforcement/ -v` passes (all tests including WP03's)

## Definition of Done

- [ ] `remediation.py` handles deploy and capture with hash verification
- [ ] `notification.py` sends WhatsApp alerts and creates GitHub issues
- [ ] `drift_check.py check` processes all drift results end-to-end (detect → remediate → notify)
- [ ] `drift_check.py check --dry-run` shows all actions without executing
- [ ] `drift_check.py check --json` outputs machine-readable results
- [ ] All pytest tests pass
- [ ] No actual SSH/SCP/CLI calls in unit tests

## Risks

- **WhatsApp delivery**: `openclaw agent --deliver` may fail if the gateway is down. Mitigation: log the failure, don't crash the enforcement run.
- **Git commit in automation**: Auto-capture creates commits. If the repo has uncommitted changes, git may refuse. Mitigation: check for clean working tree before committing; warn but don't block.
- **Rate limiting**: If many files drift simultaneously, creating multiple issues/messages could hit rate limits. Mitigation: consolidate all drift into one issue + one message per run.

## Reviewer Guidance

- Verify that remediation updates the baseline manifest after each action (so the next run doesn't re-detect the same drift)
- Check that conflict notification includes enough detail for Kent to resolve manually
- Confirm factory-default transition creates an issue (not just a WhatsApp message) so it's tracked
- Ensure all subprocess calls have timeouts

## Activity Log

- 2026-04-13T18:42:04Z – claude:opus-4-6:implementer:implementer – shell_pid=92509 – Started implementation via action command
- 2026-04-13T18:44:08Z – claude:opus-4-6:implementer:implementer – shell_pid=92509 – Ready for review: remediation + notification, 56 total tests passing
- 2026-04-13T18:44:45Z – codex:gpt-4o:reviewer:reviewer – shell_pid=93091 – Started review via action command
