---
work_package_id: WP03
title: Orchestrator integration + CLI flags
dependencies:
- WP01
- WP02
requirement_refs:
- FR-008
- FR-009
- FR-010
- FR-011
- FR-012
- FR-018
- FR-019
- FR-020
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T013
- T014
- T015
- T016
- T017
- T018
agent: "claude:opus:reviewer-renata:reviewer"
history: []
agent_profile: python-pedro
authoritative_surface: scripts/security/credential_health_check/
execution_mode: code_change
mission_id: 01KTP9M86VF89TQM5SX7JVA83Z
mission_slug: credential-liveness-probe-01KTP9M8
owned_files:
- scripts/security/credential_health_check/orchestrator.py
- scripts/security/credential_health_check/__main__.py
- scripts/security/credential_health_check/listing.py
- tests/security/credential_health_check/test_orchestrator.py
- tests/security/credential_health_check/test_listing.py
role: implementer
tags: []
shell_pid: "43048"
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

Python implementer posture: stdlib-only, test-first, locality of change. Reuse existing patterns (signal/staleness wiring, github_writer dedup+file_alert) rather than parallel implementations.

## Objective

Wire `probe_oauth_liveness()` (from WP02) into the orchestrator's `run_cycle()` using the existing pattern from `_process_staleness_alert`. Add `--liveness-only` CLI flag for the new 6h timer's exclusive use. Extend `--list --liveness` with per-credential summary rows. Reuse `github_writer.dedup_check` / `file_alert` for the GitHub issue surface.

## Branch Strategy

- Planning base branch: `main`
- Final merge target: `main`
- Lane worktree: allocated per `lanes.json` after `finalize-tasks` runs. Dependencies WP01 + WP02 mean this lane will be branched from a base that contains both of those lanes' code (computed by finalize-tasks).

## Context

| Document | Why |
|---|---|
| [../spec.md](../spec.md) | FR-008..012, FR-018..020 |
| [../plan.md](../plan.md) § IC-03 | Concern map; dedup title strategy; defense-in-depth (liveness in both modes) |
| [../data-model.md](../data-model.md) § Logged events; GH issue title format | Event/log/title contracts |
| [../research.md](../research.md) Decisions 3, 4, 5 | Cadence; output channel; separate timer |
| [../contracts/orchestrator-integration.md](../contracts/orchestrator-integration.md) | Full integration contract — function signatures, behavior, tests |
| `scripts/security/credential_health_check/orchestrator.py` | Existing 472-line module; `_process_staleness_alert` (line ~297) is the closest pattern to mirror |
| `scripts/security/credential_health_check/__main__.py` | Existing 91-line CLI entry |
| `scripts/security/credential_health_check/listing.py` | Existing 116-line list view |
| `scripts/security/credential_health_check/github_writer.py` | `dedup_check`, `file_alert` (reuse as-is) |

## Subtask Guidance

### T013 — Add `_process_liveness_alert` function

**Probe first**:

```bash
grep -n "def _process_staleness_alert\|MONITOR_ACTIVITY_READERS\|dedup_check\|file_alert" scripts/security/credential_health_check/orchestrator.py
```

Read `_process_staleness_alert` end-to-end — it's the closest analogue. Mirror its structure for `_process_liveness_alert`.

**Steps**:

1. At the top of `orchestrator.py`, add the import:

   ```python
   from .liveness import LivenessResult, probe_oauth_liveness
   ```

2. After the existing `_process_staleness_alert` function definition, add:

   ```python
   def _process_liveness_alert(
       cred,
       today: date,
       cycle_id: str,
       result: CycleResult,
       logger,
       dry_run: bool,
   ) -> None:
       if cred.liveness_probe is None or not cred.liveness_probe.enabled:
           _log(logger, logging.INFO, "liveness_skipped",
                cycle_id=cycle_id, name=cred.name,
                reason="no liveness_probe block" if cred.liveness_probe is None else "liveness_probe disabled")
           return

       try:
           liveness_result = probe_oauth_liveness(cred)
       except Exception as e:
           _log(logger, logging.ERROR, "error",
                cycle_id=cycle_id, name=cred.name,
                stage="probe_oauth_liveness", message=str(e))
           result.errors.append(f"{cred.name}: probe raised: {e}")
           return

       if liveness_result is None:
           # Probe already logged credential_alive at INFO; nothing more here.
           return

       if liveness_result.classification == "probe-error":
           result.errors.append(
               f"{cred.name}: probe_error: {liveness_result.reason}"
           )
           return

       # dead-routine-7day or dead-unexpected
       title_prefix = f"credential-liveness-{liveness_result.classification.removeprefix('dead-')}: {cred.name}"

       try:
           existing = dedup_check(title_prefix)
       except GitHubWriteError as e:
           _log(logger, logging.ERROR, "error",
                cycle_id=cycle_id, name=cred.name,
                stage="dedup_check_liveness", message=str(e))
           result.errors.append(f"{cred.name}: dedup_check failed: {e}")
           return
       if existing:
           _log(logger, logging.INFO, "alert_deduped",
                cycle_id=cycle_id, name=cred.name,
                variant="liveness", existing_issue=existing[0])
           result.alerts_deduped += 1
           return

       if dry_run:
           _log(logger, logging.INFO, "credential_evaluated",
                cycle_id=cycle_id, name=cred.name,
                action="alert_would_file", variant="liveness",
                classification=liveness_result.classification)
           return

       body = _build_liveness_issue_body(liveness_result)
       title = f"{title_prefix} ({today.isoformat()})"
       try:
           issue_number = file_alert(
               title=title,
               body=body,
               labels=["P1-bug", "area/infrastructure"],
           )
       except GitHubWriteError as e:
           _log(logger, logging.ERROR, "error",
                cycle_id=cycle_id, name=cred.name,
                stage="file_alert_liveness", message=str(e))
           result.errors.append(f"{cred.name}: file_alert failed: {e}")
           return

       result.liveness_alerts_filed += 1
       _log(logger, logging.INFO, "alert_filed",
            cycle_id=cycle_id, name=cred.name,
            variant="liveness", github_issue=issue_number,
            classification=liveness_result.classification)
   ```

3. Helper for issue body — small function in orchestrator.py:

   ```python
   def _build_liveness_issue_body(r: LivenessResult) -> str:
       body = (
           f"Credential `{r.credential_name}` failed liveness probe at {r.probed_at.isoformat()}.\n\n"
           f"Classification: {r.classification}\n"
           f"Reason: {r.reason}\n\n"
       )
       if r.classification == "dead-unexpected":
           body += (
               "If you didn't recently change passwords or revoke access, "
               "investigate at https://myaccount.google.com/permissions before re-auth.\n\n"
           )
       body += (
           f"Recovery command:\n"
           f"```\n{r.recovery_command}\n```\n\n"
           f"After re-auth, the next probe cycle will confirm liveness. "
           f"Close this issue manually after recovery (auto-close is a future-work item, "
           f"see kitty-specs/credential-liveness-probe-01KTP9M8/spec.md §Future Work)."
       )
       return body
   ```

**Files**:
- `scripts/security/credential_health_check/orchestrator.py` (+~80 lines)

**Validation**:
- Unit-test coverage added in T018.

---

### T014 — Wire into `run_cycle()` + `liveness_only` kwarg

**Steps**:

1. Add the `liveness_only: bool = False` kwarg to `run_cycle()`'s signature.
2. Inside the credential iteration loop, structure as:

   ```python
   for cred in credentials:
       if not liveness_only:
           _process_cadence_alert(cred, today, cycle_id, result, logger, dry_run)
           _process_staleness_alert(cred, today, cycle_id, result, logger, dry_run)
       # Liveness runs in BOTH modes (defense-in-depth per plan §IC-03).
       _process_liveness_alert(cred, today, cycle_id, result, logger, dry_run)
   ```

3. The manifest-quality pass (`_process_manifest_quality`) should ALSO be skipped under `liveness_only` (mirror the cadence/staleness pattern).

**Files**:
- `scripts/security/credential_health_check/orchestrator.py` (+~10 lines modified)

**Validation**:
- Tests in T018 verify `liveness_only=True` skips cadence/staleness/manifest-quality but runs liveness; `liveness_only=False` runs all four passes.

---

### T015 — Add `liveness_alerts_filed` to `CycleResult`

**Probe first**:

```bash
grep -n "class CycleResult\|@dataclass" scripts/security/credential_health_check/orchestrator.py
```

**Steps**:

1. Locate the `CycleResult` dataclass.
2. Add one field with default 0:

   ```python
   liveness_alerts_filed: int = 0
   ```

3. Place it after existing alert counters (e.g., after `cadence_alerts_filed` if present).
4. No other changes — the orchestrator's `_process_liveness_alert` increments this directly.

**Files**:
- `scripts/security/credential_health_check/orchestrator.py` (+1 line)

**Validation**:
- `pytest tests/security/credential_health_check/ -v` — existing tests pass (default 0 doesn't break construction).
- T018 tests verify `result.liveness_alerts_filed == 1` after one filed alert.

---

### T016 — Add `--liveness-only` flag to `__main__.py`

**Probe first**:

```bash
grep -n "add_argument\|parser =" scripts/security/credential_health_check/__main__.py
```

**Steps**:

1. After the existing `--dry-run` argument definition, add:

   ```python
   parser.add_argument(
       "--liveness-only",
       action="store_true",
       help=(
           "Run only the OAuth liveness probe pass for credentials with "
           "liveness_probe.enabled. Skips cadence, staleness, and "
           "manifest-quality passes. Used by credential-liveness-probe.timer (6h cadence)."
       ),
   )
   ```

2. In the `run_cycle()` invocation, pass `liveness_only=args.liveness_only`:

   ```python
   result = run_cycle(
       args.manifest, today,
       dry_run=args.dry_run, logger=logger,
       liveness_only=args.liveness_only,
   )
   ```

3. The `--list` path is NOT modified here; T017 handles the `--liveness` extension to the listing view.

**Files**:
- `scripts/security/credential_health_check/__main__.py` (+~12 lines)

**Validation**:
- `PYTHONPATH=scripts/security python3 -m credential_health_check --help` shows the new flag.
- `PYTHONPATH=scripts/security python3 -m credential_health_check --dry-run --liveness-only --manifest docs/design/architecture/data/credential-manifest.json` runs (dry-run safety net — no GH writes; logs structured output).

---

### T017 — Extend `--list --liveness` in `listing.py`

**Probe first**:

```bash
grep -n "def list_credentials\|tabulate\|print" scripts/security/credential_health_check/listing.py
```

**Steps**:

1. Add a `--liveness` flag to `__main__.py`'s parser (only relevant when `--list` is set):

   ```python
   parser.add_argument(
       "--liveness",
       action="store_true",
       help=(
           "With --list: print an additional table of OAuth liveness state "
           "per oauth2-typed credential. Read-only; no probes issued. "
           "For fresh classification, run with --dry-run --liveness-only."
       ),
   )
   ```

2. Plumb to `list_credentials(... liveness=args.liveness ...)`.

3. In `listing.py`, add a new function (or extend `list_credentials`) that prints a per-`oauth2`-credential table with columns:

   - `name`
   - `enabled` (from `liveness_probe.enabled` or `—`)
   - `gog_account` (or `—`)
   - `keyring_mtime_age` — formatted as `Xd Yh` from NOW - mtime(keyring_file); or `—` if file missing
   - `expected_next_expiration` — ISO 8601 date of `mtime + 7d`; or `—`
   - `recovery_command` (or `—`)

4. Use the existing print pattern (likely `tabulate` or plain print with column alignment — match what `list_credentials` already uses).

5. **DO NOT** add a "current_classification" column — it would be stale without a fresh probe and would mislead the operator.

**Files**:
- `scripts/security/credential_health_check/listing.py` (+~45 lines)
- `scripts/security/credential_health_check/__main__.py` (+~6 lines)

**Validation**:
- `PYTHONPATH=scripts/security python3 -m credential_health_check --list --liveness --manifest docs/design/architecture/data/credential-manifest.json` prints the new table.
- For credentials without `liveness_probe`, the row shows `—` placeholders (no crash).

---

### T018 — Tests in `test_orchestrator.py` + `test_listing.py`

**Probe first**:

```bash
grep -n "def test_\|monkeypatch" tests/security/credential_health_check/test_orchestrator.py | head -20
```

**Steps**:

Add these tests to `test_orchestrator.py`:

1. `test_orchestrator_skips_credentials_without_liveness_probe` — credential without `liveness_probe` block; assert `liveness_skipped` event logged and `file_alert` NOT called.
2. `test_orchestrator_files_issue_on_dead_routine` — mock `probe_oauth_liveness` to return `dead-routine-7day`; no existing open issue; assert `file_alert` called with `credential-liveness-routine-7day:` title prefix; `result.liveness_alerts_filed == 1`.
3. `test_orchestrator_files_separate_issue_on_dead_unexpected` — routine issue exists open; probe returns `dead-unexpected`; assert NEW issue filed with `credential-liveness-unexpected:` prefix (no dedup).
4. `test_orchestrator_dedups_repeat_routine_failures` — probe returns `dead-routine-7day`; existing open issue with matching prefix; assert `alert_deduped` logged; no new issue; `result.alerts_deduped += 1`.
5. `test_orchestrator_dry_run_does_not_file` — `dry_run=True`; dead probe; assert `alert_would_file` event; `file_alert` NOT called.
6. `test_orchestrator_probe_error_no_issue` — probe returns `probe-error`; assert `result.errors` populated; NO `file_alert` call.
7. `test_liveness_only_skips_cadence_and_staleness` — `liveness_only=True` with mixed credentials; assert `_process_cadence_alert` and `_process_staleness_alert` are NOT invoked (use monkeypatch or call-count spy).
8. `test_liveness_runs_in_both_modes` — `liveness_only=False`; assert `_process_liveness_alert` IS invoked alongside cadence + staleness.
9. `test_dedup_title_prefixes_differ_routine_vs_unexpected` — string-level assertion on the exact title prefixes.

Mocking pattern (mirror existing `test_orchestrator.py`):

```python
def test_orchestrator_files_issue_on_dead_routine(tmp_path, monkeypatch):
    # Stub probe_oauth_liveness to return a known LivenessResult.
    def fake_probe(cred):
        return LivenessResult(
            credential_name=cred.name,
            classification="dead-routine-7day",
            reason="...",
            recovery_command="echo recover",
            probed_at=datetime.now(timezone.utc),
        )
    monkeypatch.setattr("credential_health_check.orchestrator.probe_oauth_liveness", fake_probe)
    monkeypatch.setattr("credential_health_check.orchestrator.dedup_check", lambda prefix: [])
    captured = {}
    def fake_file_alert(title, body, labels):
        captured["title"] = title
        captured["body"] = body
        captured["labels"] = labels
        return 999
    monkeypatch.setattr("credential_health_check.orchestrator.file_alert", fake_file_alert)
    # Run cycle...
    # Assert captured title startswith "credential-liveness-routine-7day:"
```

Add 1 test in `test_listing.py`:

10. `test_list_liveness_includes_credential_table` — manifest with one credential having `liveness_probe`; run `list_credentials(..., liveness=True)` capturing stdout; assert credential name + gog_account appear in output.

**Files**:
- `tests/security/credential_health_check/test_orchestrator.py` (+~200 lines for 9 tests)
- `tests/security/credential_health_check/test_listing.py` (+~30 lines for 1 test)

**Validation**:
- All 10 new tests pass.
- `pytest tests/security/credential_health_check/ -v` — no regressions in existing tests.

---

## Test Strategy

All new tests use the existing monkeypatch + mock patterns. Probe + GH writer + dedup are all monkey-patched (no real subprocess or GitHub API calls). Coverage gate ≥90% line on orchestrator code paths touched by this WP (the new `_process_liveness_alert` + the `liveness_only` branch in `run_cycle`).

## Definition of Done

- [ ] `_process_liveness_alert` function exists, matches contract behavior.
- [ ] `run_cycle()` accepts `liveness_only` kwarg; mode separation works correctly.
- [ ] `CycleResult.liveness_alerts_filed` field added with default 0.
- [ ] `__main__.py` has `--liveness-only` flag; plumbing works.
- [ ] `--list --liveness` produces the documented table.
- [ ] GH issue title prefixes are EXACTLY `credential-liveness-routine-7day:` and `credential-liveness-unexpected:` — string assertion in test 9.
- [ ] Issue body includes the recovery command verbatim from the manifest.
- [ ] For `dead-unexpected` classification, body includes the "investigate at myaccount.google.com" paragraph.
- [ ] 9 new orchestrator tests + 1 new listing test pass.
- [ ] All existing tests in `tests/security/credential_health_check/` STAY passing.

## Risks

- **Import ordering**: `liveness.py` imports from `manifest` (`LivenessProbeConfig`), and `orchestrator.py` imports from `liveness`. Make sure no circular imports.
- **dedup_check signature**: read the function in `github_writer.py` to confirm it returns `list[int]` (issue numbers) or a tuple. Match accordingly.
- **file_alert signature**: same — read `github_writer.py` for the exact kwargs (labels, milestone, etc.).
- **Title format**: the `(YYYY-MM-DD)` date suffix is for human-eye readability; dedup MUST be by prefix only.
- **Body length**: GitHub issue body has a soft limit (~65k chars); our bodies are <1k. Fine.
- **`removeprefix` requires Python 3.9+**: office2 has Python 3.12; Mac dev shells should too. Fail loudly if not.

## Reviewer Guidance

- Compare `_process_liveness_alert` side-by-side with `_process_staleness_alert` — they should be near-identical in shape (dedup → file or skip).
- Verify the dual-mode behavior: `liveness_only=True` doesn't run cadence/staleness; `liveness_only=False` runs everything.
- Test 9's exact-string assertion is a regression guard; don't approve a change to the title prefix without test updates.
- The body shape must include the recovery command in a code block (so phone copy-paste works cleanly).

## Activity Log

- 2026-06-09T14:47:32Z – claude:sonnet:python-pedro:implementer – shell_pid=39817 – Assigned agent via action command
- 2026-06-09T14:59:25Z – claude:sonnet:python-pedro:implementer – shell_pid=39817 – Ready for review: orchestrator integration + CLI flags; WP02 stub removed; manifest.py + liveness.py included as WP01/WP02 base wasn't in lane-c; 153 tests pass
- 2026-06-09T15:00:02Z – claude:opus:reviewer-renata:reviewer – shell_pid=43048 – Started review via action command
- 2026-06-09T15:02:08Z – user – shell_pid=43048 – Review passed by opus: lane-base manifest.py byte-identical to WP01 (harmless duplicate work, no semantic conflict). All contract assertions verified: _process_liveness_alert shape correct, liveness_alerts_filed CycleResult field added, run_cycle liveness_only kwarg gates cadence/staleness while liveness runs in both modes per defense-in-depth, --liveness-only CLI flag plumbed through, --list --liveness table has the 6 documented columns with current_classification correctly omitted, exact title prefixes 'credential-liveness-routine-7day:' and 'credential-liveness-unexpected:' asserted, recovery command in triple-backtick block, dead-unexpected paragraph includes myaccount.google.com investigate copy, WP02 liveness.py stub cleanup confirmed (imports LivenessProbeConfig from .manifest). 19 orchestrator + 24 listing + 14 liveness tests pass; full security suite 153/153.
