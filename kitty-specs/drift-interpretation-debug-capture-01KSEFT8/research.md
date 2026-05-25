# Phase 0 Research — Drift Interpretation Debug Capture

**Mission**: drift-interpretation-debug-capture-01KSEFT8
**Plan**: [plan.md](plan.md)

This mission has a tightly-scoped technical surface. The research below records the load-bearing choices and the alternatives considered.

---

## R1 — Logging mechanism

**Decision**: Use Python stdlib `logging` with `logger = logging.getLogger(__name__)` at module level. Emit at `WARNING` level so the line appears in default journalctl output without `-x` or verbose flags.

**Rationale**:
- Matches the existing pattern in `scripts/doc_audit/judgment/drift_interpretation.py` (which already imports and uses `logging`).
- `WARNING` is appropriate: schema-fail captures are diagnostic signals operators want to see, not routine info.
- stdlib only — no new dependencies, no test fixture churn.

**Alternatives considered**:
- `print(..., file=sys.stderr)`: simpler, but skips the standard log filtering/formatting that systemd journal expects. Rejected.
- `structlog` or JSON-line logging: nicer parsing, but introduces a dependency for one log line. Rejected as over-engineered for a single diagnostic capture point.
- `INFO` level: would require explicit `-v` flag in journalctl to surface, defeating the operational point of the capture. Rejected.

---

## R2 — Env var contract

**Decision**: env var `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS`, accepting only the exact string `"1"` to enable capture. Any other value (including `"true"`, `"yes"`, `"on"`, `""`, unset) leaves capture off.

**Rationale**:
- Exact-match semantics are unambiguous and minimize "I thought I enabled it" foot-guns.
- The conservative bias (off-by-default, single explicit value to enable) matches C-002.
- Documenting the exact string `"1"` in the env var help text is simpler than maintaining a "truthy values" table.

**Alternatives considered**:
- Standard "truthy" parsing (`"1" | "true" | "yes" | "on"` case-insensitive): more user-friendly, but introduces a non-trivial helper and a new test surface. Rejected per scope.
- Numeric levels (e.g., `=2` for verbose, `=1` for basic): out of scope for this mission. If finer control is needed later, file a follow-up.

---

## R3 — Raise-site identifier

**Decision**: use each `_RetrySchemaError`'s **existing exception message** as the raise-site identifier in the log line. No new IDs assigned.

**Rationale**:
- Existing messages are already distinct: `"empty LLM response"`, `"invalid JSON: …"`, `"rationale missing or empty"`, etc. (verified via `grep -n "raise _RetrySchemaError" drift_interpretation.py` at plan time, ~10 distinct messages).
- The implementation can log `(error_message, response_text)` together with one stable prefix.
- No need to maintain a parallel ID table or update both the raise sites AND a docstring on each refactor.

**Alternatives considered**:
- Source line numbers as identifiers: brittle (refactors shift them). Rejected.
- A new `_RaiseSiteId` enum: introduces a parallel structure that must be kept in sync with the raise sites. Rejected per scope.

---

## R4 — Truncation strategy

**Decision**: byte-count truncation at 4096 bytes with `[truncated]` suffix appended to the logged string. The truncation happens on the response text *before* it's placed in the log message, so the log line itself stays under journal's per-line limits.

**Rationale**:
- 4096 bytes is enough to inspect JSON structure (typical structured-output responses are a few hundred to a few thousand bytes).
- A simple byte truncation is cheap and predictable; UTF-8 boundary issues are handled by decoding with `errors="replace"` on the truncated bytes.
- The diagnostic signal we need ("does the LLM start with markdown fences?", "is the JSON malformed?", "are field names different?") is in the first kilobyte for nearly any realistic failure mode.

**Alternatives considered**:
- No truncation: risks oversized log lines that journald may itself truncate at a per-line boundary mid-stream, losing the truncation marker. Rejected.
- Line-aware truncation (preserve last newline): more complex; doesn't add diagnostic value for our use case (the response is typically a single JSON blob, not multi-line). Rejected.
- Hash + length instead of raw bytes: privacy-preserving but useless for diagnosis. The capture is precisely about seeing the actual content. Rejected.

---

## R5 — Test fixture approach

**Decision**: extend the existing `tests/doc_audit/judgment/test_drift_interpretation.py` (or its current path — to be verified during the implement WP). Mock LLM responses inline in test functions; no new fixture files.

**Rationale**:
- Sibling tests in the repo (e.g., `test_drift_ledger.py` from mission #403) use inline mock payloads, not external fixtures. Matching the existing style minimizes review surface.
- Each test case (AS1, AS2, AS3, AS4) needs a small distinct mock — inline is appropriate.
- The capture path is small enough to test without a parametrized fixture matrix; a parametrized test over the raise sites can use a tuple of `(mock_response, expected_log_substring)`.

**Alternatives considered**:
- External JSON fixtures under `tests/fixtures/drift_interpretation/`: useful if we wanted to share mock payloads across many tests, but here we want each test to be self-contained. Rejected.
- Property-based testing (Hypothesis): the failure modes are deterministic raise sites with known messages. Hypothesis-style generation would target the wrong layer. Rejected.

---

## R6 — Office2 env var setting

**Decision**: set the env var via `systemctl --user edit felix-doc-auditor.service` to add a drop-in override:

```ini
[Service]
Environment="DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1"
```

Then `systemctl --user daemon-reload` and start/enable the timer for one tick. Revert by `systemctl --user edit felix-doc-auditor.service` and removing the Environment line.

**Rationale**:
- Systemd-user units don't require sudo. The `claude` user on office2 owns the unit file under `~/.config/systemd/user/`.
- `systemctl --user edit` writes a drop-in (not a full unit override), keeping the change small and reversible.
- The change persists across reboots if not reverted, which is the wrong default — operator must remember to revert. Capture this in `quickstart.md` and the post-mission checklist.

**Alternatives considered**:
- Edit the unit file directly: same effect, but less idiomatic than `systemctl --user edit` (no automatic drop-in handling).
- Set via shell env in a manual `python` invocation outside systemd: bypasses the actual production code path. The diagnostic value is in capturing what happens when the systemd-managed service runs — bypass would change the conditions. Rejected.
- Pass the env var as a command-line arg to the doc-auditor entry point: requires a new CLI flag, code change, etc. Out of scope. Rejected.

---

## R7 — Diagnostic doc location & naming

**Decision**: `docs/diagnostics/drift-interpretation-payload-shape.md` (no `xx_` prefix, no issue number — this is operator analysis, not an upstream bug report, so the bug-report-template convention doesn't apply directly).

**Rationale**:
- The `docs/diagnostics/` directory already contains a mix of bug reports and operational analyses (e.g., `agy-migration.md`). The slug-only naming for operational docs matches `agy-migration.md`.
- The filename is intent-revealing: someone scanning the diagnostics dir post-hoc will see "drift-interpretation-payload-shape" and know what's in it.
- The file is referenced from #404's closure comment and from the follow-up fix issue (if filed).

**Alternatives considered**:
- `docs/design/architecture/incidents/` or similar: more weight than this analysis warrants; this isn't a postmortem of a production incident.
- A note appended to `docs/runbooks/doc-auditor-driver-ops.md`: would bloat the runbook with one-off analysis content. Rejected.
- A comment on issue #404 alone (no separate doc): GitHub issue comments don't survive long-term as discoverable repo content. The diagnostic doc IS the record; the issue comment links to it.

---

## R8 — Office2 sequencing relative to other open work

**Decision**: this mission's office2 deploy step happens with the `felix-doc-auditor.timer` **disabled** by default (it is currently disabled per the #403 continuity doc). Enable temporarily for one tick during this mission, capture, then disable again. Do not leave the timer enabled — #402 is still open and would burn budget on every audit issue if it ran.

**Rationale**:
- Timer was disabled at ~05:00 UTC 2026-05-24 during the #403 triage and has stayed disabled.
- Re-enabling for a single tick is sufficient (the goal is one captured payload, not steady-state operation).
- Steady-state re-enable awaits both #404 and #402 lands per the continuity doc.

**Alternatives considered**:
- Trigger the auditor with `systemctl --user start felix-doc-auditor.service` (one-shot) instead of enabling the timer: simpler, achieves the same result for a single capture. **Implementer should use this approach in WP02 if possible** — it avoids the timer state change entirely.
- Trigger from a manual `python` invocation bypassing systemd: rejected per R6 (changes the conditions).

---

## Open questions (none)

All decisions resolved. No NEEDS CLARIFICATION items remaining.
