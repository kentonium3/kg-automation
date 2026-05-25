# Specification: Drift Interpretation Debug Capture

**Mission**: drift-interpretation-debug-capture-01KSEFT8
**Source**: GitHub issue [#404](https://github.com/kentonium3/kg-automation/issues/404)
**Mission type**: software-dev
**Target branch**: main

---

## User Scenarios & Testing

### Primary scenario

As the operator of the Felix doc-auditor, Kent wants to know **what shape** of response is being returned by the LLM when `drift_interpretation` calls fail schema validation, so he can determine whether the root cause is a prompt regression, a schema regression, or a model behavior change. Today, every drift event fails 4 retries and lands as `RETRY_EXHAUSTED` without producing any verdict, but the failure mode is opaque — the `_RetrySchemaError` is raised without recording the raw response that triggered it. Without a payload sample, no fix can be designed.

### Operational flow after this mission lands

1. Operator enables debug capture by setting an env var on office2's `felix-doc-auditor.service` unit
2. Operator enables `felix-doc-auditor.timer` for one manual tick
3. Drift event triggers `drift_interpretation`, LLM returns 200 OK, `_parse_verdict` raises `_RetrySchemaError`
4. The raise site logs the raw response body (truncated to a reasonable size) to stderr with a stable prefix
5. `journalctl --user -u felix-doc-auditor.service` shows the captured payload
6. Operator records the payload, the raise-site identifier, and root-cause hypothesis in a diagnostic document under `docs/diagnostics/`
7. Operator disables the env var, re-disables the timer, and files a follow-up mission for the actual fix

### Acceptance scenarios

- **AS1**: With `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` set and a mocked LLM response that fails `_parse_verdict`, the debug logging path records the raw response body at `WARNING` level with the `drift_interpretation.schema_fail` prefix. *(Unit test, automated.)*
- **AS2**: With the env var **unset**, the same mocked failure produces only the existing `_RetrySchemaError` raise — no raw response body is logged. *(Unit test, automated.)*
- **AS3**: With the env var set and `_parse_verdict` succeeding, no extra log line is emitted. *(Unit test, automated.)*
- **AS4**: Each existing `_RetrySchemaError` raise site in `drift_interpretation.py` (the ~10 sites around lines 404–504) is covered by the same capture mechanism — the raise site identifier (or the exception message itself, mapped to a raise site) appears alongside the raw response in the log. *(Unit test, parametrized over raise sites.)*
- **AS5**: After deploying to office2 and running one debug-enabled tick, the operator can locate the raw payload in `journalctl` output using `grep "drift_interpretation.schema_fail"`. *(Operational verification — manual step in the WP that closes out the mission.)*
- **AS6**: A diagnostic document is committed under `docs/diagnostics/` recording: (a) the raw payload (sanitized of any repo-specific content if needed), (b) which raise site fired, (c) the root-cause hypothesis (prompt / schema / model). *(Documentation deliverable.)*

### Edge cases

- **EC1 — env var truthiness**: only the literal string `"1"` enables capture. Other truthy-looking values (`"true"`, `"yes"`, `"on"`) do NOT enable capture. This matches the conservative "off by default" intent and avoids ambiguity. Document this explicitly in the env var help text.
- **EC2 — very large response body**: if the LLM returns an oversized response, the capture should truncate (e.g., first 4096 bytes) with a clear suffix indicating truncation. We want the diagnostic signal, not the full body.
- **EC3 — multiple raise sites in one call**: `_parse_verdict` can only raise once (Python semantics), so only one capture happens per call. No concern about cascading logs.
- **EC4 — no LLM response at all** (e.g., network failure raising before HTTP 200): capture only runs when a 200-OK response body exists. Pure network failures bypass `_parse_verdict` entirely.

---

## Requirements

### Functional Requirements

| ID | Description | Status |
|----|-------------|--------|
| FR-001 | When `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` is set, every `_RetrySchemaError` raise site in `scripts/doc_audit/judgment/drift_interpretation.py` MUST log the raw 200-OK LLM response body to stderr before re-raising the exception. | Required |
| FR-002 | Each captured log line MUST include a stable prefix `drift_interpretation.schema_fail` followed by an identifier for the raise site (line number, a symbolic name, or the exception message — implementer decides during plan/tasks). | Required |
| FR-003 | When the env var is unset (default), no raw response body MUST be logged, even when `_RetrySchemaError` is raised. | Required |
| FR-004 | The captured log line MUST be at `WARNING` level (not `DEBUG`) so it appears in journalctl's default verbosity. | Required |
| FR-005 | The raw response body in the log MUST be truncated to at most 4096 bytes with a `[truncated]` suffix when the body exceeds the limit. | Required |
| FR-006 | The implementation MUST NOT alter the existing `_RetrySchemaError` raise behavior — the same exception, with the same message, is raised in all cases. The capture is observation-only. | Required |
| FR-007 | The mission MUST produce a diagnostic document under `docs/diagnostics/` recording the captured payload, raise site, and root-cause hypothesis. | Required |
| FR-008 | The mission MUST close GitHub issue #404 with a comment linking to the diagnostic document and identifying whether a follow-up fix issue is needed. | Required |

### Non-Functional Requirements

| ID | Description | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Performance overhead of the capture path when env var is set MUST be negligible relative to the cost of the LLM call that just completed. | Capture path adds < 5 ms per call. Measured via existing test fixtures (mocked LLM call) or by inspection. | Required |
| NFR-002 | Performance overhead when env var is unset MUST be zero (single env var lookup at module import or per-call). | No measurable difference vs. pre-change code in unit tests. | Required |
| NFR-003 | The unit test suite for `drift_interpretation.py` MUST continue to pass without modification beyond the new test cases. | 100% existing test pass rate. | Required |

### Constraints

| ID | Description | Status |
|----|-------------|--------|
| C-001 | Raw payloads MUST NOT be committed to the repository (they may contain confidential repo content). Storage is journal logs only. The diagnostic document MAY include the raw payload only after manual review and any necessary sanitization. | Required |
| C-002 | The env var MUST be off in steady-state production. The default journalctl output during a normal tick must NOT include any `drift_interpretation.schema_fail` lines. | Required |
| C-003 | Mission scope is diagnostic-only. The actual fix (prompt change, schema change, or parsing change) MUST be deferred to a follow-up mission. | Required |
| C-004 | This is NOT a bulk edit. Only `scripts/doc_audit/judgment/drift_interpretation.py`, its test file, and a new diagnostic document are touched. (`change_mode: "regular"` in meta.json.) | Required |

---

## Success Criteria

- **SC-001**: Operator can capture a raw 200-OK LLM response payload from `drift_interpretation` by setting one env var, enabling the timer, and reading `journalctl`.
- **SC-002**: The captured payload is sufficient to identify whether the failure mode is a prompt regression, a schema regression, or a model behavior change. Specifically, the payload alone (plus the raise-site identifier) is enough for an engineer to decide which of the three root-cause categories applies.
- **SC-003**: A diagnostic document under `docs/diagnostics/` records the findings with enough detail that the next engineer (or the same engineer in a future session) can read it and start the follow-up fix mission without re-running the capture.
- **SC-004**: GitHub issue #404 is closed with the findings, and (if a follow-up fix is needed) the new fix issue is filed and cross-referenced.

---

## Key Entities

- **drift_interpretation.py**: the script under audit, at `scripts/doc_audit/judgment/drift_interpretation.py`. Contains `_parse_verdict` (lines ~388–504) which raises `_RetrySchemaError` at ~10 sites.
- **`_RetrySchemaError`**: internal exception class defined at line 210 of `drift_interpretation.py`. Retry-eligible — every raise triggers another attempt up to `RETRY_DELAYS_SECONDS = (30, 60, 120)`.
- **env var `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS`**: new — gates the capture path. Off by default. Value `"1"` enables.
- **journal log prefix `drift_interpretation.schema_fail`**: new — stable identifier for grep'ing capture output.
- **felix-doc-auditor.service** / **felix-doc-auditor.timer**: the systemd units on office2 that run the auditor. Service reads env from the systemd unit; operator sets the env var by editing the unit (or via `systemctl --user edit`).
- **docs/diagnostics/**: target directory for the mission's findings document. Naming follows the spec-kitty bug report template if applicable, or a custom filename like `drift-interpretation-payload-shape.md` if the report shape doesn't fit the template exactly.

---

## Assumptions

- **A-001**: The current behavior (100% failure rate) is stable enough that one captured payload represents the typical failure mode. If subsequent ticks reveal that the failure mode varies, the diagnostic document notes the variance and the follow-up fix mission scopes accordingly.
- **A-002**: The LLM response body is not so large or so binary that 4096-byte truncation discards diagnostic signal. If 4096 bytes proves insufficient during the operational run, the implementer can bump the limit before the mission closes — but the default truncation policy stands.
- **A-003**: `journalctl` retention on office2 is sufficient to retain the captured payload long enough for the operator to extract it (operator extracts immediately after the tick completes, so any retention > 1 hour is sufficient).
- **A-004**: The `claude` user on office2 can edit its own systemd user units via `systemctl --user edit felix-doc-auditor.service` without sudo. (Standard systemd-user semantics; verified during prior office2 deploy work.)

---

## Out of Scope

- The fix itself for whatever the diagnostic reveals (prompt regression, schema regression, model behavior change). A follow-up issue + mission handles this.
- Long-term retention of debug payloads. Each operational run captures a single tick's payload, then the env var is disabled.
- A general-purpose "capture LLM responses on failure" framework. The capture is specific to `drift_interpretation` and tied to the `_RetrySchemaError` raise sites. Generalization may be a follow-up if other judgment scripts develop similar opacity.
- Sanitization tooling for the captured payload. The diagnostic document author handles sanitization manually before committing the doc.
- Pre-emptive payload capture for `audit_interpretation` (covered separately in #402) or other judgment scripts (`tier_classification`, `cross_file_implication`, `debt_body_generation`). If those develop similar opacity, file separate issues.
- Re-enabling the timer long-term. The post-mission state is: timer disabled, env var unset, diagnostic captured, follow-up issue filed. Re-enabling the timer is a separate operational decision tied to the follow-up fix mission's completion.

---

## Dependencies

- **#403** (closed at `1b0768c`): merged. The retry_count clamp fix means the underlying `_RetrySchemaError` no longer crashes the tick on the 4th retry — necessary precondition for running a debug-enabled tick safely.
- **office2 access**: `ssh office2-claude` for the operational verification step. No new infrastructure required.
- **doc-auditor venv on office2**: `/data/services/openclaw/felix-doc-auditor-driver/venv/` — already deployed.
- **GitHub issue #404 access**: for closure comment.

---

## Discovery Decisions (recorded for audit)

1. **Mission scope**: diagnostic-only. Operator chose this over "diagnostic + fix" because the fix shape is unknown until the payload is captured, and spec-kitty WP planning works best with known deliverables.
2. **Storage**: journal logs only. Operator chose this over committed fixture or tempfile because the diagnostic value is in one captured sample, and committing raw LLM responses (which may contain repo content) is undesirable.
