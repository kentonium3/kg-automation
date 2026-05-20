---
work_package_id: WP06
title: Driver entrypoint and integration tests
dependencies:
- WP03
- WP04
- WP05
requirement_refs:
- FR-001
- FR-003
- FR-004
- FR-008
- FR-014
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T026
- T027
- T028
- T029
- T030
- T031
phase: Phase 3 — Integration
assignee: ''
agent: ''
history:
- timestamp: '2026-05-20T16:25:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/doc_audit/run.py
execution_mode: code_change
owned_files:
- scripts/doc_audit/run.py
- tests/doc_audit/test_integration_tick_outcomes.py
- tests/doc_audit/test_integration_edge_cases.py
tags: []
---

# Work Package Prompt: WP06 — Driver entrypoint and integration tests

## Objective

Implement `scripts/doc_audit/run.py` as the CLI entry point. Wire the orchestration loop: pending-approvals first, then new audits, then drift events. Add stuck-lock recovery and edge-case handling. Cover the result with integration tests for all 5 tick outcomes and the 4 documented edge cases.

This is the WP where everything comes together. WP03/WP04/WP05 are independent components; WP06 composes them into a working driver.

## Context

- Per `contracts/driver-invocation.contract.md`: single oneshot entry, exit codes 0/1/2, CLI args `--dry-run / --once / --source / --config / --version`.
- Per spec FR-004: full queue per tick. Per Q3=B (confirmed): the driver processes ALL pending signals each tick.
- Per `contracts/signal-source.contract.md`: pending-approvals (priority 10) processed before new audits (priority 20+) before drift events (priority 40).
- Per spec FR-014: stuck `status:in-progress` locks from prior crashed ticks must be recoverable without operator intervention.
- The 5 tick outcomes covered by integration tests: empty queue, debt-only audit, Tier-A auto-commit, pending-approval-apply, pending-approval-reject.
- The 4 edge cases: LLM API outage, GitHub rate limit, audit references missing file, stuck lock recovery.

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per lane; run `spec-kitty agent action implement WP06 --agent <name>`.

## Subtasks

### T026 — Implement `scripts/doc_audit/run.py` CLI

**Purpose**: The top-level executable that systemd invokes.

**Steps**:

1. Create `scripts/doc_audit/run.py` with executable shebang (`#!/usr/bin/env python3`) and `chmod +x`.

2. Implement argparse per `contracts/driver-invocation.contract.md`:
   - `--dry-run`
   - `--once` (default)
   - `--source <name>` (gh_issue or drift_event)
   - `--config <path>`
   - `--version`
   - `--help`

3. Structure:
   ```python
   #!/usr/bin/env python3
   """felix-doc-auditor scripts-first driver — main entry point."""
   import argparse
   import sys
   from datetime import datetime, timezone
   from pathlib import Path

   from doc_audit.config import load_config
   from doc_audit.signals.gh_issue import GHIssueSignalSource
   from doc_audit.signals.drift_event import DriftEventSignalSource
   from doc_audit.judgment.client import JudgmentClient
   from doc_audit.output.tick_signal import write_tick_signal, print_summary_line
   from doc_audit.output.activity_log import append_entry
   from doc_audit.data_model import TickResult

   __version__ = "0.1.0"

   def main(argv: list[str] | None = None) -> int:
       args = _parse_args(argv)
       if args.version:
           print(__version__)
           return 0

       config = load_config(args.config)
       result = TickResult(
           started_utc=_now_iso(),
           ended_utc="",  # filled at end
           status="success",
           signals_seen=0,
           signals_processed=0,
           tier_a_commits=[],
           pending_approvals_filed=[],
           pending_approvals_applied=[],
           debt_filed=[],
           drift_events_consumed=0,
           errors=[],
           judgment_calls={},
           token_usage={"input_tokens": 0, "cache_hit_input_tokens": 0, "output_tokens": 0},
       )

       try:
           _run_tick(config, args, result)
       except Exception as e:
           result.errors.append(f"Unhandled exception: {type(e).__name__}: {e}")
           result.status = "failure"
       finally:
           result.ended_utc = _now_iso()
           # Always write the tick signal + activity log entry, even on crash.
           try:
               write_tick_signal(config, result, _compute_next_tick())
               append_entry(config, result)
           except Exception as e:
               print(f"FATAL: tick signal/log write failed: {e}", file=sys.stderr)
               # Still return the appropriate exit code
           print_summary_line(result)

       return {"success": 0, "partial": 2, "failure": 1}[result.status]

   def _run_tick(config: Config, args, result: TickResult) -> None:
       """The orchestration loop. Implemented in T027."""
       ...

   def _parse_args(argv): ...
   def _now_iso(): ...
   def _compute_next_tick(): ...

   if __name__ == "__main__":
       sys.exit(main())
   ```

4. Add module-level docstring referencing `contracts/driver-invocation.contract.md`.

**Files**:
- New: `scripts/doc_audit/run.py` (~200 lines combined with T027/T028/T029)

**Validation**:
- [ ] `python3 scripts/doc_audit/run.py --version` prints version
- [ ] `python3 scripts/doc_audit/run.py --help` prints help with all documented args
- [ ] `python3 scripts/doc_audit/run.py --dry-run` exits 0 against an empty queue (mocked)
- [ ] Top-level try/finally ensures tick signal + log always written

---

### T027 — Implement orchestration loop

**Purpose**: The `_run_tick()` function that drives pending → new audits → drift events.

**Steps**:

**Critical ordering note** (per research D9 + FR-004): drift events are processed FIRST so that any GH issues they file (via `handle_drift_events.file_doc_audit_issue`) are picked up in the SAME tick's GH-issue scan. This is by design — drift detection at 03:00 UTC fires before the next hourly tick, so within one tick we want: process drift events → file resulting GH issues → enumerate the now-fresh GH queue → process pending-approvals (priority 10) BEFORE new audits (priority 20+) per FR-004 + signal-source contract.

The "drift-events first" ordering does NOT contradict FR-004's "pending-approvals first" — FR-004 governs ordering WITHIN the GH-issue scan, drift processing happens upstream of that scan.

1. Inside `_run_tick(config, args, result)`:

   ```python
   def _run_tick(config, args, result):
       # Step 1: Build signal sources (or restrict via --source)
       sources = _build_sources(config, args)

       # Step 2: Drift-event processing first (before GH-issue scan)
       # per research D9 ordering. Files GH issues for mapped drift events;
       # those issues are picked up in step 4 below within the same tick.
       drift_source = next((s for s in sources if s.name == "drift_event"), None)
       if drift_source:
           _process_drift_events(drift_source, config, result)

       # Step 3: Build GH-issue source (which now sees any drift-derived issues filed in step 2)
       gh_source = next((s for s in sources if s.name == "gh_issue"), None)
       if not gh_source:
           return

       # Step 4: Process the FULL queue in priority order per FR-004 + Q3=B
       # Sort key: (priority, created_utc) — pending-approval (10) before doc_audit (20)
       # before weekly_doc_audit (30). Drift events (priority 40) are NOT in this queue;
       # they were handled in step 2.
       signals = gh_source.pending()
       signals.sort(key=lambda s: (s.priority, s.created_utc))
       result.signals_seen = len(signals)

       judgment_client = JudgmentClient(config)
       rate_limited = False

       for signal in signals:
           if rate_limited:
               # Stop processing remaining signals once we hit rate-limit (T029).
               # Unprocessed signals remain in the queue for the next tick.
               break
           try:
               outcome = _process_signal(signal, gh_source, judgment_client, config, args, result)
               gh_source.commit(signal, outcome)
               result.signals_processed += 1
           except RateLimitError as e:
               # GitHub or Anthropic rate-limit: short-circuit the rest of the tick.
               result.errors.append(f"Rate-limited on {signal.id}: {e}")
               result.status = "failure"
               rate_limited = True
           except Exception as e:
               # Any other per-signal failure: log + continue with the next signal.
               result.errors.append(f"Signal {signal.id} failed: {type(e).__name__}: {e}")
               result.status = "partial"

       # Final status
       if result.errors and result.signals_processed == 0:
           result.status = "failure"
   ```

   Define `RateLimitError` near the top of `run.py` as a thin wrapper exception that `signals/gh_issue.py` and `routing/apply_decisions.py` raise when they detect 403 + rate-limit headers in the underlying `subprocess.CompletedProcess`.

2. `_process_signal(signal, source, judgment_client, config, args, result)` dispatches based on `signal.kind`:
   - `pending_approval` → apply decision via routing layer
   - `doc_audit` / `weekly_doc_audit` → run audit workflow (read issue, classify edits, file debt, route)
   - (drift events handled in step 2 of `_run_tick`)

3. For `pending_approval`:
   - Verify actor (SKILL.md §8.6 actor-verification check)
   - If self-apply: log gate violation, remove decision label, exit
   - Otherwise: invoke `routing.apply_decisions.apply()` with appropriate state

4. For `doc_audit` / `weekly_doc_audit`:
   - Acquire lock (add `status:in-progress` label)
   - Read in-scope docs (domain-map intersection)
   - For each candidate edit: call `tier_classification` LLM → dispatch by tier
   - Run missing-artifact detection (deterministic per SKILL.md §6)
   - Call `cross_file_implication` LLM for non-touched docs
   - Compose debt-issue bodies via `debt_body_generation` LLM (for each judgment finding)
   - Invoke routing layer to file pending-approval / debt + close audit

**Files**:
- Modified: `scripts/doc_audit/run.py` (orchestration logic appended; ~150 more lines)

**Validation**:
- [ ] Priority ordering: pending-approval (10) processed before doc_audit (20)
- [ ] Empty queue → result.status="success", no errors
- [ ] Single signal failure → result.status="partial", other signals still processed
- [ ] All signals fail → result.status="failure"

---

### T028 — Implement stuck-lock recovery (FR-014)

**Purpose**: Handle audit issues left with `status:in-progress` by a prior crashed tick.

**Steps**:

1. In `GHIssueSignalSource._fetch_doc_audits()` (from WP03), modify the "skip in-progress" behavior:
   - **What's a "referenced pending-approval"?** Per SKILL.md §3 step 9, when an audit produces Tier-B proposals, the agent files an `audit-pending-approval` issue and posts a comment on the originating audit: `"Pending review at #<new>"`. The cross-reference pattern is:
     - **Forward link**: the pending-approval issue's body contains `"Refs #<audit-issue-number>"` AND/OR its title is formatted as `"Audit #<N>: pending approval — ..."`.
     - **Back link**: the audit issue has a comment from `kg-felix-bot` containing `"Pending review at #<new>"`.
     - **Use both checks**: query `gh issue list --label "audit-pending-approval" --state open --json number,title,body`, then for each result, parse the title for `Audit #N` regex and the body for `Refs #N` to build the audit-number → pending-approval-number map.
   - If the in-progress audit has a matching `audit-pending-approval` issue (open, with OR without a decision label) → it's the expected Level-1 wait state (or post-decision processing pending). **Skip — NOT stuck.**
   - If the in-progress audit has NO matching pending-approval issue → it's a stuck lock from a prior crashed tick. INCLUDE in the result with a `payload.stale_lock = True` flag.

2. In `_process_signal` for stale-lock audits:
   - Log the recovery attempt
   - Verify the audit hasn't been mutated since the lock (timeline check)
   - Re-acquire the lock (no-op if already held) and proceed normally
   - Append entry to `result.errors` with a recovered-stale-lock marker (so the tick signal surfaces it)

3. Cross-reference SKILL.md §8.7 stale-lock detection rules.

**Files**:
- Modified: `scripts/doc_audit/signals/gh_issue.py` (stale-lock detection added)
- Modified: `scripts/doc_audit/run.py` (recovery handling in `_process_signal`)

**Validation**:
- [ ] Audit with `status:in-progress` + pending-approval → skipped (not stuck)
- [ ] Audit with `status:in-progress` + NO pending-approval → flagged as stale-lock + recovered
- [ ] Recovery records the event in `result.errors` (visible in tick signal)

---

### T029 — Wire error-handling per spec edge cases

**Purpose**: Handle the 4 documented edge cases per spec User Scenarios.

**Steps**:

1. **LLM API outage** (Anthropic SDK raises after retries):
   - Catch `anthropic.APIError` and `anthropic.APIConnectionError` at the judgment-call boundary
   - Log to `result.errors`
   - Set `result.status = "partial"` (or "failure" if no signals processed at all)
   - Continue with next signal (don't abort the whole tick)

2. **GitHub rate limit** (gh CLI returns 403 with rate-limit headers):
   - Catch in `signals/gh_issue.py` and `routing/apply_decisions.py` at the `subprocess.run` boundary
   - Raise the `RateLimitError` exception (defined in `run.py`, see T027) so the orchestration loop knows this is a tick-aborting condition (not a per-signal failure)
   - The orchestration loop catches `RateLimitError`, sets `result.status = "failure"`, logs the error, and **BREAKs the signal-processing loop** (does NOT `continue` to the next signal — any further API call will hit the same rate limit)
   - Unprocessed signals remain in the GH queue; the next tick retries them
   - Detection: 403 status from `gh` subprocess + `X-RateLimit-Remaining: 0` header in stderr OR body containing `"API rate limit exceeded"`. If the headers aren't captured by `gh` CLI, the body-substring check is the fallback.

3. **Audit references missing file**:
   - Catch `FileNotFoundError` when reading in-scope docs
   - Log in `result.errors`
   - File a debt issue noting the discrepancy
   - Close the audit with a summary noting the missing file
   - Continue processing other signals

4. **Stuck lock recovery**: covered in T028.

5. Centralize error handling: each `_process_signal` invocation wrapped in try/except; signal-specific exceptions translate to result.errors entries.

**Files**:
- Modified: `scripts/doc_audit/run.py` (error-handling in orchestration loop)

**Validation**:
- [ ] LLM outage: result.status="partial" (or "failure" if no progress), error logged, next signal attempted
- [ ] gh 403: result.status="failure", error logged, tick exits gracefully
- [ ] Missing file: debt issue filed, audit closed cleanly
- [ ] Stuck lock: recovered with marker in errors

---

### T030 [P] — Integration tests for 5 tick outcomes

**Purpose**: End-to-end integration tests covering each of the 5 expected tick outcomes.

**Steps**:

1. Create `tests/doc_audit/test_integration_tick_outcomes.py`:

   ```python
   # Pseudocode pattern — adapt per outcome

   def test_empty_queue(tmp_config, mock_gh, mock_anthropic):
       mock_gh.set_response("issue list", [])  # empty
       exit_code = run.main(["--config", str(tmp_config.path)])
       assert exit_code == 0
       signal = read_tick_signal(tmp_config)
       assert signal["status"] == "success"
       assert signal["tick"]["signals_seen"] == 0

   def test_debt_only_audit(tmp_config, mock_gh, mock_anthropic):
       # mock_gh returns 1 Doc audit: with no Tier-A/B candidates, only judgment gaps
       # mock_anthropic returns "judgment" for tier_classification calls
       # mock_anthropic returns a debt body for debt_body_generation
       ...
       assert signal["tick"]["debt_filed"] == [<expected issue number>]
       assert signal["tick"]["tier_a_commits"] == []

   def test_tier_a_auto_commit(tmp_config, mock_gh, mock_anthropic): ...
   def test_pending_approval_apply(tmp_config, mock_gh, mock_anthropic): ...
   def test_pending_approval_reject(tmp_config, mock_gh, mock_anthropic): ...
   ```

2. Each test:
   - Sets up mocked external surfaces (gh + anthropic) per the outcome
   - Invokes `run.main()` with `--config` pointing to a tmp config
   - Asserts the resulting `last-tick.json` has the expected fields
   - Asserts the activity log entry was written
   - Asserts exit code matches

3. Mocked surfaces are wired via `monkeypatch` from `conftest.py` fixtures (set up in WP02).

**Files**:
- New: `tests/doc_audit/test_integration_tick_outcomes.py` (~400 lines)

**Validation**:
- [ ] All 5 outcomes have at least one test
- [ ] Each test exercises the full driver (run.main → signal → judgment → routing → output)
- [ ] Tests pass; coverage of `run.py` reaches ≥80%

---

### T031 [P] — Integration tests for 4 edge cases

**Purpose**: Cover the spec's User Scenarios edge cases end-to-end.

**Steps**:

1. Create `tests/doc_audit/test_integration_edge_cases.py`:

   - **test_llm_api_outage**: mock_anthropic raises `anthropic.APIError` → result.status="partial" or "failure", error logged
   - **test_gh_rate_limit**: mock_gh raises with exit code 403 + rate-limit body → result.status="failure", error logged, no commit attempted
   - **test_audit_references_missing_file**: mock_gh returns audit referencing a non-existent doc path → debt issue filed, audit closed cleanly
   - **test_stuck_lock_recovery**: mock_gh returns audit with `status:in-progress` and NO pending-approval → recovered + processed normally

2. Each test follows the pattern from T030 but with the specific edge-case wiring.

**Files**:
- New: `tests/doc_audit/test_integration_edge_cases.py` (~300 lines)

**Validation**:
- [ ] All 4 edge cases have at least one test
- [ ] Each verifies the tick signal correctly reflects the failure mode (status + errors[])
- [ ] No unhandled exceptions reach top-level (try/finally always writes signal)

---

## Definition of Done

- [ ] `run.py` CLI matches contract (args, exit codes, --dry-run, --version)
- [ ] Orchestration loop: drift events → pending-approvals → new audits → weekly audits
- [ ] FR-004 satisfied: full queue per tick
- [ ] FR-014 satisfied: stuck-lock recovery
- [ ] 4 documented edge cases handled
- [ ] 5 tick outcomes covered by integration tests
- [ ] tick-signal artifact ALWAYS written (even on crash)
- [ ] Activity log entry ALWAYS appended (even on crash, with best-effort fields)
- [ ] Exit code semantics: 0=success, 1=failure, 2=partial

## Risks

| Risk | Mitigation |
|---|---|
| Orchestration loop has subtle dispatch bugs | Integration tests cover every outcome × signal-kind combination |
| Stale-lock recovery accidentally re-processes a still-active audit | Defensive check: re-read the audit's timeline; only proceed if no recent activity from `kg-felix-bot` |
| try/finally in main() doesn't catch all exit paths | Use a single try at top of main, finally writes signal; verify with test_integration_edge_cases edge cases |
| Integration tests over-mock and drift from real behavior | Live smoke test (WP07) is the fidelity floor |

## Reviewer Guidance

- Trace the orchestration: drift-events first, pending-approvals second, audits third — confirm in `run.py`
- Confirm `try/finally` in `main()` wraps EVERYTHING that could throw
- Confirm exit codes are deterministic per `contracts/driver-invocation.contract.md`
- Spot-check stuck-lock recovery vs SKILL.md §8.7 distinction (referenced pending-approval = expected wait; no pending = stuck)
- Confirm error messages in `result.errors[]` are operator-actionable

## Implementation Command

```bash
spec-kitty agent action implement WP06 --agent <name>
```

## Cross-references

- **Contract**: `contracts/driver-invocation.contract.md`, `contracts/signal-source.contract.md`
- **Data model**: E-002 AuditIssue, E-008 TickResult
- **Research**: D6 (Driver Invocation Contract), D9 (Drift-event cadence)
- **Spec**: FR-001, FR-003, FR-004, FR-007, FR-008, FR-014; NFR-002, NFR-006
- **SKILL.md §8.6** (actor-verification), §8.7 (lock lifecycle / stale-lock detection)
