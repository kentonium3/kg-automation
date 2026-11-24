---
work_package_id: WP03
title: Restart-count readers
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-011
- FR-012
- NFR-002
- NFR-003
- C-002
- C-008
- SC-004
planning_base_branch: fix/crash-loop-unit-alerting
merge_target_branch: fix/crash-loop-unit-alerting
branch_strategy: Planning artifacts for this mission were generated on fix/crash-loop-unit-alerting. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/crash-loop-unit-alerting unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-crash-loop-unit-alerting-01M858E8
base_commit: 333e36f8f4cbed12f642439e2f1d52f10a754d28
created_at: '2026-11-23T23:29:24.317587+00:00'
subtasks:
- T011
- T012
- T013
- T014
- T015
history:
- at: '2026-11-23T23:40:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/canary/
create_intent:
- scripts/canary/crash_loop_readers.py
- tests/canary/test_crash_loop_readers.py
- tests/canary/fixtures/crash_loop/system-list-units.txt
- tests/canary/fixtures/crash_loop/system-show.txt
- tests/canary/fixtures/crash_loop/user-list-units.txt
- tests/canary/fixtures/crash_loop/user-show.txt
- tests/canary/fixtures/crash_loop/docker-inspect.txt
- tests/canary/fixtures/crash_loop/README.md
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/canary/crash_loop_readers.py
- tests/canary/test_crash_loop_readers.py
- tests/canary/fixtures/crash_loop/**
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP03 – Restart-count readers

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history <WP> --note "..."`.

---

## Objective

Implement `scripts/canary/crash_loop_readers.py`. It turns the system manager, the `claude` user manager and docker into `ScopeReading`s (WP01 types). It needs no privilege, reads no journal and no credential file, works inside one shared deadline, and fails as **could-not-check**, never as false healthy (FR-011, NFR-003, R-02, R-13, R-15).

All effects are injected. The only real `subprocess.run` lives in a default runner, and tests never call it.

## Context to read first

- `research.md` R-02 (exact commands, docker isolation, the corrected security claim), R-03 (real output shapes: properties arrive **out of `-p` order**, blocks are blank-line separated, `not-found` rows), R-13 (exclusion versus failure: the full list) and R-15 (the deadline).
- `data-model.md` (`RestartObservation`, `ScopeReading`).
- WP01's `scripts/canary/crash_loop_model.py` (import, do not modify).
- `scripts/canary/run.py` `_default_run_cmd`. It uses `shell=True`. **Do not copy that**: use argv lists.

## Branch Strategy

Planning happened on `kitty/mission-crash-loop-unit-alerting-01M858E8`. The merge target is `fix/crash-loop-unit-alerting`. Get the worktree with `spec-kitty agent action implement WP03 --agent claude --mission crash-loop-unit-alerting-01M858E8`. Never edit `kitty-specs/` from the lane.

## Subtasks

### T011 — Command runner and deadline

- `class Deadline`: built from a monotonic `clock` callable (injected; default `time.monotonic`) and `budget_seconds`. `remaining()` returns a value ≥ 0.0, and `expired()` reports whether it has run out.
- `RunFn = Callable[[Sequence[str], Mapping[str, str], float], CommandResult]`, where `CommandResult(returncode, stdout, stderr)`. A timeout raises `subprocess.TimeoutExpired`, the same as `subprocess.run`.
- `default_run(argv, env, timeout)` calls `subprocess.run(list(argv), env=dict(env), capture_output=True, text=True, timeout=timeout, check=False)`, with **no shell**.
- `_timeout(deadline)` returns `min(3.0, deadline.remaining())`. If that is ≤ 0, the scope fails with `"read deadline exceeded"` without running anything.
- **Minimal environment**:
  - systemd calls get `PATH=/usr/bin:/bin`, plus `XDG_RUNTIME_DIR` and `DBUS_SESSION_BUS_ADDRESS` copied from `os.environ` when present (the user scope needs them).
  - docker calls get `PATH=/usr/bin:/bin`, `DOCKER_CONFIG=<fresh empty tempdir>`, `DOCKER_HOST=unix:///var/run/docker.sock` and no `DOCKER_CONTEXT`.
  - The tempdir comes from `tempfile.TemporaryDirectory()` and is removed afterwards. Inject the factory so tests can check that it was empty.

### T012 — systemd parsers with reconciliation

- `parse_list_units(stdout) -> tuple[list[str], int]` returns `(loaded_unit_ids, excluded_not_loaded)`. Split on whitespace; column 1 is the unit and column 2 is LOAD. Keep only `*.service` rows whose LOAD is `loaded`. A malformed line (fewer than 4 columns) raises `ReaderError`.
- `parse_show(stdout, requested: list[str]) -> dict[str, dict[str, str]]` splits into blank-line-separated blocks, parses `key=value` with `partition("=")` (values may contain `=`), and keys each block by its `Id`.
  - Raise `ReaderError` on: a block without `Id`; a duplicate `Id`; any requested ID missing from the output; any returned ID not requested.
  - Expect the property order to be arbitrary, and test that.
- `build_unit_observations(blocks, scope, generation) -> tuple[list[RestartObservation], int]`:
  - Skip (excluded, **not** an error) a block with `LoadState` other than `loaded`. That is the enumerate-then-vanish race, which reports `not-found`.
  - Skip (excluded) `Restart=no`.
  - Otherwise `NRestarts` must be a non-negative integer, or raise `ReaderError` (CX-5).
  - The state is `f"{ActiveState} ({SubState})"`.

### T013 — System and user scope readers, boot ID

- `read_boot_id(read_text=Path.read_text) -> str | None` reads `/proc/sys/kernel/random/boot_id`, strips it, and returns `None` on any `OSError`.
- `read_systemd_scope(scope, *, run, deadline, generation) -> ScopeReading`, for `system` (no flag) and `user` (`--user`):
  1. `systemctl [--user] list-units --type=service --all --plain --no-legend --no-pager`.
  2. If no loaded services are listed, return `ScopeReading.ok(scope, (), excluded, ms)`. **Do not call `show` with no units** (it would describe the manager).
  3. Otherwise `systemctl [--user] show -p Id,Restart,NRestarts,ActiveState,SubState,LoadState -- <ids…>`.
  4. A non-zero exit, a timeout, `ReaderError`, `OSError` (for example `FileNotFoundError` for systemctl) or an expired deadline returns `ScopeReading.failed(scope, reason, ms)`. The reason is short and names the command and the cause (stderr trimmed to 200 characters).
  5. If `generation` is `None` (boot ID unreadable), the scope **fails** with `"boot id unreadable"`. Without a generation the reset rule cannot be applied safely.

### T014 — Docker reader

- `read_container_scope(*, run, deadline, tempdir_factory) -> ScopeReading`:
  1. `docker ps -aq --no-trunc`. Empty output returns `ok` with no observations, and **no inspect call**.
  2. `docker inspect --format '{{json .Id}}|{{json .Name}}|{{.RestartCount}}|{{json .HostConfig.RestartPolicy.Name}}|{{json .State.Status}}' -- <ids…>`. Each line has 5 `|`-separated fields. JSON-decode fields 1, 2, 4 and 5; field 3 is an integer ≥ 0. Strip the leading `/` from the name.
  - **Reconcile**: the set of returned IDs equals the set requested, with no duplicates. Otherwise raise `ReaderError`, so the scope fails. A container removed between `ps` and `inspect` makes inspect exit non-zero, and the scope fails for that tick. This is accepted and state is preserved (R-13).
  - Exclude (not an error) a policy of `no` or `""`. `generation` is the container ID. The state is the status (`running`, `restarting`, `exited`, …).
  - Never parse anything except the formatted fields. The `--format` string is a module constant, asserted by a test (CX-3).
- `read_all_scopes(*, run=default_run, clock=time.monotonic, budget_seconds, read_boot_id=..., tempdir_factory=...) -> tuple[list[ScopeReading], str | None]` returns the readings and the boot ID. It reads the boot ID first. **If the boot ID is unreadable, all three scopes fail with `"boot id unreadable"` and no command is run**, because every unit's reboot rebase depends on it (research R-06). Otherwise it reads system, then user, then container under **one** `Deadline`. A scope reached after the deadline fails without running anything. `read_all_scopes` never raises: an unexpected exception inside one scope reader becomes that scope's `failed` reading, and the other scopes still run (FR-011, US4-1).

### T015 — Fixtures and tests

Create `tests/canary/fixtures/crash_loop/` with the **verbatim** office2 samples in `research.md` R-03, captured on 2026-11-23 with `ssh office2-claude` (read-only). The orchestrator's copy is also in the mission scratchpad. If it is unavailable, rebuild the files from R-03's quoted lines:

- `system-list-units.txt`: the five sample rows plus three `not-found` rows (`auditd.service`, `connman.service`, `console-screen.service`) and rows for `obsidian-sync.service`, `snapd.service` and `plymouth-quit.service`.
- `system-show.txt`: the three blocks exactly as printed (`Restart=always / NRestarts=39 / Id=obsidian-sync.service / LoadState=loaded / ActiveState=active / SubState=running`, and so on).
- `user-list-units.txt` and `user-show.txt` (`openclaw-gateway.service` `Restart=always NRestarts=0`, `felix-canary.service` `Restart=no`).
- `docker-inspect.txt`: three lines in the 5-field format. The office2 capture predated the `.Id` field, so add realistic 64-hex IDs.
- `README.md`: provenance (host, date, command, read-only, and which field was synthesized).

Tests (`tests/canary/test_crash_loop_readers.py`), with a fake `run` keyed by argv prefix and a fake clock:

- The real fixtures parse to the expected watched sets: system `obsidian-sync` (39) and `snapd` (1) watched, `plymouth-quit` excluded; user `openclaw-gateway` watched; containers `vikunja` and `transcribe-api` watched, `modest_colden` excluded.
- Shuffled property order still parses. Values containing `=` parse.
- **Each failure mode makes the scope incomplete**: a missing requested block, an extra block, a duplicate `Id`, a missing or non-integer `NRestarts` on a loaded `Restart=always` unit, a non-zero exit, a timeout, `FileNotFoundError`, an expired deadline, malformed docker lines, an ID mismatch, an unreadable boot ID (which fails **all three** scopes, with no command run).
- An enumerate-then-vanish unit (`LoadState=not-found` in `show`) is excluded and the scope is still complete.
- An empty enumeration makes **no** `show` or `inspect` call. Assert the recorded argv.
- The docker env has an empty `DOCKER_CONFIG` (the factory dir has no entries at call time), `DOCKER_HOST` pinned and no `DOCKER_CONTEXT`. No argv contains `shell`, and `run` is never handed a string.
- `read_all_scopes`: a hung system scope (the fake clock advances past the budget) makes the user and container scopes fail with "read deadline exceeded", **without running anything**. A raising container reader leaves system and user complete (US4-1).
- The per-command timeout passed to `run` is ≤ 3.0 and ≤ the remaining budget (the default budget is 6 s, research R-15).

## Definition of Done

- [ ] All tests pass. `.venv/bin/python -m pytest tests/canary -q` passes.
- [ ] `grep -n "shell=True" scripts/canary/crash_loop_readers.py` finds nothing, and the module never reads `journalctl` or any credential path (NFR-003).
- [ ] Commits use conventional messages and these trailers:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01AFaUqc3Puxhf5oxUb9LLP6`.

## Reviewer guidance

- Exclusion versus failure: walk every branch, and confirm that **no** malformed record produces a `complete=True` reading with that unit missing.
- Docker isolation: the env is built per call, and the tempdir is empty and removed afterwards.
- No argument-free `show` or `inspect`.
- The deadline is shared across scopes.
