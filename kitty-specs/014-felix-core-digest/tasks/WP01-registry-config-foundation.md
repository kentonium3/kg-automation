---
work_package_id: WP01
title: Registry and Config Foundation
dependencies: []
requirement_refs:
- FR-18
- FR-19
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: f73d0f9e113765419412fd554796ff2723ebacb7
created_at: '2026-04-04T15:27:49.838690+00:00'
subtasks: [T001, T002, T003, T004]
shell_pid: '91203'
history:
- date: '2026-04-04'
  action: created
  by: spec-kitty.tasks
authoritative_surface: docs/constitution/
execution_mode: code_change
feature: 014-felix-core-digest
owned_files:
- docs/constitution/agent-registry.json
- scripts/openclaw/observation/config.py
- scripts/openclaw/observation/tests/test_config.py
---

# WP01: Registry and Config Foundation

## Branch Strategy

- **Planning/base branch**: `main`
- **Merge target**: `main`
- **Implementation command**: `spec-kitty implement WP01`
- No dependencies — this WP branches directly from `main`.

## Objective

Establish the agent registry and config infrastructure that both `log_action.py`
(WP02) and `summarize.py` (WP03) depend on. This WP:
1. Adds the missing `felix-admin-tasker` entry to `agent-registry.json`
2. Adds `log_verbosity` to all three agents
3. Exposes `log_verbosity()` in `config.py`
4. Writes tests for the new method

This is the foundation WP — everything else blocks on it.

## Context

### Current State of agent-registry.json

Located at `docs/constitution/agent-registry.json`. Currently contains only two agents:
- `felix-admin-capture` (F008, assisted)
- `felix-admin-habits` (F009, assisted)

`felix-admin-tasker` was deployed in F013 but was never added to the registry.

### Current Structure Per Agent

```json
{
  "team": "SuperAdmin (B)",
  "scope": "Description of responsibilities",
  "autonomy_level": "assisted",
  "deployed_feature": "F008",
  "registered": "2026-03-15",
  "transition_history": [
    {
      "date": "2026-03-15",
      "autonomy_level": "assisted",
      "direction": "registration",
      "reason": "Initial deployment",
      "decided_by": "Kent Gale"
    }
  ]
}
```

### config.py autonomy_level() Pattern

Located at `scripts/openclaw/observation/config.py`. The `autonomy_level()` method:
```python
def autonomy_level(self, agent_name):
    """Look up autonomy level for agent. Raises KeyError if not found."""
    try:
        return self._registry["agents"][agent_name]["autonomy_level"]
    except KeyError:
        registered = list(self._registry["agents"].keys())
        raise KeyError(
            f"Agent '{agent_name}' not found in registry. "
            f"Registered agents: {registered}"
        )
```

`log_verbosity()` must follow this exact pattern.

---

## Subtask T001: Add felix-admin-tasker to agent-registry.json

**Purpose**: The tasker agent is deployed on office2 but missing from the registry.
All three agents need registry entries for log_verbosity to work.

**Steps**:
1. Read `docs/constitution/agent-registry.json`
2. Add a `felix-admin-tasker` entry under `"agents"` with:
   - `"team"`: `"SuperAdmin (B)"`
   - `"scope"`: `"Task intelligence — enrichment proposals, retroactive enrichment, incomplete task detection"`
   - `"autonomy_level"`: `"assisted"`
   - `"deployed_feature"`: `"F013"`
   - `"registered"`: `"2026-04-04"`
   - `"transition_history"`: One entry with direction `"registration"`, date `"2026-04-04"`, decided_by `"Kent Gale"`, reason `"Added to registry during F014; was deployed in F013 but not registered"`
3. Update root-level `"updated"` to `"2026-04-04"` and `"updated_by"` to `"F014"`

**Files**: `docs/constitution/agent-registry.json`

**Validation**:
- [ ] Entry matches existing agent schema exactly
- [ ] JSON is valid (no trailing commas, correct structure)
- [ ] Root metadata updated

---

## Subtask T002: Add log_verbosity to All Agents

**Purpose**: Every agent needs a `log_verbosity` field so `log_action.py` can
read it at runtime.

**Steps**:
1. Add `"log_verbosity": "standard"` to each of the three agent entries:
   - `felix-admin-capture`
   - `felix-admin-habits`
   - `felix-admin-tasker` (just added in T001)
2. Place it after `autonomy_level` for consistency

**Files**: `docs/constitution/agent-registry.json`

**Validation**:
- [ ] All three agents have `log_verbosity: "standard"`
- [ ] No other fields changed

---

## Subtask T003: Implement log_verbosity() in config.py

**Purpose**: Expose verbosity lookup so `log_action.py` can determine which
blocks to write for each agent.

**Steps**:
1. Read `scripts/openclaw/observation/config.py`
2. Add a `log_verbosity(self, agent_name)` method to the `ObservationConfig` class
3. Follow the exact pattern of `autonomy_level()`:
   - Look up `self._registry["agents"][agent_name]["log_verbosity"]`
   - On KeyError, raise with helpful message listing registered agents
4. Default value: if the field is missing from an agent entry, return `"standard"`
   (graceful degradation for agents registered before F014)

**Files**: `scripts/openclaw/observation/config.py`

**Validation**:
- [ ] Method signature matches `autonomy_level()` pattern
- [ ] Returns "standard" for agents without explicit log_verbosity
- [ ] Raises KeyError for unregistered agents (same as autonomy_level)

---

## Subtask T004: Write Tests for log_verbosity()

**Purpose**: Test-first validation of the new config method.

**Steps**:
1. Create `scripts/openclaw/observation/tests/test_config.py` (new file)
2. Write test cases:
   - `test_log_verbosity_returns_standard_for_agent`: Verify returns "standard" for a registered agent with log_verbosity set
   - `test_log_verbosity_returns_brief`: Verify returns "brief" when explicitly set
   - `test_log_verbosity_returns_verbose`: Verify returns "verbose" when explicitly set
   - `test_log_verbosity_defaults_to_standard`: Verify returns "standard" when field is missing from agent entry
   - `test_log_verbosity_unknown_agent_raises_keyerror`: Verify KeyError for unregistered agent
3. Use the same test patterns as the existing TestConfig class in test_summarize.py:
   - Create temporary registry JSON files with pytest tmp_path
   - Instantiate ObservationConfig with the temp registry path
4. Import from the same module path as existing tests

**Files**: `scripts/openclaw/observation/tests/test_config.py` (new)

**Validation**:
- [ ] All 5 test cases pass
- [ ] Tests are isolated (use temp files, no side effects)
- [ ] Import structure matches existing test conventions

---

## Definition of Done

- [ ] agent-registry.json has all three agents with `log_verbosity: "standard"`
- [ ] config.py exposes `log_verbosity()` matching `autonomy_level()` pattern
- [ ] test_config.py passes all 5 test cases
- [ ] `pytest scripts/openclaw/observation/tests/test_config.py -v` exits 0
- [ ] No existing tests broken: `pytest scripts/openclaw/observation/tests/ -v` exits 0

## Risks

- **Registry schema mismatch**: Tasker entry must match capture/habits structure exactly. Read existing entries before writing.
- **Import path**: test_config.py must use the same import mechanism as test_summarize.py (check sys.path manipulation at top of existing test file).

## Reviewer Guidance

1. Verify tasker registry entry schema matches capture/habits entries
2. Verify log_verbosity() follows autonomy_level() pattern exactly
3. Confirm default behavior (missing field → "standard")
4. Run full test suite to confirm no regressions
