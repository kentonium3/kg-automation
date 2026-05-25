"""Unit tests for ``doc_audit.judgment.drift_interpretation``.

Covers WP01 acceptance per the contracts:

- Happy paths for all three verdict shapes (PROPOSED_EDIT,
  JUDGMENT_REQUIRED, NO_CHANGE_NEEDED).
- Confidence demotion at the 0.80 boundary for both demote-eligible
  verdicts.
- Out-of-set ``proposed_edit.doc_path`` rejection — no retry, semantic
  violation maps to exit 5.
- Schema-violation retry (malformed JSON on first call, valid JSON on
  second).
- API-timeout retry (anthropic.APITimeoutError on first call,
  valid response on second).
- Retry exhaustion after 4 attempts of malformed JSON.
- ``no_retry`` flag: single attempt, no sleeps.
- Truncation tiers (full, head_region_tail, region_only).
- CLI exit codes 0 / 1 / 3 / 5.
- Cache-control marker assertion (system block carries
  ``cache_control: ephemeral``).
"""
from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Any

import pytest

# Tests rely on the conftest at tests/doc_audit/conftest.py for the
# sys.path bootstrap, ``tmp_config``, ``mock_anthropic``, and the
# ``stub_anthropic_response`` helper (in the WP04-local conftest one
# directory up). We re-export the helper here via the
# tests/doc_audit/judgment/conftest.py.

from doc_audit.judgment.client import JudgmentClient
from doc_audit.judgment.drift_interpretation import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    PROMPT_PATH,
    RETRY_DELAYS_SECONDS,
    VALID_VERDICTS,
    DocTarget,
    DriftInterpretationContext,
    DriftInterpretationError,
    DriftVerdict,
    _build_prompt,
    _call_with_retry,
    _demote_low_confidence,
    _parse_verdict,
    _truncate_doc_state,
    _verdict_to_dict,
    interpret,
    main,
)


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    *,
    doc_targets: list[DocTarget] | None = None,
    diff: str = "+ added line\n- removed line\n",
) -> DriftInterpretationContext:
    """Build a minimal valid DriftInterpretationContext."""
    if doc_targets is None:
        doc_targets = [
            DocTarget(
                path="docs/design/architecture/data/service-inventory.json",
                contents='{"openclaw": {"cron_entries": []}}',
                truncated=False,
                truncation_strategy="full",
            )
        ]
    return DriftInterpretationContext(
        event_id="47:2026-05-22T03:00:07Z",
        timestamp_utc="2026-05-22T03:00:07Z",
        baseline="openclaw-cron",
        mapping_id="openclaw-cron-drift",
        mapping_rationale="OpenClaw cron config drift maps to service-inventory.json",
        diff=diff,
        doc_targets=doc_targets,
    )


def _verdict_payload(text: str, *, input_tokens: int = 400) -> dict[str, Any]:
    """Build a fake-Anthropic response payload carrying ``text``."""
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
    """The checked-in prompt template is reachable."""
    assert PROMPT_PATH.is_file(), f"missing prompt template: {PROMPT_PATH}"


def test_prompt_has_cache_markers() -> None:
    """Prompt has both [CACHE_PREFIX_START] and [CACHE_PREFIX_END]."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    assert "[CACHE_PREFIX_START]" in text
    assert "[CACHE_PREFIX_END]" in text
    assert text.index("[CACHE_PREFIX_START]") < text.index("[CACHE_PREFIX_END]")


def test_module_constants_match_contract() -> None:
    """Spot-check module constants against the API + CLI contracts."""
    assert DEFAULT_MODEL == "claude-haiku-4-5-20251001"
    assert DEFAULT_TIMEOUT_SECONDS == 30
    assert DEFAULT_CONFIDENCE_THRESHOLD == 0.80
    assert RETRY_DELAYS_SECONDS == (30, 60, 120)
    assert VALID_VERDICTS == {
        "PROPOSED_EDIT",
        "JUDGMENT_REQUIRED",
        "NO_CHANGE_NEEDED",
    }
    # DEFAULT_MAX_TOKENS bounds output (≤200 expected per llm-json.md token budget).
    assert DEFAULT_MAX_TOKENS >= 256


# ---------------------------------------------------------------------------
# Happy-path verdict shapes
# ---------------------------------------------------------------------------


def test_interpret_no_change_needed(tmp_config, mock_anthropic, stub_anthropic_response) -> None:
    """High-confidence NO_CHANGE_NEEDED passes through unchanged."""
    stub_anthropic_response(
        _verdict_payload(json.dumps({
            "verdict": "NO_CHANGE_NEEDED",
            "confidence": 0.92,
            "rationale": "Docs do not enumerate the drifted field.",
        }))
    )
    client = JudgmentClient(tmp_config)
    context = _make_context()

    verdict = interpret(client, context, no_retry=True)

    assert verdict.verdict == "NO_CHANGE_NEEDED"
    assert verdict.confidence == 0.92
    assert "do not enumerate" in verdict.rationale
    assert verdict.proposed_edit is None
    assert verdict.question is None


def test_interpret_proposed_edit_high_confidence(tmp_config, mock_anthropic, stub_anthropic_response) -> None:
    """High-confidence PROPOSED_EDIT passes through with all fields populated."""
    stub_anthropic_response(
        _verdict_payload(json.dumps({
            "verdict": "PROPOSED_EDIT",
            "confidence": 0.88,
            "rationale": "Inventory enumerates dropins; new dropin file is missing.",
            "proposed_edit": {
                "doc_path": "docs/design/architecture/data/service-inventory.json",
                "current_value": "old",
                "proposed_value": "new",
                "rationale_detail": "Add claude-cron-watch.conf to the dropins list.",
            },
        }))
    )
    client = JudgmentClient(tmp_config)
    context = _make_context()

    verdict = interpret(client, context, no_retry=True)

    assert verdict.verdict == "PROPOSED_EDIT"
    assert verdict.confidence == 0.88
    assert verdict.proposed_edit is not None
    assert verdict.proposed_edit["doc_path"] == (
        "docs/design/architecture/data/service-inventory.json"
    )
    assert verdict.proposed_edit["current_value"] == "old"
    assert verdict.proposed_edit["proposed_value"] == "new"
    assert verdict.question is None


def test_interpret_judgment_required(tmp_config, mock_anthropic, stub_anthropic_response) -> None:
    """JUDGMENT_REQUIRED returns with the LLM's question carried through."""
    question = "Should the new deliveryMode field be added to service-inventory.json?"
    stub_anthropic_response(
        _verdict_payload(json.dumps({
            "verdict": "JUDGMENT_REQUIRED",
            "confidence": 0.55,
            "rationale": "Cannot determine without operator intent.",
            "question": question,
        }))
    )
    client = JudgmentClient(tmp_config)
    context = _make_context()

    verdict = interpret(client, context, no_retry=True)

    assert verdict.verdict == "JUDGMENT_REQUIRED"
    assert verdict.question == question
    assert verdict.proposed_edit is None


# ---------------------------------------------------------------------------
# Confidence demotion (FR-005, FR-007 boundary)
# ---------------------------------------------------------------------------


def test_interpret_demotes_proposed_edit_below_threshold(tmp_config, mock_anthropic, stub_anthropic_response) -> None:
    """PROPOSED_EDIT with confidence <0.80 demotes to JUDGMENT_REQUIRED."""
    stub_anthropic_response(
        _verdict_payload(json.dumps({
            "verdict": "PROPOSED_EDIT",
            "confidence": 0.65,
            "rationale": "Plausible but not certain.",
            "proposed_edit": {
                "doc_path": "docs/design/architecture/data/service-inventory.json",
                "current_value": "old",
                "proposed_value": "new",
            },
        }))
    )
    client = JudgmentClient(tmp_config)
    context = _make_context()

    verdict = interpret(client, context, no_retry=True)

    assert verdict.verdict == "JUDGMENT_REQUIRED"
    assert verdict.confidence == 0.65  # confidence preserved post-demotion
    assert "Demoted from PROPOSED_EDIT" in verdict.rationale
    assert "Plausible but not certain" in verdict.rationale
    assert "Original proposed_edit" in verdict.rationale
    assert verdict.question is not None
    assert verdict.proposed_edit is None


def test_interpret_demotes_no_change_needed_below_threshold(tmp_config, mock_anthropic, stub_anthropic_response) -> None:
    """NO_CHANGE_NEEDED with confidence <0.80 demotes to JUDGMENT_REQUIRED."""
    stub_anthropic_response(
        _verdict_payload(json.dumps({
            "verdict": "NO_CHANGE_NEEDED",
            "confidence": 0.50,
            "rationale": "Probably no change but not confident.",
        }))
    )
    client = JudgmentClient(tmp_config)
    context = _make_context()

    verdict = interpret(client, context, no_retry=True)

    assert verdict.verdict == "JUDGMENT_REQUIRED"
    assert verdict.confidence == 0.50
    assert "Demoted from NO_CHANGE_NEEDED" in verdict.rationale
    assert verdict.question is not None


def test_demote_at_exact_threshold_no_change(tmp_config) -> None:
    """confidence == threshold does NOT demote (≥0.80 is the gate)."""
    v = DriftVerdict(
        verdict="PROPOSED_EDIT",
        confidence=0.80,
        rationale="exact",
        proposed_edit={"doc_path": "x", "current_value": "a", "proposed_value": "b"},
    )
    assert _demote_low_confidence(v, 0.80) is v


def test_demote_judgment_required_passthrough() -> None:
    """JUDGMENT_REQUIRED verdicts are never demoted further."""
    v = DriftVerdict(
        verdict="JUDGMENT_REQUIRED",
        confidence=0.10,
        rationale="bad",
        question="why?",
    )
    assert _demote_low_confidence(v, 0.80) is v


# ---------------------------------------------------------------------------
# Out-of-set doc_path — semantic violation (exit 5, no retry)
# ---------------------------------------------------------------------------


def test_interpret_raises_on_out_of_set_doc_path(tmp_config, mock_anthropic, stub_anthropic_response) -> None:
    """Out-of-set ``proposed_edit.doc_path`` raises DriftInterpretationError."""
    stub_anthropic_response(
        _verdict_payload(json.dumps({
            "verdict": "PROPOSED_EDIT",
            "confidence": 0.90,
            "rationale": "Edit suggested.",
            "proposed_edit": {
                "doc_path": "docs/some/UNLISTED.md",
                "current_value": "old",
                "proposed_value": "new",
            },
        }))
    )
    client = JudgmentClient(tmp_config)
    context = _make_context()

    with pytest.raises(DriftInterpretationError) as exc_info:
        interpret(client, context, no_retry=True)

    assert "out-of-set" in str(exc_info.value)
    # The error must propagate immediately — no retry. Verify the
    # client was called exactly once.
    assert len(mock_anthropic.messages.calls) == 1


def test_out_of_set_doc_path_not_retried(tmp_config, mock_anthropic, stub_anthropic_response, monkeypatch) -> None:
    """Even with full retry budget, semantic violation never retries."""
    stub_anthropic_response(
        _verdict_payload(json.dumps({
            "verdict": "PROPOSED_EDIT",
            "confidence": 0.90,
            "rationale": "bad path",
            "proposed_edit": {
                "doc_path": "docs/UNLISTED.md",
                "current_value": "a",
                "proposed_value": "b",
            },
        }))
    )
    client = JudgmentClient(tmp_config)
    context = _make_context()

    # Patch time.sleep so a retry would be detectable as a sleep call;
    # we expect zero sleeps because semantic errors propagate.
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))

    with pytest.raises(DriftInterpretationError):
        interpret(client, context)  # no_retry=False — full budget

    assert sleeps == []
    assert len(mock_anthropic.messages.calls) == 1


# ---------------------------------------------------------------------------
# Retry policy (D6)
# ---------------------------------------------------------------------------


def test_retry_recovers_from_malformed_json(tmp_config, mock_anthropic, monkeypatch) -> None:
    """Schema violation (bad JSON) retries; second attempt succeeds."""
    payloads = [
        _verdict_payload("not json at all"),
        _verdict_payload(json.dumps({
            "verdict": "NO_CHANGE_NEEDED",
            "confidence": 0.91,
            "rationale": "Recovered.",
        })),
    ]
    pop_iter = iter(payloads)
    mock_anthropic.messages._loader = lambda _name: next(pop_iter)

    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))

    client = JudgmentClient(tmp_config)
    verdict = interpret(client, _make_context())

    assert verdict.verdict == "NO_CHANGE_NEEDED"
    assert len(mock_anthropic.messages.calls) == 2
    assert sleeps == [30]  # one retry-sleep (first delay)


def test_retry_recovers_from_api_timeout(tmp_config, mock_anthropic, monkeypatch) -> None:
    """anthropic.APITimeoutError on first call retries to success on second."""
    import anthropic

    state = {"attempt": 0}

    def fake_create(**kwargs: Any):
        state["attempt"] += 1
        if state["attempt"] == 1:
            request = type("R", (), {})()
            raise anthropic.APITimeoutError(request=request)
        # success on retry
        return type("Resp", (), {
            "content": [type("Blk", (), {"text": json.dumps({
                "verdict": "NO_CHANGE_NEEDED",
                "confidence": 0.95,
                "rationale": "Recovered after timeout.",
            })})()],
            "usage": {"input_tokens": 100, "cache_read_input_tokens": 80, "output_tokens": 20},
            "stop_reason": "end_turn",
        })()

    monkeypatch.setattr(mock_anthropic.messages, "create", fake_create)

    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))

    client = JudgmentClient(tmp_config)
    verdict = interpret(client, _make_context())

    assert verdict.verdict == "NO_CHANGE_NEEDED"
    assert state["attempt"] == 2
    assert sleeps == [30]


def test_retry_exhaustion_raises_drift_interpretation_error(tmp_config, mock_anthropic, stub_anthropic_response, monkeypatch) -> None:
    """4 malformed-JSON attempts in a row exhaust retries; error raised."""
    stub_anthropic_response(_verdict_payload("still not json"))

    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))

    client = JudgmentClient(tmp_config)
    with pytest.raises(DriftInterpretationError) as exc_info:
        interpret(client, _make_context())

    assert "retry exhausted" in str(exc_info.value)
    assert exc_info.value.attempts == 4
    assert sleeps == list(RETRY_DELAYS_SECONDS)
    assert len(mock_anthropic.messages.calls) == 4


def test_no_retry_flag_skips_retries(tmp_config, mock_anthropic, stub_anthropic_response, monkeypatch) -> None:
    """no_retry=True: a single failure raises immediately, no sleeps."""
    stub_anthropic_response(_verdict_payload("malformed"))

    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))

    client = JudgmentClient(tmp_config)
    with pytest.raises(DriftInterpretationError) as exc_info:
        interpret(client, _make_context(), no_retry=True)

    assert "retry exhausted" in str(exc_info.value)
    assert exc_info.value.attempts == 1
    assert sleeps == []
    assert len(mock_anthropic.messages.calls) == 1


# ---------------------------------------------------------------------------
# Truncation tiers (D2)
# ---------------------------------------------------------------------------


def test_truncate_small_file_passes_through() -> None:
    """≤8KB file: strategy=full, no truncation."""
    contents = "x" * 1000
    out, was, strategy = _truncate_doc_state(contents, "")
    assert out == contents
    assert was is False
    assert strategy == "full"


def test_truncate_medium_file_head_region_tail() -> None:
    """8-32KB file: head + diff-region + tail; truncation markers present."""
    # Build a ~20KB file with 200 lines of ~100 chars each.
    lines = [f"line {i:03d}: " + ("x" * 90) for i in range(200)]
    contents = "\n".join(lines)
    # Diff hunk pointing at lines around line 100.
    diff = (
        "--- a\n+++ b\n"
        "@@ -98,5 +98,5 @@\n"
        " context line\n"
        "-old line\n"
        "+new line\n"
        " context line\n"
    )
    out, was, strategy = _truncate_doc_state(contents, diff)
    assert was is True
    assert strategy == "head_region_tail"
    assert "...truncated..." in out
    # Head should include line 000.
    assert "line 000" in out
    # Tail should include line 199.
    assert "line 199" in out
    # Region around line 98 should include line 100.
    assert "line 100" in out
    # Output should be substantially smaller than input.
    assert len(out) < len(contents)


def test_truncate_huge_file_region_only() -> None:
    """>32KB file: region-only strategy."""
    # Build a ~50KB file.
    lines = [f"line {i:04d}: " + ("y" * 100) for i in range(500)]
    contents = "\n".join(lines)
    diff = (
        "--- a\n+++ b\n"
        "@@ -200,3 +200,3 @@\n"
        " context\n"
        "-old\n"
        "+new\n"
    )
    out, was, strategy = _truncate_doc_state(contents, diff)
    assert was is True
    assert strategy == "region_only"
    # Region around line 200 should include line 200.
    assert "line 0200" in out
    # Head lines should NOT be in the output (region_only).
    assert "line 0000" not in out
    # Output much smaller than input.
    assert len(out) < len(contents) // 4


def test_truncate_huge_file_without_diff_hunks_falls_back() -> None:
    """>32KB file with no parseable diff: still produces output."""
    lines = [f"line {i:04d}: " + ("z" * 100) for i in range(500)]
    contents = "\n".join(lines)
    out, was, strategy = _truncate_doc_state(contents, "no hunks here")
    assert was is True
    assert strategy == "region_only"
    assert len(out) > 0


# ---------------------------------------------------------------------------
# Prompt assembly + cache-control marker assertion
# ---------------------------------------------------------------------------


def test_interpret_uses_cache_control(tmp_config, mock_anthropic, stub_anthropic_response) -> None:
    """The messages.create call carries the system block with cache_control: ephemeral."""
    stub_anthropic_response(
        _verdict_payload(json.dumps({
            "verdict": "NO_CHANGE_NEEDED",
            "confidence": 0.91,
            "rationale": "ok",
        }))
    )
    client = JudgmentClient(tmp_config)
    interpret(client, _make_context(), no_retry=True)

    assert len(mock_anthropic.messages.calls) == 1
    call_kwargs = mock_anthropic.messages.calls[0]
    system = call_kwargs.get("system")
    assert isinstance(system, list) and len(system) == 1
    block = system[0]
    assert block["type"] == "text"
    assert block["cache_control"] == {"type": "ephemeral"}
    # The cached prefix must contain the LLM's role description.
    assert "drift interpreter" in block["text"]


def test_build_prompt_lists_doc_target_paths() -> None:
    """The user section enumerates allowed doc_target paths."""
    targets = [
        DocTarget(path="docs/a.md", contents="a", truncated=False, truncation_strategy="full"),
        DocTarget(path="docs/b.md", contents="b", truncated=False, truncation_strategy="full"),
    ]
    ctx = _make_context(doc_targets=targets)
    user = _build_prompt(ctx)
    assert "docs/a.md" in user
    assert "docs/b.md" in user
    assert "Allowed doc_path values" in user


# ---------------------------------------------------------------------------
# Parser edge cases (cover invalid shapes that should retry)
# ---------------------------------------------------------------------------


def test_parse_rejects_unknown_verdict(tmp_config, mock_anthropic, stub_anthropic_response) -> None:
    """Unknown verdict string is a schema violation (retryable)."""
    from doc_audit.judgment.drift_interpretation import _RetrySchemaError, _parse_verdict
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(json.dumps({
            "verdict": "MAYBE",
            "confidence": 0.9,
            "rationale": "x",
        }), _make_context())


def test_parse_rejects_confidence_out_of_range() -> None:
    from doc_audit.judgment.drift_interpretation import _RetrySchemaError, _parse_verdict
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(json.dumps({
            "verdict": "NO_CHANGE_NEEDED",
            "confidence": 2.0,
            "rationale": "x",
        }), _make_context())


def test_parse_rejects_bool_confidence() -> None:
    """bool is an int subclass — must NOT slip past the type check."""
    from doc_audit.judgment.drift_interpretation import _RetrySchemaError, _parse_verdict
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(json.dumps({
            "verdict": "NO_CHANGE_NEEDED",
            "confidence": True,
            "rationale": "x",
        }), _make_context())


def test_parse_rejects_missing_rationale() -> None:
    from doc_audit.judgment.drift_interpretation import _RetrySchemaError, _parse_verdict
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(json.dumps({
            "verdict": "NO_CHANGE_NEEDED",
            "confidence": 0.9,
            "rationale": "  ",
        }), _make_context())


def test_parse_rejects_judgment_without_question() -> None:
    from doc_audit.judgment.drift_interpretation import _RetrySchemaError, _parse_verdict
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(json.dumps({
            "verdict": "JUDGMENT_REQUIRED",
            "confidence": 0.5,
            "rationale": "x",
        }), _make_context())


def test_parse_rejects_judgment_overlong_question() -> None:
    from doc_audit.judgment.drift_interpretation import _RetrySchemaError, _parse_verdict
    long_q = "?" * 600
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(json.dumps({
            "verdict": "JUDGMENT_REQUIRED",
            "confidence": 0.5,
            "rationale": "x",
            "question": long_q,
        }), _make_context())


def test_parse_rejects_proposed_edit_without_object() -> None:
    from doc_audit.judgment.drift_interpretation import _RetrySchemaError, _parse_verdict
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(json.dumps({
            "verdict": "PROPOSED_EDIT",
            "confidence": 0.9,
            "rationale": "x",
        }), _make_context())


def test_parse_rejects_empty_response() -> None:
    from doc_audit.judgment.drift_interpretation import _RetrySchemaError, _parse_verdict
    with pytest.raises(_RetrySchemaError):
        _parse_verdict("   ", _make_context())


def test_parse_rejects_non_object_json() -> None:
    from doc_audit.judgment.drift_interpretation import _RetrySchemaError, _parse_verdict
    with pytest.raises(_RetrySchemaError):
        _parse_verdict("[1, 2, 3]", _make_context())


def test_parse_rejects_missing_proposed_edit_subfields() -> None:
    from doc_audit.judgment.drift_interpretation import _RetrySchemaError, _parse_verdict
    with pytest.raises(_RetrySchemaError):
        _parse_verdict(json.dumps({
            "verdict": "PROPOSED_EDIT",
            "confidence": 0.9,
            "rationale": "x",
            "proposed_edit": {
                "doc_path": "docs/design/architecture/data/service-inventory.json",
                "current_value": "a",
                # proposed_value missing
            },
        }), _make_context())


# ---------------------------------------------------------------------------
# DriftInterpretationError diagnostics
# ---------------------------------------------------------------------------


def test_drift_interpretation_error_diagnostic_block() -> None:
    """to_diagnostic_block returns markdown listing error + attempts + cause."""
    inner = ValueError("inner cause")
    err = DriftInterpretationError("retry exhausted", cause=inner, attempts=4)
    block = err.to_diagnostic_block()
    assert "Drift interpretation failure" in block
    assert "retry exhausted" in block
    assert "attempts: 4" in block
    assert "ValueError" in block


def test_drift_interpretation_error_without_cause() -> None:
    err = DriftInterpretationError("oops", attempts=1)
    block = err.to_diagnostic_block()
    assert "oops" in block
    assert "attempts: 1" in block


# ---------------------------------------------------------------------------
# Fixture files exist + load
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture_name", [
    "drift_event_openclaw_cron.json",
    "drift_event_openclaw_json_hash.json",
    "drift_event_systemd_dropins.json",
])
def test_fixture_file_loads_into_context(fixture_name: str) -> None:
    """Each shipped fixture deserializes into a valid DriftInterpretationContext."""
    fixture_path = FIXTURES_DIR / fixture_name
    assert fixture_path.is_file(), f"missing fixture: {fixture_path}"

    from doc_audit.judgment.drift_interpretation import _parse_context_document
    data = fixture_path.read_text(encoding="utf-8")
    context = _parse_context_document(data)
    assert context.event_id
    assert context.doc_targets
    assert context.diff


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def _setup_cli_env(monkeypatch, tmp_path: Path, mock_anthropic) -> Path:
    """Write a dummy api-key file and patch the CLI's JudgmentClient builder.

    Returns the path to write a CLI input JSON to.
    """
    api_key_path = tmp_path / "anthropic.key"
    api_key_path.write_text("test-key", encoding="utf-8")

    # The CLI's _build_cli_client constructs a Config that requires
    # absolute paths. Bypass that by replacing the builder with a
    # function that returns a JudgmentClient on a tmp_config-like
    # shape (it'll re-use mock_anthropic since the SDK is patched).
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
            signals=SignalsConfig(sources=["drift_event"]),
            github=GitHubConfig(repo="kentonium3/kg-automation", bot_identity="kg-felix-bot"),
        )
        return JudgmentClient(cfg)

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation._build_cli_client",
        _fake_builder,
    )
    return api_key_path


def test_cli_help_exits_zero(capsys) -> None:
    """``--help`` exits 0 (argparse's help path uses parser.exit)."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "drift_interpretation" in captured.out


def test_cli_exit_0_success(tmp_path, mock_anthropic, stub_anthropic_response, monkeypatch) -> None:
    """Valid input + mocked SDK returns 0; output JSON written."""
    api_key_path = _setup_cli_env(monkeypatch, tmp_path, mock_anthropic)
    stub_anthropic_response(
        _verdict_payload(json.dumps({
            "verdict": "NO_CHANGE_NEEDED",
            "confidence": 0.91,
            "rationale": "ok",
        }))
    )
    input_path = tmp_path / "in.json"
    output_path = tmp_path / "out.json"
    fixture = (FIXTURES_DIR / "drift_event_openclaw_cron.json").read_text(encoding="utf-8")
    input_path.write_text(fixture, encoding="utf-8")

    rc = main([
        "--input-file", str(input_path),
        "--output-file", str(output_path),
        "--api-key-path", str(api_key_path),
        "--no-retry",
    ])
    assert rc == 0
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["verdict"] == "NO_CHANGE_NEEDED"


def test_cli_exit_3_on_malformed_input(tmp_path, mock_anthropic, monkeypatch, capsys) -> None:
    """Malformed input JSON returns exit code 3."""
    api_key_path = _setup_cli_env(monkeypatch, tmp_path, mock_anthropic)
    input_path = tmp_path / "in.json"
    input_path.write_text("not json at all", encoding="utf-8")

    rc = main([
        "--input-file", str(input_path),
        "--api-key-path", str(api_key_path),
    ])
    assert rc == 3
    err = capsys.readouterr().err
    assert "input_parse" in err


def test_cli_exit_3_on_missing_input_file(tmp_path, mock_anthropic, monkeypatch, capsys) -> None:
    """Missing input file returns exit 3 (file-not-found is bad input)."""
    _setup_cli_env(monkeypatch, tmp_path, mock_anthropic)
    rc = main([
        "--input-file", str(tmp_path / "does-not-exist.json"),
    ])
    assert rc == 3


def test_cli_exit_3_on_bad_args(tmp_path, mock_anthropic, monkeypatch, capsys) -> None:
    """Unknown flag returns exit 3 via _StructuredArgumentParser."""
    _setup_cli_env(monkeypatch, tmp_path, mock_anthropic)
    rc = main(["--definitely-not-a-real-flag"])
    assert rc == 3
    err = capsys.readouterr().err
    assert "argparse" in err


def test_cli_exit_5_on_out_of_set_doc_path(tmp_path, mock_anthropic, stub_anthropic_response, monkeypatch, capsys) -> None:
    """Out-of-set doc_path returns exit code 5."""
    api_key_path = _setup_cli_env(monkeypatch, tmp_path, mock_anthropic)
    stub_anthropic_response(
        _verdict_payload(json.dumps({
            "verdict": "PROPOSED_EDIT",
            "confidence": 0.90,
            "rationale": "bad",
            "proposed_edit": {
                "doc_path": "docs/NOT_IN_SET.md",
                "current_value": "a",
                "proposed_value": "b",
            },
        }))
    )
    input_path = tmp_path / "in.json"
    fixture = (FIXTURES_DIR / "drift_event_openclaw_cron.json").read_text(encoding="utf-8")
    input_path.write_text(fixture, encoding="utf-8")

    rc = main([
        "--input-file", str(input_path),
        "--api-key-path", str(api_key_path),
        "--no-retry",
    ])
    assert rc == 5
    err = capsys.readouterr().err
    assert "out-of-set" in err


def test_cli_exit_1_on_retry_exhaustion(tmp_path, mock_anthropic, stub_anthropic_response, monkeypatch) -> None:
    """Retry exhaustion (no_retry=True + bad JSON) returns exit 1."""
    api_key_path = _setup_cli_env(monkeypatch, tmp_path, mock_anthropic)
    stub_anthropic_response(_verdict_payload("garbage"))
    input_path = tmp_path / "in.json"
    fixture = (FIXTURES_DIR / "drift_event_openclaw_cron.json").read_text(encoding="utf-8")
    input_path.write_text(fixture, encoding="utf-8")

    rc = main([
        "--input-file", str(input_path),
        "--api-key-path", str(api_key_path),
        "--no-retry",
    ])
    assert rc == 1


def test_cli_reads_stdin(tmp_path, mock_anthropic, stub_anthropic_response, monkeypatch) -> None:
    """No --input-file: reads JSON from stdin."""
    api_key_path = _setup_cli_env(monkeypatch, tmp_path, mock_anthropic)
    stub_anthropic_response(
        _verdict_payload(json.dumps({
            "verdict": "NO_CHANGE_NEEDED",
            "confidence": 0.93,
            "rationale": "stdin path",
        }))
    )
    fixture = (FIXTURES_DIR / "drift_event_openclaw_cron.json").read_text(encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO(fixture))

    rc = main([
        "--api-key-path", str(api_key_path),
        "--no-retry",
    ])
    assert rc == 0


def test_cli_writes_stdout(tmp_path, mock_anthropic, stub_anthropic_response, monkeypatch, capsys) -> None:
    """No --output-file: writes JSON to stdout."""
    api_key_path = _setup_cli_env(monkeypatch, tmp_path, mock_anthropic)
    stub_anthropic_response(
        _verdict_payload(json.dumps({
            "verdict": "NO_CHANGE_NEEDED",
            "confidence": 0.93,
            "rationale": "stdout path",
        }))
    )
    input_path = tmp_path / "in.json"
    fixture = (FIXTURES_DIR / "drift_event_openclaw_cron.json").read_text(encoding="utf-8")
    input_path.write_text(fixture, encoding="utf-8")

    rc = main([
        "--input-file", str(input_path),
        "--api-key-path", str(api_key_path),
        "--no-retry",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    body = json.loads(captured.out)
    assert body["verdict"] == "NO_CHANGE_NEEDED"


def test_cli_input_missing_required_field(tmp_path, mock_anthropic, monkeypatch, capsys) -> None:
    """Input JSON missing a required field returns exit 3."""
    _setup_cli_env(monkeypatch, tmp_path, mock_anthropic)
    input_path = tmp_path / "in.json"
    input_path.write_text(
        json.dumps({"event_id": "x"}),  # missing most fields
        encoding="utf-8",
    )
    rc = main(["--input-file", str(input_path)])
    assert rc == 3
    assert "input_parse" in capsys.readouterr().err


def test_cli_input_not_an_object(tmp_path, mock_anthropic, monkeypatch, capsys) -> None:
    """Input JSON that's a list rather than an object returns exit 3."""
    _setup_cli_env(monkeypatch, tmp_path, mock_anthropic)
    input_path = tmp_path / "in.json"
    input_path.write_text("[1, 2, 3]", encoding="utf-8")
    rc = main(["--input-file", str(input_path)])
    assert rc == 3


def test_cli_input_empty_doc_targets(tmp_path, mock_anthropic, monkeypatch, capsys) -> None:
    """Input with empty doc_targets list returns exit 3."""
    _setup_cli_env(monkeypatch, tmp_path, mock_anthropic)
    input_path = tmp_path / "in.json"
    input_path.write_text(
        json.dumps({
            "event_id": "x", "timestamp_utc": "2026-05-22T00:00:00Z",
            "baseline": "b", "mapping_id": "m", "mapping_rationale": "r",
            "diff": "d", "doc_targets": [],
        }),
        encoding="utf-8",
    )
    rc = main(["--input-file", str(input_path)])
    assert rc == 3


# ---------------------------------------------------------------------------
# verdict_to_dict helper
# ---------------------------------------------------------------------------


def test_verdict_to_dict_drops_none_fields() -> None:
    """Serialized dict omits proposed_edit / question when they're None."""
    v = DriftVerdict(verdict="NO_CHANGE_NEEDED", confidence=0.9, rationale="ok")
    out = _verdict_to_dict(v)
    assert "proposed_edit" not in out
    assert "question" not in out
    assert out["verdict"] == "NO_CHANGE_NEEDED"


def test_verdict_to_dict_carries_proposed_edit() -> None:
    v = DriftVerdict(
        verdict="PROPOSED_EDIT",
        confidence=0.9,
        rationale="ok",
        proposed_edit={"doc_path": "x", "current_value": "a", "proposed_value": "b"},
    )
    out = _verdict_to_dict(v)
    assert out["proposed_edit"] == {"doc_path": "x", "current_value": "a", "proposed_value": "b"}
    assert "question" not in out


# ---------------------------------------------------------------------------
# Debug capture path (FR-001..FR-006)
#
# Gated by env var DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1. When enabled, every
# ``_RetrySchemaError`` raise site in ``_parse_verdict`` logs the raw
# response body at WARNING level with prefix ``drift_interpretation.schema_fail``
# immediately before re-raising. Observation-only — exception type and
# message are unchanged.
# ---------------------------------------------------------------------------


_DEBUG_ENV_VAR = "DOC_AUDIT_DEBUG_DRIFT_PAYLOADS"
_DEBUG_LOG_PREFIX = "drift_interpretation.schema_fail"
_DRIFT_LOGGER_NAME = "doc_audit.judgment.drift_interpretation"


@pytest.fixture
def clean_debug_env(monkeypatch):
    """Ensure the debug env var is unset for the test (no leakage)."""
    monkeypatch.delenv(_DEBUG_ENV_VAR, raising=False)


def test_debug_capture_emits_log_when_env_var_set(monkeypatch, caplog) -> None:
    """AS1: env var on + invalid response → schema_fail log captured."""
    from doc_audit.judgment.drift_interpretation import _RetrySchemaError, _parse_verdict

    monkeypatch.setenv(_DEBUG_ENV_VAR, "1")

    bad_response = "not-valid-json-{"
    with caplog.at_level(logging.WARNING, logger=_DRIFT_LOGGER_NAME):
        with pytest.raises(_RetrySchemaError):
            _parse_verdict(bad_response, _make_context())

    schema_fail_records = [
        rec
        for rec in caplog.records
        if _DEBUG_LOG_PREFIX in rec.getMessage()
    ]
    assert schema_fail_records, "expected a schema_fail log line"
    # Body must be present in the formatted message.
    assert any(bad_response in rec.getMessage() for rec in schema_fail_records)
    # WARNING level (per R1).
    assert all(rec.levelno == logging.WARNING for rec in schema_fail_records)


def test_debug_capture_silent_when_env_var_unset(clean_debug_env, caplog) -> None:
    """AS2: env var unset + invalid response → no schema_fail log."""
    from doc_audit.judgment.drift_interpretation import _RetrySchemaError, _parse_verdict

    with caplog.at_level(logging.WARNING, logger=_DRIFT_LOGGER_NAME):
        with pytest.raises(_RetrySchemaError):
            _parse_verdict("not-valid-json-{", _make_context())

    assert not any(
        _DEBUG_LOG_PREFIX in rec.getMessage() for rec in caplog.records
    ), "no schema_fail log should be emitted when env var is unset"


def test_debug_capture_silent_on_valid_response(monkeypatch, caplog) -> None:
    """AS3: env var on + valid response → no schema_fail log (only failures log)."""
    from doc_audit.judgment.drift_interpretation import _parse_verdict

    monkeypatch.setenv(_DEBUG_ENV_VAR, "1")

    valid_response = json.dumps({
        "verdict": "NO_CHANGE_NEEDED",
        "confidence": 0.92,
        "rationale": "Valid path; nothing to log.",
    })

    with caplog.at_level(logging.WARNING, logger=_DRIFT_LOGGER_NAME):
        result = _parse_verdict(valid_response, _make_context())

    assert result.verdict == "NO_CHANGE_NEEDED"
    assert not any(
        _DEBUG_LOG_PREFIX in rec.getMessage() for rec in caplog.records
    )


def test_debug_capture_non_truthy_values_still_disable(monkeypatch, caplog) -> None:
    """Env var must match exact string '1' (R2). 'true' / 'yes' / '0' disable capture."""
    from doc_audit.judgment.drift_interpretation import _RetrySchemaError, _parse_verdict

    for non_match in ("true", "yes", "0", "", "TRUE", " 1 "):
        monkeypatch.setenv(_DEBUG_ENV_VAR, non_match)
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger=_DRIFT_LOGGER_NAME):
            with pytest.raises(_RetrySchemaError):
                _parse_verdict("not-valid-json-{", _make_context())
        assert not any(
            _DEBUG_LOG_PREFIX in rec.getMessage() for rec in caplog.records
        ), f"capture must be disabled for env var value {non_match!r}"


def test_debug_capture_truncates_oversized_body(monkeypatch, caplog) -> None:
    """Payloads >4096 bytes are truncated with a '[truncated]' suffix (R4)."""
    from doc_audit.judgment.drift_interpretation import (
        _DEBUG_CAPTURE_MAX_BYTES,
        _RetrySchemaError,
        _parse_verdict,
    )

    monkeypatch.setenv(_DEBUG_ENV_VAR, "1")
    # Build an oversized body that's still un-parseable JSON.
    oversized = "X" * (_DEBUG_CAPTURE_MAX_BYTES + 500)
    bad_payload = "{not-json " + oversized

    with caplog.at_level(logging.WARNING, logger=_DRIFT_LOGGER_NAME):
        with pytest.raises(_RetrySchemaError):
            _parse_verdict(bad_payload, _make_context())

    schema_fail = [
        rec.getMessage()
        for rec in caplog.records
        if _DEBUG_LOG_PREFIX in rec.getMessage()
    ]
    assert schema_fail, "expected a schema_fail log for oversized body"
    msg = schema_fail[0]
    assert "[truncated]" in msg
    # The full oversized body MUST NOT appear (since it exceeded the cap).
    assert oversized not in msg


# AS4: every _RetrySchemaError raise site in _parse_verdict emits a capture
# line. The parametrize entries below cover each distinct raise site
# reachable via _parse_verdict's public surface.
_RAISE_SITE_CASES = [
    pytest.param("", "empty LLM response", id="empty-response"),
    pytest.param("not-valid-json-{", "invalid JSON", id="invalid-json"),
    pytest.param("[1, 2, 3]", "response must be a JSON object", id="non-object-json"),
    pytest.param(
        json.dumps({"verdict": "MAYBE", "confidence": 0.9, "rationale": "x"}),
        "invalid verdict value",
        id="invalid-verdict-value",
    ),
    pytest.param(
        json.dumps({"verdict": "NO_CHANGE_NEEDED", "confidence": "high", "rationale": "x"}),
        "confidence must be a JSON number",
        id="confidence-wrong-type",
    ),
    pytest.param(
        json.dumps({"verdict": "NO_CHANGE_NEEDED", "confidence": 2.5, "rationale": "x"}),
        "confidence out of range",
        id="confidence-out-of-range",
    ),
    pytest.param(
        json.dumps({"verdict": "NO_CHANGE_NEEDED", "confidence": 0.9, "rationale": "  "}),
        "rationale missing or empty",
        id="rationale-missing",
    ),
    pytest.param(
        json.dumps({"verdict": "PROPOSED_EDIT", "confidence": 0.9, "rationale": "x"}),
        "PROPOSED_EDIT requires a proposed_edit object",
        id="proposed-edit-missing-object",
    ),
    pytest.param(
        json.dumps({
            "verdict": "PROPOSED_EDIT",
            "confidence": 0.9,
            "rationale": "x",
            "proposed_edit": {
                "doc_path": "docs/design/architecture/data/service-inventory.json",
                "current_value": "a",
                # proposed_value missing
            },
        }),
        "proposed_edit.proposed_value missing or not a non-empty string",
        id="proposed-edit-missing-subfield",
    ),
    pytest.param(
        json.dumps({"verdict": "JUDGMENT_REQUIRED", "confidence": 0.5, "rationale": "x"}),
        "JUDGMENT_REQUIRED requires a non-empty question",
        id="judgment-required-missing-question",
    ),
    pytest.param(
        json.dumps({
            "verdict": "JUDGMENT_REQUIRED",
            "confidence": 0.5,
            "rationale": "x",
            "question": "?" * 600,
        }),
        f"question exceeds {500} chars",
        id="judgment-required-overlong-question",
    ),
]


@pytest.mark.parametrize("mock_response,expected_message_substring", _RAISE_SITE_CASES)
def test_debug_capture_for_each_raise_site(
    monkeypatch,
    caplog,
    mock_response: str,
    expected_message_substring: str,
) -> None:
    """AS4: each ``_RetrySchemaError`` raise site emits a capture line.

    Verifies:
      - WARNING-level schema_fail log present
      - capture references the same identifier (message substring) as
        the exception
      - exception message unchanged (FR-006: messages/types preserved)
    """
    from doc_audit.judgment.drift_interpretation import _RetrySchemaError, _parse_verdict

    monkeypatch.setenv(_DEBUG_ENV_VAR, "1")

    with caplog.at_level(logging.WARNING, logger=_DRIFT_LOGGER_NAME):
        with pytest.raises(_RetrySchemaError) as exc_info:
            _parse_verdict(mock_response, _make_context())

    captures = [
        rec.getMessage()
        for rec in caplog.records
        if _DEBUG_LOG_PREFIX in rec.getMessage()
    ]
    assert captures, f"no capture line for response: {mock_response!r}"
    # The capture references the raise-site identifier (same string as the exception).
    assert any(expected_message_substring in cap for cap in captures), (
        f"expected {expected_message_substring!r} in capture; got {captures!r}"
    )
    # FR-006: exception message must contain the same identifier (unchanged).
    assert expected_message_substring in str(exc_info.value)
