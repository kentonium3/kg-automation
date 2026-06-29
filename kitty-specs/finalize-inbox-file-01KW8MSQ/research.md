# Research — Atomic in-place inbox finalize (mark_processed hardening)

Phase 0. The spec resolved the two design forks (helper scope; detectability), so
research here confirms the implementation-level decisions against the existing code
rather than evaluating new technology.

## R-01 — Exit-code reconciliation (0/1/2/3)

- **Decision**: Add **exit 2** = filesystem error to `mark_processed.py`; retain the
  existing **exit 3** = `04-Growth/_private/` refusal (C-001). Final contract:
  `0` success/idempotent · `1` validation · `2` filesystem error · `3` private refusal.
- **Rationale**: Exit 2 is currently unused, so the addition is non-breaking. The
  #325 contract names exit 2 for fs errors; exit 3 is a pre-existing privacy guard
  unrelated to fs errors. Keeping both is additive and preserves all current callers.
- **Alternatives considered**: Renumber to a strict 0/1/2 (rejected — would change
  the established private-refusal code 3 and break the existing contract/tests).

## R-02 — Where to catch the write OSError

- **Decision**: Catch `OSError` at the `mark_processed()` level around the
  `_atomic_write(...)` call (and the mode-stat within it), print a JSON error to
  **stderr**, and `return 2`. `_atomic_write` already unlinks its tempfile on failure
  before re-raising, so the original note is never left partial.
- **Rationale**: This is the exact 2026-05-18 incident path (group-unwritable note →
  `os.replace`/`open` raises `OSError`). Today that propagates as an uncaught
  traceback (process exit 1 + stack trace, no machine signal). Converting it to a
  clean exit-2 + structured stderr is the core deliverable (FR-001, SC-001).
- **Alternatives considered**: Catch inside `_atomic_write` and return a sentinel
  (rejected — muddies the atomic-write primitive; the helper's `main()`/`mark_processed`
  boundary is the right place to own exit-code policy).

## R-03 — JSON stdout success shape

- **Decision**: On success, print one line to **stdout**:
  `{"finalized": true, "already_processed": <bool>, "status": "processed", "file_final_path": "<abs 01-Inbox path>"}`.
  Mirrors the single-line-JSON convention used by `prescan.py`.
- **Rationale**: Lets the orchestrator machine-confirm finalize without re-reading
  the note (FR-002, SC-002). `already_processed` distinguishes a real write from an
  idempotent no-op. stdout stays a single line (NFR-004); diagnostics go to stderr.
- **Alternatives considered**: No stdout / exit-code-only (rejected — loses the
  positive confirmation signal and the final-path echo the issue's contract specifies).

## R-04 — Inbox-root validation

- **Decision**: Resolve the inbox root via `prescan.resolve_registry()` (honors the
  `PRESCAN_REGISTRY_PATH` override for hermetic tests) and require the resolved
  `--path` to live under it; otherwise **exit 1** (validation). The private-path
  refusal (exit 3) still fires first, before any disk read.
- **Rationale**: Matches the issue's step-1 validation and reuses prescan's registry
  resolver rather than duplicating path logic (DIRECTIVE_024 locality). FR-003.
- **Alternatives considered**: Hard-code `01-Inbox` (rejected — registry is the
  single source of truth and the test override depends on it).

## R-05 — Perm-denied test strategy

- **Decision**: Create a tmp note, `os.chmod(0o444)` (read-only) to force the write
  `OSError`, assert exit 2 + original-content-unchanged (NFR-003). Guard the test to
  **skip when the runner is root** (root bypasses mode bits).
- **Rationale**: Deterministic reproduction of the incident class without touching
  the real vault; the skip-guard keeps CI green where pytest runs as root.
- **Alternatives considered**: Mocking `os.replace` to raise (kept as a *second*
  unit test for portability, since CI may run as root and skip the chmod test).
