---
work_package_id: WP03
title: Architectural test ratchet
dependencies:
- WP02
requirement_refs:
- FR-004
- NFR-002
- NFR-003
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T012
- T013
- T014
- T015
- T016
agent: claude
history:
- at: '2026-06-15T02:33:00Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: tests/architectural/test_habits_history_canonical_read.py
create_intent:
- tests/architectural/test_habits_history_canonical_read.py
execution_mode: code_change
owned_files:
- tests/architectural/test_habits_history_canonical_read.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, load your assigned agent profile via `/ad-hoc-profile-load implementer-ivan` (or the equivalent profile loader in your harness).

## Objective

Add the architectural test ratchet that fails the build if any script under `scripts/habits/*.py` imports `VikunjaClient` for completion-history queries. Current-state queries remain permitted via an explicit file-level allowlist declared inside the test module. This prevents the #605 bug class from silently recurring six months from now when someone writes the trend-analysis helper.

## Context

WP02 routes the weekly helper's completion-history reads through the canonical `habits-history.jsonl` store. Without an architectural ratchet, nothing prevents a future contributor from reaching back into Vikunja `done_at` because "it seemed like the obvious place." The ratchet makes the policy executable.

The pattern follows the spec-kitty upstream convention used in `tests/architectural/test_guard_capability_call_sites.py`: an allowlist declared in the test file, AST-walked over the affected directory.

Read before starting:

- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/spec.md` (FR-004)
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/plan.md` (IC-03)
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/contracts/architectural_test.md` (the test contract you implement)
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/data-model.md` (E-04 allowlist shape)
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/research.md` (R-03 design rationale)
- Existing habits scripts under `scripts/habits/*.py` — needed to populate the allowlist accurately

## Subtasks

### T012 — Create the test module

File: `tests/architectural/test_habits_history_canonical_read.py` (NEW).

Standard pytest module — no special markers, no fixture infrastructure beyond `pathlib.Path`. Module-level docstring should explain:
- What the test guards (completion-history reads must go through `habits-history.jsonl`)
- Why (link to mission slug `trustworthy-weekly-habit-report-01KV4GZ7` and issue #605)
- How to add to the allowlist (edit `VIKUNJA_CURRENT_STATE_ALLOWLIST` with a one-line reason comment)

### T013 — AST scanner

Implement the AST scanner as a module-level function or class:

```python
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HABITS_DIR = REPO_ROOT / "scripts" / "habits"


def _find_vikunja_client_imports(source: str) -> list[tuple[int, str]]:
    """Return [(lineno, source_line), ...] for any import of VikunjaClient."""
    tree = ast.parse(source)
    hits: list[tuple[int, str]] = []
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "scripts.common.vikunja_client":
                for alias in node.names:
                    if alias.name == "VikunjaClient":
                        hits.append((node.lineno, lines[node.lineno - 1]))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "scripts.common.vikunja_client":
                    # `import scripts.common.vikunja_client` — they could still
                    # access VikunjaClient via attribute; flag it.
                    hits.append((node.lineno, lines[node.lineno - 1]))
    return hits
```

Handle these forms:
- `from scripts.common.vikunja_client import VikunjaClient`
- `from scripts.common.vikunja_client import VikunjaError, VikunjaClient`
- `from scripts.common.vikunja_client import VikunjaClient as VC`
- `import scripts.common.vikunja_client`
- `import scripts.common.vikunja_client as vc`

### T014 — Allowlist declaration

Add at module level:

```python
#: Habits scripts allowed to import VikunjaClient because their use is
#: current-state only (NOT completion history). Each entry MUST carry a
#: one-line reason comment. Adding a new entry is a code-review decision.
VIKUNJA_CURRENT_STATE_ALLOWLIST: frozenset[str] = frozenset({
    "query_active_habits_v2.py",         # current-state: "what habits are due today" list
    "exclude_completed_v2.py",           # current-state: today's already-completed check
    "morning_checkin_list.py",           # invokes query_active_habits_v2; same domain
    "record_completion.py",              # writes completion to Vikunja current state
    "sweeper.py",                        # current-state sweeper for missed day-specific habits
    "set_due_dates.py",                  # current-state mutation
    "identify_workout_task.py",          # current-state query for the day's workout task
    "backfill_jsonl_from_comments.py",   # one-time backfill READS Vikunja COMMENTS (not done_at)
    "query_active_habits_weekly.py",     # current-state ONLY: titles + repeat_after classification
})
```

**Pre-flight**: before committing the allowlist, run `ls scripts/habits/*.py` and verify every file you're allowlisting actually exists. Files that don't import VikunjaClient at all (e.g. `compute_today.py`, the WP01 wrapper `history.py`) MUST NOT be in the allowlist — the scanner will pass them anyway because there's nothing to flag.

### T015 — [P] Negative-control test

```python
def test_scanner_fires_on_unallowed_import(tmp_path: Path) -> None:
    """Prove the scanner detects an offending import.

    Constructs a temp file with the canonical VikunjaClient import line and
    asserts the scanner reports (lineno, source_line) for it.
    """
    bad_source = (
        "from scripts.common.vikunja_client import VikunjaClient\n"
        "\n"
        "def use():\n"
        "    return VikunjaClient()\n"
    )
    hits = _find_vikunja_client_imports(bad_source)
    assert hits == [(1, "from scripts.common.vikunja_client import VikunjaClient")]
```

Covers each import form (parametrize via `@pytest.mark.parametrize` to assert detection for all five shapes from T013).

### T016 — [P] Allowlist-sanity test

```python
def test_allowlist_contains_no_stale_entries() -> None:
    """Each allowlist entry must correspond to a real file under scripts/habits/."""
    missing = [
        name for name in VIKUNJA_CURRENT_STATE_ALLOWLIST
        if not (HABITS_DIR / name).is_file()
    ]
    assert not missing, (
        f"Allowlist entries point at non-existent files: {missing}. "
        "Remove stale entries from VIKUNJA_CURRENT_STATE_ALLOWLIST."
    )
```

This catches the case where a habits script is deleted but the allowlist isn't updated — the test fails on the next CI run instead of leaving silent dead entries.

### Main scan test

```python
def test_no_completion_history_reads_through_vikunja() -> None:
    """Fail if any non-allowlisted scripts/habits/*.py imports VikunjaClient."""
    violations: list[str] = []
    for path in sorted(HABITS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        if path.name in VIKUNJA_CURRENT_STATE_ALLOWLIST:
            continue
        source = path.read_text(encoding="utf-8")
        for lineno, line in _find_vikunja_client_imports(source):
            violations.append(
                f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()} — "
                "VikunjaClient import not allowlisted; completion history must "
                "read habits-history.jsonl via scripts/habits/history.py"
            )
    assert not violations, "\n".join(violations)
```

This is the main scan that delivers FR-004.

## Branch strategy

- Planning base branch: `main`
- Merge target branch: `main`
- This WP lands on its computed lane worktree.
- Depends on WP02 (the allowlist correctness depends on WP02 having removed `done_at` from `query_active_habits_weekly.py`).

## Test strategy

Tests ARE the deliverable here. Run with `pytest tests/architectural/test_habits_history_canonical_read.py -v` — all three tests (main scan, negative control, allowlist sanity) green.

NFR-002: standalone runtime under 5 seconds. AST parsing is sub-millisecond per file; 10 files = ~10ms total.

NFR-003: failure messages name the specific file and line of the violation, formatted as `<path>:<lineno>: <import line>`.

## Definition of Done

- [ ] `tests/architectural/test_habits_history_canonical_read.py` exists with main scan, negative control, and allowlist sanity tests.
- [ ] All three tests pass with the current repo state (assuming WP02 has removed `done_at` from `query_active_habits_weekly.py`).
- [ ] Negative-control test asserts detection for all five `VikunjaClient` import forms.
- [ ] Allowlist contains exactly the existing habits scripts that legitimately need current-state Vikunja access (no aspirational entries; no stale entries).
- [ ] Module docstring explains intent, links to mission slug and issue #605.
- [ ] Failure messages format as `<path>:<lineno>: <import line>`.
- [ ] Test completes in under 5 seconds standalone.

## Risks

- **Forms of import we missed**: indirect access via `importlib.import_module("scripts.common.vikunja_client")` would slip past AST detection. Acceptable — that's an obscure pattern; the architectural test is not meant to be a sealed proof, just a tripwire for the obvious case. Document the limitation in the module docstring.
- **Allowlist staleness**: the allowlist-sanity test (T016) catches removed-file cases. For the harder "file still exists but no longer needs current-state access" case, reviewers handle it during code review of allowlist changes.
- **False positives during WP02 development**: if you implement WP03 BEFORE WP02 removes `done_at`, the test will pass because `query_active_habits_weekly.py` is on the allowlist (it still imports VikunjaClient legitimately, even pre-WP02). The test doesn't enforce that `done_at` isn't being read — only that history isn't being read through VikunjaClient. This is fine; WP02's tests catch the `done_at` regression.

## Reviewer guidance

Reviewers verify:

1. The main scan asserts on the actual repo state — not on a mocked or temp directory. The scanner walks `scripts/habits/*.py` from the repo root.
2. The negative-control test covers all import variants.
3. The allowlist is justified: each entry has a one-line reason comment.
4. No entry is in the allowlist that doesn't actually import VikunjaClient — adding such entries makes the allowlist meaningless.
5. Failure messages are actionable (file:line format).

If the reviewer believes the allowlist is too permissive (e.g., a file in the allowlist actually shouldn't need VikunjaClient at all), file a follow-up issue rather than tightening as part of this WP.

## Implementation command

```bash
spec-kitty agent action implement WP03 --agent claude
```
