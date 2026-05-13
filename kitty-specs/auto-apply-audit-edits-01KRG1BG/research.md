# Research / Alignment: Auto-apply audit edits

**Mission**: `auto-apply-audit-edits-01KRG1BG`
**Date**: 2026-05-13

Records planning-phase decisions. Spec had no `[NEEDS CLARIFICATION]` markers; this file captures rationale.

---

## Decision 1: Allowlist location — hardcoded constant in the script

**Decision**: `AUTO_APPLY_CHANGE_TYPES = frozenset({...})` as a module-level constant in `handle_audit_routing.py`.

**Rationale**:
- C-001 already states: the allowlist lives in the script, not AGENTS.md prose. This is a refinement: in-script means a Python constant, not a separate config file.
- A separate `change_type_allowlist.json` would add a config-loading surface (path resolution, parse errors, missing-file handling) for zero operational benefit — there's no scenario where an operator legitimately changes the allowlist at runtime without code review.
- Future change_types should be added via PR, exactly so the policy review happens at code-review time. A constant enforces that.

**Alternatives considered**:
- **Config file**: rejected per above.
- **AGENTS.md prose**: rejected per C-001 — would re-introduce the bug (LLM reasoning through routing).

## Decision 2: External-command style — subprocess for git/gh

**Decision**: Run `git commit` and `gh issue create` via `subprocess.run`, capturing output for error reporting.

**Rationale**:
- Matches the codebase's established pattern (every other helper that does git/gh work uses subprocess).
- Importing a Python `git` library (e.g., GitPython) or `gh` library would add a dependency for negligible benefit and create a divergence from the rest of the codebase.
- Test surface: monkeypatch `subprocess.run` cleanly.
- Failure modes are well-understood: non-zero exit + captured stderr = recoverable error; raise = unrecoverable.

**Alternatives considered**:
- **Python git library**: rejected — adds dep, doesn't compose with the existing pattern.
- **Direct PyGithub API**: rejected — adds dep, requires token plumbing that `gh` already handles via auth.

## Decision 3: Atomic file writes — reuse the #254 pattern

**Decision**: Use `tempfile.mkstemp + os.replace` with mode preservation, identical to the pattern landed in `inject_parse_error_marker.py` after mission #33 (#254).

**Rationale**:
- The doc-auditor edits files that may be cross-user (e.g., a doc owned by kgale, edited by claude). The #254 perm-orphan bug would reappear if we used a naïve write.
- The pattern is proven (107 tests pass in `tests/inbox/`, end-to-end SC-002 canary verified) and small (~15 lines).
- Adds NFR-001 throughput cost of one `stat` call per edit — negligible.
- Adds a regression test (`test_atomic_write_preserves_mode`) to guard against re-introducing the bug.

**Alternatives considered**:
- **Library import** (e.g., `from inject_parse_error_marker import _atomic_write`): tempting (DRY), but the auditor's script lives in a different scripts subtree (`scripts/openclaw/agents/felix-doc-auditor/` vs `scripts/inbox/`) and importing across subtrees creates a coupling that doesn't exist today. Re-implement the 15-line helper inline; cross-reference the original in a comment for future deduplication.

## Decision 4: AGENTS.md section scope — forward path only

**Decision**: Collapse § 7.9, § 7.10, and § 7.11 to a single helper invocation in the forward path. Keep § 3 (decision-handling for existing pending-approvals) prose-driven and unchanged.

**Rationale**:
- The forward path is where the over-gating bug lives. § 3 is the path for the rare case where a pending-approval was correctly filed (e.g., an unknown change_type) and Kent applied a decision label. That path is correctly LLM-mediated today.
- After this mission, gated audits should be rare (only on truly novel change_types). Collapsing § 3 has lower ROI than the forward path.
- Scope discipline: the mission is "remove the gate from mechanical work," not "rebuild the entire auditor's decision logic in scripts." A future mission can fold § 3 in if the gated-edit rate grows enough to justify it.

**Alternatives considered**:
- **Fold § 3 in too**: rejected for scope (above).
- **Leave § 7.10 and § 7.11 prose-driven, only collapse § 7.9**: rejected — that's option (A) from planning, which Kent declined in favor of (B).

## Decision 5: Test surface — subprocess.run + monkeypatched git/gh

**Decision**: Drive the handler via `subprocess.run` from tests for full CLI surface coverage. Use `pytest.MonkeyPatch` to stub the handler's *internal* `subprocess.run` calls (to `git commit`, `gh issue create`) per test case, returning canned exit codes and outputs.

**Rationale**:
- CLI coverage at the test boundary catches argument-parsing and exit-code regressions.
- Function-level mocking of the internal subprocess calls keeps tests hermetic — no real git or gh activity during the test run.
- This matches the pattern landed by #253 for the `handle_parse_failures.py` and `handle_marker_cleanup.py` tests.

**Alternatives considered**:
- **Pure unit-test (no subprocess.run wrapping)**: faster, but misses CLI-surface coverage.
- **Real git/gh integration tests**: rejected — too brittle for a unit-test surface.

---

## Open questions

None. All technical decisions are locked.
