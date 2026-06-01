"""Anthropic SDK wrapper for the heartbeat routing decision (WP-03 T017).

Mirrors the architectural precedent of ``scripts/doc_audit/judgment/``:

- Single Anthropic SDK chokepoint per tick.
- Cache-aware prompt split on ``[CACHE_PREFIX_START]`` /
  ``[CACHE_PREFIX_END]`` markers; the cached prefix is sent as a
  ``cache_control: {"type": "ephemeral"}`` system block.
- Retry policy mirrors ``audit_interpretation._call_with_retry``:
  one retry on transient anthropic errors (``RateLimitError``,
  ``APIError``, ``APITimeoutError``, ``APIConnectionError``) with a
  5-second backoff. Schema-violation responses also retry once.
- After retry exhaustion → :class:`GateRoutingError`, which the
  orchestrator catches and translates into a fallback per FR-011.

The client is intentionally minimal -- it does not own decision
logic, only "call Haiku, parse the JSON, count tokens." Decision
semantics live in the prompt + the orchestrator (run.py).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional


__all__ = [
    "DEFAULT_API_KEY_PATH",
    "DEFAULT_MODEL",
    "GateDecision",
    "GateRoutingError",
    "RETRY_BACKOFF_SECONDS",
    "decide",
    "read_api_key",
]


logger = logging.getLogger(__name__)


DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_API_KEY_PATH = Path("/data/services/openclaw/secrets/anthropic")
DEFAULT_MAX_TOKENS = 512

# One retry per the WP prompt's spec: "1 retry on RateLimitError or 5xx
# (5s backoff). After retry exhaustion → raise GateRoutingError." We
# express that as a single delay value: 5 seconds before attempt #2.
RETRY_BACKOFF_SECONDS: tuple[int, ...] = (5,)

# Markers must exactly match the prompt file's CACHE_PREFIX_* sentinels.
_CACHE_PREFIX_START = "[CACHE_PREFIX_START]"
_CACHE_PREFIX_END = "[CACHE_PREFIX_END]"

_VALID_OUTCOMES: frozenset[str] = frozenset(
    {"HEARTBEAT_OK", "LOG_AND_SKIP", "ESCALATE_TO_SONNET"}
)
_REASON_MAX_LEN = 500


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateDecision:
    """Result of one heartbeat-gate routing call.

    The orchestrator uses this struct to:
    - Decide whether to invoke the escalator (``ESCALATE_TO_SONNET``).
    - Record per-tick token cost in the gate ledger (the three token
      fields) for the NFR-001 baseline comparison.
    - Surface the reason text to the operator via the ledger.
    """

    outcome: Literal["HEARTBEAT_OK", "LOG_AND_SKIP", "ESCALATE_TO_SONNET"]
    reason: str
    input_tokens: int = 0
    cache_hit_tokens: int = 0
    output_tokens: int = 0


class GateRoutingError(Exception):
    """Raised when the gate cannot produce a valid :class:`GateDecision`.

    Causes (per FR-011): Anthropic API exhaustion after retry, malformed
    JSON response, schema-invalid response (missing ``outcome`` or
    non-enum ``outcome`` value).

    The orchestrator catches this and falls back to the
    expensive-tier path with ``"Gate fallback — see ledger"`` as the
    reason, so observation is not silently dropped.
    """


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_api_key(api_key_path: Path) -> str:
    """Read the Anthropic API key from disk.

    NEVER logs the key. NEVER includes the key in error messages.
    Pattern matches ``doc_audit.config.read_api_key``.

    Raises:
        FileNotFoundError: With the path (NOT the key) in the message.
    """
    try:
        raw = Path(api_key_path).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Anthropic API key file not found at {api_key_path}"
        ) from exc
    return raw.strip()


def decide(
    context: Any,
    *,
    api_key_path: Path = DEFAULT_API_KEY_PATH,
    prompt_path: Path,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    client_factory: Optional[Callable[[str], Any]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> GateDecision:
    """Run the heartbeat-routing Haiku call and return a typed decision.

    Parameters
    ----------
    context:
        A :class:`heartbeat_gate.context.GateContext` (passed as ``Any``
        to keep this module decoupled from ``context`` imports for
        easier testing). Must be ``dataclasses.asdict``-able.
    api_key_path:
        File path to the Anthropic key. Default matches the production
        deployment at ``/data/services/openclaw/secrets/anthropic``.
    prompt_path:
        Path to ``routing.prompt.md``. The file is split on the
        ``[CACHE_PREFIX_START]`` / ``[CACHE_PREFIX_END]`` markers; the
        cached prefix is sent as the system block, the rest of the
        file (with ``{{...}}`` placeholders substituted from
        ``context``) is sent as the user message.
    model:
        Anthropic model identifier. Default ``claude-haiku-4-5-20251001``.
    max_tokens:
        Max output tokens. Default 512 -- ample for a JSON object.
    client_factory:
        Optional override for the Anthropic client constructor. Tests
        pass a stub that returns a canned response. Production callers
        leave this ``None`` and the function resolves
        ``anthropic.Anthropic`` at call time.
    sleep:
        Override hook for ``time.sleep`` (tests pass a no-op).

    Returns
    -------
    GateDecision
        Typed decision with token counts pulled from ``response.usage``.

    Raises
    ------
    GateRoutingError
        On any retry-exhausted API failure or schema violation. The
        orchestrator catches this and falls back per FR-011.
    """
    system_text, user_template = _split_prompt(prompt_path)
    user_text = _render_user_section(user_template, context)

    api_key = read_api_key(Path(api_key_path))
    client = _build_client(client_factory, api_key)

    last_error: Optional[BaseException] = None
    delays: tuple[int, ...] = (0,) + RETRY_BACKOFF_SECONDS

    for attempt_idx, delay in enumerate(delays, start=1):
        if delay:
            logger.info(
                "heartbeat_gate retry sleeping %ds before attempt %d",
                delay,
                attempt_idx,
            )
            sleep(delay)
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system_text,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_text}],
            )
        except Exception as exc:  # noqa: BLE001 - re-narrowed below
            if _is_retryable_api_error(exc) and attempt_idx < len(delays):
                last_error = exc
                logger.info(
                    "heartbeat_gate attempt %d failed (%s); will retry",
                    attempt_idx,
                    type(exc).__name__,
                )
                continue
            raise GateRoutingError(
                f"Anthropic call failed: {type(exc).__name__}"
            ) from exc

        try:
            outcome, reason = _parse_response(response)
        except GateRoutingError as exc:
            if attempt_idx < len(delays):
                last_error = exc
                logger.info(
                    "heartbeat_gate attempt %d returned malformed response; "
                    "will retry",
                    attempt_idx,
                )
                continue
            raise

        return GateDecision(
            outcome=outcome,
            reason=reason,
            input_tokens=_usage_field(response, "input_tokens"),
            cache_hit_tokens=_usage_field(response, "cache_read_input_tokens"),
            output_tokens=_usage_field(response, "output_tokens"),
        )

    # Defensive fallback -- the loop above always either returns or
    # raises, but if delays is empty for any reason we surface a
    # well-formed error instead of looping silently.
    raise GateRoutingError(  # pragma: no cover - unreachable
        f"heartbeat_gate retry budget exhausted: {last_error!r}"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _split_prompt(prompt_path: Path) -> tuple[str, str]:
    """Read the prompt file and split on cache markers.

    Returns ``(system_text, user_template)``. The system text is the
    content between ``[CACHE_PREFIX_START]`` and ``[CACHE_PREFIX_END]``,
    with surrounding whitespace stripped. The user template is the
    portion AFTER ``[CACHE_PREFIX_END]``, also stripped.

    Raises:
        GateRoutingError: If the markers are missing or misordered.
            We use ``GateRoutingError`` (not ``ValueError``) so the
            orchestrator's blanket ``except GateRoutingError`` catches
            this and falls back rather than crashing.
    """
    try:
        template = Path(prompt_path).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise GateRoutingError(
            f"Routing prompt file missing: {prompt_path}"
        ) from exc

    try:
        start = template.index(_CACHE_PREFIX_START) + len(_CACHE_PREFIX_START)
        end = template.index(_CACHE_PREFIX_END)
    except ValueError as exc:
        raise GateRoutingError(
            "Routing prompt missing CACHE_PREFIX markers: " f"{prompt_path}"
        ) from exc

    if end < start:
        raise GateRoutingError(
            "Routing prompt CACHE_PREFIX markers misordered: " f"{prompt_path}"
        )

    system_text = template[start:end].strip()
    user_template = template[end + len(_CACHE_PREFIX_END) :].strip()
    return system_text, user_template


def _render_user_section(user_template: str, context: Any) -> str:
    """Substitute ``{{field}}`` placeholders with ``context`` values.

    ``context`` must be ``dataclasses.asdict``-able. List/dict values
    are rendered via ``json.dumps`` so the model sees structured data
    in a stable format. Missing fields render as the empty string
    (defensive -- the prompt's static portion already specifies the
    schema, so an unknown placeholder is a prompt-author bug, not a
    runtime fault).
    """
    payload = asdict(context)

    rendered = user_template
    for key, value in payload.items():
        token = "{{" + key + "}}"
        if isinstance(value, (list, dict)):
            rendered_value = json.dumps(value, ensure_ascii=False, default=str)
        else:
            rendered_value = str(value)
        rendered = rendered.replace(token, rendered_value)
    return rendered


def _build_client(
    client_factory: Optional[Callable[[str], Any]], api_key: str
) -> Any:
    """Resolve the Anthropic client.

    The factory pattern lets tests inject a stub without monkeypatching
    the ``anthropic`` module at import time. Production callers leave
    ``client_factory=None`` and we resolve ``anthropic.Anthropic`` here
    -- the late import means tests that never call ``decide()`` do not
    need the SDK installed.
    """
    if client_factory is not None:
        return client_factory(api_key)
    import anthropic  # type: ignore[import-not-found]

    return anthropic.Anthropic(api_key=api_key)


def _is_retryable_api_error(exc: BaseException) -> bool:
    """Return True for the anthropic transient error classes.

    We import the SDK at call time so the import is lazy (tests that
    never trigger this branch never need ``anthropic`` installed). If
    the SDK is unavailable, no exception is retryable -- the failure
    propagates as a ``GateRoutingError`` on the first attempt.
    """
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - defensive
        return False

    retryable: tuple[type[BaseException], ...] = (
        getattr(anthropic, "RateLimitError", ()),
        getattr(anthropic, "APITimeoutError", ()),
        getattr(anthropic, "APIConnectionError", ()),
        getattr(anthropic, "APIError", ()),
    )
    # Filter out empty-tuple placeholders before the isinstance check
    # (defensive in case an SDK version is missing one of these classes).
    real_classes = tuple(cls for cls in retryable if isinstance(cls, type))
    if not real_classes:
        return False
    return isinstance(exc, real_classes)


def _parse_response(response: Any) -> tuple[str, str]:
    """Extract ``(outcome, reason)`` from the Anthropic response.

    Raises :class:`GateRoutingError` on:
    - Empty content.
    - Non-JSON content (after fence-stripping).
    - Missing or non-enum ``outcome`` field.
    - Non-string ``reason`` field.

    The reason is truncated to ``_REASON_MAX_LEN`` characters at parse
    time (defense in depth -- the prompt says ≤500 chars but the model
    occasionally exceeds).
    """
    text = _extract_text(response).strip()
    if not text:
        raise GateRoutingError("Empty Anthropic response content")

    stripped = _strip_code_fence(text)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise GateRoutingError(f"Non-JSON gate response: {exc}") from exc

    if not isinstance(parsed, dict):
        raise GateRoutingError(
            f"Gate response is not a JSON object: {type(parsed).__name__}"
        )

    outcome = parsed.get("outcome")
    if outcome not in _VALID_OUTCOMES:
        raise GateRoutingError(
            f"Gate response has invalid outcome: {outcome!r}"
        )

    reason_raw = parsed.get("reason", "")
    if reason_raw is None:
        reason_raw = ""
    if not isinstance(reason_raw, str):
        raise GateRoutingError(
            f"Gate response reason is not a string: {type(reason_raw).__name__}"
        )

    reason = reason_raw[:_REASON_MAX_LEN]
    return outcome, reason


def _extract_text(response: Any) -> str:
    """Pull the first text block out of an Anthropic response.

    Matches the SDK's ``response.content[0].text`` shape; tolerates
    fixture-style dicts and missing attributes (returns empty string).
    """
    content = getattr(response, "content", None) or []
    if not content:
        return ""
    first = content[0]
    if hasattr(first, "text"):
        return first.text or ""
    if isinstance(first, dict):
        return str(first.get("text", ""))
    return ""


def _strip_code_fence(text: str) -> str:
    """Strip markdown code fences from an LLM response.

    Mirrors ``doc_audit.judgment._llm_response._strip_code_fence``.
    Haiku 4.5 frequently wraps JSON in ```json ...``` despite the
    prompt forbidding fences -- so the parser strips them defensively.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):  # pragma: no branch
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _usage_field(response: Any, name: str) -> int:
    """Read ``response.usage.<name>``, defaulting to 0 if absent.

    Handles three shapes:
    - SDK object with ``.usage.<attr>``.
    - Dict-shaped ``usage`` field.
    - Missing ``usage`` entirely.
    """
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
