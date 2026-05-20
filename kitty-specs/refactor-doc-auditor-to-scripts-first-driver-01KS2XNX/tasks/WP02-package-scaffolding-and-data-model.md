---
work_package_id: WP02
title: Package scaffolding and data model
dependencies: []
requirement_refs:
- FR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
- T009
- T010
phase: Phase 1 — Foundation
assignee: ''
agent: "codex:gpt-5:spec-kitty-review:reviewer"
shell_pid: "52371"
history:
- timestamp: '2026-05-20T16:25:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/doc_audit/
execution_mode: code_change
owned_files:
- scripts/doc_audit/__init__.py
- scripts/doc_audit/data_model.py
- scripts/doc_audit/config.py
- scripts/doc_audit/config.toml
- scripts/doc_audit/README.md
- tests/doc_audit/test_data_model.py
- tests/doc_audit/test_config.py
- tests/doc_audit/conftest.py
tags: []
---

# Work Package Prompt: WP02 — Package scaffolding and data model

## Objective

Stand up the `scripts/doc_audit/` Python package skeleton and implement the 10 entity dataclasses defined in `data-model.md` (E-001..E-010). Add a config layer that reads from `config.toml` and is overridable via `--config <path>`. Provide test fixtures + conftest that subsequent WPs can build on.

This is foundational — WP03/WP04/WP05/WP06 all import from `data_model.py` and `config.py`.

## Context

- All 10 entities are documented in `data-model.md`. This WP turns each into a Python `@dataclass` with appropriate field types and validators.
- The `EditTier` enum (E-005) is a `str, Enum` to support JSON serialization without custom encoders.
- The config layer holds: API key path, model name, prompts dir, cursor file path, activity log dir, tick signal path, and the list of enabled signal sources.
- Tests in this WP validate the schemas themselves; full data-model behavior validation happens in subsequent WPs.

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per lane; run `spec-kitty agent action implement WP02 --agent <name>`.

## Subtasks

### T006 — Create `scripts/doc_audit/` package scaffold

**Purpose**: Establish the package root with a placeholder `__init__.py` and an in-tree dev/test guide.

**Steps**:

1. Create `scripts/doc_audit/__init__.py`:
   ```python
   """felix-doc-auditor scripts-first driver (mission #343 / 01KS2XNX).

   Replaces the LLM-first procedural agent with a deterministic Python
   driver that calls an LLM only at narrow judgment moments. See
   kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/
   plan.md for the design and quickstart.md for operator usage.
   """

   __version__ = "0.1.0"
   ```

2. Create `scripts/doc_audit/README.md`:
   - Brief overview of the package's purpose
   - Pointer to `kitty-specs/.../plan.md` for design
   - Pointer to `kitty-specs/.../quickstart.md` for operator usage
   - Module map: `signals/`, `judgment/`, `routing/`, `output/`, `helpers/`, `prompts/`
   - "Running tests" section: `pytest tests/doc_audit/`

**Files**:
- New: `scripts/doc_audit/__init__.py` (~10 lines)
- New: `scripts/doc_audit/README.md` (~60 lines)

**Validation**:
- [ ] `python3 -c "import doc_audit; print(doc_audit.__version__)"` returns `0.1.0` (with `PYTHONPATH=scripts/`)
- [ ] README renders correctly in GitHub preview

---

### T007 — Implement `data_model.py` with all 10 entities

**Purpose**: Define the 10 dataclasses from `data-model.md` E-001..E-010 as a single module that subsequent WPs import.

**Steps**:

1. Create `scripts/doc_audit/data_model.py`. Import order: stdlib first, then external (none expected for this module).

2. Define the `EditTier` enum (E-005):
   ```python
   from enum import Enum

   class EditTier(str, Enum):
       TIER_A = "tier_a"
       TIER_B = "tier_b"
       JUDGMENT = "judgment"
   ```

3. Define `Signal` (E-001), `AuditIssue` (E-002), `PendingApproval` (E-003), `ProposedEdit` (E-004), `DebtIssue` (E-006), `DriftEvent` (E-007), `TickResult` (E-008), `TickSignal` (E-009), `ActivityLogEntry` (E-010) as `@dataclass(frozen=True)` where the spec indicates immutability and `@dataclass` (mutable) where the entity accumulates state (TickResult, AuditIssue).

4. Each dataclass MUST have:
   - A docstring referencing the data-model.md entity ID (e.g., `"""E-001 Signal — normalized input to the driver."""`)
   - Field types matching the data-model table exactly (use `str`, `int`, `bool`, `list[T]`, `dict[K, V]`, `Optional[T]`)
   - `from typing import Optional, Literal` as needed

5. Add module-level docstring noting the link to data-model.md.

**Files**:
- New: `scripts/doc_audit/data_model.py` (~250 lines)

**Validation**:
- [ ] `python3 -c "from doc_audit.data_model import Signal, AuditIssue, PendingApproval, ProposedEdit, EditTier, DebtIssue, DriftEvent, TickResult, TickSignal, ActivityLogEntry"` succeeds
- [ ] mypy / pyright reports no type errors on the module
- [ ] Each entity's docstring cites its data-model.md E-### ID

**Examples** (one entity for reference; pattern repeats):

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class Signal:
    """E-001 Signal — normalized input to the driver."""
    id: str
    source: str
    kind: str
    priority: int
    payload: dict
    created_utc: str
```

---

### T008 — Implement `config.py` + `config.toml`

**Purpose**: Centralize all driver configuration in one place. Operator-overridable via `--config <path>`.

**Steps**:

1. Create `scripts/doc_audit/config.toml` (default config):
   ```toml
   # Driver default configuration
   # Override with: python3 scripts/doc_audit/run.py --config <path>

   [llm]
   model = "claude-haiku-4-5"
   api_key_path = "/data/services/openclaw/secrets/anthropic"
   max_tokens = 2048

   [paths]
   prompts_dir = "scripts/doc_audit/prompts"
   drift_events = "/data/services/security-monitor/logs/drift-events.jsonl"
   drift_cursor = "/data/services/security-monitor/.drift-events.cursor"
   drift_unmapped = "/data/services/security-monitor/logs/unmapped-events.jsonl"
   signal_to_doc_map = "docs/design/architecture/data/signal-to-doc-map.json"
   doc_domain_map = "docs/design/architecture/data/doc-domain-map.json"
   activity_log_dir = "/home/kgale/second-brain/agents/logs"
   tick_signal_path = "/data/services/openclaw/felix-doc-auditor-driver/last-tick.json"

   [signals]
   sources = ["gh_issue", "drift_event"]  # adapter names; order = priority within priority group

   [github]
   repo = "kentonium3/kg-automation"
   bot_identity = "kg-felix-bot"
   ```

2. Create `scripts/doc_audit/config.py`:
   - Define `@dataclass` per [llm], [paths], [signals], [github] section
   - Define top-level `Config` aggregating these
   - Function `load_config(path: Path | None) -> Config`: defaults to `scripts/doc_audit/config.toml` if `path` is None. Uses `tomllib` (stdlib in Python 3.11+).
   - Validate that file paths in `[paths]` are absolute (raise on relative paths unless explicitly marked test-mode).
   - Function `read_api_key(config: Config) -> str`: reads the file at `config.llm.api_key_path`, strips whitespace, returns the key. NEVER logs the key.

**Files**:
- New: `scripts/doc_audit/config.toml` (~30 lines)
- New: `scripts/doc_audit/config.py` (~100 lines)

**Validation**:
- [ ] `from doc_audit.config import load_config, read_api_key; cfg = load_config(None)` returns a valid Config
- [ ] `load_config()` raises clear error on missing file
- [ ] `read_api_key(cfg)` returns the file's contents (test with a fixture file, NOT the real key)

---

### T009 — Conftest + fixtures for the test package

**Purpose**: Establish shared pytest infrastructure that subsequent WPs build on.

**Steps**:

1. Create `tests/doc_audit/conftest.py` with shared fixtures:
   - `tmp_config(tmp_path)` — creates a temp config.toml with paths pointed at `tmp_path` subdirectories; returns a `Config` instance
   - `mock_gh(monkeypatch)` — patches `subprocess.run` to return canned `gh` responses
   - `mock_anthropic(monkeypatch)` — patches `anthropic.Anthropic` client to return canned responses
   - `sample_audit_issue` — a representative `AuditIssue` instance (data-model E-002)
   - `sample_signal_gh_issue` — a representative `Signal` for a GH issue
   - `sample_signal_drift_event` — a representative `Signal` for a drift event

2. Create `tests/doc_audit/fixtures/` directory with:
   - `gh_responses/` — recorded `gh` JSON outputs for common queries
   - `anthropic_responses/` — canned LLM response shapes for each judgment moment
   - `drift_events_sample.jsonl` — already created in WP01, but referenced here

**Files**:
- New: `tests/doc_audit/conftest.py` (~150 lines)
- New: `tests/doc_audit/fixtures/gh_responses/` (directory with 5-10 JSON files)
- New: `tests/doc_audit/fixtures/anthropic_responses/` (directory with 3-5 JSON files)

**Validation**:
- [ ] `pytest tests/doc_audit/ --collect-only` collects the fixtures without errors
- [ ] Each fixture is callable from a downstream test without setup boilerplate

---

### T010 [P] — Unit tests for data-model entities

**Purpose**: Lock in the data-model entities' shape so subsequent code can rely on them.

**Steps**:

1. Create `tests/doc_audit/test_data_model.py`:
   - For each entity (E-001..E-010): one test that constructs a valid instance with all required fields.
   - For `Signal`: test priority ordering — pending_approval (10) < doc_audit (20) < weekly_doc_audit (30) < drift_event (40).
   - For `EditTier`: test enum values + string equality (`EditTier.TIER_A == "tier_a"`).
   - For `TickResult` / `TickSignal`: test that empty / full / partial outcomes can each be instantiated.
   - For dataclasses with invariants noted in data-model.md (e.g., `PendingApproval.is_self_apply` triggers gate violation): test that the invariant can be checked.

2. Create `tests/doc_audit/test_config.py`:
   - Test `load_config(None)` reads the default config
   - Test `load_config(tmp_path / "alt.toml")` reads an override
   - Test that relative path in `[paths]` raises ValueError
   - Test `read_api_key()` reads a fixture file and returns its content

**Files**:
- New: `tests/doc_audit/test_data_model.py` (~200 lines)
- New: `tests/doc_audit/test_config.py` (~80 lines)

**Validation**:
- [ ] `pytest tests/doc_audit/test_data_model.py -v` — all tests pass
- [ ] `pytest tests/doc_audit/test_config.py -v` — all tests pass
- [ ] Coverage of `data_model.py` ≥90%; `config.py` ≥85%

---

## Definition of Done

- [ ] Package importable as `from doc_audit import ...`
- [ ] All 10 entities (E-001..E-010) implemented as documented in `data-model.md`
- [ ] Config layer reads default `config.toml` and accepts override
- [ ] Conftest + fixtures available for downstream WPs
- [ ] Unit tests pass; coverage targets met

## Risks

| Risk | Mitigation |
|---|---|
| Entity shapes drift from `data-model.md` over the course of implementation | Each dataclass docstring cites its E-### ID; reviewers verify the mapping |
| Config schema is over-engineered before requirements are clear | Keep schema flat (TOML sections); add validation only where the spec demands it |
| Test fixtures get heavyweight and slow tests | Keep fixtures small (canned JSON, not live API recordings); avoid pytest-vcr or similar |

## Reviewer Guidance

- Cross-check each entity definition against `data-model.md` E-001..E-010
- Verify the EditTier enum uses `str, Enum` (for JSON serialization friendliness)
- Confirm `read_api_key()` does NOT log the key (search for `print`, `logger.info`, etc. in the function body)
- Confirm `load_config()` raises a clear error message for malformed TOML
- Tests should be fast (entire WP02 test run under 5 seconds)

## Implementation Command

```bash
spec-kitty agent action implement WP02 --agent <name>
```

## Cross-references

- **Data model**: `kitty-specs/.../data-model.md` E-001..E-010
- **Research**: D14 (Python package layout), D1 (API key path)
- **Spec**: FR-003 (stateless between ticks — data model is in-memory only)

## Activity Log

- 2026-05-20T17:43:08Z – claude:opus-4.7:implementer:implementer – shell_pid=47069 – Started implementation via action command
- 2026-05-20T17:50:15Z – claude:opus-4.7:implementer:implementer – shell_pid=47069 – Ready for review: doc_audit package scaffold + 10 entities (E-001..E-010) + config layer + extended conftest + 15 canned fixtures + 39 unit tests at 100% coverage on data_model.py and config.py
- 2026-05-20T17:50:51Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=50036 – Started review via action command
- 2026-05-20T17:53:57Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=50036 – Moved to planned
- 2026-05-20T17:54:02Z – claude:opus-4.7:implementer:implementer – shell_pid=50820 – Started implementation via action command
- 2026-05-20T18:00:35Z – claude:opus-4.7:implementer:implementer – shell_pid=50820 – Cycle 2: addressed both codex findings
- 2026-05-20T18:01:56Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=52371 – Started review via action command
- 2026-05-20T18:05:31Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=52371 – Review passed: package scaffold, data model, config layer, fixtures, and tests validated
