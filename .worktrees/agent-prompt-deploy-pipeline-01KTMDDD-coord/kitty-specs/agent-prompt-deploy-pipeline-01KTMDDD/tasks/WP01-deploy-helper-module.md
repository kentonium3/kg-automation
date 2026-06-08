---
work_package_id: WP01
title: Deploy helper Python module
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- FR-010
- FR-015
- FR-016
- FR-017
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
agent: "claude"
shell_pid: "98290"
history:
- timestamp: '2026-06-08T20:25:00Z'
  actor: claude
  event: Created via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/deploy/
execution_mode: code_change
mission_id: 01KTMDDDGGY00S3S3VFGK0Z6P9
mission_slug: agent-prompt-deploy-pipeline-01KTMDDD
model: claude-sonnet-4-6
owned_files:
- scripts/openclaw/deploy/__init__.py
- scripts/openclaw/deploy/deploy_agent_prompts.py
- tests/openclaw/test_deploy_agent_prompts.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, load the assigned profile so the
session adopts the right identity, governance scope, boundaries, and
initialization declaration:

```
/ad-hoc-profile-load python-pedro
```

This sets up the implementer posture for Python work, including conventions
around stdlib-only code, test-first development, and locality of change.

## Objective

Implement the Python stdlib helper at `scripts/openclaw/deploy/deploy_agent_prompts.py` that the office2 systemd timer invokes every 5 minutes. The helper:

1. Runs `git pull --ff-only origin main` in `/home/claude/kg-automation`
2. Reads `docs/design/architecture/data/service-inventory.json` to discover Felix agents
3. For each in-scope agent + file, compares MD5 of source vs deployed
4. Atomically copies any drifted file (preserve mode)
5. Appends structured audit records to `/data/services/openclaw/deploy/agent-prompt-sync.jsonl`
6. Supports `--dry-run` and `--agent <slug>` flags
7. Exits 0 / 1 / 2 / 3 per the documented contract

This WP delivers a runnable, locally-testable helper. WP02 will add the systemd unit files; WP03 will sync architecture documentation.

## Context — read these first

| Document | Why |
|---|---|
| [../spec.md](../spec.md) | Functional + non-functional requirements; constraints; invariants |
| [../plan.md](../plan.md) § Implementation Concern Map | Decomposition into IC-01 through IC-08 |
| [../research.md](../research.md) D-001..008 + R-001..005 | Locked architectural decisions + stdlib implementation patterns |
| [../data-model.md](../data-model.md) | `AgentInventoryEntry`, `SyncAction`, `TickSummary` shapes |
| [../contracts/helper-cli.md](../contracts/helper-cli.md) | CLI surface contract (flags, exit codes, stdout/stderr discipline) |
| [../contracts/audit-log-jsonl.md](../contracts/audit-log-jsonl.md) | Audit log JSONL schema (5 record kinds + tick_summary) |
| `scripts/sync/driver.py` | Structural precedent — pattern for argparse, exit-code mapping, stdlib-only style |
| `scripts/sync/diff.py` | Precedent for pure-function decomposition with tests |

## Branch Strategy

- **Planning base / merge target**: `main`
- **Coordination branch (planning artifacts)**: `kitty/mission-agent-prompt-deploy-pipeline-01KTMDDD`
- **Execution worktree**: `spec-kitty implement WP01 --agent claude` creates the lane worktree under `.worktrees/agent-prompt-deploy-pipeline-<mid8>-lane-a/` and a lane branch off the coordination branch.
- Per the coordination branch / `OnUnitInactiveSec` precedent established in this codebase, NEVER use `git pull` without `--ff-only`; NEVER use `git merge`; NEVER use `git reset` on the office2 clone or local main.
- The `spec-kitty merge` command at mission close ships the lane → coordination → main.

## Subtask Guidance

### T001 — Discovery functions: `is_in_scope` + `iter_agents` (tests-first + impl)

**Purpose**: Read `service-inventory.json` and produce a filtered iterable of `AgentInventoryEntry` records, plus a filename allowlist gate.

**Steps**:

1. Write `tests/openclaw/test_deploy_agent_prompts.py` test scaffolding:
   - Test `is_in_scope("AGENTS.md")` → True
   - Test `is_in_scope("IDENTITY.md")` → True
   - Test `is_in_scope("SOUL.md")` → True
   - Test `is_in_scope("TOOLS.md")` → True
   - Test `is_in_scope("USER.md")` → True
   - Test `is_in_scope("HEARTBEAT.md")` → False (excluded)
   - Test `is_in_scope("AGENTS.md.tmpl")` → False (excluded)
   - Test `is_in_scope("AGENTS.md.bak.pre-mission-490")` → False (excluded)
   - Test `is_in_scope("GOVERNANCE.md")` → False (excluded)
   - Test `is_in_scope("random.md")` → False (not in allowlist)
   - Test `iter_agents` with a `tmp_path / "service-inventory.json"` fixture containing a synthetic openclaw service entry with 3 agents (one with both `source_in_repo` + `workspace`, one missing `source_in_repo`, one missing `workspace`). Assert only the complete agent is yielded.
2. Implement `is_in_scope(filename: str) -> bool` in `scripts/openclaw/deploy/deploy_agent_prompts.py`:
   - In-scope set: `{"AGENTS.md", "IDENTITY.md", "SOUL.md", "TOOLS.md", "USER.md"}` as a module-level frozenset
   - Excluded by pattern: filename starts with `HEARTBEAT.md`, OR ends with `.tmpl`, OR contains `.bak`, OR equals `GOVERNANCE.md`
   - Order: check excluded patterns FIRST (return False), then check allowlist (return True iff present)
3. Implement `iter_agents(inventory_path: Path) -> Iterator[AgentInventoryEntry]`:
   - `json.load` the file
   - Find the openclaw service entry (where `name == "openclaw"` OR where `agents` dict is present at top level — inspect service-inventory.json to choose the right key)
   - Iterate `agents` map; yield `AgentInventoryEntry(slug=key, source_in_repo=Path(value["source_in_repo"]), workspace=Path(value["workspace"]))` only when both fields are present and non-empty
   - Skip-with-warning is delegated to caller (this generator doesn't emit audit records itself)

**Files**:
- `scripts/openclaw/deploy/__init__.py` (new, empty file with module docstring)
- `scripts/openclaw/deploy/deploy_agent_prompts.py` (new, partial — discovery functions only)
- `tests/openclaw/test_deploy_agent_prompts.py` (new, partial — discovery tests only)

**Validation**: All tests pass; running `pytest tests/openclaw/test_deploy_agent_prompts.py::test_is_in_scope_* -v` and `::test_iter_agents_*` shows ≥10 passing tests.

### T002 — MD5 + `atomic_copy` (tests-first + impl, preserve mode)

**Purpose**: Compute file MD5 deterministically; atomically copy a source file to a destination while preserving the destination's prior mode.

**Steps**:

1. Add test scaffolding to `tests/openclaw/test_deploy_agent_prompts.py`:
   - Test `compute_md5(tmp_path / "f.md")` for known content matches the expected hex MD5
   - Test `compute_md5` on a large file (e.g., 200KB) doesn't load the whole thing into memory (assert on memory usage indirectly — at minimum, assert function returns within 1s)
   - Test `atomic_copy(src, dst)` where dst doesn't exist → dst created with src bytes
   - Test `atomic_copy(src, dst)` where dst exists with mode 0o644 → dst replaced with src bytes, mode still 0o644
   - Test `atomic_copy(src, dst)` where dst exists with mode 0o600 → dst replaced, mode still 0o600
   - Test `atomic_copy` cleans up temp file on `os.replace` success (no `dst.tmp.<pid>` leftover)
   - Test `atomic_copy` propagates `OSError` from `os.replace` (mocked via `unittest.mock.patch`) — caller can handle
2. Implement `compute_md5(path: Path) -> str`:
   - 64KB chunk reads (`iter(lambda: fh.read(65536), b"")`)
   - Return hex digest (32 chars)
3. Implement `atomic_copy(src: Path, dst: Path) -> None`:
   - Compute temp path: `dst.parent / f"{dst.name}.tmp.{os.getpid()}"`
   - Read src bytes; write to temp; `fh.flush()` + `os.fsync(fh.fileno())`
   - If dst exists, capture `dst.stat().st_mode & 0o777` and `os.chmod(temp, mode)` before replace
   - `os.replace(temp, dst)`
   - On any exception, `temp.unlink(missing_ok=True)` (cleanup) and re-raise

**Files**:
- `scripts/openclaw/deploy/deploy_agent_prompts.py` (add `compute_md5`, `atomic_copy`)
- `tests/openclaw/test_deploy_agent_prompts.py` (add MD5 + atomic-copy tests)

**Validation**: All new tests pass.

### T003 — `git_pull` subprocess wrapper

**Purpose**: Wrap `git fetch && git pull --ff-only origin main` as a single function that returns a structured result.

**Steps**:

1. Add test scaffolding:
   - Test `git_pull(repo_root)` with `subprocess.run` mocked to return success → returns `(success=True, head_sha=<40 char hex>, stderr="")`
   - Test `git_pull` with `git fetch` mocked to return non-zero → returns `(success=False, head_sha=None, stderr=<stderr from fetch>, stage="fetch")`
   - Test `git_pull` with `git fetch` success but `git pull --ff-only` non-zero → returns `(success=False, head_sha=None, stderr=<pull stderr>, stage="pull")`
   - Verify the argv list passed to `subprocess.run` matches exactly: `["git", "fetch", "origin", "main"]` then `["git", "pull", "--ff-only", "origin", "main"]`
   - Verify `cwd=repo_root` was passed
2. Implement `git_pull(repo_root: Path) -> GitPullResult`:
   - Use `subprocess.run` with `cwd=repo_root, capture_output=True, text=True, check=False`
   - Two subprocess calls: fetch then pull
   - On any non-zero, short-circuit with the appropriate `stage` annotation
   - On full success, run `git rev-parse HEAD` to capture the post-pull head SHA
   - Return a dataclass `GitPullResult(success: bool, head_sha: Optional[str], stderr: str, stage: Optional[str])`

**Files**:
- `scripts/openclaw/deploy/deploy_agent_prompts.py` (add `git_pull`, `GitPullResult`)
- `tests/openclaw/test_deploy_agent_prompts.py` (add git_pull tests)

**Validation**: All new tests pass; argv assertions match exactly.

### T004 — Audit log primitives

**Purpose**: Append-only JSONL audit log with five record kinds plus tick_summary, per the schema in `contracts/audit-log-jsonl.md`.

**Steps**:

1. Add test scaffolding:
   - Test `SyncAction` dataclass serializes to dict with all expected fields per kind (copy / skip / error / git_pull_failed / warning)
   - Test `TickSummary` dataclass serializes with all expected fields
   - Test `audit_append(log_path, record)` writes one JSON line ending with `\n` and does NOT seek (mode `"a"`)
   - Test `audit_append` creates parent dir if missing (use `tmp_path / "deploy" / "log.jsonl"` where `deploy/` doesn't yet exist)
   - Test back-to-back appends produce strictly-growing file size
2. Implement `SyncAction` and `TickSummary` dataclasses (frozen=True) with required fields per `contracts/audit-log-jsonl.md`.
3. Implement `audit_record(kind: str, tick_id: str, **fields) -> dict`:
   - Returns a dict with `timestamp` (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")), `tick_id`, `kind`, plus arbitrary kwarg fields
4. Implement `audit_append(log_path: Path, record: dict) -> None`:
   - `log_path.parent.mkdir(parents=True, exist_ok=True)`
   - Open `"a"` (append text mode); write `json.dumps(record, separators=(",",":"))` + `"\n"`; close
5. Implement `audit_tick_summary(log_path: Path, tick_id: str, agents_processed: int, files_copied: int, files_skipped: int, files_errored: int, git_head_after_pull: Optional[str], exit_code: int, duration_ms: int) -> None`:
   - Build the tick_summary record per the schema and append via `audit_append`

**Files**:
- `scripts/openclaw/deploy/deploy_agent_prompts.py` (add audit primitives)
- `tests/openclaw/test_deploy_agent_prompts.py` (add audit tests)

**Validation**: All new tests pass; serialization shape matches `contracts/audit-log-jsonl.md` examples.

### T005 — CLI surface: `parse_args`, `run_tick`, `main`

**Purpose**: Wire together the CLI entry point. Parse argv, orchestrate one tick, return the correct exit code.

**Steps**:

1. Add test scaffolding for parse_args (per `contracts/helper-cli.md § Test contract`):
   - `test_parse_args_defaults` → dry_run=False, agent=None
   - `test_parse_args_dry_run` → dry_run=True
   - `test_parse_args_agent` → agent="felix-admin-capture"
   - `test_parse_args_both` → both flags set
2. Add test scaffolding for `run_tick` end-to-end and for `main` exit codes:
   - `test_main_validation_no_git_dir` → exit 3
   - `test_main_validation_no_service_inventory` → exit 3
   - `test_main_validation_unknown_agent` → exit 3
   - `test_main_git_pull_failed_exit_2` → exit 2, audit log has git_pull_failed + tick_summary
   - `test_main_no_drift_exit_0` → exit 0, audit log has skips + tick_summary, files unchanged
   - `test_main_drift_copied_exit_0` → exit 0, audit log has at least one copy, dst file MD5 matches src
   - `test_main_per_file_failure_exit_1` → exit 1 (atomic_copy raises OSError on one file via mock)
   - `test_main_dry_run_no_mutations` → exit 0, no audit log lines, no dst changes
3. Implement `parse_args(argv: List[str]) -> argparse.Namespace`:
   - `argparse.ArgumentParser`; flags `--dry-run` (store_true) and `--agent` (str)
4. Implement `run_tick(args: argparse.Namespace, repo_root: Path, audit_path: Path) -> int`:
   - Generate `tick_id = str(uuid.uuid4())`
   - Capture start time (`time.monotonic`)
   - Run validation checks (cwd has .git/, service-inventory.json exists, --agent slug if any is known); on failure return exit code 3
   - If not dry-run: call `git_pull(repo_root)`; on failure write git_pull_failed record + tick_summary, return 2
   - Iterate agents via `iter_agents`; if `args.agent` is set, restrict to that slug
   - For each agent: for each file in `is_in_scope` filtered list: compute src + dst MD5; if drift, atomic_copy (catch OSError → write error record + continue) else write skip record; in dry-run mode print DRIFT line to stdout instead
   - Track files_copied, files_skipped, files_errored
   - Write tick_summary; return 0 if no errors, 1 if any error
5. Implement `main(argv: Optional[List[str]] = None) -> int`:
   - `argv = argv if argv is not None else sys.argv[1:]`
   - Parse args; call `run_tick(args, repo_root=Path.cwd(), audit_path=AUDIT_PATH)`; return its exit code
   - Module bottom: `if __name__ == "__main__": sys.exit(main())`

**Files**:
- `scripts/openclaw/deploy/deploy_agent_prompts.py` (add parse_args, run_tick, main, module-level constants AUDIT_PATH, REPO_ROOT_DEFAULT)
- `tests/openclaw/test_deploy_agent_prompts.py` (add CLI + main tests)

**Validation**: All new tests pass; manual smoke test: `cd /tmp && python3 -m scripts.openclaw.deploy.deploy_agent_prompts` from a tmp dir → exit 3 with stderr message (no .git/).

### T006 — Integration test: `run_tick` end-to-end with mocked git_pull

**Purpose**: Validate the orchestrator wires the modules together correctly under realistic conditions.

**Steps**:

1. Add `test_integration_run_tick_full_drift_to_deploy` to `tests/openclaw/test_deploy_agent_prompts.py`:
   - Build a fake repo tree under `tmp_path / "repo"` with `.git/` (just `tmp_path / "repo" / ".git" / "HEAD"`), `scripts/openclaw/agents/test-agent/AGENTS.md` with content "v2", and `docs/design/architecture/data/service-inventory.json` declaring `services[openclaw].agents.test-agent` with `source_in_repo: "scripts/openclaw/agents/test-agent/"`, `workspace: <abs path to tmp_path / "deploy" / "test-deploy-dir">`.
   - Pre-populate deploy dir with `AGENTS.md` content "v1" (different MD5).
   - Mock `git_pull` to return success.
   - Mock `Path.cwd()` to return the fake repo root.
   - Call `main([])`; assert return 0.
   - Assert deploy dir's `AGENTS.md` now contains "v2".
   - Assert audit log has exactly: 1 copy entry + 1 tick_summary (no skips, no errors).
2. Add `test_integration_run_tick_dry_run_no_mutations` mirroring the above but with `--dry-run`; assert deploy file is unchanged (still "v1") and audit log is empty.

**Files**:
- `tests/openclaw/test_deploy_agent_prompts.py` (add integration tests)

**Validation**: Tests pass.

### T007 — Coverage gate verification

**Purpose**: Confirm the coverage gate (NFR-003: ≥90% line / ≥85% branch) is met.

**Steps**:

1. From repo root, run:
   ```
   pytest tests/openclaw/test_deploy_agent_prompts.py \
     --cov=scripts.openclaw.deploy \
     --cov-branch \
     --cov-report=term-missing \
     --cov-fail-under=90
   ```
2. If branch coverage <85%, identify the uncovered branches via `--cov-report=term-missing`; either add a test or annotate with `# pragma: no branch` (per `[[reference_pytest_branch_coverage_pragma]]`) ONLY for genuinely-unreachable defensive branches (e.g., a check guarded by an earlier short-circuit return).
3. Document the final coverage report's headline numbers in the WP completion notes.

**Files**:
- (no production-code changes; tests may be added if coverage gap is real)

**Validation**: Coverage report shows ≥90% line AND ≥85% branch; pytest exits 0.

## Definition of Done

- [ ] All 7 subtasks have their tests written first AND passing
- [ ] `scripts/openclaw/deploy/__init__.py` exists (empty / docstring only)
- [ ] `scripts/openclaw/deploy/deploy_agent_prompts.py` implements all functions per the contracts
- [ ] Module is invokable as `python3 -m scripts.openclaw.deploy.deploy_agent_prompts` from `/home/claude/kg-automation` (manual smoke; not in CI)
- [ ] `tests/openclaw/test_deploy_agent_prompts.py` exists with all required test cases per the subtask guidance
- [ ] Coverage gate: `pytest --cov` shows ≥90% line / ≥85% branch
- [ ] No `requests`, `httpx`, `pydantic`, or any non-stdlib import (NFR-002)
- [ ] Module passes `python3 -c "from scripts.openclaw.deploy.deploy_agent_prompts import main; print('importable')"`
- [ ] Lane committed; WP frontmatter `lane` updated to `for_review`

## Risks

- Coverage gate strictness (NFR-003): branch coverage is often the harder threshold to hit. The `# pragma: no branch` pattern is the documented escape hatch for genuinely-unreachable defensive branches; abusing it would mask real test gaps.
- subprocess.run mocking risk: tests mock the subprocess rather than running real git. The mock contract is the argv list and the simulated returncode/stdout/stderr. Real git behavior is verified at operator install time per SC-4.
- Atomic copy temp-file collision in tests: tests using `tmp_path` for multiple atomic_copy calls within one test must use different src + dst paths to avoid temp-file name reuse (PID is the same within one test process).

## Reviewer Guidance

- Verify the production code path for `atomic_copy` actually preserves mode — write a test that confirms a 0o600 file stays 0o600 after copy (not just 0o644).
- Verify the git_pull function passes `--ff-only` exactly once (test the argv list).
- Verify the audit log file is opened in append mode (`"a"`), not `"w"` or `"r+"`.
- Verify the in-scope set is a frozenset (immutable), not a list (mutable).
- Verify the exit codes match the contract: 0 for success, 1 for partial failure (per-file), 2 for git_pull_failed, 3 for validation error.
- Check for any `requests` / `httpx` import — should be NONE.

## Next Step

After this WP merges to coordination branch:
- `spec-kitty agent action implement WP02 --agent claude` (the systemd unit WP)

## Activity Log

- 2026-06-08T21:14:29Z – claude – shell_pid=96199 – Assigned agent via action command
- 2026-06-08T21:20:48Z – claude – shell_pid=96199 – WP01 implemented + 56/56 tests pass + 97.64% coverage. Ready for review.
- 2026-06-08T21:21:07Z – claude – shell_pid=98290 – Started review via action command
- 2026-06-08T21:22:52Z – user – shell_pid=98290 – 56/56 tests, 97.64% coverage, contracts honored.
