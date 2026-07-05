---
work_package_id: WP01
title: Repoint observation log_dir default
dependencies: []
requirement_refs:
- FR-001
- FR-007
tracker_refs: []
planning_base_branch: fix/observation-digest-repoint
merge_target_branch: fix/observation-digest-repoint
branch_strategy: Planning artifacts for this mission were generated on fix/observation-digest-repoint. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/observation-digest-repoint unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-observation-digest-repoint-01KWS2E2
base_commit: 027f0e006e1cabb547808f9bbd9960892a94963a
created_at: '2026-07-05T13:06:47.868338+00:00'
subtasks:
- T001
- T002
- T003
agent: "claude"
shell_pid: "39897"
history:
- created by /spec-kitty.tasks 2026-07-05
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/observation/config.py
create_intent:
- scripts/openclaw/observation/tests/test_config_log_dir.py
execution_mode: code_change
owned_files:
- scripts/openclaw/observation/config.py
- scripts/openclaw/observation/log_action.py
- scripts/openclaw/observation/summarize.py
- scripts/openclaw/observation/tests/test_config_log_dir.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:
run `/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity, boundaries, and
initialization declaration. Then read this WP end-to-end before editing.

## Objective

Make the observation-digest subsystem's raw `log_dir` **default** resolve to the backed-up vault
path `/home/kgale/second-brain/agents/logs` independent of `HOME`, so that under the deployed
service account (`felix-core-digest.service` sets `Environment=HOME=/home/claude`) raw logs no
longer land on the stray `/home/claude/second-brain` tree. Fix related docstrings. **Do not**
touch `output_dir` (already vault-synced) or the systemd unit.

## Context

- `scripts/openclaw/observation/config.py:40` currently: `self._log_dir = Path(log_dir) if log_dir else Path.home() / "second-brain" / "agents" / "logs"`.
- `config.py:41` `output_dir` already resolves via `get_vault_path("system")/agent-activity` — **leave unchanged**.
- `log_action.py` writes to `config.log_dir`; `summarize.py` reads it. Neither hardcodes the path; both just consume `config.log_dir` — so only the default in `config.py` needs the behavior change, plus docstrings.
- Decision D1 (research.md): use a module-level absolute **constant**, NOT the vault registry (the registry is for Obsidian-synced `notes/` folders; `agents/logs` is a non-synced sibling). This matches #656's `DEFAULT_VAULT_LOGS_DIR`.

### Subtask T001 — Repoint the default (config.py)

- Add a module constant near the top of `config.py`:
  `DEFAULT_AGENT_LOGS_DIR = Path("/home/kgale/second-brain/agents/logs")`
- Change line 40 to use it: `self._log_dir = Path(log_dir) if log_dir else DEFAULT_AGENT_LOGS_DIR`
- Update the `__init__` docstring (`config.py:30`) that says `~/second-brain/agents/logs/` to the absolute vault path, and note it is `HOME`-independent.
- Do NOT change `output_dir` (line 41) or `registry_path`.

### Subtask T002 — Docstrings [P]

- `log_action.py`: any docstring/comment referencing `~/second-brain/agents/logs/` → `/home/kgale/second-brain/agents/logs/`.
- `summarize.py`: same (e.g. the module docstring line ~10 "Each agent writes a JSONL log to ~/second-brain/agents/logs/{agent-name}/").
- These are text-only; no behavior change.

### Subtask T003 — Unit test

- Add `scripts/openclaw/observation/tests/test_config_log_dir.py`:
  - Test: with `HOME` monkeypatched to an arbitrary temp dir, `ObservationConfig(...).log_dir == Path("/home/kgale/second-brain/agents/logs")` (default is HOME-independent). Provide a valid `registry_path` (point at the repo `docs/constitution/agent-registry.json` or a fixture) so construction succeeds.
  - Test: explicit `log_dir=` override is still honored.
- If the existing `scripts/openclaw/observation/tests/test_config.py` asserts the OLD `Path.home()`-based default, update that assertion (add `test_config.py` to your edits only if needed; record a one-line rationale).

## Branch Strategy

Planning/base branch: `fix/observation-digest-repoint`. Final merge target: `fix/observation-digest-repoint`
(the mission merges WPs into the feature branch; `feat→main` happens later after the post-merge
Codex review). Execution worktrees are allocated per computed lane from `lanes.json` — do not
create branches manually.

## Test Strategy

Run `pytest scripts/openclaw/observation/tests -k "log_dir or config" -q`. All pass, including the
new HOME-independence test.

## Definition of Done

- [ ] `config.py` default is the absolute constant; `output_dir` untouched.
- [ ] Docstrings in config/log_action/summarize corrected.
- [ ] New unit test passes and asserts HOME-independence + override honoring.
- [ ] No change to the systemd unit or `output_dir`.

## Risks / Reviewer guidance

- **Risk**: accidentally changing `output_dir` or importing the vault registry — reviewer verifies line 41 is untouched and no `paths.json` edit.
- **Risk**: breaking existing `test_config.py` — reviewer checks the full observation test suite passes.
- Confirm the constant value exactly matches `/home/kgale/second-brain/agents/logs` (byte-for-byte, matches #656's `DEFAULT_VAULT_LOGS_DIR`).

## Activity Log

- 2026-07-05T13:12:02Z – claude – shell_pid=37823 – Moved to for_review
- 2026-07-05T13:12:14Z – claude – shell_pid=39897 – Started review via action command
- 2026-07-05T13:14:19Z – user – shell_pid=39897 – Review passed: HOME-independent constant, output_dir/registry untouched, 223 tests green
