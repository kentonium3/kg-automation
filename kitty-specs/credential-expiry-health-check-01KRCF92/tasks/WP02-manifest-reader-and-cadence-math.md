---
work_package_id: WP02
title: Manifest reader + cadence math
dependencies:
- WP01
requirement_refs:
- C-002
- FR-001
- FR-002
- FR-003
- FR-008
- FR-011
- NFR-001
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
- T009
- T010
history:
- event: created
  at: '2026-05-11T21:43:38Z'
  by: 'spec-kitty.tasks (auto-drive via #115)'
authoritative_surface: scripts/security/credential_health_check/
execution_mode: code_change
owned_files:
- scripts/security/credential_health_check/__init__.py
- scripts/security/credential_health_check/manifest.py
- scripts/security/credential_health_check/cadence.py
- tests/security/test_manifest.py
- tests/security/test_cadence.py
- kitty-specs/credential-expiry-health-check-01KRCF92/research.md
tags: []
---

# WP02 — Manifest reader + cadence math

## Objective

Build the deterministic data-processing core of the auditor: a `Credential` dataclass, a manifest reader that validates each entry, and a cadence-boundary math module. Everything in this WP is pure-Python with no external surface dependencies — fully unit-testable.

## Context

- **Spec** anchors: FR-001 (read manifest), FR-002 (compute boundary against warning window), FR-011 (exit non-zero on unreadable manifest), FR-012 (one manifest-quality issue per cycle).
- **Plan** anchors: project structure §`scripts/security/credential_health_check/`; technical context §"stdlib-only, no virtualenv".
- **Research** anchor: **R-004 needs revision in this WP** (see §"Note on R-004 revision" below).
- **Contracts** anchor: `contracts/manifest-reader.md` is the authoritative spec for this WP.
- **Data-model** anchor: `Credential` (read-only from manifest) and `CadenceBoundary` (computed, not stored).

## Note on R-004 revision

The original `research.md` §R-004 chose a single-file Python script. Spec-kitty's WP ownership model (no overlapping `owned_files` across WPs) makes that incompatible with how WP02–WP06 split the work by concern. This WP introduces the **package layout** (`scripts/security/credential_health_check/`) with module-per-concern. Total LOC is comparable.

**As part of T006**, update `research.md` §R-004 with an addendum:

> **2026-05-11 revision (WP02)**: Implementation uses a package layout (`scripts/security/credential_health_check/__init__.py` + per-concern modules) rather than the single-file form originally chosen. Rationale: spec-kitty's `owned_files` model assigns one WP per file; package-per-concern provides clean WP boundaries without materially increasing total LOC or operational complexity.

## Branch Strategy

- **Planning/base branch**: `main`
- **Merge target branch**: `main`
- This WP runs in a lane-allocated worktree (path computed by `finalize-tasks` and recorded in `lanes.json`). Implementing agent enters that worktree, makes changes, and the spec-kitty review/merge flow handles return to `main`.

## Subtasks

### T006 — Package skeleton + research.md addendum

**Purpose**: Lay down the package directory and document the R-004 revision.

**Steps**:

1. Create `scripts/security/` directory if absent.
2. Create `scripts/security/credential_health_check/__init__.py` — empty (or with a single module docstring: `"""Credential expiry health checker. See kitty-specs/credential-expiry-health-check-01KRCF92/."""`).
3. Update `kitty-specs/credential-expiry-health-check-01KRCF92/research.md` §R-004 with the 2026-05-11 revision addendum quoted above.

**Files**:

- `scripts/security/credential_health_check/__init__.py` (create)
- `kitty-specs/credential-expiry-health-check-01KRCF92/research.md` (modify — append to §R-004)

**Validation**:

- `python -c "import sys; sys.path.insert(0, 'scripts/security'); import credential_health_check; print(credential_health_check.__doc__)"` returns the docstring.

---

### T007 — Implement `manifest.py`

**Purpose**: Read and validate `credential-manifest.json`; yield well-formed Credential records and structured ManifestQualityIssue records for malformed ones. Authoritative reference: `contracts/manifest-reader.md`.

**Steps**:

1. Define dataclasses (use `@dataclasses.dataclass` from stdlib):
   ```python
   from dataclasses import dataclass
   from datetime import date
   from typing import Optional

   @dataclass(frozen=True)
   class Credential:
       name: str
       review_cadence: str
       last_reviewed: Optional[date]   # None if cadence is non-fixed (monitor-activity, etc.)
       storage: str
       expiry_notes: str
       type: Optional[str] = None
       scope: Optional[str] = None
       used_by: tuple[str, ...] = ()
       expiry_policy: Optional[str] = None
       host: Optional[str] = None
       created_date: Optional[date] = None

   @dataclass(frozen=True)
   class ManifestQualityIssue:
       credential_name: str    # or "<index N>" if name itself is missing
       reason: str
   ```
2. Define `ManifestUnreadableError(Exception)`.
3. Implement `read_manifest(path: str) -> tuple[list[Credential], list[ManifestQualityIssue]]`:
   - Open + parse the file. On any I/O or `json.JSONDecodeError`: raise `ManifestUnreadableError(message)`.
   - Validate top-level is a dict with `credentials` key whose value is a list. Else: raise `ManifestUnreadableError`.
   - For each entry in `credentials`:
     - Apply validation per `data-model.md` §Credential validation:
       - `name` non-empty string (required)
       - `review_cadence` in the documented set: `annual`, `monitor-activity`, `on-revocation`, `n/a`, `session`
       - For fixed-cadence values (`annual` for v1): `last_reviewed` parseable as ISO-8601 date; fall back to `created_date` if `last_reviewed` missing.
     - If well-formed: construct a `Credential` and append to the `well_formed` list.
     - If malformed: append a `ManifestQualityIssue` to `malformed` with a clear reason string.
4. Return `(well_formed, malformed)`.

**Files**:

- `scripts/security/credential_health_check/manifest.py` (create, ~120 lines)

**Validation**: See T009.

**Edge cases**:

- `last_reviewed` is a string but not valid ISO-8601 → mark as malformed with reason `"last_reviewed is not a parseable ISO-8601 date: <value>"`.
- A credential entry is missing both `last_reviewed` AND `created_date` for a fixed-cadence credential → malformed, `"missing last_reviewed (and no created_date fallback)"`.
- Extra unknown fields on a credential → ignore (don't fail; manifest schema is extensible).

---

### T008 — Implement `cadence.py`

**Purpose**: Pure date arithmetic for the cadence boundary and warning window.

**Steps**:

1. Implement helpers:
   ```python
   from datetime import date, timedelta
   from .manifest import Credential

   WARNING_WINDOW_DAYS = 30
   ANNUAL_DAYS = 365

   CADENCE_INTERVALS = {
       "annual": timedelta(days=ANNUAL_DAYS),
       # extensible: "biannual": timedelta(days=183), ...
   }

   def is_fixed_interval_cadence(review_cadence: str) -> bool:
       return review_cadence in CADENCE_INTERVALS

   def compute_boundary(credential: Credential) -> date | None:
       """Return the cadence boundary date for a fixed-interval credential.
       Returns None if cadence is non-fixed-interval."""
       if not is_fixed_interval_cadence(credential.review_cadence):
           return None
       anchor = credential.last_reviewed or credential.created_date
       if anchor is None:
           # Should not happen for well-formed Credentials; defensive.
           return None
       return anchor + CADENCE_INTERVALS[credential.review_cadence]

   def is_within_warning_window(boundary: date, today: date, window_days: int = WARNING_WINDOW_DAYS) -> bool:
       """True iff today + window_days >= boundary (i.e. boundary already crossed or within window)."""
       return boundary - today <= timedelta(days=window_days)
   ```
2. Keep this module dependency-light — only imports `manifest.Credential`.

**Files**:

- `scripts/security/credential_health_check/cadence.py` (create, ~50 lines)

**Validation**: See T010.

---

### T009 — Tests for `manifest.py`

**Purpose**: Exercise every fixture from WP01 against the reader.

**Steps**:

1. Create `tests/security/test_manifest.py` with `pytest`-style tests:
   - `test_read_valid_manifest`: against `manifest-valid.json` — assert N well-formed equals `len(credentials)`, malformed empty.
   - `test_kentonium_pat_present`: against `manifest-valid.json` — assert one Credential has `name == "kentonium3-pat"`.
   - `test_near_expiry_fixture_unchanged_count`: against `manifest-near-expiry.json` — assert well-formed count equals valid count (the near-expiry mutation didn't break parseability).
   - `test_missing_last_reviewed`: against `manifest-missing-last-reviewed.json` — assert one entry is in `malformed` with reason matching `"missing last_reviewed"`.
   - `test_bad_review_cadence`: against `manifest-bad-review-cadence.json` — assert that entry is in `malformed` with reason mentioning the invalid value.
   - `test_invalid_json`: against `manifest-invalid-json.txt` — expect `ManifestUnreadableError`.
   - `test_not_a_dict`: against `manifest-not-a-dict.json` — expect `ManifestUnreadableError`.
   - `test_missing_file`: pass a nonexistent path — expect `ManifestUnreadableError`.
2. Use `pathlib.Path(__file__).parent / "fixtures" / "..."` to resolve fixture paths relative to the test file.

**Files**:

- `tests/security/test_manifest.py` (create, ~120 lines)

**Validation**:

- `python -m pytest tests/security/test_manifest.py -v` → all green.

---

### T010 — Tests for `cadence.py`

**Purpose**: Anchor the date math against deterministic inputs.

**Steps**:

1. Create `tests/security/test_cadence.py` with tests:
   - `test_compute_boundary_annual`: given a Credential with `review_cadence='annual'`, `last_reviewed=date(2025, 5, 11)` → boundary should be `date(2026, 5, 11)` (365 days later).
   - `test_compute_boundary_uses_created_date_fallback`: Credential with `last_reviewed=None`, `created_date=date(2025, 5, 11)` → boundary `date(2026, 5, 11)`.
   - `test_compute_boundary_non_fixed_returns_none`: Credential with `review_cadence='monitor-activity'` → boundary is None.
   - `test_is_within_warning_window_exactly_30_days`: boundary = today + 30 days → True.
   - `test_is_within_warning_window_31_days_out`: boundary = today + 31 days → False.
   - `test_is_within_warning_window_in_past`: boundary = today − 5 days → True.
   - `test_is_within_warning_window_custom_window`: window_days=14, boundary = today + 20 days → False.
2. Construct test Credentials with all required fields filled (minimal but valid).

**Files**:

- `tests/security/test_cadence.py` (create, ~80 lines)

**Validation**:

- `python -m pytest tests/security/test_cadence.py -v` → all green.

---

## Definition of Done

- All five subtasks complete.
- `python -m pytest tests/security/ -v` shows all `test_manifest` and `test_cadence` tests passing.
- `research.md` §R-004 has the 2026-05-11 addendum.
- A commit lands with `feat(security):` or `feat(WP02):` prefix referencing #115.

## Risks

- **Frozen dataclass on Credential**: hashability not strictly required, but `frozen=True` defends against accidental mutation downstream. Test fixtures that construct Credentials in tests need to pass full kwargs — design the dataclass with sensible defaults for optional fields.
- **Date parsing edge cases**: `date.fromisoformat("2026-04-06")` works; `"2026/04/06"` doesn't. The manifest uses ISO-8601 already, but tests should explicitly cover a malformed-date fixture.
- **Timezone**: All date math here is in UTC implicitly (no time component). Don't introduce timezone-aware datetimes — they complicate the comparison and aren't needed for daily-granularity cadence.

## Reviewer guidance

- Verify: `Credential` and `ManifestQualityIssue` are `frozen` dataclasses (immutable).
- Verify: `read_manifest` distinguishes "I can't read this file" (raises) from "I read it but some entries are bad" (returns malformed list).
- Verify: `compute_boundary` returns `None` (not raises) for non-fixed cadences — this is the contract that lets the orchestrator branch cleanly.
- Verify: `is_within_warning_window` uses `<=` not `<` at the boundary edge (boundary exactly 30 days out is in-window).
- Verify: tests use the actual WP01 fixtures, not hand-rolled JSON inside the test file.

## Suggested implement command

```bash
spec-kitty agent action implement WP02 --agent <name>
```
