# Design tracer — finalize-inbox-file-01KW8MSQ

Invariants kept, the KEEP set, and design decisions held (or bent) under
implementation pressure. **Consumed automatically by the retrospective generator
(FR-007).** Bold-lead bullets.

## The KEEP set (invariants that must survive implementation)

- **[2026-06-28][specify] in-place, NO move (retention invariant)** — finalize sets
  `status: processed` and leaves the note at its `01-Inbox/` path. `prescan.py`'s
  `archive_stale` owns the eventual move to `02-Inbox-Processed/` after the 7-day
  retention window (Kent refers back to recent inbox notes). The move-era spec was a
  regression; it is removed. Disposition: **expected** (worked as designed — the
  corrected design restores the `felix-admin-capture` AGENTS.md Step-5 invariant).

- **[2026-06-28][specify] fold into mark_processed.py, no new script** — decided
  fork: `mark_processed.py` already performs the atomic idempotent in-place
  `status: processed` write; the finalize work is folded into it (exit-code contract
  + JSON stdout + error surfacing), NOT a new `finalize_inbox_file.py`. **Deviation
  from the issue's literal title — recorded in spec.md per DIRECTIVE_010.**
  Disposition: documented design decision.

- **[2026-06-28][specify] detectability = atomic status write + exit code** — decided
  fork: no separate finalize audit line. A failed/missing finalize is surfaceable
  via the non-zero exit (orchestrator) + a note left `status: unprocessed` (prescan
  reads frontmatter). Do NOT re-introduce a `02-Inbox-Processed/` per-file log under
  the no-move design. Disposition: documented design decision.

- **[2026-06-28][specify] exit-code contract 0/1/2** — `0` success or idempotent
  re-run; `1` validation failure (bad path / outside inbox root / missing or
  unparseable frontmatter); `2` filesystem error (perm denied / write race), with
  the specific OSError on stderr. stdout = single-line JSON matching the prescan
  convention. Disposition: documented design decision (contract under test).

- **[2026-06-28][specify] reuse mark_processed atomic-write core** — the temp-sibling
  + fsync + rename atomic write already in `mark_processed.py` is the substrate;
  finalize must not duplicate or weaken it. Reuse the prescan path-registry resolver
  (`scripts/vault/paths.json`) for inbox-root validation. Disposition: documented
  design decision (locality of change, DIRECTIVE_024).
