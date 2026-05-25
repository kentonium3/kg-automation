# Implementation Plan: Drift Interpretation Debug Capture

**Mission**: drift-interpretation-debug-capture-01KSEFT8
**Date**: 2026-05-24
**Spec**: [spec.md](spec.md)
**Branch**: target=`main`, planning-base=`main`, merge-target=`main` (matches)

---

## Summary

Add an env-var-gated debug logging path to `scripts/doc_audit/judgment/drift_interpretation.py` that captures the raw 200-OK LLM response body to stderr at each `_RetrySchemaError` raise site, ship the change, then run one debug-enabled tick on office2 to capture a real payload from `journalctl`. Document the findings in `docs/diagnostics/` and close issue #404 with the analysis. The actual fix for whatever root cause is identified will be a follow-up mission.

The technical approach is small: a single helper function `_log_raw_response_if_debug(response_text: str, error_message: str)` invoked immediately before each `raise _RetrySchemaError(...)` call. The helper reads `os.environ.get("DOC_AUDIT_DEBUG_DRIFT_PAYLOADS") == "1"` (exact match), truncates to 4096 bytes, and emits a `WARNING`-level log with the stable prefix `drift_interpretation.schema_fail`. The exception message itself serves as the raise-site identifier — each of the ~10 raise sites already has a distinct message string per the source code grep at spec time.

---

## Technical Context

**Language/Version**: Python 3.13 (per office2 venv at `/data/services/openclaw/felix-doc-auditor-driver/venv/`, system-default)
**Primary Dependencies**: stdlib only for the new code path (`os`, `logging`). No new third-party packages.
**Storage**: stderr → journalctl. No file I/O. No repo commits of raw payloads (per C-001).
**Testing**: pytest (existing test suite at `tests/doc_audit/judgment/test_drift_interpretation.py` or equivalent). Mock the LLM response via the existing `JudgmentClient` mock pattern used in sibling tests.
**Target Platform**: office2 (Ubuntu 24.04 LTS) under `felix-doc-auditor.service` systemd user unit. Local pytest runs on macOS Darwin 25.5.0 for CI parity.
**Project Type**: single project (this repo). No new directories created in source tree; one new file in `docs/diagnostics/`.
**Performance Goals**: capture overhead < 5 ms per call when env var is set (NFR-001); zero overhead when unset (NFR-002).
**Constraints**: env var off by default in steady-state production (C-002); raw payloads never committed (C-001); diagnostic-only scope (C-003); not a bulk edit (C-004).
**Scale/Scope**: one source file edit + one test file edit + one new diagnostic doc. ~10 raise sites in scope (lines ~404–504 of `drift_interpretation.py`).

---

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter governance is currently **unresolved** in this project per `spec-kitty charter context --action plan --json` (pytest/python tagged unavailable in spec-kitty 3.1.8's `DEFAULT_TOOL_REGISTRY`; tracked in memory as `project_charter_tool_registry_mismatch`, deferred until after mission #343). Operating in `compact` mode per the helper's instruction.

The actual Felix Constitution at `docs/constitution/FELIX-CONSTITUTION.md` and the change-risk taxonomy at `docs/design/architecture/data/change-risk-taxonomy.json` are loaded as context for risk-tier assessment:

- **Risk tier**: **Tier 3 (Standard)** — pure logic change in a Python script. No service deploys, no schema changes, no host config. Standard pytest validation + dry-run on office2 satisfies the tier protocol.
- **Tier 3 protocol**: "Proceed with dry-run or sandbox validation where available. No pre-flight checklist required." → met by the pytest suite + office2 dry-run tick.
- **Architecture doc impact**: none. No service, credential, port, or data flow changes. The `docs/runbooks/doc-auditor-driver-ops.md` runbook may need a one-line note about the new env var; flag this as part of the implementation.

**Pass**: Charter Check passes for the diagnostic-only scope. Re-checked post-design (Phase 1) below — still passes; no new gates introduced by the design artifacts.

---

## Project Structure

### Documentation (this feature)

```
kitty-specs/drift-interpretation-debug-capture-01KSEFT8/
├── meta.json               # mission identity + change_mode=regular (already populated)
├── spec.md                 # specification (already authored)
├── plan.md                 # this file
├── research.md             # Phase 0 output
├── data-model.md           # Phase 1 output (minimal — no new entities, see Phase 1)
├── quickstart.md           # Phase 1 output
├── contracts/              # Phase 1 output (env var contract only)
├── checklists/
│   └── requirements.md     # spec quality checklist (already passing)
└── tasks/                  # populated by /spec-kitty.tasks
```

### Source Code (repository root)

```
scripts/
└── doc_audit/
    └── judgment/
        └── drift_interpretation.py   # MODIFIED — add env-var-gated debug logging

tests/
└── doc_audit/
    └── judgment/
        └── test_drift_interpretation.py  # MODIFIED — add test cases for AS1–AS4

docs/
├── diagnostics/
│   └── drift-interpretation-payload-shape.md  # NEW — operational findings record
└── runbooks/
    └── doc-auditor-driver-ops.md     # MODIFIED — one-line note about DOC_AUDIT_DEBUG_DRIFT_PAYLOADS
```

**Structure Decision**: Single project layout. The mission touches three existing directories and adds one new file. No new modules, packages, or directory hierarchies are created. The diagnostic doc lands under `docs/diagnostics/` to match existing convention for one-off operational analyses (e.g., `agy-migration.md`, `xx_*.md` reports).

---

## Phase 0 — Research

See [research.md](research.md). Summary of what's resolved:

- **Logging mechanism**: Python stdlib `logging` module, with `logger = logging.getLogger(__name__)` at module level (matches the existing pattern in `drift_interpretation.py` and sibling judgment scripts).
- **Env var contract**: exact-string `"1"` for truthiness. Documented in `contracts/env-vars.md`.
- **Raise-site identifier**: existing exception messages are already distinct per raise site (verified via `grep -n "raise _RetrySchemaError" scripts/doc_audit/judgment/drift_interpretation.py`). Use the message itself; no new identifier scheme needed.
- **Truncation strategy**: simple byte-count truncation at 4096 with `[truncated]` suffix. UTF-8 boundary safety: truncate, then decode with `errors="replace"` for the log line. The truncation happens on the raw response text (post-API, pre-validation) so no encoding ambiguity downstream.
- **Test fixture approach**: extend the existing `test_drift_interpretation.py` mock pattern. No new fixture files; in-line mock payloads suffice.
- **Office2 env var setting**: `systemctl --user edit felix-doc-auditor.service` to add `Environment="DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1"` as a drop-in. Reversible via the same command. No sudo required (systemd user units).

No NEEDS CLARIFICATION items.

---

## Phase 1 — Design & Contracts

See [data-model.md](data-model.md), [quickstart.md](quickstart.md), and [contracts/](contracts/) for the artifacts. Highlights:

- **Data model**: this mission introduces no new persistent entities. The data-model.md is a one-paragraph note recording the absence and the runtime data shape (env var → log emission decision → log line content).
- **Contracts**: one new contract — the env var `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS`. Recorded in `contracts/env-vars.md` with name, accepted values, default, scope, and reversibility. No new HTTP/RPC endpoints.
- **Quickstart**: `quickstart.md` records the operator runbook — set env var on office2, enable timer for one tick, grep journalctl, disable env var. Cross-references the canonical runbook at `docs/runbooks/doc-auditor-driver-ops.md`.

---

## Charter Check — Post-Design Re-Evaluation

Re-checked after Phase 1 artifact design. No new violations introduced:
- No new dependencies added → no DEP gate concern
- Tier classification unchanged → Tier 3
- Architecture doc update scoped to one line in the existing runbook → no `data/` JSON file changes
- Tests follow the existing pytest pattern in the repo
- Diagnostic doc location matches existing convention

**Re-pass**: Charter Check passes post-design.

---

## Complexity Tracking

No charter violations. No exceptions claimed.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | n/a | n/a |

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Captured payload contains confidential repo content; raw-log retention exposes it. | Medium | Medium | C-001: payloads stay in journal only. Diagnostic doc author sanitizes before committing. Default env var off. |
| 4096-byte truncation discards diagnostic signal (response is structured but starts with markdown-fence noise that occupies most of the budget). | Low-Medium | Low | If observed during the operational tick, bump truncation limit before mission closes. Note this in the mission's review checklist. |
| journalctl retention on office2 truncates the captured line before operator extracts it. | Very Low | Low | Operator extracts immediately post-tick. Default journald retention is days, not hours. |
| The debug logging accidentally suppresses or changes the original `_RetrySchemaError` raise. | Low | High | FR-006 enforces capture-is-observation-only. Test AS1 + AS4 verify the exception still raises with the same message. |
| The captured payload reveals a model behavior change that requires a deeper structural fix (multi-mission), not a single quick fix. | Medium | Low-Medium | This is exactly the value of the diagnostic. The follow-up mission scopes accordingly. Mission #404 is closed once the diagnostic is recorded regardless of fix size. |

---

## Open Decisions for Tasks Phase

None blocking. The implementation is small enough that WP design (in `/spec-kitty.tasks`) will likely produce 1–2 WPs:

- **WP01**: Code + tests (capture path + parametrized tests for AS1–AS4)
- **WP02**: Operational deploy + diagnostic doc + #404 closure (run on office2, capture payload, write `docs/diagnostics/drift-interpretation-payload-shape.md`, close #404 with summary comment)

Whether to split into two WPs or keep as one is a finalize-tasks decision; the dependency is clear regardless (operational deploy depends on code merge).

---

## Branch Contract — Final Restatement

- **Current branch at plan completion**: `main`
- **Planning/base branch**: `main`
- **Merge target**: `main`
- **Matches target**: `true`
- **Implication for `/spec-kitty.tasks` and `/spec-kitty.implement`**: the mission lane worktree will branch from `main`; final merge will go back to `main`. No alternative landing branch under consideration.

---

## Next Suggested Command

`/spec-kitty.tasks` (user must invoke explicitly per the plan command's MANDATORY STOP).
