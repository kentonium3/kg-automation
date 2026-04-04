---
work_package_id: WP03
title: summarize.py JSONL Rewrite
dependencies: [WP01]
requirement_refs:
- FR-08
- FR-09
- FR-10
- FR-11
- FR-12
- FR-13
- FR-14
- FR-15
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 014-felix-core-digest-WP01
base_commit: 1cc6045874580b1c667cd01084ae1076d74bcfbf
created_at: '2026-04-04T15:35:20.433513+00:00'
subtasks: [T011, T012, T013, T014, T015, T016, T017]
shell_pid: "96073"
agent: "claude"
history:
- date: '2026-04-04'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/observation/tests/
execution_mode: code_change
feature: 014-felix-core-digest
owned_files:
- scripts/openclaw/observation/summarize.py
- scripts/openclaw/observation/tests/test_summarize.py
- scripts/openclaw/observation/tests/fixtures/**
---

# WP03: summarize.py JSONL Rewrite

## Branch Strategy

- **Planning/base branch**: `main`
- **Merge target**: `main`
- **Dependencies**: WP01 (registry with log_verbosity must exist)
- **Implementation command**: `spec-kitty implement WP03 --base WP01`
- **Parallel**: Can run simultaneously with WP02 (no file overlap)

## Objective

Replace all Markdown regex parsing in `summarize.py` with JSONL parsing,
update output paths to `Agent-Logs/`, implement 5-day retention and
idempotency, and rewrite all test fixtures from Markdown to JSONL.

This is the largest single WP — it transforms the core of the observation
module from fragile regex to deterministic JSON deserialization.

## Context

### What Gets Removed from summarize.py

These regex patterns and the `parse_log_file()` function:
```python
CATEGORY_PATTERN = r"^\s*-\s*\[(\w+)\]\s*(.*)"
AGENT_PATTERN = r"\*\*Agent\*\*:\s*(.+)"
RUN_TIME_PATTERN = r"\*\*Run time\*\*:\s*(.+)"
SUMMARY_LINE_PATTERN = r"^\s*-\s*(.+?):\s*(\d+)"
```

### What Gets Preserved

The processing layer operates on dicts with `{"category": str, "text": str}`:
- `filter_actions_by_autonomy(actions, autonomy_level)` — unchanged
- `detect_critical_alerts(actions)` — unchanged
- `summarize_routine_actions(actions)` — unchanged
- `generate_digest()` — output paths change but logic preserved
- `generate_agent_detail()` — output paths change but logic preserved

### Current Fixture Files (6 Markdown)

```
tests/fixtures/
├── capture-routine.md       → capture-routine.jsonl
├── capture-flagged.md       → capture-flagged.jsonl
├── capture-error.md         → capture-error.jsonl
├── capture-security.md      → capture-security.jsonl
├── habits-routine.md        → habits-routine.jsonl
└── habits-mixed.md          → habits-mixed.jsonl
```

### New Output Structure

```
{vault_path}/Agent-Logs/
├── overview.md
├── felix-admin-capture/YYYY-MM-DD-log.md
├── felix-admin-habits/YYYY-MM-DD-log.md
└── felix-admin-tasker/YYYY-MM-DD-log.md
```

Old path: `{vault_path}/00-System/agent-activity/` — left untouched.

---

## Subtask T011: Create JSONL Test Fixtures

**Purpose**: Map all 6 existing Markdown fixtures to JSONL equivalents, plus
create 4 new fixtures for extended coverage. Test-first — fixtures exist
before the parser is written.

**Steps**:
1. Read each existing Markdown fixture and create its JSONL equivalent:

   **capture-routine.jsonl** (8 entries, all routine):
   ```jsonl
   {"ts":"2026-04-01T11:15:00Z","run_id":"felix-admin-capture-20260401-0715","agent":"felix-admin-capture","autonomy_level":"assisted","category":"routine","action":"scan_inbox","target":"Inbox directory","outcome":"completed"}
   {"ts":"2026-04-01T11:15:01Z","run_id":"felix-admin-capture-20260401-0715","agent":"felix-admin-capture","autonomy_level":"assisted","category":"routine","action":"file_processed","target":"Inbox 2026-04-01 0630.md","outcome":"completed"}
   ```
   (Continue for all 8 actions in the original fixture)

   **capture-flagged.jsonl**: 5 routine + 1 flagged entry with category "flagged"
   **capture-error.jsonl**: 4 routine + 1 error entry with category "error"
   **capture-security.jsonl**: 2 routine + 1 security entry
   **habits-routine.jsonl**: 3 routine entries for felix-admin-habits
   **habits-mixed.jsonl**: 3 routine + 1 flagged for felix-admin-habits

2. Create 4 new fixtures:

   **multi-run.jsonl**: Two separate runs for the same agent on the same day
   (different run_ids, e.g., `felix-admin-capture-20260401-0715` and
   `felix-admin-capture-20260401-1215`). Tests multi-run consolidation.

   **verbose-trace.jsonl**: Entries with `context` and `trace` blocks populated.
   Includes confidence scores, api_calls, and clarification_asked fields.

   **malformed.jsonl**: Mix of valid lines, invalid JSON lines (`{broken`),
   lines missing required fields (`{"agent":"x"}`), and empty lines.

   **truncated-refs.jsonl**: Entries with `context.proposal_ref` cross-references
   and a string field that exceeds 120 chars (should already be truncated in the
   fixture since log_action.py enforces this at write time).

3. Each JSONL fixture must preserve the same agent name, categories, and action
   semantics as the original Markdown so existing test assertions remain valid.

**Files**: `scripts/openclaw/observation/tests/fixtures/*.jsonl` (10 new files)

**Validation**:
- [ ] Every line in every fixture is valid JSON
- [ ] 6 equivalents match original fixtures' agent names and category distributions
- [ ] 4 new fixtures cover: multi-run, verbose, malformed, truncated

---

## Subtask T012: Implement parse_jsonl_log()

**Purpose**: Replace `parse_log_file()` with a JSONL parser that returns
compatible data structures for the processing layer.

**Steps**:
1. Add `parse_jsonl_log(path)` function to `summarize.py`:
   ```python
   def parse_jsonl_log(path):
       """Parse a JSONL log file and return a list of action dicts.

       Each dict has at minimum: agent, run_id, category, action, target, outcome, ts.
       Invalid lines are logged to stderr and skipped.
       """
   ```
2. Read the file line by line
3. For each line: `json.loads(line.strip())`
4. Validate required fields present: `agent`, `category`, `action`, `target`, `outcome`
5. Map to processing-layer compatible dict:
   - `"category"` → `entry["category"]`
   - `"text"` → `f"{entry['action']}: {entry['target']}"` (or similar — must produce
     readable text for digest generation)
   - Preserve all other fields for pass-through
6. Return list of parsed action dicts
7. Group by run_id for multi-run consolidation in digest generation

**Compatibility note**: The existing processing layer expects `{"category": str, "text": str}`.
The new parser must return this shape. Additional fields (run_id, ts, context) are
preserved as extra keys — the processing layer ignores them.

**Files**: `scripts/openclaw/observation/summarize.py`

**Validation**:
- [ ] Returns list of dicts with at least `category` and `text` keys
- [ ] All valid lines parsed
- [ ] run_id preserved for multi-run grouping

---

## Subtask T013: Rewrite find_log_files()

**Purpose**: Current `find_log_files()` globs a flat directory for `*{date}*`.
New version must walk per-agent subdirectories.

**Steps**:
1. Replace `find_log_files(log_dir, target_date)`:
   ```python
   def find_log_files(log_dir, target_date):
       """Find JSONL log files for target_date across all agent subdirectories.

       Returns dict: {agent_name: Path} mapping agent names to their daily log files.
       """
   ```
2. Walk `log_dir` looking for subdirectories (each is an agent name)
3. In each subdirectory, look for `{target_date}.jsonl`
4. Return a dict mapping agent name to file path (not a flat list)
5. Skip non-directory entries in log_dir

**Files**: `scripts/openclaw/observation/summarize.py`

**Validation**:
- [ ] Finds files in per-agent subdirectories
- [ ] Returns dict keyed by agent name
- [ ] Ignores non-JSONL files and non-directory entries

---

## Subtask T014: Add Malformed Line Handling

**Purpose**: JSONL files may contain malformed lines (agent crash, partial write).
These must not crash the digest generation.

**Steps**:
1. In `parse_jsonl_log()`, wrap each line parse in try/except:
   - `json.JSONDecodeError`: log to stderr, skip line
   - Missing required fields: log to stderr, skip line
   - Empty lines: skip silently (no stderr)
2. Log format: `f"WARNING: Skipping malformed line {line_num} in {path}: {error}"`
3. Continue processing remaining lines
4. Return only valid entries

**Files**: `scripts/openclaw/observation/summarize.py`

**Validation**:
- [ ] Malformed JSON → stderr warning, line skipped
- [ ] Missing required field → stderr warning, line skipped
- [ ] Empty lines → silently skipped
- [ ] Valid lines after malformed lines are still processed

---

## Subtask T015: Update Digest Output Paths and Generation

**Purpose**: Change output from flat files at `00-System/agent-activity/` to
per-agent subdirectories at `Agent-Logs/`.

**Steps**:
1. In `run()`, update output path construction:
   - Overview: `{output_dir}/Agent-Logs/overview.md`
   - Per-agent: `{output_dir}/Agent-Logs/{agent_name}/{date}-log.md`
2. Create agent subdirectories under `Agent-Logs/` if they don't exist
3. Update `generate_digest()`: overview content unchanged, just path changes
4. Update `generate_agent_detail()`: content format unchanged, path changes to
   write into per-agent subdirectory
5. Update log reference paths in overview to point to new per-agent locations
6. Update `config.py` default `output_dir` to point to vault `notes/` path
   (currently `~/second-brain/notes/00-System/agent-activity/`, change to
   `~/second-brain/notes/`)

**Note**: The `Agent-Logs/` prefix is part of the output path, not a change to
`output_dir`. The config's `output_dir` points to the vault notes root; the
code constructs `Agent-Logs/` within it.

**Files**: `scripts/openclaw/observation/summarize.py`

**Validation**:
- [ ] overview.md written to `Agent-Logs/overview.md`
- [ ] Per-agent files in `Agent-Logs/{agent}/YYYY-MM-DD-log.md`
- [ ] Agent subdirectories created automatically
- [ ] Log reference paths in overview are correct

---

## Subtask T016: Implement Retention and Idempotency

**Purpose**: 5-day retention keeps digest directories clean. Idempotency
prevents unnecessary writes when agents are idle.

**Retention steps**:
1. After writing today's digest files, scan each agent subdirectory under `Agent-Logs/`
2. Parse date from each filename: `YYYY-MM-DD-log.md` → extract `YYYY-MM-DD`
3. If date is more than 5 calendar days before target_date: delete the file
4. Use date parsing, NOT filesystem mtime
5. overview.md is never subject to retention (always regenerated)

**Idempotency steps**:
1. Before processing each agent, check if new content exists since last digest:
   - Stat the agent's JSONL log file for mtime
   - Stat the agent's digest file for mtime
   - If JSONL mtime <= digest mtime: skip this agent (no new content)
2. If all agents are skipped, also skip overview.md regeneration
3. On first run (no existing digest file): always process

**Files**: `scripts/openclaw/observation/summarize.py`

**Validation**:
- [ ] Files older than 5 days deleted (by filename date)
- [ ] Files exactly 5 days old: kept
- [ ] Files 6+ days old: deleted
- [ ] No write when JSONL hasn't changed since last digest
- [ ] First run always writes (no existing digest to compare)

---

## Subtask T017: Update Tests and Remove Markdown Artifacts

**Purpose**: Update test_summarize.py to use JSONL fixtures and remove all
Markdown parsing artifacts.

**Steps**:
1. Update `TestLogParsing` class:
   - Change all fixture references from `.md` to `.jsonl`
   - Update `test_parse_single_log_file` → `test_parse_single_jsonl_log`
   - Update assertions to match new parse_jsonl_log() return format
   - Add test for multi-run JSONL (uses `multi-run.jsonl`)
   - Add test for verbose trace fields (uses `verbose-trace.jsonl`)
   - Add test for malformed line handling (uses `malformed.jsonl`)
   - Add test for truncated refs (uses `truncated-refs.jsonl`)

2. Update `TestDigestGeneration` class:
   - Update tests to use new output path structure (Agent-Logs/)
   - Add test for retention: create old-dated files, run, verify deleted
   - Add test for idempotency: run twice with no new content, verify no re-write

3. Remove from summarize.py:
   - `CATEGORY_PATTERN`, `AGENT_PATTERN`, `RUN_TIME_PATTERN`, `SUMMARY_LINE_PATTERN`
   - `parse_log_file()` function

4. Delete old Markdown fixture files (ONLY after all tests pass with JSONL):
   - `capture-routine.md`, `capture-flagged.md`, `capture-error.md`
   - `capture-security.md`, `habits-routine.md`, `habits-mixed.md`

**Files**: `scripts/openclaw/observation/tests/test_summarize.py`, `scripts/openclaw/observation/tests/fixtures/*.md` (deleted)

**Validation**:
- [ ] All existing test behavior preserved with JSONL fixtures
- [ ] New tests for multi-run, verbose, malformed, truncated
- [ ] Retention and idempotency tests pass
- [ ] No Markdown regex patterns remain in summarize.py
- [ ] No Markdown fixture files remain in tests/fixtures/
- [ ] Full suite: `pytest scripts/openclaw/observation/tests/ -v` exits 0

---

## Definition of Done

- [ ] parse_jsonl_log() replaces parse_log_file()
- [ ] find_log_files() walks per-agent subdirectories
- [ ] Malformed lines logged and skipped
- [ ] Output at Agent-Logs/ with per-agent subdirectories
- [ ] 5-day retention enforced (filename-based)
- [ ] Idempotent on no new content
- [ ] All 10 JSONL fixtures in place
- [ ] All tests pass against JSONL (no Markdown artifacts remain)
- [ ] `pytest scripts/openclaw/observation/tests/ -v` exits 0

## Risks

- **Processing layer compatibility**: parse_jsonl_log() must return dicts with
  `category` and `text` keys matching what filter_actions_by_autonomy() expects.
  Test this explicitly.
- **Fixture fidelity**: JSONL fixtures must reproduce the exact same category
  distributions as Markdown originals. Cross-reference research.md R3 for the mapping.
- **Retention edge case**: Files with unparseable date in filename should be left
  alone (logged to stderr, not deleted).

## Reviewer Guidance

1. Verify all 4 regex patterns removed from summarize.py
2. Verify parse_log_file() function removed
3. Check that processing layer functions (filter, detect, summarize) are unchanged
4. Confirm JSONL fixture content matches original Markdown semantics
5. Run full test suite — zero failures expected
6. Check that old output path code is removed (no references to `00-System/agent-activity/`)

## Activity Log

- 2026-04-04T15:35:20Z – gemini – shell_pid=92783 – Started implementation via workflow command
- 2026-04-04T15:54:08Z – gemini – shell_pid=92783 – All 7 subtasks done. 53/53 tests passing. JSONL parsing, new output paths, retention, idempotency, all fixtures replaced.
- 2026-04-04T15:54:15Z – claude – shell_pid=96073 – Started review via workflow command
- 2026-04-04T15:54:33Z – claude – shell_pid=96073 – Review passed: regex removed, JSONL parsing in place, Agent-Logs/ output, retention+idempotency tested, 53/53 tests, no MD artifacts remain
- 2026-04-04T16:52:27Z – claude – shell_pid=96073 – Merged to main, 72/72 tests passing
