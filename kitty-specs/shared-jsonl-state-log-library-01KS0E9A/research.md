# Research: Engineering decisions

**Mission**: `shared-jsonl-state-log-library-01KS0E9A`
**Phase**: 0 (research — resolve all clarifications before design)

This document records the load-bearing engineering decisions for this mission. Each decision is justified against the spec's NFRs and constraints, and the rejected alternatives are listed so future maintainers can see what was considered.

No external research was commissioned — all decisions are derived from established stdlib patterns + the spec's explicit constraints.

---

## D1 — Locking strategy

**Decision**: Use `fcntl.LOCK_EX` (POSIX advisory exclusive lock) on the data file's own file descriptor, held across the entire read-check-write sequence.

**Rationale**:
- The append flow is: open file → acquire lock → linear scan for `(task_id, date, state)` tuple → if absent, write line → release lock → close. The lock must span the scan + write, else a second writer could find "no existing record" simultaneously and produce a duplicate.
- POSIX advisory locks via `fcntl.LOCK_EX` are the stdlib standard; they're respected by any cooperating process on the same kernel.
- File-on-itself locking (vs a sibling lockfile) keeps the locked resource and the protected resource colocated. No risk of lockfile drift, stale removal, or missing-after-restart issues.

**Rejected alternatives**:
- **Sibling lockfile** (e.g., `habits-history.jsonl.lock`): adds a second file per domain, requires cleanup logic on abnormal exit, no real benefit over file-on-itself.
- **`flock` shell command via subprocess**: same primitive but adds a subprocess and shell-quoting concerns. Less direct than the Python stdlib call.
- **No locking, rely on O_APPEND atomicity**: O_APPEND only guarantees that a single `write()` syscall is atomic; it does NOT prevent two readers from seeing identical "no existing record" state and both writing. Idempotency would be silently broken.

**NFR coverage**: NFR-003 (100% pass rate on 100 concurrent-write trials).

---

## D2 — Idempotency mechanism

**Decision**: Linear scan of the existing file for any line whose `(task_id, date, state)` tuple matches the incoming record. If found, no-op return. If absent, append.

**Rationale**:
- Scan happens inside the locked critical section, so it sees a stable snapshot.
- Expected file size is ~10k lines worst case (NFR-001's reference horizon) — linear scan is well under the 50 ms p99 budget.
- No external index, no separate state — the file IS the state. Robust to corruption (worst case: a partial line at end-of-file is treated as "different from incoming" and dedup misses once; one duplicate line is acceptable degradation vs implementing index repair).

**Rejected alternatives**:
- **Hash index sidecar**: faster lookup, but introduces a second file that can drift out of sync with the data. Complexity > benefit for our volumes.
- **SQLite-backed state**: introduces a third-party dep concern (only stdlib per NFR-004 — though sqlite3 IS stdlib, the file-format change is invasive).

**NFR coverage**: NFR-001 (< 50 ms p99 @ 10k lines).

---

## D3 — Validation implementation

**Decision**: Hand-written validators in `state_log_schema.py`. No external JSON-schema library.

**Rationale**:
- NFR-004 mandates zero third-party deps.
- The schema is small (7 required fields, 3 domain enums, a handful of type checks). A few dozen lines of Python is sufficient.
- Hand-written validators give precise error messages tied to the spec's contract (e.g., `"state 'Complet' not in habits enum {complete, incomplete, skipped}"`), more useful than a generic jsonschema error.

**Rejected alternatives**:
- **`jsonschema` package**: third-party dep, more general than we need.
- **`pydantic`**: third-party dep, much more general than we need.
- **`dataclasses` alone**: stdlib but only provides type hints, not runtime validation. We use dataclasses for the in-memory record representation but layer hand-written validation on top.

**NFR coverage**: NFR-004 (zero third-party deps).

---

## D4 — CLI surface

**Decision**: Thin `__main__` wrapper exposing two subcommands:

```
python3 -m scripts.common.state_log append --domain <name> < record.json
python3 -m scripts.common.state_log read --domain <name> [--task-id N] [--date YYYY-MM-DD] [--date-from ...] [--date-to ...] [--state ...] [--source ...]
```

- `append` reads a single JSON object on stdin (one line), writes via the library's `append()` function. Exit 0 on success or idempotent no-op. Exit non-zero on validation failure (with stderr message).
- `read` writes matching records to stdout, one JSON object per line. Exit 0 always (empty result is OK).

**Rationale**:
- LLM agents that invoke the library via `Bash exec` need a CLI. C-005 mandates the dual surface.
- Subcommand style matches existing helpers in `scripts/` (e.g., `prescan.py`, `provision_felix_bot.py`).
- JSON on stdin / JSON on stdout is the existing pattern in `scripts/inbox/` and other helpers.

**Rejected alternatives**:
- **Flag-only invocation (no stdin)**: requires JSON-encoded record on the command line, which exposes secrets in `ps` output and shell history. Stdin is the safe path.
- **Separate `append-cli.py` + `read-cli.py` scripts**: duplicates the `__main__` boilerplate; subcommands keep one entry point.

---

## D5 — Concurrent-write test methodology

**Decision**: `tests/common/test_state_log_concurrent.py` uses `multiprocessing.Pool` to spawn N=10 worker processes, each calling `append` M=10 times against the same domain (100 total writes targeting 100 distinct records). After all complete, assert:

1. File has exactly 100 lines.
2. Each line parses as JSON (no interleaving, no truncation).
3. Each line's `(task_id, date)` matches one of the expected 100 distinct identities (no duplicates from race, no losses).

**Rationale**:
- Multiprocessing spawns true OS processes, exercising the cross-process fcntl lock (not just in-process threading).
- 100 writes is enough to surface races in a non-locking implementation immediately; small enough to keep the test fast (< 5s).
- Verifying line count + parse + identity uniqueness covers all three failure modes (interleave, truncate, dedup race).

**Rejected alternatives**:
- **threading.Thread**: GIL serializes Python execution, so threads don't faithfully reproduce cross-process races on the file.
- **Subprocess shell loop**: works but adds shell startup overhead per iteration; multiprocessing.Pool is cleaner.

**NFR coverage**: NFR-003 (100% pass rate over 100 concurrent-write trials). The single test trial IS the 100-trial assertion.

---

## D6 — Atomic-append technique

**Decision**: Open the file with `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, mode=0o664)`, then `fcntl.flock(fd, fcntl.LOCK_EX)` before any read. Use `os.fdopen()` for read access alongside the same fd.

**Rationale**:
- `O_APPEND` ensures each `write()` is positioned at end-of-file atomically at the kernel level. Combined with the exclusive lock, this means another process holding the lock cannot interleave.
- The 0664 mode is set at open time; we don't rely on later `chmod` (which could race).
- Reading from the same fd avoids the open-twice race where a second writer could append between our read and our write.

**Rejected alternatives**:
- **Open separately for read and write**: race window between close-after-read and reopen-for-write.
- **Read entire file, then truncate-and-rewrite**: violates "append-only" and risks data loss on crash mid-write.

---

## D7 — Directory + permission setup

**Decision**: At first `append`, ensure `/data/services/openclaw/state/` exists with mode 0775 owner claude:secondbrain. If absent, create via `pathlib.Path.mkdir(parents=True, mode=0o775)`. The setgid bit on the parent is NOT relied upon — we set group ownership explicitly via `os.chown` if the resulting group doesn't match `secondbrain`.

**Rationale**:
- The library may be the first thing to touch this path post-install. Self-bootstrapping is required (FR-008).
- The `secondbrain` group is the existing convention for claude+kgale shared vault access on office2 (per recent #322/#323 work).

**Rejected alternatives**:
- **Require operator pre-create the directory**: brittle; doc/runbook drift risk.
- **Mode 0777**: too permissive given system-level data sensitivity.

---

## D8 — Tests location

**Decision**: `tests/common/test_state_log_*.py`. Three files for clarity:
- `test_state_log_append.py` — happy path + validation rejections + idempotency
- `test_state_log_read.py` — filter combinations + empty-file behavior
- `test_state_log_concurrent.py` — multiprocessing concurrent-write test

**Rationale**:
- Mirrors `scripts/common/` source layout: one test module group per source group.
- Three files keep each focused on a single concern; easier to attribute test failures to the right behavior.
- The existing `tests/` tree (e.g., `tests/inbox/`, `tests/vikunja/`) uses the same per-domain pattern.

**NFR coverage**: NFR-005 (≥ 90% line + branch coverage measured by `coverage.py`).

---

## D9 — Out-of-scope: rotation, async, cross-host

These were explicitly listed as out-of-scope in the spec. Not researched. Will be revisited when a consumer phase needs them.

- **Rotation**: append-forever is acceptable until any single domain file exceeds ~10k lines (multi-year horizon). If/when needed, a separate utility script can rotate by year.
- **Async I/O**: every known consumer is synchronous (cron job + agent invocation). Async only becomes interesting if webhook receivers land (ADR-0002 Phase 8).
- **Cross-host locking**: there is only one host (office2). N/A.

---

## Summary

Nine engineering decisions documented, all aligned with the spec's NFRs and constraints. No `[NEEDS CLARIFICATION]` markers remain. Ready for Phase 1 design artifacts.
