---
work_package_id: WP02
title: Log Writer (log_action.py)
dependencies: [WP01]
requirement_refs:
- FR-01
- FR-02
- FR-03
- FR-04
- FR-05
- FR-06
- FR-07
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 014-felix-core-digest-WP01
base_commit: 1cc6045874580b1c667cd01084ae1076d74bcfbf
created_at: '2026-04-04T15:34:34.535128+00:00'
subtasks: [T005, T006, T007, T008, T009, T010]
shell_pid: "92524"
agent: "claude"
history:
- date: '2026-04-04'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/observation/
execution_mode: code_change
feature: 014-felix-core-digest
owned_files:
- scripts/openclaw/observation/log_action.py
- scripts/openclaw/observation/tests/test_log_action.py
---

# WP02: Log Writer (log_action.py)

## Branch Strategy

- **Planning/base branch**: `main`
- **Merge target**: `main`
- **Dependencies**: WP01 (registry + config must exist first)
- **Implementation command**: `spec-kitty implement WP02 --base WP01`
- **Parallel**: Can run simultaneously with WP03 (no file overlap)

## Objective

Create `log_action.py` as the deterministic log writer — the single boundary
between stochastic agent judgment and well-formed JSONL output. This script
receives structured CLI arguments from agents (via OpenClaw's `exec` tool),
validates them, and appends a single JSONL entry to the correct log file.

**Architectural intent**: Agents determine WHAT happened (stochastic). This
script owns HOW it's recorded (deterministic). The agent never writes raw
structured data directly.

## Context

### CLI Invocation Pattern

Agents call log_action.py via OpenClaw's exec tool:
```bash
python scripts/openclaw/observation/log_action.py \
  --agent felix-admin-capture \
  --category routine \
  --action file_processed \
  --target "Inbox 2026-04-04 0715.md" \
  --outcome completed \
  --context '{"project": "Personal", "vikunja_task_id": null}'
```

### JSONL Output Schema

Required fields (every entry):
```json
{"ts": "2026-04-04T05:12:04Z", "run_id": "felix-admin-capture-20260404-0512", "agent": "felix-admin-capture", "autonomy_level": "assisted", "category": "routine", "action": "file_processed", "target": "Inbox 2026-04-04 0715.md", "outcome": "completed"}
```

With context (standard verbosity):
```json
{"ts": "...", "run_id": "...", "agent": "...", "autonomy_level": "...", "category": "...", "action": "...", "target": "...", "outcome": "...", "context": {"project": "Personal", "vikunja_task_id": null}}
```

With trace (verbose only):
```json
{"...all above...", "trace": {"confidence": {"project": 0.94}, "api_calls": [{"endpoint": "GET /projects", "status": 200, "latency_ms": 87}]}}
```

### Log File Path

```
~/second-brain/agents/logs/{agent-name}/YYYY-MM-DD.jsonl
```

### Dependencies

- `config.py` with `log_verbosity()` method (from WP01)
- `agent-registry.json` with `log_verbosity` field (from WP01)
- Python standard library only (NFR-04)

---

## Subtask T005: Write test_log_action.py (Test-First)

**Purpose**: Define all expected behaviors before writing implementation code.
This is the test-first paradigm — tests define the contract.

**Steps**:
1. Create `scripts/openclaw/observation/tests/test_log_action.py`
2. Write test classes covering all behaviors:

**TestSchemaValidation**:
- `test_valid_entry_writes_jsonl`: Valid required args → JSONL line appended to file
- `test_missing_required_field_exits_nonzero`: Missing --agent → exit code 1, no file write
- `test_invalid_category_exits_nonzero`: --category "invalid" → exit code 1, no file write
- `test_valid_categories_accepted`: Each of routine, flagged, error, security → accepted

**TestTimestampAndRunId**:
- `test_ts_is_utc_iso8601`: Written ts field is valid UTC ISO-8601
- `test_run_id_format`: run_id matches `{agent}-{YYYYMMDD}-{HHMM}` pattern
- `test_ts_and_run_id_not_accepted_from_cli`: If --ts passed, it's ignored (generated internally)

**TestFileIO**:
- `test_creates_agent_subdirectory`: First write creates `{agent}/` under log dir
- `test_appends_to_existing_file`: Second write appends (file has 2 lines)
- `test_correct_daily_filename`: File is `YYYY-MM-DD.jsonl` matching current date
- `test_each_write_is_single_line`: Entry is exactly one line (no embedded newlines)

**TestTruncation**:
- `test_short_string_unchanged`: 50-char target → written as-is
- `test_long_string_truncated`: 150-char target → truncated at 120 + "[truncated]"
- `test_truncation_applies_to_all_string_fields`: action, target, outcome all enforced

**TestVerbosity**:
- `test_brief_strips_context_and_trace`: context/trace args provided but not written
- `test_standard_writes_context_strips_trace`: context written, trace stripped
- `test_verbose_writes_all`: context and trace both written
- `test_no_context_at_standard_is_fine`: Standard verbosity, no --context arg → valid entry without context key

**TestAutonomyLevel**:
- `test_autonomy_level_read_from_registry`: Written entry has correct autonomy_level from registry

3. Use pytest tmp_path for all file operations
4. For registry-dependent tests, create temp registry JSON files
5. Use `subprocess.run()` to invoke log_action.py as a CLI (testing the actual entry point)

**Files**: `scripts/openclaw/observation/tests/test_log_action.py` (new)

**Validation**:
- [ ] All test cases defined (expect failures before implementation)
- [ ] Tests use subprocess.run for CLI integration testing
- [ ] Temp directories used for all file I/O

---

## Subtask T006: Implement CLI Interface

**Purpose**: Define the argparse entry point for log_action.py.

**Steps**:
1. Create `scripts/openclaw/observation/log_action.py`
2. Implement `main()` with argparse:
   - Required args: `--agent`, `--category`, `--action`, `--target`, `--outcome`
   - Optional args: `--context` (JSON string), `--trace` (JSON string)
   - Optional overrides: `--registry` (path), `--log-dir` (path, default `~/second-brain/agents/logs/`)
3. Add `if __name__ == "__main__": main()` entry point
4. Import only from Python standard library (json, argparse, pathlib, datetime, sys)

**Files**: `scripts/openclaw/observation/log_action.py` (new)

**Validation**:
- [ ] `python log_action.py --help` shows all args
- [ ] Missing required args → argparse error (exit 2)
- [ ] No external imports

---

## Subtask T007: Implement Schema Validation

**Purpose**: Fast-fail on invalid input before any file I/O.

**Steps**:
1. Validate `--category` against allowed values: `routine`, `flagged`, `error`, `security`
2. Validate all required fields are non-empty strings
3. If `--context` provided, parse as JSON; fail on invalid JSON
4. If `--trace` provided, parse as JSON; fail on invalid JSON
5. On any validation failure: print error to stderr, exit with code 1, no file written

**Files**: `scripts/openclaw/observation/log_action.py`

**Validation**:
- [ ] Invalid category → stderr message + exit 1
- [ ] Empty required field → stderr message + exit 1
- [ ] Malformed JSON in --context → stderr message + exit 1

---

## Subtask T008: Implement JSONL Serialization and File I/O

**Purpose**: The core write path — serialize validated data to JSONL and append
to the correct daily log file.

**Steps**:
1. Generate `ts` as UTC ISO-8601: `datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`
2. Generate `run_id`: `f"{agent}-{now.strftime('%Y%m%d')}-{now.strftime('%H%M')}"`
3. Look up `autonomy_level` from registry via `config.py`
4. Build the entry dict with all required fields
5. Compute log file path: `{log_dir}/{agent}/{YYYY-MM-DD}.jsonl`
6. Create agent subdirectory if it doesn't exist (`mkdir -p` equivalent)
7. Append one JSON line: `json.dumps(entry, ensure_ascii=False) + "\n"`
8. Use file open mode `"a"` (append) — never truncate

**Files**: `scripts/openclaw/observation/log_action.py`

**Validation**:
- [ ] Written line is valid JSON (can be parsed back)
- [ ] File is append-only (existing content preserved)
- [ ] Agent subdirectory created on first write
- [ ] Filename matches current UTC date

---

## Subtask T009: Implement Truncation Enforcement

**Purpose**: Prevent generative output from bloating log files. Any string
field value exceeding 120 characters is truncated.

**Steps**:
1. Before serialization, iterate over all string values in the entry dict (top-level only: action, target, outcome)
2. Also iterate over string values in context dict if present
3. If `len(value) > 120`: truncate to 120 chars and append `[truncated]`
4. Do NOT truncate: ts, run_id, agent, category (these are controlled values)
5. This is enforced in Python — not left to the agent

**Files**: `scripts/openclaw/observation/log_action.py`

**Validation**:
- [ ] 120-char value → unchanged
- [ ] 121-char value → truncated to 120 + "[truncated]"
- [ ] ts, run_id, agent, category never truncated

---

## Subtask T010: Implement Verbosity Filtering

**Purpose**: Control which optional blocks are written based on the agent's
`log_verbosity` registry setting.

**Steps**:
1. Read agent's log_verbosity via `ObservationConfig.log_verbosity(agent_name)`
2. Apply filtering:
   - `"brief"`: Write only required fields. Strip `context` and `trace` even if provided.
   - `"standard"`: Write required + `context` (if provided). Strip `trace`.
   - `"verbose"`: Write all provided fields.
3. If `--context` is provided but verbosity is "brief", silently drop it (not an error)
4. If `--trace` is provided but verbosity is not "verbose", silently drop it

**Files**: `scripts/openclaw/observation/log_action.py`

**Validation**:
- [ ] Brief agent: context arg provided → not in output
- [ ] Standard agent: context written, trace dropped
- [ ] Verbose agent: all fields written
- [ ] No error when optional args are provided but filtered out

---

## Definition of Done

- [ ] `test_log_action.py` defines all test cases (T005)
- [ ] All tests pass: `pytest scripts/openclaw/observation/tests/test_log_action.py -v`
- [ ] `python log_action.py --help` works
- [ ] Valid call writes exactly one JSONL line to correct file
- [ ] Invalid call exits 1 with no file modification
- [ ] No imports outside Python standard library
- [ ] Full test suite clean: `pytest scripts/openclaw/observation/tests/ -v`

## Risks

- **Concurrent appends**: Multiple agents could run simultaneously. File append (`"a"` mode) on Linux is atomic for writes under PIPE_BUF (4096 bytes). Single JSONL lines will be well under this. No locking needed.
- **Registry path resolution**: log_action.py must find agent-registry.json relative to itself (same pattern as config.py repo root detection).

## Reviewer Guidance

1. Verify no external imports (stdlib only)
2. Check that ts and run_id are ALWAYS generated internally, never from CLI
3. Confirm truncation applies to all user-supplied string fields
4. Verify file append mode (never truncate)
5. Run tests with `--tb=short` to check error paths

## Activity Log

- 2026-04-04T15:34:34Z – claude – shell_pid=92524 – Started implementation via workflow command
- 2026-04-04T15:37:04Z – claude – shell_pid=92524 – All 6 subtasks done. 45/45 tests passing (19 new + 26 existing). log_action.py: CLI, validation, truncation, verbosity, append-only JSONL.
