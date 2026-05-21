"""Anthropic SDK wrapper for the three judgment moments.

This module is the **single chokepoint** for Anthropic API access from
the driver. It implements:

- Authentication via ``doc_audit.config.read_api_key`` (key never logged).
- Prompt-cache marker placement per research D2 — the boilerplate
  between ``[CACHE_PREFIX_START]`` and ``[CACHE_PREFIX_END]`` is sent
  as a ``cache_control: {"type": "ephemeral"}`` system block.
- A typed response object (``JudgmentResponse``) carrying the raw text,
  token counts, and stop reason needed by the moment modules and the
  per-tick cost rollup (NFR-001).

The client is intentionally **business-rule-free**. It does not know
about guardrails, tier values, or any moment-specific schema — the
moment modules (``judgment/tier_classification.py`` etc.) own that
logic. This keeps the client reusable for any future judgment moment.

See ``contracts/judgment-prompts.contract.md`` for the I/O contract.
SDK version: anthropic >=0.103,<1.0 (pinned in ``requirements.txt``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic

from doc_audit.config import Config, read_api_key


CACHE_PREFIX_START = "[CACHE_PREFIX_START]"
CACHE_PREFIX_END = "[CACHE_PREFIX_END]"


@dataclass(frozen=True)
class JudgmentResponse:
    """Parsed result of one judgment LLM call.

    Carries everything the moment modules need to:
    - Schema-validate the response (``content``).
    - Roll up tick-level cost telemetry (token fields per NFR-001).
    - Surface anomalous stop reasons in the activity log
      (``stop_reason``).
    """

    content: str
    input_tokens: int
    cache_hit_input_tokens: int
    output_tokens: int
    stop_reason: str


class JudgmentClient:
    """Thin Anthropic-SDK wrapper with prompt-cache support.

    Instantiate once per driver tick; reuse across all three judgment
    moments so the prompt cache stays warm.

    The cached prefix (boilerplate / rule recap / output schema) is
    invariant across calls within a tick; the per-call variable
    section is sent as the user message. See research D2.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        # ``read_api_key`` never logs or echoes the key value.
        api_key = read_api_key(config)
        # Resolve ``anthropic.Anthropic`` at call time (NOT at import
        # time) so test monkeypatches on the module attribute take
        # effect. See ``tests/doc_audit/conftest.py::mock_anthropic``.
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = config.llm.model
        self.max_tokens = config.llm.max_tokens

    def call(
        self, prompt_template_path: Path, variable_section: str
    ) -> JudgmentResponse:
        """Execute one judgment call.

        The template is split on the cache markers; the cached prefix
        is sent as a ``cache_control: ephemeral`` system block and the
        variable section is sent as the user message.

        Raises:
            ValueError: If the template is missing or has misordered
                ``[CACHE_PREFIX_START]`` / ``[CACHE_PREFIX_END]``
                markers. The error message includes the template
                path so the caller can repair the artifact.
            anthropic.APIError: Re-raised verbatim. The driver decides
                retry vs surface.
        """

        template = prompt_template_path.read_text(encoding="utf-8")
        cached_prefix, _ = self._split_cache_markers(
            template, prompt_template_path
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[
                {
                    "type": "text",
                    "text": cached_prefix,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": variable_section}],
        )

        return JudgmentResponse(
            content=self._extract_text(response),
            input_tokens=self._usage_field(response, "input_tokens"),
            cache_hit_input_tokens=self._usage_field(
                response, "cache_read_input_tokens"
            ),
            output_tokens=self._usage_field(response, "output_tokens"),
            stop_reason=getattr(response, "stop_reason", "") or "",
        )

    @staticmethod
    def _split_cache_markers(
        template: str, template_path: Path
    ) -> tuple[str, str]:
        """Extract content between cache markers.

        Returns ``(cached_prefix, variable_section)``. Wraps the
        underlying ``str.index`` ``ValueError`` with the template path
        so callers know which file is malformed.
        """

        try:
            start = template.index(CACHE_PREFIX_START) + len(
                CACHE_PREFIX_START
            )
            end = template.index(CACHE_PREFIX_END)
        except ValueError as exc:
            raise ValueError(
                "Prompt template missing or misordered "
                f"{CACHE_PREFIX_START}/{CACHE_PREFIX_END} markers: "
                f"{template_path}"
            ) from exc

        if end < start:
            raise ValueError(
                "Prompt template missing or misordered "
                f"{CACHE_PREFIX_START}/{CACHE_PREFIX_END} markers: "
                f"{template_path}"
            )

        cached = template[start:end].strip()
        rest_start = template.index(CACHE_PREFIX_END) + len(CACHE_PREFIX_END)
        rest = template[rest_start:].strip()
        return cached, rest

    # ---------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Pull the first text block out of an Anthropic response."""

        content = getattr(response, "content", None) or []
        if not content:
            return ""
        first = content[0]
        # SDK exposes ``.text`` on TextBlock; fall back to ``["text"]``
        # for any dict-like shapes (e.g., fixture stubs in tests).
        if hasattr(first, "text"):
            return first.text or ""
        if isinstance(first, dict):
            return str(first.get("text", ""))
        return ""

    @staticmethod
    def _usage_field(response: Any, name: str) -> int:
        """Read a ``usage.<name>`` field, defaulting to 0 if absent."""

        usage = getattr(response, "usage", None)
        if usage is None:
            return 0
        if hasattr(usage, name):
            value = getattr(usage, name)
        elif isinstance(usage, dict):
            value = usage.get(name, 0)
        else:
            value = 0
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0


__all__ = ["JudgmentClient", "JudgmentResponse"]
