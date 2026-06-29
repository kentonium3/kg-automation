# Spec: Atomic in-place inbox finalize (mark_processed hardening)

**Mission**: `finalize-inbox-file-01KW8MSQ` · **Issue**: kentonium3/kg-automation#325
(P1-feature, `area/felix-core`) · **Type**: software-dev · **Tier**: 3
(Logic/Workflow)

## Overview

The `felix-admin-capture` agent finalizes each fully-routed inbox note by writing
`status: processed` to its frontmatter, **in place** — the note stays in
`01-Inbox/`; `prescan.py`'s `archive_stale` owns the eventual move to
`02-Inbox-Processed/` after a 7-day retention window. This mission closes the
**silent-finalize-failure** class: a finalize whose filesystem write fails must be
**detectable**, not silent.

### Current state (ground-truth, verified 2026-06-28 — fidelity per DIRECTIVE_010)

The #325 body predates the current code and is **stale in one respect**: it frames
the work as "replacing the agent's fragile inline `Edit`." That replacement
**already happened** in a prior mission:

- `scripts/inbox/mark_processed.py` already performs the atomic, mode-preserving,
  idempotent in-place `status: processed` + `processed_at` write (temp + fsync +
  `os.replace`; full frontmatter/body round-trip).
- `felix-admin-capture/AGENTS.md` Step 5c (line 125) already invokes it via the
  mandatory module form `python3 -m scripts.inbox.mark_processed --path <path>`,
  and Step 5 already carries the "do NOT delete; preserve in `01-Inbox/`" invariant
  (line 113).

So the **remaining** gap is narrower and is what this mission delivers:

1. The helper currently lets a write `OSError` (permission denied, write race —
   the literal 2026-05-18 incident cause) propagate as an **uncaught traceback**;
   there is no clean exit-2 surface and no machine-readable failure signal.
2. The helper emits **no stdout success signal**, so the orchestrator cannot
   machine-confirm a finalize without re-reading the note.
3. The helper does **not validate** that the path is under the inbox root.
4. Step 5c invokes the helper but defines **no exit-code handling** — a non-zero
   exit would still go unsurfaced.

## User Scenarios & Testing

**Primary actor**: the `felix-admin-capture` agent (orchestrated, per-tick).

- **Happy path**: agent routes a note, calls the finalize helper → note's
  frontmatter gets `status: processed` atomically, note stays at its `01-Inbox/`
  path, helper prints a single-line JSON success object, exits 0. Agent records
  finalize complete.
- **Idempotent re-run**: helper called on an already-`processed` note → no write,
  JSON reports `already_processed: true`, exit 0.
- **Filesystem-failure exception (the incident)**: the frontmatter write fails
  (e.g. note is group-unwritable). Helper does NOT crash and does NOT leave a
  partial file — it exits **2** with the specific `OSError` on stderr; the note is
  left **uncorrupted** and still `unprocessed`. The orchestrator detects the
  non-zero exit and surfaces/escalates rather than silently continuing.
- **Validation exception**: path outside the inbox root, or missing/unparseable
  frontmatter → exit **1**, error JSON on stderr, no write.
- **Privacy refusal**: path under `04-Growth/_private/` → exit **3** before any
  disk read (existing C-001 guard).

## Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | The finalize helper surfaces a filesystem write failure (`OSError`: permission denied, write race) as a distinct, non-silent outcome — **exit code 2** with the specific `OSError` on stderr — instead of an uncaught traceback. | Draft |
| FR-002 | On success (including idempotent no-op), the helper emits a **single-line JSON object on stdout** describing the outcome (at minimum: finalized flag, whether already-processed, and the in-place `01-Inbox/` final path), matching the `prescan.py` single-line-JSON convention, so the orchestrator can machine-confirm finalize without re-reading the note. | Draft |
| FR-003 | The helper validates that `--path` resolves to a file **under the inbox root** (resolved from `scripts/vault/paths.json`, same registry pattern as `prescan.py`); a path outside the inbox root is a validation failure (**exit 1**). | Draft |
| FR-004 | All existing guarantees are preserved: atomic mode-preserving write, idempotency on already-`processed` notes, full frontmatter + body round-trip, **in place — the note stays at its `01-Inbox/` path (no move)**, and the `04-Growth/_private/` refusal (**exit 3**). | Draft |
| FR-005 | `felix-admin-capture` Step 5c standing orders define explicit **exit-code handling**: `0` → finalize complete; `1` → validation failure, surface (do not silently continue); `2` → filesystem error, surface/escalate. The "do NOT move; preserve in `01-Inbox/`" invariant is retained. | Draft |
| FR-006 | Architecture/doc updates required by the `mission-agent-prompt-changed` doc-map class are committed within this mission (service-inventory JSON + markdown agent entry; `audited-surfaces.json`; `openclaw-agent-setup.md` / `agent-prompt-sync-ops.md` as applicable). | Draft |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | No new runtime dependencies. | Stdlib-only (preserves the helper's existing no-deps constraint); 0 added packages. | Draft |
| NFR-002 | Invocation via the mandatory module form. | `python3 -m scripts.inbox.mark_processed`; script-path form is not relied upon (per the helper `-m` convention). | Draft |
| NFR-003 | The exit-2 path leaves the original note uncorrupted. | A perm-denied finalize test asserts the on-disk note byte-for-byte equals the pre-call original (atomic-write guarantee: original or full new content, never partial). | Draft |
| NFR-004 | stdout is parse-clean. | On success, stdout contains exactly one line (the JSON object); all diagnostics/errors go to stderr. | Draft |

## Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | In place only — finalize never moves the note to `02-Inbox-Processed/`; `prescan.py`'s `archive_stale` owns the 7-day archive. No `02-Inbox-Processed/` per-file log is (re)introduced. | Active |
| C-002 | `04-Growth/_private/` is never read or written; the path refusal (exit 3) fires before any disk read. | Active |
| C-003 | Exit-code contract is **0/1/2/3** (0 success/idempotent · 1 validation · 2 filesystem error · 3 private-path refusal). Additive: exit 2 was previously unused; exit 3 is retained. | Active |
| C-004 | Tier 3. The AGENTS.md edit reaches office2 via the **pull-based agent-prompt-sync** pipeline (slug `felix-admin-capture` → deploy dir **`inbox-agent`**), NOT a `deploys/queued/` felix-deployer manifest. Rebaseline **not required** — the agent-prompt surface is not hashed by `audit.sh` (known gap #621). | Active |

## Success Criteria

- **SC-001**: A finalize that hits a filesystem write failure is detectable within
  the same agent tick (non-zero exit + uncorrupted, still-`unprocessed` note),
  closing the 5-day-silent gap from the 2026-05-18 incident.
- **SC-002**: A successful finalize is machine-confirmable from a single stdout
  line without re-reading the note.
- **SC-003**: Re-running finalize on an already-finalized note is a no-op success
  (idempotent): zero side effects, exit 0.
- **SC-004**: 100% of helper outcomes (happy, idempotent, validation-fail,
  fs-fail, private-refusal) are covered by automated tests.

## Key Entities

- **Inbox note** — a `.md` file in `01-Inbox/` with YAML frontmatter; the `status`
  field (`unprocessed` → `processed`) is the finalize target.
- **Vault path registry** — `scripts/vault/paths.json`; resolves the inbox root
  (shared with `prescan.py`).
- **`felix-admin-capture` agent** — the orchestrated consumer; Step 5c invokes the
  finalize helper.

## Architecture Impact

Per `signal-to-doc-map.json` change class **`agent-prompt-changed`**
(`mission-agent-prompt-changed`), the AGENTS.md edit requires reviewing/updating:

- `docs/design/architecture/data/service-inventory.json` + `service-inventory.md`
  — the `felix-admin-capture` agent entry (finalize now carries an
  error-surfacing exit contract; note/depends_on may need a touch).
- `docs/design/architecture/data/audited-surfaces.json` — confirm the
  agent-prompt surface mapping is current.
- `docs/runbooks/openclaw-agent-setup.md` and
  `docs/runbooks/agent-prompt-sync-ops.md` — per-agent deploy + auto-sync
  expectations (update only if the finalize-step contract is described there).
- **Rebaseline (#557)**: merge commit records `Rebaseline: not required —
  agent-prompt-sync surface is not hashed by audit.sh (gap #621)`.

The helper change (`scripts/inbox/mark_processed.py`) is Tier-3 logic with no
architecture-data impact beyond the above.

## Assumptions

- **A1 (fidelity, DIRECTIVE_010)**: `mark_processed.py` is the canonical finalize
  primitive and Step 5c already invokes it (verified `AGENTS.md:125`, Jun 18). The
  issue's "replace inline `Edit`" framing is stale; the delivered scope is helper
  robustness + Step 5c error handling.
- **A2 (deviation, DIRECTIVE_010)**: work is folded into `mark_processed.py`, not a
  new `scripts/inbox/finalize_inbox_file.py` as the issue title literally states
  (operator decision — avoid a near-duplicate of the atomic-write core).
- **A3**: detectability is achieved via the atomic `status` write (read by prescan)
  + the exit-code contract; no separate finalize audit line (operator decision).
- **A4**: reconciling the helper to a 0/1/2/3 contract (adding the previously
  unused exit 2, retaining exit 3) is an additive, reasonable default.

## Out of Scope (separate issues)

- The universal error/alerting primitive RFC (#327).
- Documenting the two office2 deploy-path boundary (pull-based agent-prompt-sync vs
  felix-deployer `deploys/queued/`) — separate follow-up issue.
