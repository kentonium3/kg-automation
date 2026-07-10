---
work_package_id: WP03
title: Completion-assertion ledger + verifier + Vikunja auto-emit
dependencies: []
requirement_refs:
- FR-001
- FR-004
- FR-005
- FR-006
- NFR-001
tracker_refs: []
planning_base_branch: fix/felix-truthful-reporting
merge_target_branch: fix/felix-truthful-reporting
branch_strategy: Planning artifacts for this mission were generated on fix/felix-truthful-reporting. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-truthful-reporting unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
phase: Phase 1 - Detection
assignee: ''
agent: claude
agent_profile: "python-pedro"
history:
- at: '2026-07-10T18:45:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/trust/
create_intent:
- scripts/trust/completion_assertion.py
- scripts/trust/assertion_verifier.py
- tests/trust/test_completion_assertion.py
- tests/trust/test_assertion_verifier.py
execution_mode: code_change
owned_files:
- scripts/trust/completion_assertion.py
- scripts/trust/assertion_verifier.py
- scripts/vikunja/create_task.py
- tests/trust/test_completion_assertion.py
- tests/trust/test_assertion_verifier.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before doing anything else, load your assigned agent profile via the
`/ad-hoc-profile-load` skill (pass the `role`/`agent` from this WP's
frontmatter). It applies your identity, governance scope, boundaries, and the
initialization declaration for this session. Do not begin implementation until
the profile is loaded and its initialization declaration is complete.

## Branch Strategy

- Current branch at workflow start: `fix/felix-truthful-reporting`.
- Planning/base branch for this feature: `fix/felix-truthful-reporting`.
- Completed changes must merge into `fix/felix-truthful-reporting`.
- The concrete lane/worktree for this WP is resolved by `/spec-kitty.implement`
  at dispatch time — do not create branches or worktrees by hand. Let the
  workflow place your commits.

## Objectives & Success Criteria

This WP delivers the **deterministic completion-assertion action ledger**, its
**verifier library**, and a **fail-safe auto-emit hook** on the Vikunja task
helper. Emission is deterministic (the creation helper auto-emits on success) —
NOT free-form agent compliance. The verifier grounds asserted artifacts against
their existence in the owning system.

Scope of this WP (alert emission, the timer, and the scan runner belong to WP04):

- **FR-001** (detection contribution) — the ledger + verifier are the
  artifact-grounding half of "report an action complete only when it actually
  happened and can be corroborated." (The verbal-lie blind spot is doctrine-only,
  out of scope.)
- **FR-004** — a deterministic action ledger: when a supported artifact is
  created on behalf of a delegated request, the creating **helper** records a
  structured completion-assertion (`artifact_kind` + id **list**, grounded in the
  creation result) with a correlation ref when available.
- **FR-005 (verification half)** — the verifier detects a completion-assertion
  whose named artifact cannot be corroborated in its owning system
  (`artifact_missing`). Rendering/emitting that finding as an alert is WP04.
- **FR-006(a)** — bounded to emitted completion-assertions whose artifacts can be
  checked against their owning system; deterministic, no general verifier.
- **Multi-artifact support** — the motivating case created **7 Vikunja reminder
  tasks** from one request. One assertion therefore carries a **list** of
  `artifact_ids`, each verified independently.
- **Fail-safe (NFR-001)** — a ledger-write failure must **never** break task
  creation. `record_assertion` swallows its own errors, logs, returns falsey, and
  never raises into the caller.

Success = the record helper (+ CLI), the verifier library, and the localized
non-breaking Vikunja hook are implemented and unit-tested green, with the
existing Vikunja `create_task` tests still passing.

## Context & Constraints

- **python3-only** (office2 has no `python` binary). Invoke helpers as
  `python3 -m scripts.trust.completion_assertion` / `-m scripts.trust.assertion_verifier`.
- **Append-only JSONL with `fcntl.LOCK_EX`.** Mirror the established pattern in
  `scripts/common/alert_bus/ledger.py` (#706): `os.open(..., O_WRONLY | O_CREAT | O_APPEND, 0o600)`,
  `fcntl.flock(fd, LOCK_EX)` around the write, `LOCK_UN` + `close` in `finally`,
  `path.parent.mkdir(parents=True, exist_ok=True)`. One JSON object per line.
- **Ledger home is env-overridable.** Read a dir from
  `FELIX_TRUST_ASSERTIONS_DIR`; default `/data/services/trust/assertions/`.
  Files are date-partitioned `<YYYY-MM-DD>.jsonl` (same shape as the #706 ledger).
  Tests point the env var at a tmpdir — no office2 calls.
- **NO LLM anywhere** in this WP. Verification is deterministic existence-checking
  only. Do not introduce any model call, judge, or semantic comparison.
- **Deterministic verification only** — per-id lookups against the owning system,
  with `unverifiable_kind` (warn) as the safe fallback where no cheap existence
  check exists (avoids false `artifact_missing`).
- **Schemas are fixed** by `data-model.md` (`CompletionAssertion`,
  `AssertionFinding`) and `contracts/detector-cli.md` (C4, C5). `artifact_ids` is
  a **list[str]**; `ts` is ISO-8601 UTC.
- This WP does **not** create `scripts/trust/__init__.py` or
  `tests/trust/__init__.py` — WP02 owns those. Do not add or edit them here.

## Subtasks & Detailed Guidance

### T011 — `scripts/trust/completion_assertion.py` (record helper + CLI)

- **Purpose**: The deterministic, fail-safe append-only ledger writer for
  completion-assertions, plus a thin CLI for the manual/bypass path.
- **Steps**:
  - Public API:
    `record_assertion(agent: str, artifact_kind: str, artifact_ids: list[str], claim: str, request_ref: str | None = None) -> bool`.
  - Build one record matching the `CompletionAssertion` schema in `data-model.md`:
    `ts` (ISO-8601 UTC, e.g. `datetime.now(timezone.utc).isoformat()`), `agent`,
    `request_summary` (optional; may be omitted/`None`), `request_ref` (default
    `None` — no outbound-message log exists today), `artifact_kind`, `artifact_ids`
    (the **list**, preserved verbatim), `claim`.
  - Append it as one `json.dumps(...) + "\n"` line under `fcntl.LOCK_EX`, mirroring
    `_append_line` in `scripts/common/alert_bus/ledger.py`. Resolve the target file
    from an `assertions_dir()` helper reading `FELIX_TRUST_ASSERTIONS_DIR`
    (default `/data/services/trust/assertions/`), date-partitioned by UTC day.
  - **Best-effort / fail-safe**: wrap the whole body in a top-level
    `try/except Exception` that logs (stderr / `logging`) and `return False` — it
    must **NEVER** raise into the caller. `return True` only on a successful write.
    (Mirror `record_alert`'s discipline exactly.)
  - Thin argparse CLI (for the manual/bypass path):
    `python3 -m scripts.trust.completion_assertion --agent … --artifact-kind … --artifact-id X --artifact-id Y --claim …`
    with repeated `--artifact-id` collected into the list
    (`action="append"`), plus optional `--request-ref`. The CLI calls
    `record_assertion`, prints a short status line, and returns **non-zero on
    failure** but **never raises** (guard the whole `main()` body).
- **Files**: `scripts/trust/completion_assertion.py`.
- **Notes**: Export `record_assertion`, `assertions_dir`, and the env-var name
  via `__all__`. Keep it small and self-contained; no dependency on the verifier.

### T012 — `scripts/trust/assertion_verifier.py` (verifier library)

- **Purpose**: Deterministically ground each asserted artifact against its owning
  system, returning `AssertionFinding` objects (per `data-model.md` / C5).
- **Steps**:
  - `verify_assertion(a) -> list[AssertionFinding]` where `a` is a
    `CompletionAssertion` (dict or value object). Verify **each** id in
    `artifact_ids` **independently**; return zero or more findings (one per
    missing/unverifiable id).
  - `artifact_kind == "vikunja_task"` → look up each id via the Vikunja client.
    Reuse the client builder pattern from `scripts/vikunja/create_task.py`
    (`_build_client()` → `scripts.common.vikunja_client.VikunjaClient`; e.g.
    `client.get(f"/tasks/{id}")`). Any id not found → an `artifact_missing`
    finding (`kind="artifact_missing"`, carrying `agent`, `artifact_kind`,
    `artifact_id`, `claim`).
  - `artifact_kind in {"calendar_event", "vault_note"}` → no cheap existence
    check today → one `unverifiable_kind` (**warn**) finding rather than a false
    `artifact_missing`.
  - `artifact_kind == "other"` → `unverifiable_kind` (warn).
  - Accept an injectable client (parameter or `_build_client()` default) so tests
    can pass a mock; **no office2 calls** in tests.
  - Deterministic; **no LLM**. Treat a client lookup that raises "not found" (or
    returns falsey) as missing; a transient client error should be handled
    conservatively (log + do not fabricate a false `artifact_missing` — prefer to
    surface it as a non-finding or an `unverifiable_kind` so a Vikunja outage does
    not spam missing-artifact alerts).
  - Also expose a **clean reader** helper — e.g.
    `iter_recent_assertions(since_offset: int | None = None)` or
    `read_assertions(path)` — that reads and iterates the recent assertion JSONL
    (one dict per line, tolerant of blank/partial trailing lines). WP04's runner
    will call this and advance a watermark; keep the reading concern here and the
    watermark/state concern in WP04.
- **Files**: `scripts/trust/assertion_verifier.py`.
- **Notes**: Represent `AssertionFinding` as a small dataclass or dict matching
  the data-model fields. Do **not** import or trigger alert emission here — that
  is WP04. Export the public functions via `__all__`.

### T013 — Vikunja auto-emit hook in `scripts/vikunja/create_task.py`

- **Purpose**: Deterministically emit a completion-assertion on every successful
  Vikunja task create, so an honest creation always leaves a ledger record.
- **Steps**:
  - After a **successful** create (the `task` dict returned from `create_task()`
    in `main()`, which carries `task["id"]`), call:
    ```python
    from scripts.trust.completion_assertion import record_assertion
    record_assertion(
        agent=<resolved agent>,
        artifact_kind="vikunja_task",
        artifact_ids=[str(task.get("id"))],
        claim=<short claim, e.g. f"Created Vikunja task #{task.get('identifier')}">,
    )
    ```
  - **Wrap the hook in its own `try/except Exception`** so any failure (import
    error, write error, anything) is swallowed — **task creation must still
    return success (exit 0) even if the assertion write fails.** Do not let the
    hook alter `main()`'s return value or `create_task()`'s return contract.
  - Determine the agent identity from an env var / optional arg with a sensible
    default (e.g. read `FELIX_AGENT`/`FELIX_TRUST_AGENT` env, default `"main"` or
    `"unknown"`). Keep it a single localized resolution; do not thread it through
    the whole call chain.
  - Keep the change **minimal and localized** — the hook lives on the success path
    of `main()` (after `task` is obtained, before/around the existing print).
    `create_task()` (the pure PUT helper) keeps its exact signature and return
    type. Do not import `record_assertion` at module top if that risks a hard
    import failure on office2 — import it lazily inside the guarded hook.
- **Files**: `scripts/vikunja/create_task.py` (owned by this WP).
- **Notes**: The `task` dict carries `id` (API id) and `identifier` (UI `#NN`).
  Assert on `str(id)` — that is what the verifier looks up via `/tasks/{id}`.

### T014 — Unit tests

- **Purpose**: Prove roundtrip, multi-artifact, per-id verification, fail-safe,
  and non-breaking hook behavior — all with mocks, no office2.
- **Steps** — `tests/trust/test_completion_assertion.py`:
  - **Record roundtrip**: point `FELIX_TRUST_ASSERTIONS_DIR` at a tmpdir,
    `record_assertion(...)` returns `True`, read the written JSONL line back and
    assert `artifact_ids` is preserved as a **list** and all fields match.
  - **Multi-artifact**: record with **7** ids; read back and assert the list of 7
    survives intact.
  - **Fail-safe**: simulate a write error (e.g. monkeypatch the append/`os.open`
    to raise, or point the dir at an unwritable path) → `record_assertion` returns
    `False` and **does not raise**.
  - **CLI**: invoke the argparse CLI with repeated `--artifact-id`; assert the
    list is collected and a non-zero exit on a forced failure without raising.
- **Steps** — `tests/trust/test_assertion_verifier.py`:
  - **`artifact_missing`**: mock the Vikunja client so a given id is not found →
    `verify_assertion` returns an `artifact_missing` finding for that id.
  - **Per-id independence**: a mix of present + missing ids in one assertion →
    exactly the missing ones produce findings.
  - **`unverifiable_kind`**: `artifact_kind` in `{"other","calendar_event"}` →
    `unverifiable_kind` (warn) finding, no client lookup / no `artifact_missing`.
  - **Vikunja hook non-breaking**: call `create_task.main(...)` with a mock
    Vikunja client for a successful create, and force `record_assertion` to raise
    (monkeypatch) → `main` still returns `0` and the created-task output is
    unchanged.
  - Mock the Vikunja client throughout (`_build_client` or an injected client);
    **NO office2 calls**.
- **Files**: `tests/trust/test_completion_assertion.py`,
  `tests/trust/test_assertion_verifier.py`.
- **Notes**: Use `monkeypatch.setenv("FELIX_TRUST_ASSERTIONS_DIR", str(tmp_path))`.
  Do not create `tests/trust/__init__.py` (WP02 owns it) — rely on pytest
  rootdir/`conftest` discovery already established by WP02.

## Test Strategy

Run the WP's unit tests with branch coverage on the new package:

```
python3 -m pytest tests/trust/test_completion_assertion.py tests/trust/test_assertion_verifier.py -v --cov=scripts/trust --cov-branch
```

Prove no regression on the Vikunja helper by also running its existing tests:

```
python3 -m pytest tests/vikunja/ -v
```

(If the existing Vikunja tests live under a different path, discover it — e.g.
`python3 -m pytest -k create_task -v` — and run that. The hook must not change
any existing assertion in those tests.)

All tests are deterministic and mock the Vikunja client and the alert bus; no
network, no office2, no LLM.

## Definition of Done

- [ ] `record_assertion(...)` writes one append-only JSONL line under
      `fcntl.LOCK_EX`, `artifact_ids` a list, env-overridable dir; is best-effort
      / fail-safe (returns `False`, never raises).
- [ ] CLI accepts repeated `--artifact-id`, returns non-zero on failure, never
      raises.
- [ ] `verify_assertion` checks **each** id independently — `artifact_missing`
      for a missing `vikunja_task` id, `unverifiable_kind` for
      `other`/calendar/vault — deterministically, no LLM. Clean reader helper
      exposed for WP04.
- [ ] Vikunja `create_task` auto-emits an assertion on success via a **fail-safe**
      hook that never breaks task creation and keeps `create_task`'s return
      contract.
- [ ] New unit tests cover roundtrip, multi-artifact (7 ids), per-id
      verification, `unverifiable_kind`, fail-safe, and non-breaking hook — all
      green.
- [ ] Existing Vikunja `create_task` tests still green (no regression).

## Risks

- **The hook must never break task creation.** This is the single highest risk:
  the auto-emit must be wrapped so any failure (import, write, agent resolution)
  is swallowed and task creation still returns success. Verify this with a test
  that forces `record_assertion` to raise.
- **No LLM.** Verification is deterministic existence-checking only. Do not add a
  model call, judge, or semantic comparison anywhere.
- **Preserve `create_task`'s contract.** `create_task()` (the pure PUT helper)
  keeps its exact signature/return; the hook lives only on `main()`'s success
  path and does not alter the return value or the printed output.
- **File-collision safety.** WP03 solely owns `scripts/vikunja/create_task.py`,
  `scripts/trust/completion_assertion.py`, and `scripts/trust/assertion_verifier.py`
  — no overlap with WP01/WP02 (which own the `__init__.py` files and other trust
  modules). Do not touch files outside `owned_files`.
- **Vikunja transient errors** must not fabricate false `artifact_missing`
  findings — a client outage is not a missing artifact. Handle conservatively.

## Reviewer Guidance

- Verify **fail-safe on every write path**: `record_assertion` and the Vikunja
  hook must both swallow their own errors and never raise into the caller; the
  CLI returns non-zero on failure without raising. Confirm the forced-error tests
  actually exercise this.
- Confirm **per-artifact verification**: each id in `artifact_ids` is looked up
  independently, and a mixed present/missing assertion yields findings only for
  the missing ids.
- Confirm the **Vikunja hook is localized and non-breaking**: it sits on
  `main()`'s success path, `create_task()`'s signature/return is unchanged, and a
  forced hook failure leaves `main`'s exit code and output intact.
- Confirm **no LLM** and fully **deterministic** verification — existence checks
  only, `unverifiable_kind` as the safe fallback, no semantic judgment.
- Confirm the JSONL write mirrors the #706 `fcntl.LOCK_EX` append pattern and the
  ledger dir is env-overridable (`FELIX_TRUST_ASSERTIONS_DIR`) with the documented
  default.
