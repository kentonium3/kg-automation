# Phase 0 Research — habits-checkin-d6-extract

Resolves the four research items identified during planning interrogation. All findings derive from empirical inspection of the current codebase plus the authoritative `credentials-and-secrets.md` narrative and `credential-manifest.json` data.

---

## R1 — Vikunja auth/credential source (BROAD scope per Kent's plan-time direction)

**Decision**: Helpers read the Vikunja API token from `/data/services/openclaw/secrets/vikunja-api` (a mode-600 plaintext file). API base URL is hardcoded to `https://office2.tail0f5f56.ts.net/api/v1`.

**Rationale**:
- Authoritative data: [`docs/design/architecture/data/credential-manifest.json`](../../docs/design/architecture/data/credential-manifest.json) entry `vikunja-api`:
  ```
  type: api-token
  storage: /data/services/openclaw/secrets/vikunja-api
  used_by: openclaw-gateway
  ```
- Authoritative narrative: [`docs/design/architecture/credentials-and-secrets.md`](../../docs/design/architecture/credentials-and-secrets.md) § "Storage Mechanisms" — defines four mechanisms; the Vikunja token uses **Mechanism #3: Scoped plaintext files (mode 600)**.
- Canonical implementation precedent: [`scripts/security/credential_health_check/vikunja_writer.py`](../../scripts/security/credential_health_check/vikunja_writer.py) reads the token at exactly this path and is the existing pattern for Vikunja-writing scripts in Felix.

**Documentation status**: secrets management is well-documented. No gap to fill — Kent's plan-time concern ("is this a documented practice?") is answered yes.

**Alternatives considered**:
- Environment variable injection: rejected — Felix's secrets convention puts host-bound files at scoped paths, not env vars (Mechanism #3 over Mechanism #4).
- Reading from `~/.openclaw/skills/vikunja-api/SKILL.md`: rejected — SKILL.md is documentation, not a credential source. Agents read SKILL.md to learn the API; scripts read the token file directly.
- Per-helper hardcoded values: rejected — fails Felix's storage-mechanism convention; would create cross-environment portability issues.

---

## R2 — HTTP library choice

**Decision**: `urllib.request` from the Python stdlib. No `requests` or other third-party HTTP libraries.

**Rationale**:
- `vikunja_writer.py` (the canonical Vikunja-writing script) uses `urllib.request` exclusively.
- No `requirements.txt` or `pyproject.toml` lists `requests` as a dependency for the existing helpers.
- stdlib-only keeps the helpers portable, dependency-free, and consistent with the existing codebase pattern.
- The Vikunja API surface is simple (a handful of GET/PUT calls with JSON bodies); `urllib.request` is fully adequate.

**Alternatives considered**:
- `requests`: more ergonomic but introduces a dependency for no functional gain.
- `httpx`: same.

---

## R3 — Test mocking convention

**Decision**: pytest + `unittest.mock` (stdlib). Tests live at `tests/habits/test_<helper>.py`, parallel to `scripts/habits/<helper>.py`.

**Rationale**:
- Precedent: [`tests/security/test_vikunja_writer.py`](../../tests/security/test_vikunja_writer.py) uses this exact pattern — `from unittest.mock import MagicMock, patch`, `import pytest`, direct module imports.
- Existing `tests/` directory has subdirectories `inbox/`, `openclaw/`, `scripts/`, `security/` — confirms the per-domain test layout convention.
- `tests/security/test_vikunja_writer.py` demonstrates how to mock `urllib.request.urlopen` calls; this informs the habits tests' mocking approach directly.

**Test fixture strategy**:
- Mock Vikunja API responses with `unittest.mock.patch` on `urllib.request.urlopen`
- Provide sample task / comment JSON fixtures inline within each test (small enough; no separate fixtures dir needed for this mission)
- For TZ-sensitive tests (compute_today, set_due_dates), use `zoneinfo.ZoneInfo("America/New_York")` and `freezegun` if needed — but precedent in `vikunja_writer.py` suggests direct `date()`/`datetime()` construction without time-freezing libraries is sufficient

---

## R4 — Test directory layout

**Decision**: `tests/habits/` with `__init__.py` (so test modules can import each other's helpers if needed), one test module per helper.

**Rationale**: matches `tests/security/` (the precedent) which has a `credential_health_check/__init__.py` setup allowing tests to import the under-test module via `from credential_health_check.vikunja_writer import ...`.

**Files to create**:
- `tests/habits/__init__.py` (empty)
- `tests/habits/test_compute_today.py`
- `tests/habits/test_query_active_habits.py`
- `tests/habits/test_set_due_dates.py`
- `tests/habits/test_exclude_completed.py`

---

## Cross-cutting findings

### #112 regression-prevention precedent

`vikunja_writer.py` already implements the `render_due_date_iso(due: date) -> str` pattern that returns `YYYY-MM-DDT23:59:59<ET_OFFSET>` (e.g., `2026-05-15T23:59:59-04:00`). Per C-003 (no library extraction in this mission), the new `set_due_dates.py` should **duplicate this pattern in-line** rather than import it. The second copy is what justifies extraction; for now, both implementations live independently.

### Credentials-and-secrets gap check (Kent's plan-time concern)

Both narrative (`credentials-and-secrets.md`) and data (`credential-manifest.json`) cover the Vikunja API token completely:
- 4 storage mechanisms enumerated
- 13 credentials in the manifest
- Per-credential `expiry_policy`, `review_cadence`, `last_reviewed`, `notes`
- The `vikunja-api` entry has all required fields

**Verdict**: no documentation gap. Plan-time concern resolved.

---

## Decisions summary

| Item | Decision |
|---|---|
| Vikunja token source | `/data/services/openclaw/secrets/vikunja-api` (mode 600 file) |
| Vikunja API base URL | `https://office2.tail0f5f56.ts.net/api/v1` (hardcoded constant per `vikunja_writer.py`) |
| HTTP library | `urllib.request` (stdlib) |
| Test framework | pytest + `unittest.mock` |
| Test directory | `tests/habits/` with `__init__.py` |
| #112 fix pattern | Duplicate `render_due_date_iso()` in-line; library extraction deferred (C-003) |

All four Phase 0 research items resolved with documented rationale grounded in existing code and architecture data. No `[NEEDS CLARIFICATION]` markers remain. Ready for Phase 1 design.
