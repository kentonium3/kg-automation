# Research / Alignment: Inbox parse-failure and cleanup helpers

**Mission**: `inbox-parse-failure-cleanup-helpers-01KRFVS4`
**Date**: 2026-05-13

This document records planning-phase decisions. The spec had no open `[NEEDS CLARIFICATION]` markers; this file captures rationale so future readers can audit each non-trivial choice.

---

## Decision 1: Invocation style — direct function imports, not subprocess

**Decision**: The new orchestrator helpers import the existing inbox modules and call their library functions directly (`inject_marker`, `strip_marker`, `find_existing_open_issue`, `file_new_issue`). No `subprocess.run` of the existing CLIs.

**Rationale**:
- The existing modules already expose clean library APIs alongside their thin `main()` CLI wrappers. No refactor needed.
- Library + thin-CLI is the canonical Python pattern (used by `click`, `pytest`, every well-structured codebase). Subprocess for in-codebase Python-to-Python orchestration is unusual.
- More durable: function signatures are checkable by mypy/pyright. CLI-flag dependencies are stringly-typed and fail silently in production when someone renames a flag.
- Easier to unit-test: mock at the function level rather than fork+exec a subprocess.
- Faster: no Python startup overhead per entry. Negligible at scale ≤5 but cleaner regardless.

**Alternatives considered**:
- **Subprocess**: would treat the existing CLIs as the contract surface. Initial lean during planning, rejected after pressure-test from Kent ("which approach is more standard, more durable?"). The existing scripts' library functions are the more stable contract.

**Spec implication**: C-003 was updated to allow either CLI-wrap or function-wrap; "wrap, not rewrite" means we don't rewrite business logic, not that we must use subprocess.

## Decision 2: Input format — JSON tempfile via `@<path>`

**Decision**: Both helpers accept a single positional argument of the form `@/path/to/prescan.json`. The leading `@` is preserved from the existing convention in `file_inbox_quality_issue.py --parse-failures @<path>`.

**Rationale**:
- Parse-error reasons can contain quotes, backticks, and other shell-sensitive characters. Passing them via shell-quoted CLI args has bitten the codebase before; the JSON tempfile convention is a deliberate workaround already used in production.
- Reusing the existing convention means operators familiar with the inbox helpers don't have to learn a new style.
- The agent's Step 1 already writes prescan output to `/tmp/inbox-prescan-latest.json`. Passing that exact path to the new helpers is zero-friction.

**Alternatives considered**:
- **Stdin JSON**: would avoid the tempfile but introduces a piping pattern that doesn't match existing scripts. Rejected.
- **Multiple `--parse-failures` / `--marker-cleanup-needed` flags**: would require the agent to slice the JSON itself. Rejected — pushes deterministic work back into the prompt.

## Decision 3: Error handling — continue-then-fail

**Decision**: On partial failure, the helper processes every entry (logging each success/failure individually), then exits non-zero with stderr summarizing which entries failed.

**Rationale**:
- Matches the agent's current Step 6.3 behavior ("If the issue-filing helper or any marker-inject helper exits non-zero, log the failure with action type `parse_failure_handling_error` and continue. The next cron tick will retry the failed leg.").
- Avoids the "first failure aborts all subsequent work" anti-pattern, which would let one stuck note block N-1 healthy ones.
- Cron tick retry semantics still apply — the next tick re-reads prescan and re-attempts the same entries.

**Alternatives considered**:
- **Fail-fast**: exit on first failure. Rejected — see above.
- **Always-succeed-with-warnings**: exit 0 even on partial failure, surface failures only via logs. Rejected — the agent's current observability uses non-zero exit as the failure signal.

## Decision 4: Logging integration — subprocess `log_action.py`

**Decision**: The new helpers shell out to `log_action.py` for each emitted log entry, matching the agent's existing observability pattern. (This is the one place we use subprocess — and only because `log_action.py` is the canonical Felix-side action-log writer.)

**Rationale**:
- The agent's action log is consumed by other Felix observability tooling. Keeping `log_action.py` as the single writer maintains a clean contract.
- `log_action.py` is a separate concern (writes to `~/second-brain/agents/state/` with its own conventions); reimplementing its logic inside the orchestrator would duplicate that surface.
- Subprocess overhead per log emission is acceptable (the dominant cost is the actual work being logged).

**Alternatives considered**:
- **Import `log_action`**: would mirror Decision 1's pattern. Feasible but adds coupling to `log_action.py`'s internal API, which has historically changed. Subprocess via the stable CLI is more durable here.

## Decision 5: Test strategy — function-level mocking + tmp_path integration

**Decision**: Tests use `pytest.MonkeyPatch` to swap the wrapped library functions (`inject_marker`, `strip_marker`, etc.) with mocks. Drive the orchestrator via `subprocess.run` for CLI-surface coverage. Use `tmp_path` for any real file I/O.

**Rationale**:
- Mocking at the library-function level gives precise control over success/failure modes per entry without needing real GitHub API calls or filesystem state.
- Driving the orchestrator via subprocess validates the CLI parsing surface, exit codes, and stderr/stdout contract.
- `tmp_path` fixtures keep tests hermetic — no writes to the real inbox.

**Alternatives considered**:
- **Pure unit tests** (no subprocess.run): faster but skips CLI-parsing coverage. Rejected.
- **Pure integration tests** (no mocking): would require a real GitHub repo for issue filing and real filesystem state. Rejected — too brittle.

## Decision 6: AGENTS.md prompt edits — one command per step

**Decision**: Step 5a in `AGENTS.md` and `AGENTS.md.tmpl` becomes a single `python3 .../handle_marker_cleanup.py @/tmp/inbox-prescan-latest.json` invocation. Step 6 becomes a single `python3 .../handle_parse_failures.py @/tmp/inbox-prescan-latest.json` invocation. All multi-step bash recipes are removed.

**Rationale**:
- The whole point of this mission. Multi-step bash inside an LLM prompt is the fragility surface.
- Both `AGENTS.md` and `AGENTS.md.tmpl` are edited together (C-002) to prevent template/runtime drift.

**Alternatives considered**:
- **Keep some hand-holding prose**: e.g., "the helper will exit non-zero if anything fails; check the log if you see that." Rejected — that's still asking the LLM to interpret a deterministic signal. Operators monitor cron-run statuses via tooling, not via the agent prompt.

---

## Open questions

None. All technical decisions are locked.
