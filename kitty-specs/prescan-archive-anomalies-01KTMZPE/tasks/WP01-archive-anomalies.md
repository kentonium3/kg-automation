---
work_package_id: WP01
title: Extend prescan.py with archive-anomaly scan
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- FR-010
- FR-011
- FR-012
- FR-013
- FR-014
- FR-015
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
agent: claude
history: []
agent_profile: python-pedro
authoritative_surface: scripts/inbox/
execution_mode: code_change
mission_id: 01KTMZPE0QR0AZACXF1A0X9SV6
mission_slug: prescan-archive-anomalies-01KTMZPE
model: claude-sonnet-4-6
owned_files:
- scripts/inbox/prescan.py
- tests/scripts/inbox/test_prescan.py
- docs/design/architecture/data/service-inventory.json
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

Python implementer posture: stdlib-only, test-first, locality of change.

## Objective

Extend `scripts/inbox/prescan.py` with `scan_archive_anomalies(processed_dir, now_utc)` that returns one `ArchiveAnomaly` per non-`processed`-status `.md` file in `02-Inbox-Processed/`. Add as additive `archive_anomalies` field on `PrescanResult`. Bounded scan (cap 5000 by mtime). Daily logs (`inbox-processing-*.md`) filtered. Daily log gets `### archive_anomalies` section when non-empty. Stderr gets `archive_anomalies=N`. Read-only — no remediation.

## Context

| Document | Why |
|---|---|
| [../spec.md](../spec.md) | FR-001..015, NFR-001..005, SC-1..7 |
| [../plan.md](../plan.md) § IC-01..04 | Concern map per subtask |
| `scripts/inbox/prescan.py` | Existing helper (778 lines); extend at the bottom or near `archive_stale` (line ~478) |
| `tests/scripts/inbox/test_prescan.py` | Existing tests (extend; don't replace) |
| `tests/inbox/fixtures/` | Add new fixtures (e.g., `archive-unprocessed.md`, `archive-needs-review.md`, `archive-no-status.md`, `archive-parse-fail.md`) |

## Subtask Guidance

### T001 — Dataclass + scan + result field

**Probe first** (per `[[feedback_design_phase_research]]`):

```bash
grep -n "def classify_file\|class InboxFile\|class PrescanResult" scripts/inbox/prescan.py
```

Look at:
- `classify_file(path, now_utc) -> InboxFile`: what's its return shape? Does `InboxFile` have a `status_raw` field already? If yes, reuse. If no, extract from `_extract_frontmatter_block()`.
- `PrescanResult` dataclass: add `archive_anomalies: list = field(default_factory=list)` as the LAST field for ordering stability.

**Implement** in `scripts/inbox/prescan.py` (near the existing `archive_stale`/`scan_directory` functions):

```python
ARCHIVE_SCAN_CAP = 5000  # module-level; operator-tuneable via code edit

@dataclass
class ArchiveAnomaly:
    path: str
    status_raw: Optional[str]
    classification: str  # "unprocessed" | "needs-review" | "unknown-treated-as-unprocessed" | "parse-failure"
    warning: str


def scan_archive_anomalies(
    processed_dir: Path,
    now_utc: datetime,
) -> tuple[list[ArchiveAnomaly], list[str]]:
    """Scan 02-Inbox-Processed/ for files whose status is NOT 'processed'.
    
    Returns (anomalies, warnings). The warnings list is appended to
    PrescanResult.warnings by the caller (run_prescan).
    
    Filters daily-log files by filename prefix 'inbox-processing-'.
    Caps at ARCHIVE_SCAN_CAP files (mtime descending) when exceeded.
    Returns ([], [<missing-dir-warning>]) if processed_dir does not exist.
    """
    warnings: list[str] = []
    if not processed_dir.exists():
        warnings.append(f"archive scan: processed_dir does not exist at {processed_dir}")
        return [], warnings
    
    # Collect .md files non-recursively, exclude daily logs
    candidates = [
        p for p in processed_dir.iterdir()
        if p.is_file()
        and p.suffix == ".md"
        and not p.name.startswith("inbox-processing-")
    ]
    
    # Apply cap (most-recent mtime first)
    if len(candidates) > ARCHIVE_SCAN_CAP:
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        skipped = len(candidates) - ARCHIVE_SCAN_CAP
        candidates = candidates[:ARCHIVE_SCAN_CAP]
        warnings.append(
            f"archive scan: cap_applied (scanned {ARCHIVE_SCAN_CAP} most-recent; "
            f"skipped {skipped} older files)"
        )
    
    anomalies: list[ArchiveAnomaly] = []
    for path in candidates:
        info = classify_file(path, now_utc)
        # Extract status_raw — InboxFile may have it; if not, parse from frontmatter
        status_raw = getattr(info, "status_raw", None)
        # OR: extract via _extract_frontmatter_block(path.read_text(encoding='utf-8'))
        # then a simple regex for `status:\s*(\S+)`
        # ... pick whichever the actual classify_file signature supports
        
        if status_raw == "processed":
            continue
        
        # Classify the anomaly
        if status_raw in ("unprocessed",):
            kind = "unprocessed"
            warning = f"status:unprocessed found in 02-Inbox-Processed/"
        elif status_raw in ("needs-review",):
            kind = "needs-review"
            warning = f"status:needs-review found in 02-Inbox-Processed/ (belongs in 01-Inbox/)"
        elif status_raw is None:
            kind = "unknown-treated-as-unprocessed"
            warning = "no status field; treated as unprocessed"
        # parse_failure detection: classify_file may flag malformation;
        # if InboxFile has a parse_failure indicator, branch here
        elif getattr(info, "malformation", None):
            kind = "parse-failure"
            warning = f"parse-failure in archive: {info.malformation}"
        else:
            kind = "unknown-treated-as-unprocessed"
            warning = f"unknown status:{status_raw}; treated as unprocessed"
        
        anomalies.append(ArchiveAnomaly(
            path=str(path),
            status_raw=status_raw,
            classification=kind,
            warning=warning,
        ))
    
    return anomalies, warnings
```

**NOTE**: the pseudo-code above is a sketch. **You MUST probe `classify_file()` first** to know whether `status_raw` is exposed on `InboxFile`. If not exposed, either:
- (preferred) Add a `status_raw: Optional[str]` field to `InboxFile` and populate it during `classify_file`. This is an additive change to existing internals.
- (fallback) Parse frontmatter directly in `scan_archive_anomalies` via `_extract_frontmatter_block()` + a regex.

Either way: **do NOT break existing `classify_file()` callers**. The current inbox scan loop must keep working.

### T002 — Wire into run_prescan + log + stderr

In `run_prescan()` (line ~597 area), after the existing inbox scan + archive-stale step, add the archive-anomaly scan. Append its warnings to `PrescanResult.warnings`; set `result.archive_anomalies = anomalies`.

In `_append_daily_log()` (line ~557), when `result.archive_anomalies` is non-empty, append:

```
### archive_anomalies (count=N)
- <path>: <warning>
- <path>: <warning>
...
```

When empty: omit the section entirely (no log noise on healthy ticks).

In the stderr summary line (look for the existing "archived" / "warnings" emission), insert `archive_anomalies=<int>` between them. Existing log-parsing consumers (if any) need to tolerate the additional field, but the position is deterministic.

### T003 — Tests (≥10 cases)

Add to `tests/scripts/inbox/test_prescan.py` (NOT a new test file):

- `test_archive_anomaly_unprocessed_status` — file with `status: unprocessed` in archive → anomaly with `classification: "unprocessed"`
- `test_archive_anomaly_needs_review_status` — file with `status: needs-review` → anomaly with `classification: "needs-review"`
- `test_archive_anomaly_no_status` — file with no frontmatter status field → anomaly with `classification: "unknown-treated-as-unprocessed"`
- `test_archive_anomaly_parse_failure` — file with malformed YAML → anomaly with `classification: "parse-failure"`
- `test_archive_anomaly_skips_daily_logs` — `inbox-processing-2026-06-08.md` is NOT flagged regardless of content
- `test_archive_anomaly_skips_processed_status` — file with `status: processed` is NOT flagged
- `test_archive_anomaly_cap_applied` — archive has 5001 files → only 5000 scanned + cap_applied warning
- `test_archive_anomaly_missing_dir_safe` — `processed_dir` doesn't exist → returns ([], [warning]) no crash
- `test_archive_anomaly_field_in_prescan_result` — `PrescanResult.archive_anomalies` is `list[ArchiveAnomaly]` (additive shape)
- `test_archive_anomaly_log_section_omitted_when_empty` — daily log does NOT contain `archive_anomalies` heading when count=0
- `test_archive_anomaly_log_section_present_when_nonempty` — daily log contains the section + count=N
- `test_archive_anomaly_stderr_summary_includes_count` — stderr summary line contains `archive_anomalies=<int>`

Add fixtures under `tests/inbox/fixtures/` as needed.

### T004 — Coverage gate

```bash
pytest tests/scripts/inbox/test_prescan.py tests/inbox/test_prescan_parse_failure.py \
  --cov=scripts.inbox.prescan \
  --cov-branch \
  --cov-report=term-missing \
  --cov-fail-under=90
```

Must show ≥90% line AND ≥85% branch. Use `# pragma: no branch` ONLY for genuinely-unreachable defensive paths (e.g., a check guarded by an earlier short-circuit return); document each pragma with a one-line comment.

### T005 — Arch-doc update

Update `docs/design/architecture/data/service-inventory.json`:

Locate `services[?(@.name=="openclaw-gateway")].agents.felix-admin-capture.components[?(@.id=="inbox-prescan-helper")]`. Update:
- `purpose`: append a sentence like " Post-mission `prescan-archive-anomalies-01KTMZPE` (#568): also scans `02-Inbox-Processed/` for files whose `status` is not `processed` and surfaces them in the new `archive_anomalies` field of `PrescanResult` + a daily-log section + stderr summary. Read-only; the visibility surface lets agents or operators detect any regression of the silent-content-loss bug class (#563)."
- `updated_at`: bump to today
- `updated_by`: prepend `"prescan-archive-anomalies-01KTMZPE (#568) + "`

Bump top-level `last_updated` and prepend mission to top-level `updated_by`.

Verify: `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json')); print('OK')"`.

## Definition of Done

- [ ] `ARCHIVE_SCAN_CAP = 5000` module-level constant in prescan.py
- [ ] `ArchiveAnomaly` dataclass added
- [ ] `scan_archive_anomalies()` function added (with cap + missing-dir safety + daily-log filter)
- [ ] `PrescanResult.archive_anomalies` field added (additive default factory)
- [ ] `run_prescan()` wired to call the scan + populate the field + log + stderr
- [ ] ≥10 new tests in `tests/scripts/inbox/test_prescan.py`
- [ ] Coverage gate passes (≥90% line / ≥85% branch on `scripts.inbox.prescan`)
- [ ] No regression in existing prescan tests (full `pytest tests/inbox/ tests/scripts/inbox/` passes)
- [ ] `service-inventory.json` updated and validates
- [ ] Lane committed; WP moved to `for_review`

## Risks

- **classify_file API surface**: probe before assuming `status_raw` is exposed. The fallback (parse frontmatter in scan_archive_anomalies) adds slight duplication but is acceptable.
- **Cap latency**: mtime sort on 5,000 files is fast (≤100 ms). NFR-001's <2s budget is comfortably met.
- **Daily-log filter regex**: case-sensitive prefix match on `inbox-processing-` (no glob). The existing daily-log writer always uses lowercase prefix.

## Reviewer expectations

- Independent (codex preferred): focus on edge cases (missing dir, empty archive, all-processed archive, cap exactly at the boundary).
- Spot-check the daily-log surface: anomaly section ABSENT on healthy tick, PRESENT on anomalous tick.
- Confirm no regression in the existing prescan tests.
