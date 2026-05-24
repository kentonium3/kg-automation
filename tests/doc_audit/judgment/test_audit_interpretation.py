"""Unit tests for ``doc_audit.judgment.audit_interpretation``.

Covers WP01 acceptance for the commit-audit Moment 0 path:

- Happy paths for all three verdict shapes (PROPOSED_EDIT,
  JUDGMENT_REQUIRED, NO_CHANGE_NEEDED).
- Per-doc loop: ``interpret_audit`` with N in-scope docs makes N LLM
  calls and returns N verdicts in order.
- Per-doc isolation: failure on doc 2 does not stop docs 1 / 3 from
  being evaluated.
- Confidence demotion at the 0.80 boundary.
- Out-of-scope ``proposed_edit.doc_path`` demotes to JUDGMENT_REQUIRED
  (audit path does not raise — distinct from drift).
- Schema-violation retry (malformed JSON on first call, valid JSON on
  second).
- Retry exhaustion → synthetic JUDGMENT_REQUIRED for that doc, other
  docs still evaluable.
- ``no_retry`` flag: single attempt per doc, no sleeps.
- CLI exit codes 0 / 1 / 3.
- Cache-control marker assertion (system block carries
  ``cache_control: ephemeral``).
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from doc_audit.judgment.client import JudgmentClient
from doc_audit.judgment.audit_interpretation import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    PROMPT_PATH,
    RETRY_DELAYS_SECONDS,
    VALID_VERDICTS,
    AuditInterpretationContext,
    AuditVerdict,
    DocTarget,
    DriftInterpretationError,
    _build_prompt,
    _demote_low_confidence,
    _parse_verdict,
    _verdict_to_dict,
    interpret_audit,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(
    path: str = "docs/runbooks/habits-ops.md",
    contents: str = "# Habits ops\nrun `python -m habits.cli`\n",
) -> DocTarget:
    return DocTarget(
        path=path,
        contents=contents,
        truncated=False,
        truncation_strategy="full",
    )


def _make_context(
    *,
    in_scope_docs: list[DocTarget] | None = None,
    diff: str = "+ added line\n- removed line\n",
    audit_issue: int = 412,
    commit_sha: str = "a1b2c3d",
) -> AuditInterpretationContext:
    if in_scope_docs is None:
        in_scope_docs = [_make_doc()]
    return AuditInterpretationContext(
        audit_issue=audit_issue,
        commit_sha=commit_sha,
        diff=diff,
        in_scope_docs=in_scope_docs,
    )


def _verdict_payload(text: str, *, input_tokens: int = 400) -> dict[str, Any]:
    return {
        "text": text,
        "usage": {
            "input_tokens": input_tokens,
            "cache_read_input_tokens": int(input_tokens * 0.8),
            "output_tokens": 50,
        },
    }


# ---------------------------------------------------------------------------
# Module-surface smoke tests
# ---------------------------------------------------------------------------


def test_prompt_path_exists() -> None:
    assert PROMPT_PATH.is_file(), f"missing prompt template: {PROMPT_PATH}"


def test_prompt_has_cache_markers() -> None:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    assert "[CACHE_PREFIX_START]" in text
    assert "[CACHE_PREFIX_END]" in text
    assert text.index("[CACHE_PREFIX_START]") < text.index("[CACHE_PREFIX_END]")


def test_module_constants_match_contract() -> None:
    assert DEFAULT_MODEL == "claude-haiku-4-5-20251001"
    assert DEFAULT_TIMEOUT_SECONDS == 30
    assert DEFAULT_CONFIDENCE_THRESHOLD == 0.80
    assert RETRY_DELAYS_SECONDS == (30, 60, 120)
    assert VALID_VERDICTS == {
        "PROPOSED_EDIT",
        "JUDGMENT_REQUIRED",
        "NO_CHANGE_NEEDED",
    }
    assert DEFAULT_MAX_TOKENS >= 256


# ---------------------------------------------------------------------------
# Happy-path verdict shapes (single-doc context)
# ---------------------------------------------------------------------------


def test_interpret_audit_no_change_needed(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    stub_anthropic_response(
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "NO_CHANGE_NEEDED",
                    "confidence": 0.92,
                    "rationale": "Doc does not reference the modified code path.",
                }
            )
        )
    )
    client = JudgmentClient(tmp_config)
    context = _make_context()

    verdicts = interpret_audit(client, context, no_retry=True)

    assert len(verdicts) == 1
    v = verdicts[0]
    assert v.doc_path == context.in_scope_docs[0].path
    assert v.verdict == "NO_CHANGE_NEEDED"
    assert v.confidence == 0.92
    assert "does not reference" in v.rationale
    assert v.proposed_edit is None
    assert v.question is None


def test_interpret_audit_proposed_edit_high_confidence(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    doc_path = "docs/runbooks/habits-ops.md"
    stub_anthropic_response(
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "PROPOSED_EDIT",
                    "confidence": 0.93,
                    "rationale": "CLI flag renamed; doc still references old form.",
                    "proposed_edit": {
                        "doc_path": doc_path,
                        "current_value": "python -m habits.cli --reset-streak",
                        "proposed_value": "python -m habits.cli --reset-counter",
                    },
                }
            )
        )
    )
    client = JudgmentClient(tmp_config)
    context = _make_context(in_scope_docs=[_make_doc(path=doc_path)])

    verdicts = interpret_audit(client, context, no_retry=True)

    assert len(verdicts) == 1
    v = verdicts[0]
    assert v.verdict == "PROPOSED_EDIT"
    assert v.proposed_edit is not None
    assert v.proposed_edit["doc_path"] == doc_path
    assert v.proposed_edit["current_value"] == "python -m habits.cli --reset-streak"
    assert v.question is None


def test_interpret_audit_judgment_required(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    question = "Should this commit's behavior change be reflected in the runbook?"
    stub_anthropic_response(
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "JUDGMENT_REQUIRED",
                    "confidence": 0.55,
                    "rationale": "Multiple plausible doc rewrites depending on operator intent.",
                    "question": question,
                }
            )
        )
    )
    client = JudgmentClient(tmp_config)
    context = _make_context()

    verdicts = interpret_audit(client, context, no_retry=True)

    assert len(verdicts) == 1
    v = verdicts[0]
    assert v.verdict == "JUDGMENT_REQUIRED"
    assert v.question == question
    assert v.proposed_edit is None


# ---------------------------------------------------------------------------
# Multi-doc loop (D2 from data-model — per-doc verdicts)
# ---------------------------------------------------------------------------


def test_interpret_audit_three_docs_three_calls(
    tmp_config, mock_anthropic
) -> None:
    """3 in-scope docs => 3 LLM calls => 3 AuditVerdicts."""
    docs = [
        _make_doc(path="docs/a.md", contents="contents-a"),
        _make_doc(path="docs/b.md", contents="contents-b"),
        _make_doc(path="docs/c.md", contents="contents-c"),
    ]
    payloads = [
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "NO_CHANGE_NEEDED",
                    "confidence": 0.91,
                    "rationale": "doc a is clean",
                }
            )
        ),
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "PROPOSED_EDIT",
                    "confidence": 0.88,
                    "rationale": "doc b needs renaming",
                    "proposed_edit": {
                        "doc_path": "docs/b.md",
                        "current_value": "old",
                        "proposed_value": "new",
                    },
                }
            )
        ),
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "JUDGMENT_REQUIRED",
                    "confidence": 0.45,
                    "rationale": "doc c ambiguous",
                    "question": "How should this section be updated?",
                }
            )
        ),
    ]
    pop_iter = iter(payloads)
    mock_anthropic.messages._loader = lambda _name: next(pop_iter)

    client = JudgmentClient(tmp_config)
    context = _make_context(in_scope_docs=docs)
    verdicts = interpret_audit(client, context, no_retry=True)

    assert len(verdicts) == 3
    assert [v.doc_path for v in verdicts] == ["docs/a.md", "docs/b.md", "docs/c.md"]
    assert verdicts[0].verdict == "NO_CHANGE_NEEDED"
    assert verdicts[1].verdict == "PROPOSED_EDIT"
    assert verdicts[2].verdict == "JUDGMENT_REQUIRED"
    assert len(mock_anthropic.messages.calls) == 3


def test_interpret_audit_per_doc_isolation_doc2_fails(
    tmp_config, mock_anthropic, monkeypatch
) -> None:
    """Doc 2's retry-exhausted failure doesn't stop docs 1 or 3."""
    docs = [
        _make_doc(path="docs/a.md"),
        _make_doc(path="docs/b.md"),
        _make_doc(path="docs/c.md"),
    ]

    call_counter = {"n": 0}

    def loader(_name: str) -> dict[str, Any]:
        call_counter["n"] += 1
        n = call_counter["n"]
        # 1st call (doc a) → valid NO_CHANGE_NEEDED
        if n == 1:
            return _verdict_payload(
                json.dumps(
                    {
                        "verdict": "NO_CHANGE_NEEDED",
                        "confidence": 0.95,
                        "rationale": "ok",
                    }
                )
            )
        # 2nd call (doc b) → always malformed → exhaust retries (single attempt with no_retry)
        if n == 2:
            return _verdict_payload("garbage")
        # 3rd call (doc c) → valid PROPOSED_EDIT
        if n == 3:
            return _verdict_payload(
                json.dumps(
                    {
                        "verdict": "PROPOSED_EDIT",
                        "confidence": 0.88,
                        "rationale": "ok",
                        "proposed_edit": {
                            "doc_path": "docs/c.md",
                            "current_value": "old",
                            "proposed_value": "new",
                        },
                    }
                )
            )
        return _verdict_payload("garbage")

    mock_anthropic.messages._loader = loader

    client = JudgmentClient(tmp_config)
    context = _make_context(in_scope_docs=docs)
    verdicts = interpret_audit(client, context, no_retry=True)

    assert len(verdicts) == 3
    # Doc a — succeeded
    assert verdicts[0].doc_path == "docs/a.md"
    assert verdicts[0].verdict == "NO_CHANGE_NEEDED"
    # Doc b — synthetic JUDGMENT_REQUIRED for retry exhaustion
    assert verdicts[1].doc_path == "docs/b.md"
    assert verdicts[1].verdict == "JUDGMENT_REQUIRED"
    assert verdicts[1].confidence == 0.0
    assert verdicts[1].rationale == "LLM retry exhausted"
    assert verdicts[1].question is not None
    # Doc c — succeeded
    assert verdicts[2].doc_path == "docs/c.md"
    assert verdicts[2].verdict == "PROPOSED_EDIT"


def test_interpret_audit_empty_in_scope_returns_empty(tmp_config) -> None:
    """An empty in_scope_docs list yields an empty verdict list — no LLM call."""
    client = JudgmentClient(tmp_config)
    context = _make_context(in_scope_docs=[])
    # We avoid using mock_anthropic.messages.calls assertion (no LLM call expected)
    verdicts = interpret_audit(client, context, no_retry=True)
    assert verdicts == []


# ---------------------------------------------------------------------------
# Confidence demotion (FR-005, FR-007 boundary)
# ---------------------------------------------------------------------------


def test_interpret_audit_demotes_proposed_edit_below_threshold(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    doc_path = "docs/runbooks/habits-ops.md"
    stub_anthropic_response(
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "PROPOSED_EDIT",
                    "confidence": 0.65,
                    "rationale": "Plausible but not certain.",
                    "proposed_edit": {
                        "doc_path": doc_path,
                        "current_value": "old",
                        "proposed_value": "new",
                    },
                }
            )
        )
    )
    client = JudgmentClient(tmp_config)
    context = _make_context(in_scope_docs=[_make_doc(path=doc_path)])

    verdicts = interpret_audit(client, context, no_retry=True)
    v = verdicts[0]
    assert v.verdict == "JUDGMENT_REQUIRED"
    assert v.confidence == 0.65
    assert "Demoted from PROPOSED_EDIT" in v.rationale
    assert "Original proposed_edit" in v.rationale
    assert v.question is not None
    assert v.proposed_edit is None


def test_interpret_audit_demotes_no_change_needed_below_threshold(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    stub_anthropic_response(
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "NO_CHANGE_NEEDED",
                    "confidence": 0.50,
                    "rationale": "Probably clean.",
                }
            )
        )
    )
    client = JudgmentClient(tmp_config)
    context = _make_context()

    verdicts = interpret_audit(client, context, no_retry=True)
    v = verdicts[0]
    assert v.verdict == "JUDGMENT_REQUIRED"
    assert v.confidence == 0.50
    assert "Demoted from NO_CHANGE_NEEDED" in v.rationale
    assert v.question is not None


def test_demote_at_exact_threshold_no_change() -> None:
    """confidence == 0.80 does NOT demote (≥0.80 is the gate)."""
    v = AuditVerdict(
        doc_path="docs/x.md",
        verdict="PROPOSED_EDIT",
        confidence=0.80,
        rationale="exact",
        proposed_edit={"doc_path": "docs/x.md", "current_value": "a", "proposed_value": "b"},
    )
    assert _demote_low_confidence(v, 0.80) is v


def test_demote_judgment_required_passthrough() -> None:
    v = AuditVerdict(
        doc_path="docs/x.md",
        verdict="JUDGMENT_REQUIRED",
        confidence=0.10,
        rationale="bad",
        question="why?",
    )
    assert _demote_low_confidence(v, 0.80) is v


# ---------------------------------------------------------------------------
# Out-of-scope doc_path — DEMOTE (not raise) per audit-path contract
# ---------------------------------------------------------------------------


def test_interpret_audit_out_of_scope_doc_path_demotes(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """LLM proposing an edit to a path other than the supplied in-scope doc demotes."""
    in_scope_path = "docs/runbooks/habits-ops.md"
    other_path = "docs/UNLISTED.md"
    stub_anthropic_response(
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "PROPOSED_EDIT",
                    "confidence": 0.93,
                    "rationale": "edit suggested",
                    "proposed_edit": {
                        "doc_path": other_path,
                        "current_value": "a",
                        "proposed_value": "b",
                    },
                }
            )
        )
    )
    client = JudgmentClient(tmp_config)
    context = _make_context(in_scope_docs=[_make_doc(path=in_scope_path)])

    verdicts = interpret_audit(client, context, no_retry=True)
    v = verdicts[0]
    assert v.doc_path == in_scope_path
    assert v.verdict == "JUDGMENT_REQUIRED"
    assert v.proposed_edit is None
    assert other_path in v.rationale
    assert in_scope_path in v.rationale
    assert v.question is not None
    assert other_path in v.question


# ---------------------------------------------------------------------------
# Retry policy (D6)
# ---------------------------------------------------------------------------


def test_retry_recovers_from_malformed_json(
    tmp_config, mock_anthropic, monkeypatch
) -> None:
    """Schema violation (bad JSON) retries; second attempt succeeds."""
    payloads = [
        _verdict_payload("not json at all"),
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "NO_CHANGE_NEEDED",
                    "confidence": 0.91,
                    "rationale": "Recovered.",
                }
            )
        ),
    ]
    pop_iter = iter(payloads)
    mock_anthropic.messages._loader = lambda _name: next(pop_iter)

    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))

    client = JudgmentClient(tmp_config)
    verdicts = interpret_audit(client, _make_context())

    assert len(verdicts) == 1
    assert verdicts[0].verdict == "NO_CHANGE_NEEDED"
    assert len(mock_anthropic.messages.calls) == 2
    assert sleeps == [30]


def test_retry_recovers_from_api_timeout(
    tmp_config, mock_anthropic, monkeypatch
) -> None:
    """anthropic.APITimeoutError on first call retries to success on second."""
    import anthropic

    state = {"attempt": 0}

    def fake_create(**kwargs: Any):
        state["attempt"] += 1
        if state["attempt"] == 1:
            request = type("R", (), {})()
            raise anthropic.APITimeoutError(request=request)
        return type(
            "Resp",
            (),
            {
                "content": [
                    type(
                        "Blk",
                        (),
                        {
                            "text": json.dumps(
                                {
                                    "verdict": "NO_CHANGE_NEEDED",
                                    "confidence": 0.95,
                                    "rationale": "Recovered after timeout.",
                                }
                            )
                        },
                    )()
                ],
                "usage": {
                    "input_tokens": 100,
                    "cache_read_input_tokens": 80,
                    "output_tokens": 20,
                },
                "stop_reason": "end_turn",
            },
        )()

    monkeypatch.setattr(mock_anthropic.messages, "create", fake_create)

    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))

    client = JudgmentClient(tmp_config)
    verdicts = interpret_audit(client, _make_context())

    assert len(verdicts) == 1
    assert verdicts[0].verdict == "NO_CHANGE_NEEDED"
    assert state["attempt"] == 2
    assert sleeps == [30]


def test_retry_exhaustion_yields_synthetic_judgment_required(
    tmp_config, mock_anthropic, stub_anthropic_response, monkeypatch
) -> None:
    """4 attempts of bad JSON exhaust retries; verdict is synthetic JUDGMENT_REQUIRED."""
    stub_anthropic_response(_verdict_payload("still not json"))

    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))

    client = JudgmentClient(tmp_config)
    verdicts = interpret_audit(client, _make_context())

    assert len(verdicts) == 1
    v = verdicts[0]
    assert v.verdict == "JUDGMENT_REQUIRED"
    assert v.confidence == 0.0
    assert v.rationale == "LLM retry exhausted"
    assert sleeps == list(RETRY_DELAYS_SECONDS)
    assert len(mock_anthropic.messages.calls) == 4


def test_no_retry_flag_skips_retries(
    tmp_config, mock_anthropic, stub_anthropic_response, monkeypatch
) -> None:
    """no_retry=True: a single failure yields synthetic JUDGMENT_REQUIRED, no sleeps."""
    stub_anthropic_response(_verdict_payload("malformed"))

    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))

    client = JudgmentClient(tmp_config)
    verdicts = interpret_audit(client, _make_context(), no_retry=True)

    assert len(verdicts) == 1
    assert verdicts[0].verdict == "JUDGMENT_REQUIRED"
    assert verdicts[0].rationale == "LLM retry exhausted"
    assert sleeps == []
    assert len(mock_anthropic.messages.calls) == 1


# ---------------------------------------------------------------------------
# Prompt assembly + cache-control marker assertion
# ---------------------------------------------------------------------------


def test_interpret_uses_cache_control(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """The messages.create call carries the system block with cache_control: ephemeral."""
    stub_anthropic_response(
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "NO_CHANGE_NEEDED",
                    "confidence": 0.91,
                    "rationale": "ok",
                }
            )
        )
    )
    client = JudgmentClient(tmp_config)
    interpret_audit(client, _make_context(), no_retry=True)

    assert len(mock_anthropic.messages.calls) == 1
    call_kwargs = mock_anthropic.messages.calls[0]
    system = call_kwargs.get("system")
    assert isinstance(system, list) and len(system) == 1
    block = system[0]
    assert block["type"] == "text"
    assert block["cache_control"] == {"type": "ephemeral"}
    assert "commit-audit interpreter" in block["text"]


def test_build_prompt_includes_doc_path() -> None:
    """The user section enumerates the single in-scope doc path."""
    doc = _make_doc(path="docs/runbooks/habits-ops.md")
    ctx = _make_context(in_scope_docs=[doc])
    user = _build_prompt(doc, ctx)
    assert "docs/runbooks/habits-ops.md" in user
    assert "proposed_edit.doc_path MUST equal" in user
    assert "audit_issue: 412" in user
    assert "commit_sha: a1b2c3d" in user


# ---------------------------------------------------------------------------
# Parser edge cases (cover invalid shapes that should retry)
# ---------------------------------------------------------------------------


def test_parse_rejects_unknown_verdict() -> None:
    from doc_audit.judgment.audit_interpretation import _RetrySchemaError
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(
            json.dumps(
                {
                    "verdict": "MAYBE",
                    "confidence": 0.9,
                    "rationale": "x",
                }
            ),
            _make_doc(),
        )


def test_parse_rejects_confidence_out_of_range() -> None:
    from doc_audit.judgment.audit_interpretation import _RetrySchemaError
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(
            json.dumps(
                {
                    "verdict": "NO_CHANGE_NEEDED",
                    "confidence": 2.0,
                    "rationale": "x",
                }
            ),
            _make_doc(),
        )


def test_parse_rejects_bool_confidence() -> None:
    from doc_audit.judgment.audit_interpretation import _RetrySchemaError
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(
            json.dumps(
                {
                    "verdict": "NO_CHANGE_NEEDED",
                    "confidence": True,
                    "rationale": "x",
                }
            ),
            _make_doc(),
        )


def test_parse_rejects_missing_rationale() -> None:
    from doc_audit.judgment.audit_interpretation import _RetrySchemaError
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(
            json.dumps(
                {
                    "verdict": "NO_CHANGE_NEEDED",
                    "confidence": 0.9,
                    "rationale": "  ",
                }
            ),
            _make_doc(),
        )


def test_parse_rejects_judgment_without_question() -> None:
    from doc_audit.judgment.audit_interpretation import _RetrySchemaError
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(
            json.dumps(
                {
                    "verdict": "JUDGMENT_REQUIRED",
                    "confidence": 0.5,
                    "rationale": "x",
                }
            ),
            _make_doc(),
        )


def test_parse_rejects_judgment_overlong_question() -> None:
    from doc_audit.judgment.audit_interpretation import _RetrySchemaError
    long_q = "?" * 600
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(
            json.dumps(
                {
                    "verdict": "JUDGMENT_REQUIRED",
                    "confidence": 0.5,
                    "rationale": "x",
                    "question": long_q,
                }
            ),
            _make_doc(),
        )


def test_parse_rejects_proposed_edit_without_object() -> None:
    from doc_audit.judgment.audit_interpretation import _RetrySchemaError
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(
            json.dumps(
                {
                    "verdict": "PROPOSED_EDIT",
                    "confidence": 0.9,
                    "rationale": "x",
                }
            ),
            _make_doc(),
        )


def test_parse_rejects_empty_response() -> None:
    from doc_audit.judgment.audit_interpretation import _RetrySchemaError
    with pytest.raises(_RetrySchemaError):
        _parse_verdict("   ", _make_doc())


def test_parse_rejects_non_object_json() -> None:
    from doc_audit.judgment.audit_interpretation import _RetrySchemaError
    with pytest.raises(_RetrySchemaError):
        _parse_verdict("[1, 2, 3]", _make_doc())


def test_parse_rejects_missing_proposed_edit_subfields() -> None:
    from doc_audit.judgment.audit_interpretation import _RetrySchemaError
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(
            json.dumps(
                {
                    "verdict": "PROPOSED_EDIT",
                    "confidence": 0.9,
                    "rationale": "x",
                    "proposed_edit": {
                        "doc_path": "docs/runbooks/habits-ops.md",
                        "current_value": "a",
                        # proposed_value missing
                    },
                }
            ),
            _make_doc(),
        )


def test_parse_rejects_invalid_json() -> None:
    from doc_audit.judgment.audit_interpretation import _RetrySchemaError
    with pytest.raises(_RetrySchemaError):
        _parse_verdict("{not-json", _make_doc())


# ---------------------------------------------------------------------------
# verdict_to_dict helper
# ---------------------------------------------------------------------------


def test_verdict_to_dict_drops_none_fields() -> None:
    v = AuditVerdict(
        doc_path="docs/x.md",
        verdict="NO_CHANGE_NEEDED",
        confidence=0.9,
        rationale="ok",
    )
    out = _verdict_to_dict(v)
    assert "proposed_edit" not in out
    assert "question" not in out
    assert out["verdict"] == "NO_CHANGE_NEEDED"
    assert out["doc_path"] == "docs/x.md"


def test_verdict_to_dict_carries_proposed_edit() -> None:
    v = AuditVerdict(
        doc_path="docs/x.md",
        verdict="PROPOSED_EDIT",
        confidence=0.9,
        rationale="ok",
        proposed_edit={"doc_path": "docs/x.md", "current_value": "a", "proposed_value": "b"},
    )
    out = _verdict_to_dict(v)
    assert out["proposed_edit"] == {"doc_path": "docs/x.md", "current_value": "a", "proposed_value": "b"}
    assert "question" not in out


def test_verdict_to_dict_carries_question() -> None:
    v = AuditVerdict(
        doc_path="docs/x.md",
        verdict="JUDGMENT_REQUIRED",
        confidence=0.5,
        rationale="ok",
        question="really?",
    )
    out = _verdict_to_dict(v)
    assert out["question"] == "really?"
    assert "proposed_edit" not in out


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def _make_cli_input(audit_issue: int = 412, doc_count: int = 1) -> dict[str, Any]:
    docs = []
    for i in range(doc_count):
        docs.append(
            {
                "path": f"docs/runbooks/example-{i}.md",
                "contents": f"contents {i}",
                "truncated": False,
                "truncation_strategy": "full",
            }
        )
    return {
        "audit_issue": audit_issue,
        "commit_sha": "a1b2c3d",
        "diff": "--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new\n",
        "in_scope_docs": docs,
    }


def _setup_cli_env(monkeypatch, tmp_path: Path) -> Path:
    api_key_path = tmp_path / "anthropic.key"
    api_key_path.write_text("test-key", encoding="utf-8")

    from doc_audit.config import Config, GitHubConfig, LLMConfig, PathsConfig, SignalsConfig

    def _fake_builder(api_key_path_arg: Path, model: str) -> JudgmentClient:
        cfg = Config(
            llm=LLMConfig(
                model=model,
                api_key_path=str(api_key_path_arg),
                max_tokens=512,
            ),
            paths=PathsConfig(
                prompts_dir="/tmp/prompts",
                drift_events="/tmp/drift-events.jsonl",
                drift_cursor="/tmp/.drift-events.cursor",
                drift_unmapped="/tmp/unmapped-events.jsonl",
                signal_to_doc_map="/tmp/signal-to-doc-map.json",
                doc_domain_map="/tmp/doc-domain-map.json",
                activity_log_dir="/tmp/activity",
                tick_signal_path="/tmp/last-tick.json",
            ),
            signals=SignalsConfig(sources=["gh_issue"]),
            github=GitHubConfig(repo="kentonium3/kg-automation", bot_identity="kg-felix-bot"),
        )
        return JudgmentClient(cfg)

    monkeypatch.setattr(
        "doc_audit.judgment.audit_interpretation._build_cli_client",
        _fake_builder,
    )
    return api_key_path


def test_cli_help_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "audit_interpretation" in captured.out


def test_cli_exit_0_success(
    tmp_path, mock_anthropic, stub_anthropic_response, monkeypatch
) -> None:
    """Valid input + mocked SDK returns 0; output JSON array written."""
    api_key_path = _setup_cli_env(monkeypatch, tmp_path)
    stub_anthropic_response(
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "NO_CHANGE_NEEDED",
                    "confidence": 0.91,
                    "rationale": "ok",
                }
            )
        )
    )
    input_path = tmp_path / "in.json"
    output_path = tmp_path / "out.json"
    input_path.write_text(json.dumps(_make_cli_input()), encoding="utf-8")

    rc = main(
        [
            "--input-file",
            str(input_path),
            "--output-file",
            str(output_path),
            "--api-key-path",
            str(api_key_path),
            "--no-retry",
        ]
    )
    assert rc == 0
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert isinstance(written, list)
    assert len(written) == 1
    assert written[0]["verdict"] == "NO_CHANGE_NEEDED"
    assert written[0]["doc_path"] == "docs/runbooks/example-0.md"


def test_cli_exit_0_writes_array_for_multiple_docs(
    tmp_path, mock_anthropic, monkeypatch
) -> None:
    api_key_path = _setup_cli_env(monkeypatch, tmp_path)
    payloads = [
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "NO_CHANGE_NEEDED",
                    "confidence": 0.95,
                    "rationale": "a clean",
                }
            )
        ),
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "NO_CHANGE_NEEDED",
                    "confidence": 0.92,
                    "rationale": "b clean",
                }
            )
        ),
    ]
    pop_iter = iter(payloads)
    mock_anthropic.messages._loader = lambda _name: next(pop_iter)

    input_path = tmp_path / "in.json"
    output_path = tmp_path / "out.json"
    input_path.write_text(json.dumps(_make_cli_input(doc_count=2)), encoding="utf-8")

    rc = main(
        [
            "--input-file",
            str(input_path),
            "--output-file",
            str(output_path),
            "--api-key-path",
            str(api_key_path),
            "--no-retry",
        ]
    )
    assert rc == 0
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(written) == 2


def test_cli_exit_3_on_malformed_input(
    tmp_path, monkeypatch, capsys
) -> None:
    _setup_cli_env(monkeypatch, tmp_path)
    input_path = tmp_path / "in.json"
    input_path.write_text("not json at all", encoding="utf-8")
    rc = main(
        [
            "--input-file",
            str(input_path),
        ]
    )
    assert rc == 3
    err = capsys.readouterr().err
    assert "input_parse" in err


def test_cli_exit_3_on_missing_input_file(
    tmp_path, monkeypatch, capsys
) -> None:
    _setup_cli_env(monkeypatch, tmp_path)
    rc = main(
        [
            "--input-file",
            str(tmp_path / "does-not-exist.json"),
        ]
    )
    assert rc == 3


def test_cli_exit_3_on_bad_args(tmp_path, monkeypatch, capsys) -> None:
    _setup_cli_env(monkeypatch, tmp_path)
    rc = main(["--definitely-not-a-real-flag"])
    assert rc == 3
    err = capsys.readouterr().err
    assert "argparse" in err


def test_cli_reads_stdin(
    tmp_path, mock_anthropic, stub_anthropic_response, monkeypatch
) -> None:
    api_key_path = _setup_cli_env(monkeypatch, tmp_path)
    stub_anthropic_response(
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "NO_CHANGE_NEEDED",
                    "confidence": 0.93,
                    "rationale": "stdin path",
                }
            )
        )
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_make_cli_input())))

    rc = main(
        [
            "--api-key-path",
            str(api_key_path),
            "--no-retry",
        ]
    )
    assert rc == 0


def test_cli_writes_stdout(
    tmp_path, mock_anthropic, stub_anthropic_response, monkeypatch, capsys
) -> None:
    api_key_path = _setup_cli_env(monkeypatch, tmp_path)
    stub_anthropic_response(
        _verdict_payload(
            json.dumps(
                {
                    "verdict": "NO_CHANGE_NEEDED",
                    "confidence": 0.93,
                    "rationale": "stdout path",
                }
            )
        )
    )
    input_path = tmp_path / "in.json"
    input_path.write_text(json.dumps(_make_cli_input()), encoding="utf-8")

    rc = main(
        [
            "--input-file",
            str(input_path),
            "--api-key-path",
            str(api_key_path),
            "--no-retry",
        ]
    )
    assert rc == 0
    body = json.loads(capsys.readouterr().out)
    assert isinstance(body, list)
    assert body[0]["verdict"] == "NO_CHANGE_NEEDED"


def test_cli_input_missing_required_field(tmp_path, monkeypatch, capsys) -> None:
    _setup_cli_env(monkeypatch, tmp_path)
    input_path = tmp_path / "in.json"
    input_path.write_text(json.dumps({"audit_issue": 412}), encoding="utf-8")
    rc = main(["--input-file", str(input_path)])
    assert rc == 3


def test_cli_input_not_an_object(tmp_path, monkeypatch, capsys) -> None:
    _setup_cli_env(monkeypatch, tmp_path)
    input_path = tmp_path / "in.json"
    input_path.write_text("[1, 2, 3]", encoding="utf-8")
    rc = main(["--input-file", str(input_path)])
    assert rc == 3


def test_cli_input_empty_in_scope_docs(tmp_path, monkeypatch, capsys) -> None:
    _setup_cli_env(monkeypatch, tmp_path)
    input_path = tmp_path / "in.json"
    input_path.write_text(
        json.dumps(
            {
                "audit_issue": 412,
                "commit_sha": "abc",
                "diff": "",
                "in_scope_docs": [],
            }
        ),
        encoding="utf-8",
    )
    rc = main(["--input-file", str(input_path)])
    assert rc == 3


def test_cli_input_non_int_audit_issue(tmp_path, monkeypatch, capsys) -> None:
    _setup_cli_env(monkeypatch, tmp_path)
    input_path = tmp_path / "in.json"
    input_path.write_text(
        json.dumps(
            {
                "audit_issue": "not-an-int",
                "commit_sha": "abc",
                "diff": "",
                "in_scope_docs": [
                    {
                        "path": "docs/x.md",
                        "contents": "x",
                        "truncated": False,
                        "truncation_strategy": "full",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rc = main(["--input-file", str(input_path)])
    assert rc == 3


def test_cli_input_doc_missing_field(tmp_path, monkeypatch, capsys) -> None:
    _setup_cli_env(monkeypatch, tmp_path)
    input_path = tmp_path / "in.json"
    input_path.write_text(
        json.dumps(
            {
                "audit_issue": 412,
                "commit_sha": "abc",
                "diff": "",
                "in_scope_docs": [{"path": "docs/x.md"}],
            }
        ),
        encoding="utf-8",
    )
    rc = main(["--input-file", str(input_path)])
    assert rc == 3


def test_cli_input_doc_not_object(tmp_path, monkeypatch, capsys) -> None:
    _setup_cli_env(monkeypatch, tmp_path)
    input_path = tmp_path / "in.json"
    input_path.write_text(
        json.dumps(
            {
                "audit_issue": 412,
                "commit_sha": "abc",
                "diff": "",
                "in_scope_docs": ["not-an-object"],
            }
        ),
        encoding="utf-8",
    )
    rc = main(["--input-file", str(input_path)])
    assert rc == 3
