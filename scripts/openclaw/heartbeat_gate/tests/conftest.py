"""Pytest bootstrap and shared fixtures for heartbeat-gate tests (WP-03 T021).

- ``sys.path`` bootstrap so ``scripts.openclaw...`` imports resolve when
  pytest is invoked from any working directory.
- Helpers for synthesizing canned ``last-tick.json`` bodies (matching
  ``contracts/tick-signal.contract.md``).
- A ``FakeAnthropicClient`` factory that records the kwargs of each
  ``messages.create`` call -- tests assert on the system block's
  ``cache_control`` annotation.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# sys.path bootstrap
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Last-tick.json fixture factory
# ---------------------------------------------------------------------------


def write_last_tick(
    path: Path,
    *,
    cycle_id: str = "01J6XYZAB1234567890ABCDEFG",
    started_at_utc: str = "2026-06-01T17:15:00Z",
    signals_evaluated: Optional[list[dict]] = None,
    issues_filed: Optional[list[dict]] = None,
    errors: Optional[list[dict]] = None,
    exit_status: str = "success",
) -> Path:
    """Write a ``last-tick.json`` matching the v1 schema.

    Returns ``path`` for chaining.
    """
    payload = {
        "schema_version": 1,
        "cycle_id": cycle_id,
        "started_at_utc": started_at_utc,
        "duration_ms": 740,
        "exit_status": exit_status,
        "signals_evaluated": signals_evaluated
        if signals_evaluated is not None
        else [
            {
                "signal_id": "whatsapp_creds_restore",
                "count_cycle": 0,
                "count_rolling": 0,
                "threshold_status": "below",
            },
            {
                "signal_id": "web_watchdog_reconnect",
                "count_cycle": 0,
                "count_rolling": 0,
                "threshold_status": "below",
            },
            {
                "signal_id": "openclaw_unhandled_error",
                "count_cycle": 0,
                "count_rolling": 0,
                "threshold_status": "below",
            },
        ],
        "issues_filed": issues_filed if issues_filed is not None else [],
        "issues_skipped_dedup": [],
        "errors": errors if errors is not None else [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Fake Anthropic client
# ---------------------------------------------------------------------------


@dataclass
class FakeUsage:
    """Minimal ``response.usage`` shape."""

    input_tokens: int = 100
    cache_read_input_tokens: int = 80
    output_tokens: int = 25


@dataclass
class FakeBlock:
    text: str = ""


@dataclass
class FakeResponse:
    content: list[FakeBlock] = field(default_factory=list)
    usage: Optional[FakeUsage] = None
    stop_reason: str = "end_turn"


class FakeMessages:
    """Records each ``create`` call kwargs; returns a configurable response."""

    def __init__(
        self,
        responses: list[FakeResponse],
        errors_to_raise: Optional[list[Optional[BaseException]]] = None,
    ) -> None:
        self._responses = list(responses)
        self._errors = list(errors_to_raise or [])
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        if self._errors:
            exc = self._errors.pop(0)
            if exc is not None:
                raise exc
        if not self._responses:
            raise AssertionError("FakeMessages: no more responses configured")
        return self._responses.pop(0)


class FakeAnthropicClient:
    """SDK-compatible client carrying ``.messages.create``."""

    def __init__(self, messages: FakeMessages) -> None:
        self.messages = messages


def make_client_factory(
    *,
    response_text: str = '{"outcome": "HEARTBEAT_OK", "reason": "all clean"}',
    usage: Optional[FakeUsage] = None,
    errors_to_raise: Optional[list[Optional[BaseException]]] = None,
    additional_responses: Optional[list[FakeResponse]] = None,
) -> Callable[[str], FakeAnthropicClient]:
    """Build a ``client_factory(api_key) -> FakeAnthropicClient``."""

    first_response = FakeResponse(
        content=[FakeBlock(text=response_text)],
        usage=usage or FakeUsage(),
    )
    responses = [first_response]
    if additional_responses:
        responses.extend(additional_responses)
    messages = FakeMessages(responses, errors_to_raise=errors_to_raise)
    client = FakeAnthropicClient(messages)

    def _factory(api_key: str) -> FakeAnthropicClient:
        return client

    # Expose the messages object on the factory so tests can inspect calls.
    _factory.messages = messages  # type: ignore[attr-defined]
    return _factory
