---
title: "Diagnostic: drift_interpretation payload shape (issue #404 root cause)"
doc_type: diagnostic
status: active
---
# Diagnostic: drift_interpretation payload shape (issue #404 root cause)

**Date captured**: 2026-05-25
**Mission**: drift-interpretation-payload-capture-01KSEJD7
**Status**: ANALYSIS COMPLETE — follow-up fix tracked in #411

## Summary

The `_RetrySchemaError` that is exhausting all 4 retries on every Moment 0
drift event is **not** a schema violation. The LLM is returning well-formed,
on-schema JSON — but wrapping it in Markdown code fences (` ```json ... ``` `).
`_parse_verdict` calls `json.loads()` on the raw response, which fails at
"line 1 column 1 (char 0)" because char 0 is the opening backtick.

The retry budget never recovers because the LLM consistently re-wraps the
output the same way on every retry — same model, same prompt, same prefix
character.

## Captured payload (sanitized)

Captured from `journalctl --user -u felix-doc-auditor.service` on office2 with
`DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` set via a systemd drop-in. Six independent
`drift_interpretation.schema_fail` log lines were captured across two distinct
drift events and 6 retry attempts. The shape was identical in every case.

Representative captured response (the leading/trailing characters that defeat
`json.loads()` are preserved verbatim; the `rationale` text has been collapsed
to a short non-substantive placeholder so the doc artifact does not embed
LLM-emitted analysis of unrelated paths):

```text
```json
{
  "verdict": "NO_CHANGE_NEEDED",
  "confidence": 0.90,
  "rationale": "<sanitized — single-sentence rationale referencing a non-tracked field>"
}
```
```

The outer triple-backtick fences (with the `json` language hint) are part of
the LLM response body. The inner JSON is structurally valid and on-schema —
all three required fields (`verdict`, `confidence`, `rationale`) are present,
`verdict` is one of `VALID_VERDICTS`, `confidence` is a float in `[0, 1]`.

## Raise-site identification

The `_RetrySchemaError` carries message:
`invalid JSON: Expecting value: line 1 column 1 (char 0)`.

Raise site: `scripts/doc_audit/judgment/drift_interpretation.py:455`
(the `json.JSONDecodeError` branch of `_parse_verdict`). The error text
"Expecting value: line 1 column 1 (char 0)" is the standard `json.loads()`
error for input whose first non-whitespace character is not a valid JSON
token start — here, the backtick of ` ``` `.

In the post-mission #53 code, `_log_raw_response_if_debug` at line 454
captures the raw `response_text` before the raise, which is how this
diagnostic was assembled.

## Schema vs payload diff

**Expected by `_parse_verdict`** (per `drift_interpretation.prompt.md` and
`contracts/llm-json.md`):

```json
{ "verdict": "...", "confidence": 0.9, "rationale": "..." }
```

Raw response text (`response.content[0].text`) must be a single JSON object
literal. The prompt instructs: *"Return STRICT JSON in one of the three
shapes. No prose."*

**Actual on the wire**:

```
```json
{ "verdict": "...", "confidence": 0.9, "rationale": "..." }
```
```

The inner object matches the schema perfectly. The outer Markdown code-fence
wrapper is the defect.

**Diff**: the LLM is honoring "no prose" but is treating the JSON body as a
code block and wrapping it in a ` ```json ` … ` ``` ` fence. `json.loads()`
rejects this because the literal string is no longer a JSON value at char 0.

## Root cause hypothesis

- [ ] Prompt regression
- [ ] Schema regression
- [x] Model behavior change

**Justification**: The prompt has not been altered in the time window
spanning this regression (last touched by mission #362, deployed since then;
this prompt has been working before #404). The Pydantic-like schema in
`_parse_verdict` is unchanged across the same window. What did change is
that the Haiku 4.5 deployment now defaults to Markdown-fenced output for
JSON-shape responses; the prompt's "STRICT JSON … no prose" instruction is
not strong enough to suppress that default. (Strictly, this could also be
framed as a *prompt-regression-against-evolving-model-behavior* — the prompt
that worked yesterday no longer works today because the model's default
formatting shifted under us. Either framing points at the same fix.)

Six independent captures across two unrelated drift events (a `.bak` file
appearing in `systemd-user-dropins.txt` and a `deliveryMode` change in
`openclaw-cron.txt`) all produced fenced output. The pattern is not
content-dependent.

## Recommended follow-up fix shape

Strip Markdown code fences in `_parse_verdict` before calling `json.loads()`.
The minimal robust pattern is: after `text = (response_text or "").strip()`,
if `text` starts with `"\`\`\`"`, drop the first line (which may be
`\`\`\`json` or just `\`\`\``) and the trailing fence line, then re-strip. A
small helper `_strip_code_fence(text: str) -> str` keeps the change
mechanically reviewable. The empty/non-string/multi-block edge cases should
fall through to the existing `_RetrySchemaError("invalid JSON: …")` branch
unchanged. Additionally, the prompt could be tightened (e.g., "Do not wrap
the JSON in code fences. Emit only the JSON object.") as a belt-and-suspenders
layer, but the parser-side fix is the load-bearing change since the prompt
fix alone is at the mercy of model behavior.

## Next steps

1. File follow-up issue with this diagnostic as input.
2. Re-enable timer once follow-up fix AND #402 land.
3. Archive this doc after the fix verifies (move to `docs/archive/diagnostics/`).

## Discovered

2026-05-25 by claude (mission drift-interpretation-payload-capture-01KSEJD7, issue #404).
