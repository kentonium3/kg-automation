---
work_package_id: WP01
title: Library core + schema documentation
dependencies: []
requirement_refs:
- C-001
- C-002
- C-003
- C-004
- C-005
- C-006
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
- FR-011
- FR-012
- FR-013
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-shared-jsonl-state-log-library-01KS0E9A
base_commit: 0d2e85a4e14c9939968ac09a0a2fe48b30f0c069
created_at: '2026-05-19T16:00:57.092379+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
shell_pid: "26952"
agent: "codex:gpt-5:python-reviewer:reviewer"
history:
- at: '2026-05-19T15:51:00Z'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/common/
execution_mode: code_change
mission_id: 01KS0E9A6TZBA9AWT97DR1XMQB
mission_slug: shared-jsonl-state-log-library-01KS0E9A
owned_files:
- scripts/common/**
- docs/design/architecture/data/agent-state-log-schema.md
- docs/INDEX.md
tags: []
---

# WP01 — Library core + schema documentation

## Objective

Build the production-ready Python library at `scripts/common/state_log.py` (plus `state_log_schema.py` sibling) and publish the formal schema documentation. This is the foundation for ADR-0002 Phases 3-7 — every Vikunja-touching agent will consume from this library. No agent code is modified in this WP.

## Context

- **Source issue**: [#305](https://github.com/kentonium3/kg-automation/issues/305)
- **Spec**: `kitty-specs/shared-jsonl-state-log-library-01KS0E9A/spec.md`
- **Plan**: `kitty-specs/shared-jsonl-state-log-library-01KS0E9A/plan.md`
- **Research / decisions**: `kitty-specs/shared-jsonl-state-log-library-01KS0E9A/research.md` (D1-D9)
- **Data model**: `kitty-specs/shared-jsonl-state-log-library-01KS0E9A/data-model.md`
- **API contract**: `kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/api.md`
- **CLI contract**: `kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/cli.md`
- **JSONL format contract**: `kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/jsonl.md`
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree allocated per the computed lane from `lanes.json` (set during finalize-tasks). The lane's branch is created off `main` and will merge back to `main` on approval.

## Subtasks

### T001 — Create `scripts/common/__init__.py`

**Purpose**: Make `scripts/common/` an importable Python package.

**Steps**:
1. Create the directory `scripts/common/` if it does not exist.
2. Create the empty file `scripts/common/__init__.py`.

**Validation**:
- [ ] `python3 -c "import scripts.common; print('ok')"` from repo root prints `ok` and exits 0.
- [ ] File exists at `scripts/common/__init__.py` and is empty (no docstring, no imports).

---

### T002 — Create `scripts/common/state_log_schema.py`

**Purpose**: Pure-data module exporting the schema constants and validators. No I/O. Importable independently of the file-handling module so consumer code that only needs to know "what states exist" doesn't pay for the I/O dependency.

**Steps**:

1. **Imports**: stdlib only — `dataclasses`, `datetime`, `re`, `typing`.

2. **Define `DOMAIN_STATES`**:
   ```python
   DOMAIN_STATES: dict[str, frozenset[str]] = {
       "habits": frozenset({"complete", "incomplete", "skipped"}),
       "escalation": frozenset({"triggered", "level-1", "level-2", "resolved", "dismissed"}),
       "enrichment": frozenset({"pending", "enriched", "deferred", "failed"}),
   }
   ```
   Use `frozenset` (not `set`) for immutability — caller cannot accidentally mutate.

3. **Define `REQUIRED_FIELDS`**:
   ```python
   REQUIRED_FIELDS: tuple[str, ...] = (
       "domain", "task_id", "title", "date", "state", "source", "timestamp",
   )
   ```
   `note` is optional; not in this tuple.

4. **Define dataclass `StateLogRecord`** (frozen, slots, all 8 fields). Matches the shape in `data-model.md`.

5. **Define `validate_record(record: dict, domain: str) -> None`**:
   - Raises `ValueError` on the FIRST violation (short-circuit; do not collect multiple errors).
   - Error messages quote the offending field name and value: e.g., `state 'Complet' not in habits enum {complete, incomplete, skipped}`.
   - Validation order:
     a. `domain` argument is a known domain (in `DOMAIN_STATES`).
     b. Each REQUIRED_FIELDS field is present in `record`.
     c. `record["domain"]` matches `domain` argument.
     d. `record["task_id"]` is `int` and `> 0`.
     e. `record["title"]` is non-empty `str` after `.strip()`.
     f. `record["date"]` matches `^\d{4}-\d{2}-\d{2}$` AND parses via `datetime.date.fromisoformat()`.
     g. `record["state"]` is in `DOMAIN_STATES[domain]`.
     h. `record["source"]` is non-empty `str`.
     i. `record["timestamp"]` parses via `datetime.datetime.fromisoformat()` AND has a `tzinfo` (timezone offset).
     j. If `note` is present, it MUST be `str` or explicitly `None` (use `if "note" in record:` to distinguish from omitted-vs-null).

**Files**:
- `scripts/common/state_log_schema.py` (new, ~120 lines)

**Validation**:
- [ ] Module imports without errors: `python3 -c "from scripts.common import state_log_schema; print(state_log_schema.DOMAIN_STATES)"` prints the three domains.
- [ ] `validate_record({}, "habits")` raises `ValueError` (missing required fields).
- [ ] A well-formed habits record passes `validate_record` without raising.

---

### T003 — Create `scripts/common/state_log.py` core

**Purpose**: The I/O layer. `append` and `read` plus their private helpers. Builds on `state_log_schema.py`.

**Steps**:

1. **Imports**: stdlib only — `json`, `fcntl`, `os`, `pathlib`, `typing`, plus the schema module.

2. **Module constants**:
   ```python
   STATE_DIR: Path = Path("/data/services/openclaw/state")
   STATE_FILE_MODE: int = 0o664
   STATE_DIR_MODE: int = 0o775
   ```
   **IMPORTANT**: `STATE_DIR` MUST be a module-level constant (not hardcoded inline) so tests can monkey-patch it to a temp dir. Document this in the module docstring.

3. **Re-export schema constants for convenience**:
   ```python
   from scripts.common.state_log_schema import DOMAIN_STATES, REQUIRED_FIELDS, validate_record
   ```

4. **Private helper `_state_file(domain: str) -> Path`**:
   Returns `STATE_DIR / f"{domain}-history.jsonl"`. Validates domain is known.

5. **Private helper `_ensure_dir() -> None`**:
   If `STATE_DIR` does not exist, create it via `STATE_DIR.mkdir(parents=True, mode=STATE_DIR_MODE, exist_ok=True)`. Best-effort `os.chown` to set group to `secondbrain` if available (silent on failure — group ownership is advisory).

6. **Private helper `_idempotency_match(file_path: Path, task_id: int, date: str, state: str) -> bool`**:
   - If file does not exist: return False.
   - Otherwise: iterate lines, parse each as JSON, compare `(task_id, date, state)` tuple. Return True on first match.
   - Tolerate malformed lines (skip silently — a partial last line from a crashed write doesn't poison the dedup).

7. **Public function `append(domain: str, record: dict) -> None`** — per `contracts/api.md`:
   - Validate via `validate_record(record, domain)` (raises ValueError).
   - `_ensure_dir()`.
   - Open the target file with `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, mode=STATE_FILE_MODE)`.
   - `fcntl.flock(fd, fcntl.LOCK_EX)` — held across the entire read-check-write.
   - Open the same file separately for reading (via `os.fdopen` or re-open read-only — fine because we hold the lock; reads see the same state).
   - Call `_idempotency_match`. If True: release lock, return without writing.
   - Otherwise: `os.write(fd, (json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n").encode("utf-8"))`.
   - Release lock + close FD.

8. **Public function `read(domain: str, **filters) -> list[dict]`** — per `contracts/api.md`:
   - Validate domain is known (raise ValueError otherwise).
   - Validate filter kwargs are in the allowed set: `{"task_id", "date", "date_from", "date_to", "state", "source"}` (raise TypeError otherwise).
   - If the target file does not exist: return `[]`.
   - Open with `os.open(path, os.O_RDONLY)`, acquire `fcntl.LOCK_SH`.
   - Read line by line, parse each as JSON, apply filters as AND-combined predicates. Skip malformed lines silently.
   - Release lock + close, return list (file-order).

9. **Public function `validate_record`** — re-exported from schema module.

**Files**:
- `scripts/common/state_log.py` (new, ~180 lines without CLI; ~240 with the CLI from T004)

**Module-level docstring**: 5-10 lines summarizing the contract + pointing to `kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/api.md`.

**Validation**:
- [ ] `python3 -c "from scripts.common.state_log import append, read, DOMAIN_STATES; print(DOMAIN_STATES['habits'])"` prints `frozenset({'complete', 'incomplete', 'skipped'})`.
- [ ] Manual smoke test with monkey-patched `STATE_DIR`: append a record, read it back, verify same dict.

---

### T004 — Add `__main__` CLI to `state_log.py`

**Purpose**: Provide a shell-callable surface (LLM agents using OpenClaw's Bash tool need this; consumer cron scripts may also use it). Per C-005, library must be safely callable as both module and CLI.

**Steps**:

1. Add an `if __name__ == "__main__":` block at the bottom of `state_log.py` calling a `main()` function.

2. Define `main(argv: list[str] | None = None) -> int` using `argparse`:
   - Top-level parser with `subparsers` (dest="subcommand").
   - `append` subparser: `--domain` (required, choices = list of DOMAIN_STATES keys). Reads JSON from stdin.
   - `read` subparser: `--domain` (required, same choices), plus optional `--task-id` (int), `--date`, `--date-from`, `--date-to`, `--state`, `--source` (all str).

3. `append` handler:
   - Read stdin via `sys.stdin.read().strip()`.
   - If empty: print usage error to stderr, return 3.
   - Parse as JSON; on JSONDecodeError: print error to stderr, return 3.
   - Call `append(args.domain, record)`.
   - On `ValueError`: print error to stderr, return 1.
   - On `OSError`: print error to stderr, return 2.
   - On success: return 0 (no stdout).

4. `read` handler:
   - Build filters dict from non-None args (filter out `subcommand`, `domain`).
   - Call `read(args.domain, **filters)`.
   - On `ValueError` / `TypeError`: print error to stderr, return 3.
   - On `OSError`: print error to stderr, return 2.
   - On success: print each record as JSON-on-its-own-line to stdout, return 0.

5. Help text matches `contracts/cli.md`.

**Files**:
- `scripts/common/state_log.py` (extend; CLI adds ~60 lines)

**Validation**:
- [ ] `python3 -m scripts.common.state_log --help` prints help.
- [ ] `python3 -m scripts.common.state_log append --help` shows the `--domain` choices.
- [ ] `echo '{}' | python3 -m scripts.common.state_log append --domain habits` exits 1 (validation failure).
- [ ] `python3 -m scripts.common.state_log read --domain habits` exits 0 with empty stdout (file doesn't exist yet on dev machine — that's the expected empty-list path).

---

### T005 — Create `docs/design/architecture/data/agent-state-log-schema.md`

**Purpose**: Public schema documentation per FR-012. Same content as `data-model.md` but framed as an architecture doc (not a planning artifact) so it's discoverable from the canonical docs tree.

**Steps**:

1. Required frontmatter:
   ```yaml
   ---
   title: Agent State Log Schema
   doc_type: reference
   status: approved
   audience: agents_and_humans
   level: reference
   owners: [kent]
   last_validated: '2026-05-19'
   ---
   ```

2. Sections:
   - **Purpose**: ~3-5 sentences. The canonical JSONL state log schema shared by all Vikunja-touching Felix agents per ADR-0002 Q5-C.
   - **File layout**: List the three files under `/data/services/openclaw/state/`, with modes and ownership.
   - **Record schema**: Field table identical to `data-model.md` § Field type contracts.
   - **Per-domain state enums**: Three tables (one per domain) with each state value's semantic meaning.
   - **Idempotency contract**: One paragraph — `(task_id, date, state)` is the dedup tuple per domain.
   - **Example records**: Copy 4-5 examples from `data-model.md`.
   - **Library reference**: Link to `scripts/common/state_log.py` and `contracts/api.md`.

3. Cross-link from this new file back to ADR-0002 and to the spec/plan in `kitty-specs/`.

**Files**:
- `docs/design/architecture/data/agent-state-log-schema.md` (new, ~180 lines)

**Validation**:
- [ ] `python3 tooling/scripts/validate_docs.py` passes (frontmatter valid).
- [ ] Manually open the file in a markdown viewer; verify all internal links resolve.

---

### T006 — Update `docs/INDEX.md` to reference the new schema doc

**Purpose**: Surface the new schema doc in the master documentation index per the kg-automation docs convention.

**Steps**:

1. Open `docs/INDEX.md`.
2. Find the section listing files under `docs/design/architecture/data/`.
3. Add a one-line entry: `agent-state-log-schema.md` with type annotation (reference) and a brief description (~10 words).
4. Preserve existing alphabetical / domain-grouped ordering.

**Files**:
- `docs/INDEX.md` (modify; ~1-2 lines added)

**Validation**:
- [ ] `python3 tooling/scripts/validate_docs.py` passes.
- [ ] Grep confirms the new entry: `grep "agent-state-log-schema" docs/INDEX.md`.

---

## Definition of Done

- [ ] All 6 subtasks T001-T006 complete and individually validated.
- [ ] `python3 -c "from scripts.common.state_log import append, read, validate_record, DOMAIN_STATES, REQUIRED_FIELDS"` succeeds — all public API surface is importable.
- [ ] `python3 -m scripts.common.state_log --help` exits 0 with reasonable help text.
- [ ] `python3 tooling/scripts/validate_docs.py` passes (no frontmatter regressions; new schema doc registers correctly).
- [ ] Manual smoke test with monkey-patched `STATE_DIR` to a tmp dir: append-then-read returns the same record.
- [ ] No new third-party dependencies introduced (NFR-004).
- [ ] No network imports in `scripts/common/` (C-004 — `grep -E 'import (urllib|http|socket|requests|httpx)' scripts/common/` returns nothing).
- [ ] All files committed by the spec-kitty workflow; no uncommitted artifacts.

## Risks & mitigations

- **fcntl behavior on macOS dev**: BSD `flock` shim works fine for advisory locking. Verified by WP02's concurrent test.
- **Mode-on-creation race**: `os.open` with explicit mode + umask handling — using the `mode=` arg avoids the chmod-after-open race.
- **Schema doc drift from code**: The dataclass + DOMAIN_STATES are the source of truth; the doc is a mirror. Future canary work (#327 / RFC) could detect drift programmatically.
- **`/data/services/openclaw/state/` doesn't exist on the dev mac**: `_ensure_dir` handles creation. Dev environment uses a tmp dir via monkey-patch (WP02 controls this).

## Reviewer guidance

- Check imports: must be stdlib only. Reject any `pip install` requirement.
- Check the `validate_record` short-circuit order against the spec's FR-005 contract. Each rejection case must name the field and value.
- Verify `STATE_DIR` is a module-level constant (importable + monkey-patchable from tests), not inlined.
- Check the CLI subcommands match `contracts/cli.md` exit codes exactly: 0/1/2/3.
- Check the docs render: `tooling/scripts/validate_docs.py` must pass, and the schema doc's frontmatter must be `audience: agents_and_humans` (this is a contract document, not a runbook).
- Spot-check the schema doc against `state_log_schema.py` to ensure enums and field types match precisely.

## Implementation command

```bash
spec-kitty agent action implement WP01 --agent <agent-name>
```

This will check out the WP01 worktree (per `lanes.json`), apply this prompt, and surface for review on completion.

## Activity Log

- 2026-05-19T16:00:59Z – claude:opus:implementer:implementer – shell_pid=24926 – Assigned agent via action command
- 2026-05-19T16:11:26Z – claude:opus:implementer:implementer – shell_pid=24926 – Ready for review — 6 subtasks T001-T006 complete; library + CLI + schema docs
- 2026-05-19T16:11:57Z – codex:gpt-5:python-reviewer:reviewer – shell_pid=26952 – Started review via action command
- 2026-05-19T16:15:03Z – codex:gpt-5:python-reviewer:reviewer – shell_pid=26952 – Review passed (Codex sandbox couldn't write status; orchestrator running on behalf): library core, CLI, schema docs, docs INDEX, imports, CLI exit codes, validate_docs, no network imports — all checks passed
