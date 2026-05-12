---
work_package_id: WP06
title: Orchestrator + CLI + logging
dependencies:
- WP02
- WP03
- WP04
- WP05
requirement_refs:
- FR-001
- FR-004
- FR-007
- FR-008
- FR-011
- FR-012
- NFR-001
- NFR-002
- NFR-003
- NFR-004
- NFR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T025
- T026
- T027
- T028
- T029
agent: "claude"
shell_pid: "49509"
history:
- event: created
  at: '2026-05-11T21:43:38Z'
  by: 'spec-kitty.tasks (auto-drive via #115)'
authoritative_surface: scripts/security/credential_health_check/orchestrator.py
execution_mode: code_change
owned_files:
- scripts/security/credential_health_check/orchestrator.py
- scripts/security/credential_health_check/__main__.py
- tests/security/test_orchestrator.py
tags: []
---

# WP06 — Orchestrator + CLI + logging

## Objective

Stitch the components together into a runnable Python entry point with deterministic per-cycle execution, structured logging, and a clean CLI surface. End-to-end behavior: read manifest → for each credential, compute boundary OR check signal → dedup → write artefacts → log.

## Context

- **Spec** anchors: FR-001..FR-013 are wired through the orchestrator; FR-007 dedup, FR-008 post-rotation behaviour, FR-009 once-per-day cadence, FR-011 manifest-failure exit, FR-012 batched manifest-quality issue.
- **Plan** anchor: stdlib-only logging to stdout for journalctl capture (R-002).
- **Data-model** anchor: §CycleLog (structured log lines, cycle_id correlation).
- **Contracts** anchors: all four contracts are consumed here.

## Branch Strategy

- **Planning/base branch**: `main`
- **Merge target branch**: `main`
- This WP runs in a lane-allocated worktree; merges to `main`.

## Subtasks

### T025 — `orchestrator.py`: the per-cycle loop

**Purpose**: The function that ties everything together.

**Steps**:

1. Create `scripts/security/credential_health_check/orchestrator.py`:
   ```python
   from dataclasses import dataclass
   from datetime import date
   from .manifest import read_manifest, Credential, ManifestQualityIssue, ManifestUnreadableError
   from .cadence import compute_boundary, is_fixed_interval_cadence, is_within_warning_window
   from .signals import MONITOR_ACTIVITY_READERS, ActivitySignalFailure
   from .github_writer import (
       cadence_alert_title, cadence_alert_title_prefix,
       staleness_alert_title, staleness_alert_title_prefix,
       manifest_quality_title, MANIFEST_QUALITY_TITLE_PREFIX,
       cadence_alert_body, staleness_alert_body, manifest_quality_body,
       dedup_check, create_issue,
       GitHubWriteError,
   )
   from .vikunja_writer import create_task, VikunjaWriteError

   @dataclass(frozen=True)
   class CycleResult:
       credentials_evaluated: int
       cadence_alerts_filed: int
       staleness_alerts_filed: int
       alerts_deduped: int
       manifest_quality_issue_filed: bool
       errors: list[str]

   def run_cycle(manifest_path: str, today: date, *, dry_run: bool = False, logger=None) -> CycleResult:
       """Execute one full cycle. Returns a CycleResult summary."""
       # 1. Read manifest. ManifestUnreadableError escapes — caller decides exit.
       well_formed, malformed = read_manifest(manifest_path)
       # 2. For each credential, evaluate and act.
       # 3. After the per-credential loop, batch-file manifest quality if any malformed.
       # 4. Return CycleResult.
       ...
   ```
2. Per-credential branch:
   - If `is_fixed_interval_cadence(c.review_cadence)`: compute boundary; if within warning window, dedup-then-file (cadence path).
   - Elif `c.name` in `MONITOR_ACTIVITY_READERS`: call the reader; if it returns a failure, dedup-then-file (staleness path).
   - Else: skip (logged at `credential_evaluated` event).
3. Cadence-path filing order: **Vikunja task first**, then GitHub issue. If task creation fails: log, skip the credential, do NOT file the GitHub issue. If issue creation fails after task succeeded: log the orphan, continue.
4. Staleness-path filing: GitHub issue only.
5. Manifest-quality batch: after the per-credential loop, if `len(malformed) > 0` AND no open manifest-quality issue exists, file one batched issue (FR-012).

**Files**: `scripts/security/credential_health_check/orchestrator.py` (create, ~180 lines).

---

### T026 — `__main__.py`: CLI surface + logging config

**Purpose**: argparse, logging, `--dry-run` and `--manifest` flags.

**Steps**:

1. Create `scripts/security/credential_health_check/__main__.py`:
   ```python
   import argparse, sys, logging
   from datetime import date, datetime, timezone
   from .orchestrator import run_cycle
   from .manifest import ManifestUnreadableError

   DEFAULT_MANIFEST = "/home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json"

   def main(argv: list[str] | None = None) -> int:
       parser = argparse.ArgumentParser(prog="credential_health_check", description="Daily credential expiry check.")
       parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="Path to credential-manifest.json")
       parser.add_argument("--dry-run", action="store_true", help="Evaluate and log but do not file alerts.")
       parser.add_argument("--today", default=None, help="Override 'today' for testing (ISO-8601 date).")
       args = parser.parse_args(argv)

       logging.basicConfig(
           level=logging.INFO,
           format="%(asctime)s %(levelname)s %(name)s %(message)s",
           stream=sys.stdout,
       )
       logger = logging.getLogger("credential_health_check")

       today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()

       try:
           result = run_cycle(args.manifest, today, dry_run=args.dry_run, logger=logger)
       except ManifestUnreadableError as e:
           logger.error("manifest_unreadable", extra={"path": args.manifest, "error": str(e)})
           return 1
       except Exception as e:
           logger.exception("unhandled_exception")
           return 2

       logger.info(
           "cycle_end credentials_evaluated=%d cadence_filed=%d staleness_filed=%d deduped=%d manifest_quality=%s errors=%d",
           result.credentials_evaluated,
           result.cadence_alerts_filed,
           result.staleness_alerts_filed,
           result.alerts_deduped,
           result.manifest_quality_issue_filed,
           len(result.errors),
       )
       return 0

   if __name__ == "__main__":
       sys.exit(main())
   ```

**Files**: `scripts/security/credential_health_check/__main__.py` (create, ~60 lines).

---

### T027 — Structured log lines + cycle ID

**Purpose**: Make `journalctl --user -u credential-health-check` output grep-able per data-model §CycleLog.

**Steps**:

1. Inside `orchestrator.py`, generate a `cycle_id` (`uuid.uuid4().hex[:8]`) at cycle start.
2. Wrap logging calls so each line is prefixed with `cycle_id=<id>` and the event name. Use `logger.info("event_name extra1=val1 extra2=val2", ...)` style (simple, parseable, no JSON dep).
3. Log at these points:
   - `cycle_start cycle_id=<id> today=<iso> manifest=<path>`
   - `manifest_read cycle_id=<id> well_formed=N malformed=M`
   - `credential_evaluated cycle_id=<id> name=<name> action=<one of: within_cadence|warning_window|alert_filed|deduped|skip_non_fixed|signal_healthy|signal_failed>`
   - `alert_filed cycle_id=<id> name=<name> variant=<cadence|staleness|manifest_quality> github_issue=<N> vikunja_task=<N or null>`
   - `alert_deduped cycle_id=<id> name=<name> existing_issue=<N>`
   - `manifest_quality_filed cycle_id=<id> github_issue=<N> entries=<list>`
   - `error cycle_id=<id> stage=<...> message=<...>`
   - `cycle_end cycle_id=<id> credentials_evaluated=N ...`

**Files**: `scripts/security/credential_health_check/orchestrator.py` (modify).

---

### T028 — Manifest-quality batch wiring

**Purpose**: FR-012 implementation.

**Steps**:

1. After the per-credential loop, if `malformed` is non-empty:
   - Compute `MANIFEST_QUALITY_TITLE_PREFIX` and run `dedup_check(prefix)`.
   - If no existing open issue: render `manifest_quality_body(malformed, today)`, file one issue with title `manifest_quality_title(len(malformed), today)`.
   - If existing open issue: log `alert_deduped` for the manifest-quality variant. Do not refresh the existing issue.
2. Set `result.manifest_quality_issue_filed = True` when a new issue was created.

**Files**: `scripts/security/credential_health_check/orchestrator.py` (modify).

---

### T029 — Tests for orchestrator

**Purpose**: End-to-end orchestration tests with mocked external surfaces.

**Steps**:

1. Create `tests/security/test_orchestrator.py`.
2. Patch all the external functions: `dedup_check`, `create_issue`, `create_task` (in the `github_writer` and `vikunja_writer` namespaces). Also patch the signal readers to return controlled values.
3. Cases:
   - `test_cycle_no_credentials_due_files_nothing`: against `manifest-valid.json` with no near-expiry — expect 0 issues, 0 tasks, 0 manifest-quality. All credentials "within cadence" or "signal healthy".
   - `test_cycle_near_expiry_files_paired_alert`: against `manifest-near-expiry.json` — expect 1 task created BEFORE 1 issue created, with the task ID present in the issue body call.
   - `test_cycle_dedup_skips_already_open`: stub `dedup_check` to return `[42]` for the near-expiry credential — expect 0 new artefacts; result.alerts_deduped increments.
   - `test_cycle_vikunja_failure_skips_credential`: stub `create_task` to raise `VikunjaWriteError` — expect 0 issues created for that credential, error logged, processing continues.
   - `test_cycle_github_failure_after_task_orphans_task`: stub `create_task` succeeds, `create_issue` raises — expect the orphan logged, processing continues.
   - `test_cycle_manifest_quality_batched`: against `manifest-missing-last-reviewed.json` — expect one manifest-quality issue filed.
   - `test_cycle_manifest_unreadable_exits_nonzero`: against `manifest-invalid-json.txt` — expect `ManifestUnreadableError` propagates (caller handles).
   - `test_cycle_dry_run_does_not_call_writers`: with `dry_run=True`, expect writer mocks were never invoked.
   - `test_cycle_activity_staleness_files_issue_only`: stub `tailscale_auth_signal` returning a failure — expect 1 issue, 0 tasks.

**Files**: `tests/security/test_orchestrator.py` (create, ~250 lines).

---

## Definition of Done

- All five subtasks complete.
- `python -m pytest tests/security/ -v` → all `test_orchestrator` tests passing (plus all earlier WP tests).
- `python -m credential_health_check --manifest tests/security/fixtures/manifest-near-expiry.json --dry-run --today 2026-05-11` from the repo root prints the expected dry-run log output without filing anything.
- Commit prefix: `feat(security):` or `feat(WP06):` referencing #115.

## Risks

- **External-surface mocking depth**: tests must patch the writer functions, not `subprocess.run` directly — the orchestrator depends on the writers' public APIs.
- **Filing-order semantics**: Vikunja first, then GitHub. Reversing this means the GitHub body can't reference the task ID. Test `test_cycle_near_expiry_files_paired_alert` explicitly asserts call ordering.
- **`--today` override**: this is for testing. Production runs always use the current UTC date. Make sure `__main__.py` only honors `--today` when explicitly passed.

## Reviewer guidance

- Verify: cycle_id is generated once at cycle start, included on every log line.
- Verify: `run_cycle` is a pure function of (manifest_path, today, dry_run) plus side effects to external systems via the writers. No global mutation.
- Verify: filing-order test (Vikunja-before-GitHub) is explicit, not implicit.
- Verify: every error path logs and continues (except `ManifestUnreadableError` which propagates and exits non-zero per FR-011).
- Verify: dry_run shortcuts the writer calls entirely (`create_task` and `create_issue` are not called).

## Suggested implement command

```bash
spec-kitty agent action implement WP06 --agent <name>
```

## Activity Log

- 2026-05-11T22:07:44Z – claude – shell_pid=24213 – Started implementation via action command
- 2026-05-12T01:34:49Z – claude – shell_pid=24213 – 10 orchestrator tests; 106 cumulative. End-to-end CLI smoke test succeeded.
- 2026-05-12T01:34:53Z – claude – shell_pid=49509 – Started review via action command
