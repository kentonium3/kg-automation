---
work_package_id: WP01
title: The installed-report channel module
dependencies: []
requirement_refs:
- FR-001
- FR-004
- NFR-002
planning_base_branch: fix/deploy-runtime-installed-report
merge_target_branch: fix/deploy-runtime-installed-report
branch_strategy: Planning artifacts for this mission were generated on fix/deploy-runtime-installed-report. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/deploy-runtime-installed-report unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-deploy-runtime-installed-report-01M4ZP8E
base_commit: 295a7c05a3e68a1b123e80b6351da8554799ec7a
created_at: '2026-10-15T12:11:00.205035+00:00'
subtasks:
- T001
- T002
- T003
- T004
history:
- at: '2026-10-15T09:00:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (plan revised after three post-plan reviews)
agent_profile: python-pedro
authoritative_surface: scripts/deploy/lib/
create_intent:
- scripts/deploy/lib/installed_report.py
- tests/deploy/test_installed_report.py
execution_mode: code_change
lane: planned
model: claude-opus-5-5
owned_files:
- scripts/deploy/lib/installed_report.py
- tests/deploy/test_installed_report.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP01 – The installed-report channel module

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history <WP> --note "..."`.

---

## Branch Strategy

- **Planning base branch**: `fix/deploy-runtime-installed-report` · **Merge target branch**: `fix/deploy-runtime-installed-report`. Worktrees come from `lanes.json`.

## Context

Spec: `spec.md`, especially FR-001–FR-010 and C-001/C-002. Plan: `plan.md` (the IC named below). Contract: `contracts/installed-report.md`, which is authoritative for format, reader rules, mapper rules and result keys. Data model: `data-model.md`. Review dispositions: `research.md`.

## Objective (IC-01)

`scripts/deploy/lib/installed_report.py` owns the channel:

- `ENV_VAR = "FELIX_DEPLOY_INSTALLED_REPORT"`
- `WRITE_FAILED_MARKER = "FELIX_DEPLOY_INSTALLED_REPORT_WRITE_FAILED"`
- the limits `MAX_BYTES = 1 MiB` and `MAX_ENTRIES = 10_000`
- `record_installed(source, dest)`
- `read_report(path) -> dict`

## Subtasks

### T001 – Producer `record_installed(source, dest)`

- If the variable is unset or empty, do nothing.
- Otherwise append one line, `json.dumps({"source": str(Path(source).resolve()), "dest": str(Path(dest).resolve())}) + "\n"`, in a single `write`, with the file opened in `"a"` mode.
- Any `OSError` means print exactly one line `f"{WRITE_FAILED_MARKER}: {exc}"` to **stderr**, then return normally. It never raises.

### T002 – Hardened reader `read_report(path)`

- Missing file (`FileNotFoundError` on open): `{"entries": [], "rejected": False, "missing": True, "warnings": []}`.
- Otherwise:
  - open with `os.open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK)`;
  - `fstat` must be `S_ISREG`;
  - `os.read` loops until cap+1 bytes or EOF.
- Reject **wholesale** in all of these cases. The result is `{"entries": [], "rejected": True, "missing": False, "warnings": [why]}`.
  - more than `MAX_BYTES`;
  - invalid UTF-8 under strict decoding;
  - any non-blank line that is not a JSON object with string `source` and `dest`, both absolute;
  - more than `MAX_ENTRIES` entries;
  - a symlink, FIFO or directory (`ELOOP`, or the non-regular check);
  - any `OSError`.
- On success, deduplicate entries in order: `{"entries": [...], "rejected": False, "missing": False, "warnings": []}`.
- It never raises.

### T003 – Tests (`tests/deploy/test_installed_report.py`)

Producer:
- unset variable writes nothing;
- set variable gives one line per call;
- an unwritable directory emits the marker on stderr and does not raise.

Reader:
- missing file;
- valid file;
- **mixed valid and invalid lines are rejected wholesale**;
- relative path rejected;
- non-string rejected;
- oversized file (write cap + 10 bytes);
- invalid UTF-8;
- over-limit entries (use monkeypatched `MAX_ENTRIES = 3`);
- a FIFO (`os.mkfifo`) is rejected **without blocking**; guard it with a 2-second `signal.alarm` timeout so a regression fails instead of hanging;
- a symlink to a valid file is rejected;
- a directory is rejected.

### T004 – Round trip

A producer write followed by a read returns exactly the entries written. Resolution is applied: a symlinked source records its resolved path.

## Definition of Done

All tests pass; the module never raises, which is asserted by fuzzing 20 random byte blobs through `read_report`; `python3 -m pytest tests/deploy -q` is green.

## Review Guidance

Check against the contract and C-002: nothing may widen expectations without proof. Every new behavior needs a test that fails when the behavior is removed.

## Progress & Status

`spec-kitty agent tasks add-history WP01 --note "…"` · implement: `spec-kitty agent action implement WP01 --agent claude --mission deploy-runtime-installed-report-01M4ZP8E`
