---
work_package_id: WP07
title: Live smoke and pre-rework baseline measurement
dependencies:
- WP06
requirement_refs:
- FR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T032
- T033
- T034
- T035
phase: Phase 4 — Verification
assignee: ''
agent: "codex:gpt-5:spec-kitty-review:reviewer"
shell_pid: "20967"
history:
- timestamp: '2026-05-20T16:25:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: tests/doc_audit/test_smoke_live.py
execution_mode: code_change
owned_files:
- tests/doc_audit/test_smoke_live.py
- docs/design/architecture/baselines/felix-doc-auditor-pre-rework.json
- docs/design/architecture/baselines/README.md
- scripts/doc_audit/baselines/**
tags: []
---

# Work Package Prompt: WP07 — Live smoke and pre-rework baseline measurement

## Objective

Write the live smoke test that hits real GitHub + real Anthropic API, and capture the pre-rework token-cost baseline against the existing openclaw-agent-mediated auditor. This produces the numerator for the NFR-001 ≥80% reduction acceptance gate.

## Context

- The live smoke test is the fidelity floor — it catches integration drift that mocked tests miss.
- The baseline measurement is the LAST chance to capture data from the existing openclaw-agent path before cutover (WP09) retires it forever.
- Measurement methodology must be REPEATABLE in 6 months (research D13 commitment). Document the method in the baseline file's `methodology` field.

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per lane; run `spec-kitty agent action implement WP07 --agent <name>`.

## Subtasks

### T032 — Write `tests/doc_audit/test_smoke_live.py`

**Purpose**: One integration test that exercises the full driver against live GH + live Anthropic.

**Steps**:

1. Create `tests/doc_audit/test_smoke_live.py`:

   ```python
   """Live smoke test for the doc-audit driver.

   Gated by pytest marker `live_smoke` — opt-in only.
   Run via: pytest -m live_smoke tests/doc_audit/test_smoke_live.py

   Requires:
   - Real GitHub credentials (gh CLI auth as kg-felix-bot)
   - Real Anthropic API key (at config.llm.api_key_path)
   - Network connectivity to api.anthropic.com and github.com

   Test pattern: run the driver against a known-empty queue (no audits at the
   start), assert exit code 0 + tick signal status=success. Then optionally
   file a single synthetic audit issue, run the driver again, assert outcome.
   """
   import pytest
   import subprocess
   from pathlib import Path

   pytestmark = pytest.mark.live_smoke

   def test_smoke_empty_queue():
       """Driver completes a tick against an empty queue end-to-end."""
       # Ensure no audit issues are open before the test
       result = subprocess.run(
           ["gh", "issue", "list", "--label", "Doc audit:", "--state", "open", "--json", "number"],
           capture_output=True, text=True, check=True
       )
       import json
       open_audits = json.loads(result.stdout)
       assert len(open_audits) == 0, f"Pre-condition: queue must be empty (found {len(open_audits)})"

       # Run the driver
       driver = subprocess.run(
           ["python3", "scripts/doc_audit/run.py"],
           capture_output=True, text=True
       )
       assert driver.returncode == 0, f"Driver failed: {driver.stderr}"

       # Read tick signal
       signal_path = Path("/data/services/openclaw/felix-doc-auditor-driver/last-tick.json")
       if not signal_path.exists():
           # If running outside office2, the path is different; consider env override
           pytest.skip(f"Tick signal path {signal_path} not present (test running off-office2?)")
       signal = json.loads(signal_path.read_text())
       assert signal["status"] == "success"
       assert signal["tick"]["signals_seen"] == 0

   def test_smoke_synthetic_audit(monkeypatch):
       """OPTIONAL: file a synthetic audit, run driver, verify processed cleanly.

       Marked separately so it can be skipped when the operator doesn't want
       to file test artifacts.
       """
       pytest.skip("Manual test — uncomment when filing synthetic audit acceptable")
       # Implementation pattern:
       # 1. File audit via felix-file-issue.py with synthetic title
       # 2. Run driver
       # 3. Verify audit closed cleanly + tick signal records the processing
       # 4. Clean up: ensure audit is closed (driver should have done this)
   ```

2. Register `live_smoke` marker in `pyproject.toml` or `pytest.ini`:
   ```ini
   [tool.pytest.ini_options]
   markers = [
       "live_smoke: live integration test requiring real credentials and network"
   ]
   ```

**Files**:
- New: `tests/doc_audit/test_smoke_live.py` (~150 lines)
- Modified: `pyproject.toml` or `pytest.ini` (marker registration)

**Validation**:
- [ ] `pytest tests/doc_audit/test_smoke_live.py` (no marker arg) skips the test by default
- [ ] `pytest -m live_smoke tests/doc_audit/test_smoke_live.py` runs and passes on office2 against an empty queue
- [ ] Test asserts pre-condition (empty queue) BEFORE running the driver

---

### T033 — Run pre-rework baseline measurement

**Purpose**: Capture per-tick token consumption from the EXISTING openclaw-agent auditor under representative conditions.

**Steps**:

1. **Identify "representative" ticks**:
   - 1 empty-queue tick
   - 1 debt-only audit tick (an audit that produces only debt issues)
   - 1 Tier-A apply tick (an audit that produces only a Tier-A frontmatter bump)

   If a Tier-A apply tick isn't naturally available, this is acceptable — record what was measurable and note the gap in the baseline file.

2. **Instrumentation approach**:
   - openclaw doesn't directly emit per-call token usage in its journal output
   - Option A: instrument inside the agent's session jsonl (read after each tick, use `anthropic.tokens.count` to estimate cumulative size)
   - Option B (preferred): inspect the agent's session jsonl directly — each tick appends user/assistant messages; sum token counts via SDK call
   - Option C: parse the openclaw journal for any token-usage hints

3. **Procedure**:
   - For each representative tick: capture the session jsonl delta (lines added during the tick) and feed to `anthropic.tokens.count` for an accurate count
   - Record: tick_outcome, input_tokens, output_tokens, duration
   - Repeat ≥3 times per outcome to get stable averages (across natural tick variation)

4. **Constraints**:
   - Do NOT alter the current auditor's behavior during measurement
   - Run measurements during normal operations; don't synthesize traffic
   - If naturally-occurring tick mix doesn't cover all 3 outcomes within a reasonable window (~3 days), record what's available and document the gap

**Files**: no committed files yet (intermediate data captured in workspace)

**Validation**:
- [ ] At least 1 measurement per outcome available
- [ ] Token counts are sanity-checked (input >> output; cache_read fields zero for the openclaw path which doesn't use caching)

---

### T034 — Write `baselines/felix-doc-auditor-pre-rework.json`

**Purpose**: Commit the baseline data to the repo for NFR-001 acceptance + future re-measurement.

**Steps**:

1. Create `docs/design/architecture/baselines/` directory.

2. Create `docs/design/architecture/baselines/README.md`:
   - One paragraph explaining the directory's purpose (capture measurement baselines for NFR acceptance gates)
   - Link to this mission (#343) and the mission of any future re-baselining

3. Create `docs/design/architecture/baselines/felix-doc-auditor-pre-rework.json`:

   ```json
   {
     "schema_version": "1.0",
     "name": "felix-doc-auditor-pre-rework",
     "captured_at": "2026-MM-DDTHH:MM:SSZ",
     "captured_by": "#343-WP07",
     "captured_via": "human operator running scripts/doc_audit/baselines/measure-pre-rework.sh on office2",
     "subject": {
       "service": "felix-doc-auditor",
       "host": "office2",
       "model": "anthropic/claude-haiku-4-5",
       "invocation": "openclaw agent --agent felix-doc-auditor ...",
       "git_sha": "<sha at time of measurement>"
     },
     "measurements": [
       {
         "outcome": "empty",
         "samples": [
           {"tick_id": "<session_id>", "input_tokens": ..., "output_tokens": ..., "duration_seconds": ...}
         ],
         "average_input_tokens": ...,
         "average_output_tokens": ...,
         "average_duration_seconds": ...
       },
       {"outcome": "debt_only", ...},
       {"outcome": "tier_a_apply", ...}
     ],
     "methodology": "<plain-prose description of how each sample was captured>",
     "open_caveats": [
       "<any outcome that couldn't be sampled and why>",
       "<any other caveats>"
     ]
   }
   ```

4. Set `updated_by` field in `signal-to-doc-map.json` and other affected JSON to include this mission's tag.

**Files**:
- New: `docs/design/architecture/baselines/README.md` (~30 lines)
- New: `docs/design/architecture/baselines/felix-doc-auditor-pre-rework.json` (~80 lines)

**Validation**:
- [ ] Baseline JSON parses; all fields present
- [ ] At least 1 outcome has at least 1 sample
- [ ] `methodology` field clearly explains how a future re-measurement would replicate it

---

### T035 — Document methodology

**Purpose**: Ensure NFR-001's "repeatable in 6 months" criterion is satisfied.

**Steps**:

1. In `felix-doc-auditor-pre-rework.json` `methodology` field, document:
   - Where to find the agent's session jsonl
   - How to extract per-tick deltas
   - How to call `anthropic.tokens.count` to convert text → token counts
   - Sample-size guidance (≥3 per outcome)

2. Add a brief script `scripts/doc_audit/baselines/measure-tokens.py` (helper for the post-rework measurement in WP09) that consumes a session jsonl + emits the per-tick token data in the same format. This script will be reused for the post-rework measurement.

3. Update `docs/design/architecture/baselines/README.md` to document this script.

**Files**:
- Modified: `docs/design/architecture/baselines/felix-doc-auditor-pre-rework.json` (methodology field)
- New: `scripts/doc_audit/baselines/measure-tokens.py` (~80 lines) — note this is under `scripts/doc_audit/`, not under `tests/`. Owned by this WP since the baseline measurement is its concern.
- Modified: `docs/design/architecture/baselines/README.md`

**Note on ownership**: This WP's `owned_files` includes `tests/doc_audit/test_smoke_live.py` and `docs/design/architecture/baselines/**`. The new helper script `scripts/doc_audit/baselines/measure-tokens.py` should be added to the owned_files list before committing — update the WP frontmatter accordingly.

**Validation**:
- [ ] Methodology section is self-contained — a future operator could follow it without other context
- [ ] `measure-tokens.py` runs cleanly against a session jsonl fixture
- [ ] README mentions the script

---

## Definition of Done

- [ ] Live smoke test exists, runs cleanly (when invoked with `-m live_smoke`)
- [ ] At least 1 sample per outcome captured in baseline JSON
- [ ] Baseline file committed to repo with full methodology
- [ ] `measure-tokens.py` helper exists for future re-measurement
- [ ] README in baselines/ explains the directory's purpose + reproduction steps

## Risks

| Risk | Mitigation |
|---|---|
| Live smoke perturbs production by filing test artifacts | Use ONLY empty-queue test by default; mark synthetic-audit test as skip-by-default |
| Baseline measurement only captures cheap ticks (empty), missing expensive ones | Run measurement over a 3-day window to catch natural variation; document any missing outcomes |
| Methodology field is too vague for future re-execution | Reviewer checks: could a stranger run the measurement in 6 months from the methodology field alone? |

## Reviewer Guidance

- Confirm live smoke test is gated by marker (default-skipped)
- Confirm baseline JSON schema matches what `measure-tokens.py` produces
- Spot-check the methodology field for completeness
- Verify the baselines/ directory is referenced from `docs/INDEX.md` OR captured as docs-debt if INDEX update is deferred

## Implementation Command

```bash
spec-kitty agent action implement WP07 --agent <name>
```

## Cross-references

- **Research**: D13 (Cost baseline methodology)
- **Spec**: NFR-001 (≥80% token reduction)
- **Future consumer**: WP09 uses this baseline + measure-tokens.py to verify the reduction post-cutover

## Activity Log

- 2026-05-21T13:21:22Z – claude:opus-4.7:implementer:implementer – shell_pid=16281 – Started implementation via action command
- 2026-05-21T13:32:50Z – claude:opus-4.7:implementer:implementer – shell_pid=16281 – Ready for review: live_smoke pytest marker registered + 2 smoke tests (skip-by-default); pre-rework baseline JSON with 3 outcomes (28 empty / 4 debt_only / 2 tier_a_apply) from 33h natural-traffic window; measure-tokens.py helper for repeatable measurement; README explains directory purpose and reproduction steps.
- 2026-05-21T13:34:11Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=18779 – Started review via action command
- 2026-05-21T13:38:28Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=18779 – Moved to planned
- 2026-05-21T13:38:34Z – claude:opus-4.7:implementer:implementer – shell_pid=19823 – Started implementation via action command
- 2026-05-21T13:43:50Z – claude:opus-4.7:implementer:implementer – shell_pid=19823 – Cycle 2: smoke skip-by-default exits 0; baselines linked from INDEX
- 2026-05-21T13:44:27Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=20967 – Started review via action command
