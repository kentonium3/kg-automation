"""Unit tests for ``doc_audit.judgment._llm_response``.

Covers WP01 acceptance criteria for the shared ``_strip_code_fence``
helper extracted from ``drift_interpretation`` (mission #55). The
helper's contract is: strip leading/trailing markdown code fences from
an LLM response while leaving unfenced input unchanged.

Test cases enumerated in the WP01 prompt's T002 table. Each case
exercises one distinct branch of the helper to satisfy NFR-003 (>=95%
branch coverage on the helper).
"""
from __future__ import annotations

import json

from doc_audit.judgment._llm_response import _strip_code_fence


def test_fenced_with_json_tag_strips_cleanly() -> None:
    """A standard ```json ... ``` fence around valid JSON is removed."""

    text = "```json\n{\"foo\": 1}\n```"
    assert _strip_code_fence(text) == '{"foo": 1}'


def test_fenced_without_tag_strips_cleanly() -> None:
    """A bare ``` ... ``` fence (no language tag) is also removed."""

    text = "```\n{\"foo\": 1}\n```"
    assert _strip_code_fence(text) == '{"foo": 1}'


def test_fenced_with_surrounding_whitespace_strips_cleanly() -> None:
    """Leading/trailing whitespace around the fence is tolerated."""

    text = "  \n```json\n{\"foo\": 1}\n```\n  "
    assert _strip_code_fence(text) == '{"foo": 1}'


def test_unfenced_input_is_returned_unchanged_and_round_trips_as_json() -> None:
    """Unfenced valid JSON is returned byte-for-byte (FR-007 no-op path).

    Also documents that the helper does not interfere with downstream
    ``json.loads`` on already-clean input.
    """

    text = '{"foo": 1}'
    result = _strip_code_fence(text)
    assert result == text
    assert json.loads(result) == {"foo": 1}


def test_empty_string_returns_empty_string() -> None:
    """Empty input is returned unchanged."""

    assert _strip_code_fence("") == ""


def test_whitespace_only_input_is_returned_unchanged() -> None:
    """Whitespace-only input (no fence present) is returned unchanged."""

    text = "   \n  \t  "
    assert _strip_code_fence(text) == text


def test_fenced_with_malformed_json_inside_strips_fence_without_validating() -> None:
    """The helper strips fences regardless of payload validity.

    JSON validation is the caller's responsibility (e.g.
    ``_parse_verdict`` runs ``json.loads`` after stripping).
    """

    text = "```json\n{not valid\n```"
    assert _strip_code_fence(text) == "{not valid"


def test_fenced_opening_without_closing_fence_drops_only_opener() -> None:
    """Fenced input missing the closing fence: drop the opener, keep the body.

    Exercises the trailing-fence False branch (line 37->39 in
    ``_llm_response.py``) — the input starts with a fence but the last line
    does not, so only the opening line is removed.
    """

    text = "```json\nfoo bar baz"
    assert _strip_code_fence(text) == "foo bar baz"


def test_lone_opening_fence_yields_empty_string() -> None:
    """A bare ``\\`\\`\\``` with no body collapses to an empty string.

    After dropping the opener, ``lines`` becomes empty, so the trailing-fence
    check short-circuits on ``lines`` being falsy.
    """

    assert _strip_code_fence("```") == ""
