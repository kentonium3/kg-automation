# Contract — env-assumption checker + guard

## Module: `scripts/openclaw/agents/env_assumptions.py`

### Public API

```python
def scan_text(text: str, path: str = "<memory>") -> list[Finding]:
    """Pure: classify invocations in one prompt's text. Deterministic, no I/O."""

def scan_file(path: Path) -> list[Finding]:
    """Read path and scan_text its contents."""

def scan_agents_root(root: Path) -> list[Finding]:
    """Scan every AGENTS.md and AGENTS.md.tmpl under the agents root (excluding the
    retired felix-doc-auditor workspace, per validate_workspace.EXCLUDED)."""
```

`Finding` and `ViolationKind` per `data-model.md`.

### Determinism / purity (NFR-001)
- No network, no subprocess, no environment reads, no clock. Same bytes → same Findings.

### Waivers (SC-001)
- A line may be waived with an inline marker `# env-guard: waive <ViolationKind> — <reason>`
  on the same or preceding line. Waived lines are excluded from Findings but counted +
  reported so waivers are visible (not silent). Fixtures pin waiver parsing.

## Consumer 1: Test-CI guard — `scripts/openclaw/agents/tests/test_env_assumptions_guard.py`

- `test_fleet_has_no_env_assumptions()` — `scan_agents_root(DEFAULT_ROOT)` returns no
  non-waived Findings; on failure, asserts with a message enumerating each
  `path:line kind — remediation` (NFR-004).
- Unit tests — one per ViolationKind true-positive, one per canonical-form true-negative,
  the must-not-flag prose/comment/placeholder set (R-03), waiver parsing, and the two #656
  seed shapes (NFR-003).
- Runs in the existing Test CI (collected from `scripts/openclaw/agents/tests/`); no
  `.github/workflows/` change (C-001, FR-003).
- Budget: the fleet scan completes < 5 s (NFR-002).

## Consumer 2: Workspace validator fold — `validate_workspace.py`

```python
def check_runtime_env_assumptions(workspace_dir: Path) -> CheckResult:
    findings = [f for p in _prompt_files(workspace_dir) for f in scan_file(p)]
    return CheckResult(
        name="runtime_env_assumptions",
        passed=not findings,
        detail=("ok" if not findings
                else "; ".join(f"{f.path}:{f.line} {f.kind.value}" for f in findings)),
    )
```

- Appended to the `checks` list in `validate_workspace(workspace_dir)` alongside the
  existing `check_privacy_boundary` / `check_output_discipline` — same return contract,
  no regression to those checks (FR-004, SC-002).
- `validate_workspace.py --json` exit status reflects the new check (non-zero when any
  workspace fails).

## Non-goals
- The checker does NOT execute or lint the helper scripts themselves; it only inspects the
  invocation SHAPE in prompts.
- It does NOT modify prompts (conversion is IC-04's manual edit work).
