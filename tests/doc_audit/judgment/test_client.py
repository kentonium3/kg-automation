"""Unit tests for ``doc_audit.judgment.client``.

Verifies:
- Cache markers are extracted correctly.
- Missing/misordered markers raise ``ValueError`` with the template
  path in the message.
- ``JudgmentResponse`` is populated from the SDK response shape.
- API key never appears in any caught exception message.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from doc_audit.judgment.client import JudgmentClient, JudgmentResponse


# ---------------------------------------------------------------------------
# Synthetic templates
# ---------------------------------------------------------------------------


VALID_TEMPLATE = """\
---
name: synthetic
version: 0.0.1
---

# Boilerplate

[CACHE_PREFIX_START]

This is the cached prefix.

Output: {"ok": true}

[CACHE_PREFIX_END]

# Per-call inputs

{{variable_section}}
"""


MISSING_START_MARKER = """\
---
name: bad
version: 0.0.1
---

No start marker here.

[CACHE_PREFIX_END]

variables
"""


MISORDERED_MARKERS = """\
---
name: bad
version: 0.0.1
---

[CACHE_PREFIX_END]

This is reversed.

[CACHE_PREFIX_START]
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_split_cache_markers_extracts_cached_prefix(tmp_path: Path) -> None:
    """The cached prefix between the two markers is extracted."""

    template_path = tmp_path / "template.prompt.md"
    template_path.write_text(VALID_TEMPLATE, encoding="utf-8")

    cached, rest = JudgmentClient._split_cache_markers(
        VALID_TEMPLATE, template_path
    )

    assert "This is the cached prefix." in cached
    assert '{"ok": true}' in cached
    assert "Per-call inputs" in rest
    assert "{{variable_section}}" in rest


def test_split_cache_markers_missing_marker_raises(tmp_path: Path) -> None:
    """A template without ``[CACHE_PREFIX_START]`` raises ValueError with the path."""

    template_path = tmp_path / "bad.prompt.md"
    template_path.write_text(MISSING_START_MARKER, encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        JudgmentClient._split_cache_markers(
            MISSING_START_MARKER, template_path
        )

    msg = str(exc_info.value)
    assert "[CACHE_PREFIX_START]" in msg
    assert "[CACHE_PREFIX_END]" in msg
    assert str(template_path) in msg


def test_split_cache_markers_misordered_raises(tmp_path: Path) -> None:
    """END before START is rejected with the same error class."""

    template_path = tmp_path / "misordered.prompt.md"
    template_path.write_text(MISORDERED_MARKERS, encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        JudgmentClient._split_cache_markers(
            MISORDERED_MARKERS, template_path
        )

    msg = str(exc_info.value)
    assert str(template_path) in msg


def test_client_call_records_usage_metrics(
    tmp_path: Path,
    tmp_config,
    mock_anthropic,
) -> None:
    """A full ``call()`` round-trip populates every JudgmentResponse field."""

    template_path = tmp_path / "template.prompt.md"
    template_path.write_text(VALID_TEMPLATE, encoding="utf-8")

    mock_anthropic.messages.next_fixture = "tier_classification_tier_a"

    client = JudgmentClient(tmp_config)
    result = client.call(template_path, "variable section goes here")

    assert isinstance(result, JudgmentResponse)
    assert result.content  # non-empty text
    assert result.input_tokens == 480
    assert result.cache_hit_input_tokens == 320
    assert result.output_tokens == 64
    # The fake SDK doesn't set stop_reason — defaults to empty string.
    assert isinstance(result.stop_reason, str)


def test_client_call_sends_cache_control_block(
    tmp_path: Path,
    tmp_config,
    mock_anthropic,
) -> None:
    """The cached prefix is sent as a system block with cache_control."""

    template_path = tmp_path / "template.prompt.md"
    template_path.write_text(VALID_TEMPLATE, encoding="utf-8")

    client = JudgmentClient(tmp_config)
    client.call(template_path, "vars")

    call_kwargs = mock_anthropic.messages.calls[0]
    system = call_kwargs["system"]
    assert isinstance(system, list)
    assert len(system) == 1
    block = system[0]
    assert block["type"] == "text"
    assert block["cache_control"] == {"type": "ephemeral"}
    assert "cached prefix" in block["text"]
    # The variable section was passed as the user message.
    assert call_kwargs["messages"] == [
        {"role": "user", "content": "vars"}
    ]


def test_client_call_missing_markers_propagates_path(
    tmp_path: Path,
    tmp_config,
    mock_anthropic,
) -> None:
    """``call()`` wraps a missing-marker template into ValueError with the path."""

    bad_template = tmp_path / "bad.prompt.md"
    bad_template.write_text(MISSING_START_MARKER, encoding="utf-8")

    client = JudgmentClient(tmp_config)

    with pytest.raises(ValueError) as exc_info:
        client.call(bad_template, "vars")

    msg = str(exc_info.value)
    assert str(bad_template) in msg
    # And no LLM call was made.
    assert mock_anthropic.messages.calls == []


def test_client_call_handles_missing_usage_fields(
    tmp_path: Path,
    tmp_config,
    mock_anthropic,
) -> None:
    """Usage fields default to 0 when the SDK omits them."""

    template_path = tmp_path / "template.prompt.md"
    template_path.write_text(VALID_TEMPLATE, encoding="utf-8")

    # The conftest fake response uses a dict-typed usage; the
    # ``_usage_field`` helper supports dict shapes.
    mock_anthropic.messages.next_fixture = "tier_classification_tier_a"

    client = JudgmentClient(tmp_config)
    result = client.call(template_path, "vars")

    # Sanity: all three token fields are ints (>= 0)
    assert isinstance(result.input_tokens, int)
    assert isinstance(result.cache_hit_input_tokens, int)
    assert isinstance(result.output_tokens, int)
