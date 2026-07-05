---
work_package_id: WP03
title: Prescan log-dir repoint + dedup import correctness
dependencies: []
requirement_refs:
- FR-006
- FR-011
tracker_refs: []
planning_base_branch: fix/felix-admin-cron-path-fix
merge_target_branch: fix/felix-admin-cron-path-fix
branch_strategy: Planning artifacts for this mission were generated on fix/felix-admin-cron-path-fix. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-admin-cron-path-fix unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
- T010
agent: "codex:gpt-5-codex:reviewer-renata:reviewer"
shell_pid: "59528"
history:
- at: 2026-07-05T02:30:00Z
  actor: system
  action: Prompt generated via /spec-kitty.tasks for
agent_profile: python-pedro
authoritative_surface: scripts/inbox/
create_intent:
- tests/inbox/test_prescan_paths_and_dedup.py
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/inbox/prescan.py
- scripts/inbox/append_routing_entry.py
- tests/inbox/test_prescan_paths_and_dedup.py
role: implementer
tags: []
---

# Work Package Prompt: WP03 – Prescan log-dir + dedup imports

## ⚡ Do This First: Load Agent Profile

Load `/ad-hoc-profile-load python-pedro` (role: implementer) before anything else.

## Branch Strategy

- Planning/base + merge target: `fix/felix-admin-cron-path-fix`.

## Objectives & Success Criteria

Two fixes to the same file family:
1. **FR-006** — forensic logs must land in the Obsidian-synced vault
   `/home/kgale/second-brain/agents/logs/`, not the stray `/home/claude/...`.
2. **FR-011 (Codex #1 C2, critical)** — `prescan.py` imports the routing-log
   reader with a **bare** `from routing_log import RoutingLogReader` that fails
   from any non-repo cwd even *with* the `PYTHONPATH` guardrail, silently dropping
   to "dedup-disabled mode". Convert to a package-absolute import so dedup actually
   works. Done when a full prescan from `/tmp` shows dedup **active** (SC-8).

## Context & Constraints

- Plan IC-02/IC-03; `research.md` R3/R7-C2; `contracts` C2b/C3.
- The correct log path is used as reference by `scripts/inbox/file_inbox_quality_issue.py:37`
  (`/home/kgale/second-brain/agents/logs/...`) — mirror it (absolute, never `~`).
- `append_routing_entry.py` currently inserts its script dir into `sys.path` then
  does `from routing_log import RoutingLogWriter`; align it to the package import
  so both writer and reader use one convention.

## Subtasks & Detailed Guidance

### Subtask T007 – prescan.py log dir (FR-006)
- **File**: `scripts/inbox/prescan.py`
- **Steps**: change `DEFAULT_LOG_DIR` (line ~56, currently
  `Path("/home/claude/second-brain/agents/logs")`) to
  `Path("/home/kgale/second-brain/agents/logs")`. Fix the docstring at line ~27
  that documents the old default.

### Subtask T008 – prescan.py package import (FR-011)
- **File**: `scripts/inbox/prescan.py`
- **Steps**: change the import (line ~771)
  `from routing_log import RoutingLogReader` → `from scripts.inbox.routing_log import RoutingLogReader`.
  Keep the ImportError fallback but it should no longer trigger in normal operation.
- **Notes**: this is the load-bearing dedup fix. Verify the "dedup-disabled mode"
  branch (line ~777) is not reached under the guardrail.

### Subtask T009 – append_routing_entry.py import alignment (FR-011)
- **File**: `scripts/inbox/append_routing_entry.py`
- **Steps**: replace the `sys.path.insert(0, SCRIPT_DIR)` hack (lines ~15-16) +
  `from routing_log import RoutingLogWriter` (line ~18) with
  `from scripts.inbox.routing_log import RoutingLogWriter`. Remove the now-unneeded
  `sys.path` manipulation.

### Subtask T010 – tests (SC-8, H1)
- **File**: `tests/inbox/test_prescan_paths_and_dedup.py`
- **Steps**:
  - Assert `prescan.DEFAULT_LOG_DIR == Path("/home/kgale/second-brain/agents/logs")`
    and is unchanged under monkeypatched HOME.
  - **Dedup active**: run a full prescan (or the import path it uses) from a cwd
    of `/tmp` with the repo root on `PYTHONPATH`; assert **no** "dedup-disabled"
    warning is emitted and the routing-log reader import resolves.
  - **Frontmatter-only dedup (H1)**: a note with missing/unknown `status`
    frontmatter is treated as unprocessed, so the ledger is the sole guard — assert
    that with the ledger present the note is deduped, and with an empty ledger it is
    re-evaluated (documents the cutover risk WP05 mitigates atomically).

## Test Strategy

- `python3 -m pytest tests/inbox/test_prescan_paths_and_dedup.py -q`.
- The dedup-from-/tmp test is the acceptance proof for FR-011/SC-8.

## Risks & Mitigations

- Circular import when switching to `scripts.inbox.routing_log` — unlikely (routing_log
  imports only stdlib); verify import at module load.

## Integration Verification (before for_review)

- [ ] `DEFAULT_LOG_DIR` → vault; no `/home/claude/second-brain` remains in the file.
- [ ] Package-absolute imports in both files; `sys.path` hack removed.
- [ ] Dedup-active-from-/tmp test passes (no dedup-disabled warning).

## Review Guidance

- The critical check: prove dedup is not silently disabled from a non-repo cwd.

## Activity Log

- 2026-07-05T02:30:00Z – system – Prompt created.
- 2026-07-05T03:23:05Z – claude:sonnet:python-pedro:implementer – shell_pid=47053 – Assigned agent via action command
- 2026-07-05T03:40:45Z – claude:sonnet:python-pedro:implementer – shell_pid=47053 – Ready for review: (T007) DEFAULT_LOG_DIR → /home/kgale/second-brain/agents/logs (vault); (T008) prescan dedup block → package-absolute import with sys.modules aliasing to prevent dual-module loading; (T009) append_routing_entry sys.path hack removed → package-absolute import with same aliasing guard; (T010) 11 tests pass — includes SC-8 subprocess proof (dedup-active from /tmp with repo-root-only PYTHONPATH, bare-import-fails negative proof). Full inbox suite 288 pass 0 regress. Ruff exit 0.
- 2026-07-05T03:41:49Z – codex:gpt-5-codex:reviewer-renata:reviewer – shell_pid=59528 – Started review via action command
- 2026-07-05T03:45:18Z – user – shell_pid=59528 – Review passed: FR-006 log path and FR-011 package-absolute dedup import verified; focused and full inbox tests pass; anti-pattern checklist pass/N/A
