"""WP04-local fixtures.

Provides ``judgment_prompt_dir`` — a real or stub path the moment
modules can pull a template from when ``client.call()`` is actually
invoked. We also expose ``stub_anthropic_response`` — a helper that
binds the next fake-anthropic response to an inline payload dict
without needing a JSON file under
``tests/doc_audit/fixtures/anthropic_responses/`` (which is owned
by WP02).
"""
from __future__ import annotations

from typing import Any, Callable

import pytest


@pytest.fixture
def stub_anthropic_response(mock_anthropic) -> Callable[[dict[str, Any]], None]:
    """Replace the next fake-Anthropic response with an inline payload.

    Usage::

        stub_anthropic_response({
            "text": "{\"tier\": \"tier_a\", \"rationale\": \"...\"}",
            "usage": {
                "input_tokens": 100,
                "cache_read_input_tokens": 50,
                "output_tokens": 10,
            },
        })

    Subsequent ``client.call()`` returns a fake response built from
    this payload. Each call to ``stub_anthropic_response`` overrides
    the previous binding.

    Why this exists: the conftest ``mock_anthropic`` loads canned
    responses from JSON files under
    ``tests/doc_audit/fixtures/anthropic_responses/`` (owned by WP02).
    WP04 tests need response shapes specific to the contract Moments
    1-3 we're testing, but we should not add files under that fixture
    directory because it is outside WP04's owned-files list. Inlining
    the payload here keeps WP04 self-contained.
    """

    def setter(payload: dict[str, Any]) -> None:
        # Inject a one-shot loader; ``next_fixture`` value is
        # irrelevant — the loader ignores it.
        mock_anthropic.messages._loader = lambda _name: payload
        mock_anthropic.messages.next_fixture = "stub"

    return setter
