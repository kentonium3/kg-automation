---
work_package_id: WP03
title: Ledger — binding, attempts, durability, summaries
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-003
- FR-005
- FR-007
- NFR-001
- NFR-002
- NFR-007
planning_base_branch: feat/849-arms-run
merge_target_branch: feat/849-arms-run
branch_strategy: Planning artifacts for this mission were generated on feat/849-arms-run. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-arms-run unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
- T015
phase: Phase 1 - Core
history: []
agent_profile: python-pedro
authoritative_surface: scripts/research/arms849/ledger.py
create_intent:
- scripts/research/arms849/ledger.py
- tests/research/test_arms849_ledger.py
execution_mode: code_change
owned_files:
- scripts/research/arms849/ledger.py
- tests/research/test_arms849_ledger.py
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP03 — Ledger

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load`
(profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope,
and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch**: `feat/849-arms-run`
- **Final merge target**: `feat/849-arms-run`
- `/spec-kitty.implement` populates the actual worktree `base_branch` from `lanes.json`.
- If human instructions contradict these fields, stop and resolve the landing branch.

## Objective

Extract the ledger out of `run_849_harness.py` into `arms849/ledger.py` and make it the one the
spec describes: bound to one corpus, prompt, question manifest, serving configuration and code;
every attempt durable **before** it starts; crash-safe on a torn final line; one writer; never
averaging a non-scored cell. Read first: `data-model.md` §Ledger/§Outcome; `contracts/ledger-schema.md`;
`research.md` D-10, D-12, D-13, D-16; the existing `run_849_harness.py` (`open_ledger`,
`_append`, `read_ledger`, `summarise`, `LedgerBoundToAnotherCorpus`) — you are moving and
extending that behaviour, keeping its tests' intent (WP08 re-points the harness to this module).

## Subtasks

### T011 — Header binding

**Steps**:
1. `@dataclass class Header` with every field in data-model.md §Ledger (record, started (explicit
   UTC), registration_commit, corpus, prompt_hash, question_manifest_sha, serving (dict),
   model_context_tokens, limit_applied, run_env_commit, run_env_manifest_sha, code_hashes,
   preflight_sha, blinding_seed, recovery_log, plan).
2. `Binding.from_environment(corpus_dir, serving, export_manifest, preflight, code_paths)`: computes
   corpus fingerprints (reuse `load_849_corpus.fingerprint`), reads the prompt and manifest
   digests from `arms849.prompt` / `arms849.questions` **constants**, hashes the code files'
   contents.
3. `open_ledger(path, binding) -> Ledger`: first use writes the Header; on resume compares
   **every** binding field and raises `LedgerBoundToAnotherConfig(differences)` naming each
   differing field with both values (extend the existing message style: "runs from two
   configurations averaged together are indistinguishable…").
4. The header is immutable: `Ledger` exposes no way to rewrite line 1.

### T012 — Attempts

**Steps**:
1. `begin_attempt(key) -> attempt_no`: appends `{"record": "attempt_start", arm, question, repeat,
   attempt, ts}` **before** returning; `attempt_no` = count of prior `attempt_start` rows for the
   key + 1; raises `AttemptsExhausted` if that would exceed 3 (FR-007; D-12).
2. `record(key, row)`: appends a `run` row; enforces I2 (no second `ok` for a key), I3, I4
   (`exceeds_model_context` rows carry `prompt_tokens > model_context_tokens`), and the serving
   equality assertion on every append.
3. `terminal(key) -> Outcome | None`: `ok` or `exceeds_model_context` if present, `error` if three
   attempts have failed, else `None`.
4. `pending_keys(plan) -> list[RunKey]` in protocol order, skipping terminal keys (the resume
   contract: an interrupted attempt with no `run` row counts as one attempt used).
5. Per-attempt timeout is a **value** the ledger stores on the row (`elapsed_s`, `error:
   timeout`); the enforcement lives in the harness (WP08). Document the split.

### T013 — Durability and the lock

**Steps**:
1. `_append`: one JSON line, `flush`, `os.fsync` (keep the existing implementation's reasoning).
2. Lock: on open, `fcntl.flock(LOCK_EX | LOCK_NB)` on `path + ".lock"` holding the pid; a second
   opener raises `LedgerLocked(holder_pid)`; released on close/exit (context manager).
3. Reader: under the lock, parse every line; if **only the last** line fails to parse, truncate
   the file to the previous newline, append `recovered_torn_tail@<ts>` to the header's
   `recovery_log` (by rewriting?? — no: the header is immutable; write the recovery note as an
   `event` row instead and keep `recovery_log` as a derived view), and continue; any interior
   malformed line raises `LedgerCorrupt(line_no)`.
4. `event(kind, detail)`: appends `{"record": "event", kind, detail, ts}` for `server_restart`,
   `cache_clear`, `gate`, `halt`, `recovered_torn_tail`.

### T014 — `summarise`

**Steps**:
1. Over `run` rows with `outcome == "ok"` only: per (arm, question) `n_scored`, mean/range of
   `assembled_context_tokens` and `prompt_tokens`, sums of the cache split, `cold` = rows with
   `cache_state == "cold"` (observed, D-13) vs `warm`, `r_g_ratio` list; plus counts of every
   other outcome and of attempts. Keep the existing `summarise` tests' intent: a cell with no
   number can never read as zero.
2. `calibration()`: returns the single `calibration` record or `None`; `has_terminal_error(arm,
   repeat)` for D-10's halt rule (WP04 uses both).
3. `grading_rows()`: the `ok` rows with `text`, `truncated`, keyed for WP08's exporter.

### T015 — Tests

**File**: `tests/research/test_arms849_ledger.py` (~250 lines). Must include: header refusal on
each binding field individually (parametrised); `attempt_start` precedes `run`; a fourth attempt
refused; second `ok` for a key refused; serving mismatch on append refused; **kill-mid-write**:
write a valid ledger, append half a line, reopen → recovered, one `event` row, rows intact;
interior corruption → `LedgerCorrupt`; second writer refused while the first holds the lock (use
a subprocess); `summarise` excludes non-`ok` and never yields 0 for an exceeds cell.

## Definition of Done

- `arms849/ledger.py` carries the behaviour `run_849_harness.py` had plus D-10/D-12/D-13/D-16;
  the harness is **not** modified in this WP (WP08 re-points it); tests green; `mark-status T011
  T012 T013 T014 T015 --status done`.

## Risks / reviewer guidance

- Reviewer: the torn-tail recovery must be provably limited to the **last** line; try a torn line
  in the middle and confirm `LedgerCorrupt`.
- The binding comparison must be exhaustive — a new header field that is not compared is a
  silent hole; assert in a test that every `Header` field is in the compared set.
