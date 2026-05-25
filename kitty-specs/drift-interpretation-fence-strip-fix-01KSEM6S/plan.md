# Implementation Plan: Drift Interpretation Fence Strip Fix

**Mission**: drift-interpretation-fence-strip-fix-01KSEM6S
**Date**: 2026-05-24
**Spec**: [spec.md](spec.md)
**Branch**: target=`main`, planning-base=`main`, merge-target=`main` (matches)

---

## Summary

Add a small `_strip_code_fence(text: str) -> str` helper to `scripts/doc_audit/judgment/drift_interpretation.py`, wire it into `_parse_verdict` immediately before `json.loads()`, and add unit tests covering AS1–AS5. The helper handles the canonical Haiku 4.5 fence pattern (` ```json … ``` `), the no-language-hint variant (` ``` … ``` `), and unfenced input (pass-through). No prompt change. No office2 deploy in this mission.

---

## Technical Context

**Language/Version**: Python 3.13 (existing module).
**Primary Dependencies**: stdlib only — no new imports beyond what `drift_interpretation.py` already uses.
**Storage**: n/a.
**Testing**: pytest. Extend `tests/doc_audit/judgment/test_drift_interpretation.py` with fence cases.
**Target Platform**: pytest runs locally on macOS; production runs on office2 (Ubuntu 24.04).
**Project Type**: single project.
**Performance Goals**: helper is O(n) string operations only.
**Constraints**: no prompt change (NFR-003); no bulk-edit pattern; existing capture path (`_log_raw_response_if_debug`) sees the RAW response, not the stripped one.
**Scale/Scope**: 2 files modified. Helper ~15 lines + 1 wire-in line + ~80 lines of unit tests.

---

## Charter Check

Risk tier: **Tier 3 (Standard)** — pure Python logic change in a judgment script. No host config, no schema changes, no service deploy. Charter Check passes pre-design and post-design.

Charter governance is unresolved (memory `project_charter_tool_registry_mismatch`). Compact mode.

---

## Project Structure

```
scripts/doc_audit/judgment/drift_interpretation.py     # MODIFIED
tests/doc_audit/judgment/test_drift_interpretation.py  # MODIFIED (add fence tests)
```

No new files. No new directories.

---

## Phase 0 — Research (consolidated)

**R1 — Helper signature and placement**: `_strip_code_fence(text: str) -> str` near other module-private helpers in `drift_interpretation.py`. Returns the unmodified text if no fence is present; strips first and last lines if the first non-whitespace character is a backtick.

**R2 — Algorithm choice**: simple line-based strip. Pseudocode:
```python
def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.splitlines()
    # Drop opening fence line (e.g. ```json or just ```)
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    # Drop trailing fence line if present
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
```
This is O(n) string + line operations. No regex, no quadratic patterns. UTF-8 safe (Python's `str` is character-based).

**R3 — Wire-in point**: in `_parse_verdict`, the line currently is:
```python
data = json.loads(response_text)
```
Change to:
```python
data = json.loads(_strip_code_fence(response_text))
```
The `_log_raw_response_if_debug` call (from mission #53) still uses the original `response_text` so diagnostic capture sees the wire bytes.

**R4 — Test approach**: extend the existing parametrized test pattern in `test_drift_interpretation.py`. Cases:
- Fenced with `json` hint
- Fenced without hint
- Unfenced (regression check)
- Empty after stripping (falls through to existing "empty LLM response" branch)
- Malformed JSON inside the fence (falls through to existing "invalid JSON" branch)
- Whitespace handling (leading whitespace before fence; trailing whitespace after fence)

**R5 — Prompt change?**: NO. The prompt already says "No code fences" at `drift_interpretation.prompt.md:21-22`. Haiku 4.5 ignores it. Tightening further (e.g., adding "DO NOT use markdown") is unlikely to help and risks other regressions. Hold the prompt steady; fix the parser.

No NEEDS CLARIFICATION items.

---

## Phase 1 — Design & Contracts (consolidated)

**Data model**: no new entities. The change is purely a string normalization step.

**Contracts**: no new contracts. The existing `_RetrySchemaError` exception family is preserved exactly. The `_log_raw_response_if_debug` env var contract (mission #53) is preserved exactly.

**Quickstart**: post-merge operator verification (not part of this mission, just guidance):
```bash
# After this mission merges + pushes to origin
ssh office2-claude 'cd /home/claude/kg-automation && git pull origin main'
ssh office2-claude 'systemctl --user start felix-doc-auditor.service'
# Wait, then inspect:
ssh office2-claude 'tail /data/services/security-monitor/logs/drift-events-ledger.jsonl | jq -c "{event_id, verdict, retry_count, outcome}"'
# Expect: most events with real verdicts (CONFIRMED / REJECTED / etc.), not RETRY_EXHAUSTED
```

---

## Single WP Decision

This mission ships as **one WP** (WP01). 5 subtasks fit the ideal range.

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Helper accidentally strips inner content (e.g., a triple-backtick that's part of a string inside the JSON). | Very Low | Medium | Line-based strip only checks for backticks at the START of lines. JSON strings with internal backticks (the `rationale` field could conceivably contain code examples) won't trigger a mid-string strip. Tests cover this edge case (EC2 multi-fence). |
| Future model rotation back to unfenced — strip becomes no-op. | Low | None (no-op is the goal). | Test AS3 covers unfenced regression. |
| Future model rotation to a different wrapping (XML tags, prose preamble, etc.). | Low | Medium | Out of scope. If observed, file a follow-up issue; this fix targets ONLY markdown fences. |
| `_strip_code_fence` is called from places other than `_parse_verdict`. | Very Low | Low | Per FR-005 the helper is module-private and called from one site (line ~455). Reviewer verifies via grep. |

---

## Branch Contract — Final Restatement

- Current branch: `main`
- Planning/base: `main`
- Merge target: `main`
- Matches target: `true`

---

## Next Suggested Command

`/spec-kitty.tasks`.
