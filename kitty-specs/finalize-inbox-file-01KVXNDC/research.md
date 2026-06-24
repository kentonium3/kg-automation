# Research: Atomic inbox-file finalize helper

Phase 0 — resolve design decisions before writing contracts/data-model. No
`[NEEDS CLARIFICATION]` markers remain; all items below resolved from the existing
`scripts/inbox/` codebase and the issue contract.

## D-01 — Reuse vs. supersede existing inbox primitives

- **Decision**: Compose, don't duplicate. `finalize_inbox_file.py` orchestrates
  the finalize sequence by reusing the existing primitives where they already
  encapsulate a step: `mark_processed.py` (frontmatter `status: processed`) and
  `routing_log.py` / `append_routing_entry.py` (daily-log append). The new helper
  owns orchestration, per-step idempotence checks, the atomic move, and the
  unified exit-code/JSON contract.
- **Rationale**: DIRECTIVE_001 (architectural integrity) — avoid behavior
  divergence between the agent's finalize path and the primitives already covered
  by `test_mark_processed.py` / `test_routing_log.py`. If a primitive's public
  surface doesn't cleanly support an idempotence pre-check or in-process call, the
  helper imports its core function rather than shelling out.
- **Alternatives considered**: (a) Reimplement all four steps inline in the new
  helper — rejected (duplication, drift risk). (b) Shell out to each primitive as
  a subprocess — rejected (loses structured error capture and atomicity control;
  harder to test). Tasks phase confirms each primitive's importable surface.

## D-02 — Vault path resolution

- **Decision**: Resolve inbox root + processed dir from `scripts/vault/paths.json`
  using the same loader pattern as `prescan.py` (`Path(__file__).resolve().parent.parent
  / "vault" / "paths.json"`), honoring a registry-path env override so tests point
  at a tmp vault.
- **Rationale**: C-001 — no hardcoded vault paths; consistency with prescan.
- **Alternatives considered**: CLI flags for roots — rejected (registry is the
  single source of truth; flags invite drift).

## D-03 — Atomic write + move semantics

- **Decision**: Frontmatter rewrite uses temp-file-in-same-dir + `fsync` +
  `os.replace`/`os.rename` (the prescan atomic-write pattern). The file move uses
  `os.rename`. A cross-filesystem move raises `OSError` (`EXDEV`) which the helper
  treats as a filesystem failure (exit 2) — it does **not** fall back to copy.
- **Rationale**: NFR-001 + C-004 — no partially-written/partially-moved file is
  ever observable; cross-FS surprises fail loudly rather than silently changing
  semantics. The inbox and processed dirs are siblings in one vault → same
  filesystem in practice, so `EXDEV` indicates a misconfiguration worth surfacing.
- **Alternatives considered**: `shutil.move` (copy+unlink fallback) — rejected
  (non-atomic, violates C-004 / NFR-001).

## D-04 — Idempotence checks (partial-state recovery)

- **Decision**: Each mutating step is preceded by a check: status step is a no-op
  if frontmatter already `processed`; move step is a no-op if a file of the same
  basename already exists in the processed dir; log step is a no-op if a line for
  the basename already exists in today's log. Re-invocation completes only the
  missing steps.
- **Rationale**: FR-007, NFR-002 — recover the 2026-05-13/05-18 partial-finalize
  states without duplication.
- **Alternatives considered**: a lockfile/state-journal — rejected (the on-disk
  state itself is the source of truth; a journal adds a new failure mode).

## D-05 — Outcome contract (exit codes + stdout JSON)

- **Decision**: Exit `0` (success or already-finalized), `1` (validation: bad
  path, outside inbox root, missing/malformed frontmatter), `2` (filesystem:
  permission denied, cross-FS, rename race) with the specific `OSError` on stderr.
  stdout on success is a single-line JSON object
  `{"finalized": true, "steps_executed": [...], "file_final_path": "..."}`,
  matching the `prescan.py` stdout convention.
- **Rationale**: FR-008, FR-009, NFR-003, C-005 — deterministic machine-readable
  outcome so the orchestrating agent never has to infer success from prose.
- **Alternatives considered**: single exit `1` for all errors — rejected (the
  agent's standing orders must distinguish "won't ever succeed" (validation) from
  "retryable/environmental" (filesystem)).

## D-06 — Daily-log line format & file bootstrap

- **Decision**: Append one line per file to
  `02-Inbox-Processed/inbox-processing-<YYYY-MM-DD>.md` (UTC date), creating the
  file with standard frontmatter if absent. Line records `filename | routed_by |
  finalized_at_utc`. The exact line shape reuses `routing_log.py` conventions
  where they exist.
- **Rationale**: FR-005, C-003. The basename presence test for idempotence
  (D-04) keys off the `filename` field.
- **Alternatives considered**: appending to a single rolling log — rejected
  (per-day file matches existing processing-log convention and the issue).

## D-07 — Agent standing-orders cutover + office2 delivery

- **Decision**: Replace felix-admin-capture step-5 inline `Edit` + `Bash mv` with
  one `python3 scripts/inbox/finalize_inbox_file.py <path> --routed-by
  felix-admin-capture` call; standing orders define: exit 0 → record complete;
  exit 1 → treat as a content/validation defect, do not retry, surface; exit 2 →
  environmental, surface for operator (do not mark complete). Delivery to office2
  goes through `deploys/queued/finalize-inbox-file.yaml` so the helper is present
  before the standing-orders cutover takes effect.
- **Rationale**: FR-010, C-002, deploy discipline. AGENTS.md is an audited
  surface but unhashed by the security monitor → no rebaseline (record at merge).
- **Alternatives considered**: edit AGENTS.md directly on office2 — rejected
  (out-of-band change, bypasses the manifest pipeline).
