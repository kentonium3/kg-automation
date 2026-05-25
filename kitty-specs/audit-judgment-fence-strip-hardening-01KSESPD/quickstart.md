# Quickstart: Audit Judgment Fence-Strip Hardening

**Audience**: Developer (or future agent) touching the doc-audit judgment scripts after this mission merges.

## What this mission did

Centralized the markdown-code-fence-stripping helper that the doc-audit judgment scripts use before `json.loads()`-ing LLM responses. Replaced four separate parse-time defenses (one fixed, three vulnerable pre-mission) with one shared implementation.

## Where the helper lives

```
scripts/doc_audit/judgment/_llm_response.py
```

A single function: `_strip_code_fence(text: str) -> str`.

## When to use it

Any time a judgment-pipeline script calls `json.loads()` on a raw LLM response. The helper is a no-op pass-through for unfenced inputs, so calling it is always safe and never wrong.

## When NOT to use it

- Parsing **internal artifacts** (e.g., `_parse_context_document` reads files we wrote ourselves; those never get fence-wrapped).
- Parsing responses from non-LLM sources (HTTP APIs returning JSON, file reads, etc.).
- Anywhere outside `scripts/doc_audit/judgment/` — the helper is package-private (leading underscore).

## How to add a new judgment script that calls an LLM

1. Import the helper at the top of the new module:
   ```python
   from doc_audit.judgment._llm_response import _strip_code_fence
   ```
2. At the `json.loads()` site:
   ```python
   parsed = json.loads(_strip_code_fence(response_text))
   ```
3. Add at least one fenced + one unfenced regression case to the script's test file (mirror what `test_audit_interpretation.py`, `test_cross_file_implication.py`, `test_drift_interpretation.py`, or `test_tier_classification.py` do).

## How to verify a deployed change

After merging and deploying to office2:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && git pull origin main'
ssh office2-claude 'systemctl --user start felix-doc-auditor.service'
# wait ~3-5 minutes for a tick to complete
ssh office2-claude 'journalctl --user -u felix-doc-auditor.service -n 200 --no-pager'
```

Expected journal mix:
- Zero `_RetrySchemaError` lines attributable to fence-wrapping from any of the protected scripts.
- `size-guard short-circuit` lines for oversized prompts (existing mission #56 behavior).
- Real verdicts (`NO_CHANGE_NEEDED`, `CONFIRMED`, `JUDGMENT_REQUIRED`, etc.) for below-threshold prompts.

## How to run tests locally

```bash
cd /Users/kentgale/repos/kg-automation
pytest tests/doc_audit/judgment/ -v
```

Includes the new `test_llm_response.py` and the extended regression cases in each `test_<judgment-script>.py` file.

## Related references

- Issue [#416](https://github.com/kentonium3/kg-automation/issues/416) — this mission's tracking issue.
- Mission #55 (commit `0e87918f`) — original `_strip_code_fence` for `drift_interpretation` only.
- Mission #56 (commit `3356b9b0`) — 180K-token size guard that surfaced this bug for `audit_interpretation`.
- Diagnostic: `docs/diagnostics/drift-interpretation-payload-shape.md` — observed Haiku 4.5 fence behavior.
