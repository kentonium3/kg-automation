---
work_package_id: WP03
title: Enforcement script — detection engine
dependencies:
- WP02
requirement_refs:
- FR-008
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T009
- T010
- T011
- T012
history:
- date: '2026-04-13'
  action: created
  agent: claude-opus-4-6
authoritative_surface: scripts/openclaw/enforcement/
execution_mode: code_change
owned_files:
- scripts/openclaw/enforcement/drift_check.py
- scripts/openclaw/enforcement/detection.py
- tests/openclaw/__init__.py
- tests/openclaw/enforcement/__init__.py
- tests/openclaw/enforcement/conftest.py
- tests/openclaw/enforcement/test_detection.py
tags: []
---

# WP03: Enforcement Script — Detection Engine

## Objective

Build the core drift detection engine: a Python module that loads baseline manifests, computes current hashes on both repo and office2, and classifies each file's drift state using three-way diff logic.

## Context

The enforcement script uses a **three-way diff** to implement "last author edits win":

```
For each tracked file:
  current_repo_hash = sha256(repo_file)
  current_office2_hash = sha256(office2_file)  # via SSH
  baseline_repo_hash = manifest[agent][file].repo_sha256
  baseline_office2_hash = manifest[agent][file].office2_sha256

  repo_changed = (current_repo_hash != baseline_repo_hash)
  office2_changed = (current_office2_hash != baseline_office2_hash)

  if not repo_changed and not office2_changed:
    → NO_CHANGE
  elif repo_changed and not office2_changed:
    → REPO_CHANGED (action: auto-deploy repo→office2)
  elif not repo_changed and office2_changed:
    → OFFICE2_CHANGED (action: auto-capture office2→repo)
  elif repo_changed and office2_changed:
    → CONFLICT (action: notify Kent)
```

Additionally, the script checks factory-default files: if a file's current hash diverges from the factory baseline hash, it has been customized and should be flagged for tracking.

## Branch Strategy

- Planning base branch: `main`
- Merge target branch: `main`
- Execution worktree: allocated by spec-kitty lane assignment per `lanes.json`

## Detailed Guidance

### T009: Create drift-check.py — CLI entry, manifest loading, hash computation

**Purpose**: Main entry point for the enforcement script. Handles CLI arguments, loads config and manifests, computes hashes.

**Steps**:
1. Create `scripts/openclaw/enforcement/drift_check.py` with:
   - `argparse` CLI with subcommands: `check` (detect drift), `report` (output-only, no action)
   - `--config` flag pointing to `drift-check-config.json` (default: relative path)
   - `--dry-run` flag to show what would happen without taking action
   - `--json` flag for machine-readable output

2. Manifest loading functions:
   ```python
   def load_manifest(path: str) -> dict:
       """Load baseline-manifest.json"""

   def load_factory_baselines(path: str) -> dict:
       """Load factory-baselines.json"""

   def load_config(path: str) -> dict:
       """Load drift-check-config.json"""
   ```

3. Hash computation:
   ```python
   def compute_local_hash(file_path: str) -> str | None:
       """SHA256 of a local file. Returns None if file missing."""

   def compute_remote_hash(ssh_host: str, file_path: str) -> str | None:
       """SHA256 of a remote file via SSH. Returns None if file missing."""
       # Use: ssh office2-claude 'sha256sum <path>'
       # Parse output to extract hash

   def compute_all_hashes(config: dict) -> dict:
       """For each agent and file, compute current repo and office2 hashes."""
       # Batch SSH commands where possible for performance
   ```

4. The SSH host should default to `office2-claude` (hardcoded or from config).

**Files**: `scripts/openclaw/enforcement/drift_check.py` (new, ~150 lines)

**Edge cases**:
- File exists in manifest but was deleted on one side → treat as drift (hash = None ≠ baseline hash)
- SSH command fails → log error, skip that file, continue with others
- Manifest file missing → exit with clear error message

### T010: Implement three-way diff logic

**Purpose**: Core classification engine. Compares current hashes against baseline to determine drift state and recommended action.

**Steps**:
1. Create `scripts/openclaw/enforcement/detection.py` with:
   ```python
   from enum import Enum
   from dataclasses import dataclass

   class DriftState(Enum):
       NO_CHANGE = "no_change"
       REPO_CHANGED = "repo_changed"        # Action: deploy repo→office2
       OFFICE2_CHANGED = "office2_changed"   # Action: capture office2→repo
       CONFLICT = "conflict"                  # Action: notify
       FILE_MISSING_REPO = "file_missing_repo"
       FILE_MISSING_OFFICE2 = "file_missing_office2"

   @dataclass
   class DriftResult:
       agent_id: str
       filename: str
       state: DriftState
       current_repo_hash: str | None
       current_office2_hash: str | None
       baseline_repo_hash: str | None
       baseline_office2_hash: str | None
       is_factory_default: bool

   def classify_drift(
       current_repo: str | None,
       current_office2: str | None,
       baseline_repo: str | None,
       baseline_office2: str | None,
   ) -> DriftState:
       """Three-way diff classification."""
   ```

2. The `classify_drift` function implements the decision matrix from the Context section above.

3. Add a top-level function that processes all agents and files:
   ```python
   def detect_all_drift(
       current_hashes: dict,
       manifest: dict,
       factory_baselines: dict,
   ) -> list[DriftResult]:
       """Classify drift state for every tracked file."""
   ```

**Files**: `scripts/openclaw/enforcement/detection.py` (new, ~100 lines)

### T011: Implement factory-default threshold detection

**Purpose**: Detect when a factory-default file gets customized (hash no longer matches any known factory baseline).

**Steps**:
1. Add to `detection.py`:
   ```python
   def is_factory_default(
       current_hash: str | None,
       filename: str,
       factory_baselines: dict,
   ) -> bool:
       """Check if a file's hash matches any known factory baseline."""
       baselines = factory_baselines.get("baselines", {}).get(filename)
       if baselines is None:
           return False
       if isinstance(baselines, str):
           return current_hash == baselines
       if isinstance(baselines, dict):
           return current_hash in baselines.values()
       return False
   ```

2. Integrate into `detect_all_drift`: set `is_factory_default` on each `DriftResult`.

3. A file that transitions from `is_factory_default=True` to `is_factory_default=False` means it was customized — the enforcement action depends on the drift state:
   - If `OFFICE2_CHANGED` + was factory default → this is a new customization event → auto-capture + file issue
   - If `NO_CHANGE` + still factory default → skip (untracked, no alert)

**Files**: `scripts/openclaw/enforcement/detection.py` (updated)

### T012: Write pytest tests for detection engine

**Purpose**: Test the three-way diff logic, factory-default detection, and hash computation edge cases.

**Steps**:
1. Create `tests/openclaw/enforcement/test_detection.py` with:
   - Test `classify_drift` for all 6 states (NO_CHANGE, REPO_CHANGED, OFFICE2_CHANGED, CONFLICT, FILE_MISSING_REPO, FILE_MISSING_OFFICE2)
   - Test `is_factory_default` with string baselines, dict baselines, missing baselines
   - Test `detect_all_drift` with a mock manifest and factory baselines

2. Create `tests/openclaw/enforcement/conftest.py` with fixtures:
   - `sample_manifest`: realistic manifest with 2-3 agents
   - `sample_factory_baselines`: known factory hashes
   - `sample_current_hashes`: various drift scenarios

3. Create `tests/openclaw/__init__.py` and `tests/openclaw/enforcement/__init__.py` for package structure.

**Files**:
- `tests/openclaw/enforcement/test_detection.py` (new)
- `tests/openclaw/enforcement/conftest.py` (new)
- `tests/openclaw/__init__.py` (new, empty)
- `tests/openclaw/enforcement/__init__.py` (new, empty)

**Validation**:
- [ ] All 6 drift states tested with explicit assertions
- [ ] Factory-default detection covers string, dict, and missing cases
- [ ] Edge case: None hashes (missing files) handled correctly
- [ ] `pytest tests/openclaw/enforcement/ -v` passes

## Definition of Done

- [ ] `drift_check.py` loads config, manifest, and factory baselines without error
- [ ] `detection.py` correctly classifies all drift states via three-way diff
- [ ] Factory-default detection works for all baseline formats
- [ ] `drift_check.py check --dry-run --json` produces correct drift report for current state
- [ ] All pytest tests pass
- [ ] No SSH calls required for unit tests (mocked)

## Risks

- **SSH batching for performance**: Computing 25 hashes via individual SSH calls is slow. Consider batching: `ssh office2-claude 'for f in <list>; do sha256sum "$f"; done'`.
- **Hash format differences**: `sha256sum` (Linux) outputs `<hash>  <path>`, `shasum -a 256` (Mac) outputs `<hash>  <path>`. Parse carefully.

## Reviewer Guidance

- Verify the `classify_drift` function handles all 4 quadrants of the decision matrix correctly
- Check that `None` hash (missing file) is treated as a change from baseline
- Ensure tests cover the factory-default transition case (was default, now customized)
- Confirm no SSH calls leak into unit tests
