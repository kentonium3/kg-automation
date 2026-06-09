# Contract: Orchestrator Integration

**Module**: `scripts/security/credential_health_check/orchestrator.py`

## New function: `_process_liveness_alert`

```python
def _process_liveness_alert(
    cred: Credential,
    today: date,
    cycle_id: str,
    result: CycleResult,
    logger: logging.Logger,
    dry_run: bool,
) -> None: ...
```

### Behavior

1. If `cred.liveness_probe is None` OR `cred.liveness_probe.enabled is False` → log `liveness_skipped` and return.
2. Call `liveness_result = probe_oauth_liveness(cred)` (catches `ValueError` defensively as a per-credential error per existing pattern).
3. If `liveness_result is None` → log `credential_alive` and return.
4. If `liveness_result.classification == "probe-error"` → log `credential_probe_error`, append to `result.errors` (existing field), return (no GH issue filed).
5. Otherwise (`dead-routine-7day` or `dead-unexpected`):
   - Build title prefix: `f"credential-liveness-{liveness_result.classification.removeprefix('dead-')}: {cred.name}"`.
   - `existing = github_writer.dedup_check(title_prefix)`.
   - If `existing` → log `alert_deduped` (variant=`liveness`), increment `result.alerts_deduped`, return.
   - If `dry_run` → log `alert_would_file` (variant=`liveness`), return.
   - Otherwise: `issue_number = github_writer.file_alert(title=<title>, body=<body>, labels=["P1-bug", "area/infrastructure"])`.
   - Log `credential_dead` with `github_issue_filed=True, github_issue_number=issue_number`.
   - Increment `result.liveness_alerts_filed` (new field on `CycleResult`).

### CycleResult extension

`CycleResult` gains one new field:

```python
@dataclass
class CycleResult:
    # ... existing fields unchanged ...
    liveness_alerts_filed: int = 0
```

Additive; existing fields untouched.

## Modified function: `run_cycle`

`run_cycle` gains a new conditional pass after the existing staleness pass:

```python
def run_cycle(
    manifest_path: str,
    today: date,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
    *,
    liveness_only: bool = False,  # NEW kwarg
) -> CycleResult:
    ...
    for cred in credentials:
        if not liveness_only:
            _process_cadence_alert(cred, today, cycle_id, result, logger, dry_run)
            _process_staleness_alert(cred, today, cycle_id, result, logger, dry_run)
        # liveness runs in BOTH modes (the new daily-cadence-only mode AND --liveness-only)
        _process_liveness_alert(cred, today, cycle_id, result, logger, dry_run)
    ...
```

Logic:
- Normal mode (default): all three passes run.
- `--liveness-only`: only `_process_liveness_alert` runs per credential. Faster (≤60s per NFR-001 for typical N).

### Why liveness runs in BOTH modes

The existing daily cycle includes liveness as a safety net — if the 6h timer fails for a day, the daily run still surfaces a dead token. The `--liveness-only` mode is for the high-frequency 6h timer.

If this turns out to be redundant in practice (the 6h timer is reliable), we can later remove liveness from the daily pass with a one-line change. The bias here is toward defense-in-depth.

## Modified CLI: `__main__.py`

Add `--liveness-only`:

```python
parser.add_argument(
    "--liveness-only",
    action="store_true",
    help=(
        "Run only the OAuth liveness probe pass for credentials with "
        "liveness_probe.enabled. Skips cadence, staleness, and "
        "manifest-quality. Used by credential-liveness-probe.timer (6h cadence)."
    ),
)
```

Plumb through `run_cycle(..., liveness_only=args.liveness_only)`.

`--list --liveness` is documented in a separate listing contract section below.

## Modified CLI: `--list --liveness`

`listing.py` gains a `--liveness` flag that, combined with `--list`, prints an additional table of `oauth2`-typed credentials. Per FR-012, columns:

| Column | Source |
|---|---|
| `name` | `Credential.name` |
| `enabled` | `Credential.liveness_probe.enabled` (or `—` if no block) |
| `gog_account` | `Credential.liveness_probe.gog_account` (or `—`) |
| `keyring_mtime_age` | NOW - mtime(keyring_file), formatted as `Xd Yh` (or `—` if file missing) |
| `expected_next_expiration` | mtime + 7d, ISO 8601 date (or `—`) |
| `recovery_command` | `Credential.liveness_probe.recovery_command` (or `—`) |

This view is READ-ONLY: no probes issued. The "current classification" column from FR-012 is intentionally NOT included — without a fresh probe, the value is stale and misleading. Operator runs `python3 -m credential_health_check --dry-run --liveness-only` to get a fresh classification per credential.

This is a deliberate scope reduction from the spec's FR-012 — we'd add it later if the operator finds the view insufficient. Documented here so the test doesn't fail on an "expected_classification" column that we deliberately deferred. Spec.md FR-012 is functionally satisfied (the view shows liveness state per credential); the staleness concern is addressed via the dry-run path.

## Tests

| Test | Setup | Expected |
|---|---|---|
| `test_orchestrator_skips_credentials_without_liveness_probe` | manifest has cred without `liveness_probe` block | `liveness_skipped` logged; no probe call; no issue filed |
| `test_orchestrator_files_issue_on_dead_routine` | mocked probe returns `dead-routine-7day`; no existing open issue | `file_alert` called with `credential-liveness-routine-7day:` title prefix; `result.liveness_alerts_filed == 1` |
| `test_orchestrator_files_separate_issue_on_dead_unexpected` | mocked probe returns `dead-unexpected`; routine issue exists open | new issue filed with `credential-liveness-unexpected:` prefix (does NOT dedup against routine) |
| `test_orchestrator_dedups_repeat_routine_failures` | mocked probe returns `dead-routine-7day`; existing open issue with matching prefix | `alert_deduped` logged; no new issue; `result.alerts_deduped += 1` |
| `test_orchestrator_dry_run_does_not_file` | `dry_run=True`; mocked probe returns dead | `alert_would_file` logged; `file_alert` NOT called |
| `test_orchestrator_probe_error_no_issue` | mocked probe returns `probe-error` | `credential_probe_error` logged; `result.errors` populated; NO `file_alert` call |
| `test_liveness_only_skips_cadence_and_staleness` | `liveness_only=True`; multiple credentials, only one with liveness | only `_process_liveness_alert` invoked; not `_process_cadence_alert` or `_process_staleness_alert` |
| `test_run_cycle_liveness_in_both_modes` | both default + liveness-only mode | `_process_liveness_alert` called in both |

Existing orchestrator tests STAY passing.

## CycleResult schema is additive

External readers of `CycleResult` (none currently — it's used only inside the orchestrator + `__main__.py` summary) are unaffected. The new `liveness_alerts_filed` field has default `0`, so existing constructors don't need to change.
