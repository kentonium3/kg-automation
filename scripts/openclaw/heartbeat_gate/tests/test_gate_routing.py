"""Tests for ``heartbeat_gate.gate`` (WP-03 T021)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.openclaw.heartbeat_gate import gate as _gate
from scripts.openclaw.heartbeat_gate.context import GateContext
from scripts.openclaw.heartbeat_gate.gate import (
    GateDecision,
    GateRoutingError,
    decide,
    read_api_key,
)
from scripts.openclaw.heartbeat_gate.tests.conftest import (
    FakeBlock,
    FakeResponse,
    FakeUsage,
    make_client_factory,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api_key_file(tmp_path: Path) -> Path:
    path = tmp_path / "anthropic.key"
    path.write_text("test-key-not-real\n")
    return path


@pytest.fixture
def prompt_path() -> Path:
    return (
        Path(__file__).resolve().parents[1] / "prompts" / "routing.prompt.md"
    )


@pytest.fixture
def sample_context() -> GateContext:
    return GateContext(
        tick_id="01JTEST",
        digest_snapshot_at_utc="2026-06-01T17:15:00Z",
        signals_evaluated=[],
        issues_filed=[],
        errors=[],
        heartbeat_md_state="empty",
        novelty_markers=[],
    )


# ---------------------------------------------------------------------------
# Happy-path outcomes
# ---------------------------------------------------------------------------


def test_decide_heartbeat_ok(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    factory = make_client_factory(
        response_text='{"outcome": "HEARTBEAT_OK", "reason": "all clean"}',
        usage=FakeUsage(input_tokens=120, cache_read_input_tokens=100, output_tokens=8),
    )
    decision = decide(
        sample_context,
        api_key_path=api_key_file,
        prompt_path=prompt_path,
        client_factory=factory,
    )
    assert isinstance(decision, GateDecision)
    assert decision.outcome == "HEARTBEAT_OK"
    assert decision.reason == "all clean"
    assert decision.input_tokens == 120
    assert decision.cache_hit_tokens == 100
    assert decision.output_tokens == 8


def test_decide_log_and_skip(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    factory = make_client_factory(
        response_text='{"outcome": "LOG_AND_SKIP", "reason": "single noisy event"}',
    )
    decision = decide(
        sample_context,
        api_key_path=api_key_file,
        prompt_path=prompt_path,
        client_factory=factory,
    )
    assert decision.outcome == "LOG_AND_SKIP"
    assert decision.reason == "single noisy event"


def test_decide_escalate_to_sonnet(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    factory = make_client_factory(
        response_text=(
            '{"outcome": "ESCALATE_TO_SONNET", '
            '"reason": "Signal whatsapp_creds_restore tripped both thresholds."}'
        ),
    )
    decision = decide(
        sample_context,
        api_key_path=api_key_file,
        prompt_path=prompt_path,
        client_factory=factory,
    )
    assert decision.outcome == "ESCALATE_TO_SONNET"
    assert "tripped" in decision.reason


def test_decide_strips_code_fence_around_json(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    factory = make_client_factory(
        response_text='```json\n{"outcome": "HEARTBEAT_OK", "reason": "ok"}\n```',
    )
    decision = decide(
        sample_context,
        api_key_path=api_key_file,
        prompt_path=prompt_path,
        client_factory=factory,
    )
    assert decision.outcome == "HEARTBEAT_OK"


def test_decide_truncates_overlong_reason(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    overlong = "x" * 1000
    factory = make_client_factory(
        response_text=json.dumps(
            {"outcome": "LOG_AND_SKIP", "reason": overlong}
        ),
    )
    decision = decide(
        sample_context,
        api_key_path=api_key_file,
        prompt_path=prompt_path,
        client_factory=factory,
    )
    assert len(decision.reason) == 500


def test_decide_accepts_null_reason(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    # The schema marks reason as optional for HEARTBEAT_OK; the parser
    # must coerce ``null`` to empty string rather than raising.
    factory = make_client_factory(
        response_text='{"outcome": "HEARTBEAT_OK", "reason": null}',
    )
    decision = decide(
        sample_context,
        api_key_path=api_key_file,
        prompt_path=prompt_path,
        client_factory=factory,
    )
    assert decision.outcome == "HEARTBEAT_OK"
    assert decision.reason == ""


# ---------------------------------------------------------------------------
# Cache structure
# ---------------------------------------------------------------------------


def test_decide_sends_cache_control_on_system_block(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    factory = make_client_factory()
    decide(
        sample_context,
        api_key_path=api_key_file,
        prompt_path=prompt_path,
        client_factory=factory,
    )
    call = factory.messages.calls[0]  # type: ignore[attr-defined]
    system_blocks = call["system"]
    assert isinstance(system_blocks, list) and len(system_blocks) == 1
    block = system_blocks[0]
    assert block["type"] == "text"
    # The cache-control annotation MUST be present so prompt caching
    # actually engages -- this is the load-bearing assertion for NFR-001
    # cost projection.
    assert block["cache_control"] == {"type": "ephemeral"}


def test_decide_user_message_excludes_static_rules(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    """The cached static rules MUST NOT appear in the user message body.

    If they did, the dynamic per-tick content would be polluting the
    cache key and the cache hit rate would drop to ~0%.
    """
    factory = make_client_factory()
    decide(
        sample_context,
        api_key_path=api_key_file,
        prompt_path=prompt_path,
        client_factory=factory,
    )
    call = factory.messages.calls[0]  # type: ignore[attr-defined]
    user_msg = call["messages"][0]["content"]
    # The "Why this gate exists" header lives in the cached system
    # portion; it must not bleed into the user message.
    assert "Why this gate exists" not in user_msg
    # The user template's "Per-call inputs" header should be present.
    assert "Per-call inputs" in user_msg
    # Placeholder substitution: tick_id should be present in rendered form.
    assert "01JTEST" in user_msg


def test_decide_user_message_includes_context_fields(
    prompt_path: Path, api_key_file: Path
) -> None:
    ctx = GateContext(
        tick_id="01JABC",
        digest_snapshot_at_utc="2026-06-01T17:15:00Z",
        signals_evaluated=[
            {
                "signal_id": "whatsapp_creds_restore",
                "count_cycle": 12,
                "threshold_status": "tripped_both",
            }
        ],
        issues_filed=[],
        errors=[],
        heartbeat_md_state="empty",
        novelty_markers=["whatsapp_creds_restore"],
    )
    factory = make_client_factory()
    decide(
        ctx,
        api_key_path=api_key_file,
        prompt_path=prompt_path,
        client_factory=factory,
    )
    call = factory.messages.calls[0]  # type: ignore[attr-defined]
    user_msg = call["messages"][0]["content"]
    assert "whatsapp_creds_restore" in user_msg
    assert "tripped_both" in user_msg


# ---------------------------------------------------------------------------
# Error / retry behavior
# ---------------------------------------------------------------------------


def test_decide_malformed_json_raises_after_retry(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    # Both attempts return non-JSON; retry exhausts and we raise.
    factory = make_client_factory(
        response_text="not json at all",
        additional_responses=[
            FakeResponse(
                content=[FakeBlock(text="still not json")],
                usage=FakeUsage(),
            )
        ],
    )
    sleep_calls: list[float] = []
    with pytest.raises(GateRoutingError):
        decide(
            sample_context,
            api_key_path=api_key_file,
            prompt_path=prompt_path,
            client_factory=factory,
            sleep=lambda s: sleep_calls.append(s),
        )
    # Retry was attempted with the 5s backoff.
    assert sleep_calls == [5]


def test_decide_invalid_outcome_raises_after_retry(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    factory = make_client_factory(
        response_text='{"outcome": "ESCALATE_NOW", "reason": "?"}',
        additional_responses=[
            FakeResponse(
                content=[
                    FakeBlock(text='{"outcome": "UNKNOWN", "reason": "x"}')
                ],
                usage=FakeUsage(),
            )
        ],
    )
    with pytest.raises(GateRoutingError):
        decide(
            sample_context,
            api_key_path=api_key_file,
            prompt_path=prompt_path,
            client_factory=factory,
            sleep=lambda s: None,
        )


def test_decide_rate_limit_then_success(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    # First attempt raises a subclass of anthropic.RateLimitError so
    # the SDK's __init__ doesn't fight us. The gate's retry-class check
    # uses isinstance() so a subclass triggers the retry branch.
    import anthropic

    class _TestRateLimit(anthropic.RateLimitError):
        def __init__(self) -> None:  # noqa: D401 - test helper
            BaseException.__init__(self, "rate limited")

    rate_err = _TestRateLimit()
    factory = make_client_factory(
        response_text='{"outcome": "HEARTBEAT_OK", "reason": "ok"}',
        errors_to_raise=[rate_err, None],
    )
    sleep_calls: list[float] = []
    decision = decide(
        sample_context,
        api_key_path=api_key_file,
        prompt_path=prompt_path,
        client_factory=factory,
        sleep=lambda s: sleep_calls.append(s),
    )
    assert decision.outcome == "HEARTBEAT_OK"
    assert sleep_calls == [5]


def test_decide_rate_limit_exhausts_retries(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    import anthropic

    class _TestRateLimit(anthropic.RateLimitError):
        def __init__(self) -> None:
            BaseException.__init__(self, "rate limited")

    # Both attempts raise -> GateRoutingError.
    factory = make_client_factory(
        response_text='{"outcome": "HEARTBEAT_OK", "reason": "ok"}',
        errors_to_raise=[_TestRateLimit(), _TestRateLimit()],
    )
    with pytest.raises(GateRoutingError):
        decide(
            sample_context,
            api_key_path=api_key_file,
            prompt_path=prompt_path,
            client_factory=factory,
            sleep=lambda s: None,
        )


def test_decide_non_retryable_exception_raises_immediately(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    # A ValueError is NOT an anthropic transient -- the gate must NOT
    # retry generic exceptions; it should wrap and raise.
    factory = make_client_factory(
        response_text='{"outcome": "HEARTBEAT_OK", "reason": "ok"}',
        errors_to_raise=[ValueError("some random failure")],
    )
    with pytest.raises(GateRoutingError):
        decide(
            sample_context,
            api_key_path=api_key_file,
            prompt_path=prompt_path,
            client_factory=factory,
            sleep=lambda s: None,
        )


def test_decide_empty_response_content_raises(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    factory = make_client_factory(
        response_text="",
        additional_responses=[
            FakeResponse(content=[], usage=FakeUsage())
        ],
    )
    with pytest.raises(GateRoutingError):
        decide(
            sample_context,
            api_key_path=api_key_file,
            prompt_path=prompt_path,
            client_factory=factory,
            sleep=lambda s: None,
        )


# ---------------------------------------------------------------------------
# Prompt-file integrity
# ---------------------------------------------------------------------------


def test_decide_missing_prompt_raises(
    sample_context: GateContext, api_key_file: Path, tmp_path: Path
) -> None:
    factory = make_client_factory()
    with pytest.raises(GateRoutingError):
        decide(
            sample_context,
            api_key_path=api_key_file,
            prompt_path=tmp_path / "nonexistent.md",
            client_factory=factory,
        )


def test_decide_prompt_missing_cache_markers_raises(
    sample_context: GateContext, api_key_file: Path, tmp_path: Path
) -> None:
    bad_prompt = tmp_path / "bad.prompt.md"
    bad_prompt.write_text("# Routing prompt\n\nNo cache markers here.\n")
    factory = make_client_factory()
    with pytest.raises(GateRoutingError):
        decide(
            sample_context,
            api_key_path=api_key_file,
            prompt_path=bad_prompt,
            client_factory=factory,
        )


def test_decide_prompt_misordered_markers_raises(
    sample_context: GateContext, api_key_file: Path, tmp_path: Path
) -> None:
    bad = tmp_path / "bad2.prompt.md"
    bad.write_text(
        "[CACHE_PREFIX_END]\nSomething\n[CACHE_PREFIX_START]\nMore\n"
    )
    factory = make_client_factory()
    with pytest.raises(GateRoutingError):
        decide(
            sample_context,
            api_key_path=api_key_file,
            prompt_path=bad,
            client_factory=factory,
        )


# ---------------------------------------------------------------------------
# read_api_key
# ---------------------------------------------------------------------------


def test_read_api_key_strips_whitespace(tmp_path: Path) -> None:
    path = tmp_path / "key"
    path.write_text("  sk-real-key-abcdef\n\n")
    assert read_api_key(path) == "sk-real-key-abcdef"


def test_read_api_key_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as exc_info:
        read_api_key(tmp_path / "nope")
    # Path must surface in the error, NOT the key.
    assert "nope" in str(exc_info.value)


def test_response_parser_rejects_list_payload(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    factory = make_client_factory(
        response_text='[{"outcome": "HEARTBEAT_OK"}]',
        additional_responses=[
            FakeResponse(
                content=[FakeBlock(text='[{"outcome": "HEARTBEAT_OK"}]')],
                usage=FakeUsage(),
            )
        ],
    )
    with pytest.raises(GateRoutingError):
        decide(
            sample_context,
            api_key_path=api_key_file,
            prompt_path=prompt_path,
            client_factory=factory,
            sleep=lambda s: None,
        )


def test_response_parser_rejects_non_string_reason(
    sample_context: GateContext, prompt_path: Path, api_key_file: Path
) -> None:
    factory = make_client_factory(
        response_text='{"outcome": "HEARTBEAT_OK", "reason": 12345}',
        additional_responses=[
            FakeResponse(
                content=[
                    FakeBlock(
                        text='{"outcome": "HEARTBEAT_OK", "reason": 12345}'
                    )
                ],
                usage=FakeUsage(),
            )
        ],
    )
    with pytest.raises(GateRoutingError):
        decide(
            sample_context,
            api_key_path=api_key_file,
            prompt_path=prompt_path,
            client_factory=factory,
            sleep=lambda s: None,
        )
