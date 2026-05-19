# Tasks: Shared JSONL state-log library

**Mission**: `shared-jsonl-state-log-library-01KS0E9A`
**Mission ID**: `01KS0E9A6TZBA9AWT97DR1XMQB`
**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Source issue**: [#305](https://github.com/kentonium3/kg-automation/issues/305)
**Branch strategy**: planning_base=`main`, merge_target=`main`, branch_matches_target=`true`

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create `scripts/common/__init__.py` (empty marker) | WP01 | [P] | [D] |
| T002 | Create `scripts/common/state_log_schema.py` (DOMAIN_STATES, REQUIRED_FIELDS, dataclass, validators) | WP01 | | [D] |
| T003 | Create `scripts/common/state_log.py` core (`append`, `read`, fcntl locking, idempotency scan, bootstrap) | WP01 | | [D] |
| T004 | Add `__main__` CLI to `state_log.py` (argparse subcommands `append` and `read`) | WP01 | | [D] |
| T005 | Create `docs/design/architecture/data/agent-state-log-schema.md` (FR-012 schema doc) | WP01 | [D] |
| T006 | Update `docs/INDEX.md` to reference the new schema doc | WP01 | [D] |
| T007 | Create `tests/common/__init__.py` | WP02 | [D] |
| T008 | Create `tests/common/test_state_log_append.py` (happy path, validation rejections, idempotency, bootstrap) | WP02 | | [D] |
| T009 | Create `tests/common/test_state_log_read.py` (filter combinations, empty file, TypeError on unknown kwarg) | WP02 | [D] |
| T010 | Create `tests/common/test_state_log_concurrent.py` (multiprocessing concurrent-append, NFR-003) | WP02 | [D] |
| T011 | Create `tests/common/test_state_log_cli.py` (subprocess CLI tests, exit codes) | WP02 | [D] |

`[P]` = parallel-safe (different file/concern; no inter-subtask dependency)

---

## Work Packages

### WP01 — Library core + schema documentation

**Prompt**: [tasks/WP01-library-core-and-schema-docs.md](tasks/WP01-library-core-and-schema-docs.md)
**Goal**: Produce the production-ready Python library (`scripts/common/state_log.py` + `state_log_schema.py`) and the public schema documentation. Foundation for all downstream phases.
**Priority**: P0 (foundational; WP02 depends on this)
**Dependencies**: none
**Estimated prompt size**: ~400 lines

#### Included subtasks

- [x] T001 Create `scripts/common/__init__.py` (empty marker)
- [x] T002 Create `scripts/common/state_log_schema.py` (DOMAIN_STATES, REQUIRED_FIELDS, dataclass, validators)
- [x] T003 Create `scripts/common/state_log.py` core (`append`, `read`, fcntl locking, idempotency scan, bootstrap)
- [x] T004 Add `__main__` CLI to `state_log.py`
- [x] T005 Create `docs/design/architecture/data/agent-state-log-schema.md`
- [x] T006 Update `docs/INDEX.md` to reference the new schema doc

#### Implementation sketch

1. Lay down the `scripts/common/` package (T001).
2. Write the schema module first (T002) — pure data + validators with no I/O. This gives WP02 a stable validation surface to test against.
3. Build the I/O layer (T003) on top of the schema module: append + read + bootstrap + locking.
4. Layer the CLI (T004) as a thin wrapper on the public Python API.
5. Document the contract (T005) — same schema content as in code, written for human / agent consumption.
6. Wire the new doc into the architecture INDEX (T006).

#### Parallel opportunities

T001, T005, T006 are independent of one another and of T002/T003/T004 sequencing. An implementer can write the empty `__init__.py` + start the schema doc draft + edit INDEX.md in parallel with the code work.

#### Risks

- **fcntl semantics on macOS dev vs Linux office2**: POSIX advisory locks work the same on both for our purposes (same-host, same-fs). Verify with the multiprocess test in WP02.
- **`/data/services/openclaw/state/` doesn't exist yet on office2**: library MUST self-bootstrap. Don't silently swallow `PermissionError` — surface as `OSError`.
- **Schema doc drift**: the doc is hand-authored; the code is the source of truth. WP02's tests verify the code's enums; consider a future canary that cross-checks the doc against `DOMAIN_STATES`.

#### Success criteria (from spec.md)

Verified by code structure + the WP02 test suite:
- SC-001, SC-002, SC-003, SC-005, SC-006

---

### WP02 — Test suite (happy path, validation, idempotency, concurrency, CLI)

**Prompt**: [tasks/WP02-test-suite.md](tasks/WP02-test-suite.md)
**Goal**: Exhaustive test coverage of the library — happy path, every validation failure mode, idempotency, multiprocess concurrent-append safety, and CLI surface. Establish the ≥ 90% coverage floor.
**Priority**: P0 (verification of WP01)
**Dependencies**: **WP01** (tests import / invoke the library)
**Estimated prompt size**: ~450 lines

#### Included subtasks

- [x] T007 Create `tests/common/__init__.py`
- [x] T008 Create `tests/common/test_state_log_append.py`
- [x] T009 Create `tests/common/test_state_log_read.py`
- [x] T010 Create `tests/common/test_state_log_concurrent.py`
- [x] T011 Create `tests/common/test_state_log_cli.py`

#### Implementation sketch

1. Initialize the `tests/common/` package (T007).
2. Cover `append` exhaustively (T008): happy path (with bootstrap of `/data/services/openclaw/state/`), each REQUIRED_FIELDS missing case, each domain enum rejection (3 domains × 1 invalid state each), each field-type rejection, the idempotency dedup.
3. Cover `read` (T009): each filter combination, empty-file behavior, range filters, unknown kwarg → TypeError, unknown domain → ValueError.
4. Cover concurrency (T010): multiprocessing.Pool with N=10 workers × M=10 records each = 100 writes, assert 100 unique well-formed lines.
5. Cover CLI (T011): `subprocess.run` invocations against `python3 -m scripts.common.state_log`, verify stdin/stdout/stderr/exit-code for each subcommand and each error path.

#### Parallel opportunities

T008-T011 each target a different test file and a different concern of the library. After T007, the four test files can be written in parallel. (For spec-kitty's single-implementer-per-WP model, this means the implementer doesn't need to thread between them — finish one, then start the next.)

#### Risks

- **Coverage measurement**: NFR-005 requires ≥90% line + branch. The CLI wrapper might be hard to fully cover via subprocess; include direct unit tests of the argparse parser if needed.
- **Tempdir for tests**: Tests MUST use `tmp_path` (pytest fixture) or `tempfile.TemporaryDirectory`, NOT the production `/data/services/openclaw/state/`. Use the `state_log` module's path-parameterization (if added in WP01) or monkey-patch the constant.
  - **Coordination note for WP01**: state_log.py should expose the state-dir path as an importable constant (e.g., `STATE_DIR = Path("/data/services/openclaw/state")`) so tests can monkey-patch it. Document this in T003.
- **Multiprocess test on different OSes**: macOS uses spawn, Linux uses fork by default. Test should explicitly set `multiprocessing.set_start_method("spawn", force=True)` for portability.
- **Concurrent-test flakiness**: 100 trials should be deterministic with proper locking; if flaky, that IS the NFR-003 failure surfacing.

#### Success criteria (from spec.md)

Verified by these tests:
- SC-001 (append latency: NFR-001 assertion)
- SC-002 (read latency: NFR-002 assertion)
- SC-003 (typo rejection: validation-rejection tests in T008)
- SC-004 (concurrent-write correctness: T010)
- SC-005 (idempotency: dedup test in T008)
- SC-007 (≥90% coverage: measured by `coverage run -m pytest tests/common/`)

---

## Dependency graph

```
WP01 (library core + docs, no deps, P0)
  └── WP02 (tests, depends on WP01, P0)
```

Linear dependency chain. No parallel execution opportunity between WPs in this mission (the dependency is hard — tests need the library).

## MVP scope

Both WPs are required for the foundation library to be "done" per the spec. WP01 alone delivers a working library that consumer phases COULD adopt, but without WP02 the NFR-005 coverage target and NFR-003 concurrency proof aren't met. **MVP = WP01 + WP02** (the full mission scope).

## Parallelization summary

Within WPs:
- WP01: T001 + T005 + T006 are parallel-safe with the code subtasks (different files, no shared content)
- WP02: T007 then T008/T009/T010/T011 can all proceed independently after T007

Across WPs: WP02 strictly depends on WP01 — no cross-WP parallelization.

## Notes for implementers

- Constraint C-001 is hardcoded: state files MUST live under `/data/services/openclaw/state/`. Tests parameterize this only for isolation (tmp dirs); production code does NOT support changing the path.
- Constraint C-004 (no network I/O): the library MUST NOT `import urllib`, `import http`, `import socket`, etc. Tests should grep the implementation files to assert this if a clean lint pass is desired.
- The state enums in T002 are LOCKED IN per Kent's 2026-05-19 discovery decision (Option A — strict per-domain enums). Adding states later requires a PR to this library, NOT a runtime extension.
