# Data Model: Audit Judgment Fence-Strip Hardening

**Phase**: 1 — Design

## Entities

**None.**

This mission introduces a pure function (`str → str`), modifies call sites that operate on local-scope strings, and adds tests. There are no persistent entities, no database schemas, no serializable models, no state machines.

## Type signatures

For completeness, the function signature added by this mission:

```python
def _strip_code_fence(text: str) -> str:
    """Strip markdown code fences from an LLM response.

    Returns the input unchanged if no fence is present. Otherwise drops the
    opening fence line and the trailing fence line, then re-strips whitespace.
    """
```

This is the existing function from `drift_interpretation.py:436-458`, relocated to `scripts/doc_audit/judgment/_llm_response.py`.

## State transitions

None. The function is stateless.
