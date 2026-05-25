"""Moment 0 drift-interpretation LLM judgment.

Per spec FR-001..FR-008, FR-017 / contract
``kitty-specs/drift-event-auto-resolution-01KS8J32/contracts/llm-json.md``.

This is the load-bearing module of the drift-event auto-resolution
mission. ``interpret()`` consumes a single drift event (assembled by
``handle_drift_events.py``) and returns a structured ``DriftVerdict``
that the routing layer translates into one of four outcomes:

- ``PROPOSED_EDIT`` (conf ≥0.80): translate to ``ProposedEdit`` and
  pass to ``tier_classification`` (Moment 1).
- ``PROPOSED_EDIT`` (conf <0.80): demoted to ``JUDGMENT_REQUIRED``
  with the proposed edit folded into the rationale (FR-005).
- ``JUDGMENT_REQUIRED``: file a ``[doc-audit]`` issue carrying the
  LLM's question (FR-006).
- ``NO_CHANGE_NEEDED`` (conf ≥0.80): auto-close the drift event with
  a one-line summary; no GitHub artifact (FR-007).
- ``NO_CHANGE_NEEDED`` (conf <0.80): demoted to ``JUDGMENT_REQUIRED``.

Defense-in-depth
----------------
The parser enforces every E1 invariant before returning. Two failure
classes are distinguished:

- **Schema violations** (malformed JSON, missing field, wrong type,
  out-of-range confidence) DO retry — the LLM can produce clean JSON
  on the next attempt.
- **Semantic violations** (``proposed_edit.doc_path`` not in the
  input ``doc_targets``) do NOT retry — the LLM keeps choosing the
  same out-of-set path on the same prompt. This is the load-bearing
  LLM-drift safety check. Exit code 5 propagates immediately.

Retry policy (D6)
-----------------
Three retries with delays ``(30, 60, 120)`` seconds. After all
retries are exhausted, ``DriftInterpretationError("retry exhausted")``
is raised. The caller (``handle_drift_events.py``) catches it, writes
``verdict=RETRY_EXHAUSTED`` to the ledger, and falls back to the
pre-#362 ``[doc-audit]`` issue path (FR-009).

Cache contract (FR-017)
-----------------------
The system-prompt portion of the call MUST be ≥80% of total prompt
tokens and is sent with ``cache_control: ephemeral`` via the shared
``JudgmentClient``. The variable per-event section is the user
message.

Pattern source: ``scripts/doc_audit/judgment/tier_classification.py``.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from doc_audit.judgment.client import JudgmentClient


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module constants (per contracts/api.md + contracts/cli.md)
# ---------------------------------------------------------------------------

#: Default Anthropic model (C-009).
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

#: Per-attempt HTTP timeout (NFR-002 single-attempt P95 budget).
DEFAULT_TIMEOUT_SECONDS = 30

#: Confidence floor below which PROPOSED_EDIT / NO_CHANGE_NEEDED demote
#: to JUDGMENT_REQUIRED (FR-005, FR-007 boundary).
DEFAULT_CONFIDENCE_THRESHOLD = 0.80

#: Max output tokens for one verdict JSON.
DEFAULT_MAX_TOKENS = 512

#: Retry delays in seconds (D6). First attempt immediate; sleep before
#: each retry. Total max wait = 30 + 60 + 120 = 210s (NFR-006 envelope).
RETRY_DELAYS_SECONDS: tuple[int, ...] = (30, 60, 120)

#: Default API key path on office2 (mode 0600).
DEFAULT_API_KEY_PATH = Path("/data/services/openclaw/secrets/anthropic")

#: Cache-aware prompt template path.
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "drift_interpretation.prompt.md"
)

#: Allowed verdict values (case-sensitive).
VALID_VERDICTS = frozenset({"PROPOSED_EDIT", "JUDGMENT_REQUIRED", "NO_CHANGE_NEEDED"})

#: Max length of a ``JUDGMENT_REQUIRED.question`` (per contracts/llm-json.md).
QUESTION_MAX_CHARS = 500

#: Truncation tier boundaries (D2).
_TIER_FULL_MAX_BYTES = 8 * 1024
_TIER_MID_MAX_BYTES = 32 * 1024

#: Truncation marker inserted at boundaries.
_TRUNCATE_MARKER = "\n...truncated...\n"

#: Cache markers in the prompt template (mirror client convention).
_CACHE_PREFIX_START = "[CACHE_PREFIX_START]"
_CACHE_PREFIX_END = "[CACHE_PREFIX_END]"

#: Env var that gates raw-response debug capture at every
#: ``_RetrySchemaError`` raise site in ``_parse_verdict`` (per FR-001/FR-003).
#: Exact string match ``"1"`` only — any other value disables capture.
_DEBUG_CAPTURE_ENV_VAR = "DOC_AUDIT_DEBUG_DRIFT_PAYLOADS"

#: Truncation cap for the captured response body, in bytes (R4).
_DEBUG_CAPTURE_MAX_BYTES = 4096


# ---------------------------------------------------------------------------
# Dataclasses (per data-model E1, E2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocTarget:
    """One target doc with its current state (truncated per D2)."""

    path: str
    contents: str
    truncated: bool
    truncation_strategy: str  # "full" | "head_region_tail" | "region_only"


@dataclass(frozen=True)
class DriftInterpretationContext:
    """Input to Moment 0 LLM judgment (E2).

    Assembled from a single drift-events.jsonl row + its matching
    Mapping (signal-to-doc-map.json) + the current contents of each
    target doc (truncated per D2 if needed).
    """

    event_id: str
    timestamp_utc: str
    baseline: str
    mapping_id: str
    mapping_rationale: str
    diff: str
    doc_targets: list[DocTarget]


@dataclass(frozen=True)
class DriftVerdict:
    """LLM-produced verdict on a drift event (E1).

    Invariants (enforced by ``_parse_verdict``):
        - ``verdict`` in :data:`VALID_VERDICTS`
        - ``confidence`` in [0.0, 1.0]
        - ``rationale`` non-empty
        - ``proposed_edit`` present iff ``verdict == "PROPOSED_EDIT"``
        - ``question`` present iff ``verdict == "JUDGMENT_REQUIRED"``
    """

    verdict: str
    confidence: float
    rationale: str
    proposed_edit: Optional[dict] = None
    question: Optional[str] = None


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DriftInterpretationError(Exception):
    """Raised on unrecoverable failures (E5).

    Carries diagnostic context for inclusion in the escalation
    ``[doc-audit]`` issue body when all retries are exhausted (FR-009)
    OR when a semantic violation (out-of-set ``doc_path``) is detected.
    """

    def __init__(
        self,
        message: str,
        *,
        cause: Optional[Exception] = None,
        attempts: int = 0,
    ) -> None:
        super().__init__(message)
        self.cause = cause
        self.attempts = attempts

    def to_diagnostic_block(self) -> str:
        """Markdown block for inclusion in the [doc-audit] issue body."""
        lines = [
            "### Drift interpretation failure",
            "",
            f"- error: `{self}`",
            f"- attempts: {self.attempts}",
        ]
        if self.cause is not None:
            cause_repr = f"{type(self.cause).__name__}: {self.cause}"
            lines.append(f"- cause: `{cause_repr}`")
        lines.append("")
        return "\n".join(lines)


class _RetrySchemaError(Exception):
    """Internal-only — raised by ``_parse_verdict`` for retry-eligible schema violations.

    Distinct from ``DriftInterpretationError`` so the retry wrapper can
    distinguish between "LLM produced bad JSON; try again" and
    "LLM produced an out-of-set ``doc_path``; this is semantic and
    will not be fixed by retrying" (the latter raises
    ``DriftInterpretationError`` directly inside ``_parse_verdict``).
    """


# ---------------------------------------------------------------------------
# Doc-state truncation (D2)
# ---------------------------------------------------------------------------


_HUNK_RE = re.compile(
    r"^@@\s+-(?P<old_start>\d+)(?:,(?P<old_count>\d+))?\s+"
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))?\s+@@",
    re.MULTILINE,
)


def _extract_hunk_line_ranges(diff: str) -> list[tuple[int, int]]:
    """Pull (start, end) inclusive line numbers from unified diff hunks.

    Uses the ``+`` (new file) line numbers because the contents passed
    to truncation is the CURRENT file (post-change view of doc_target).
    """
    ranges: list[tuple[int, int]] = []
    for match in _HUNK_RE.finditer(diff):
        new_start = int(match.group("new_start"))
        new_count_raw = match.group("new_count")
        new_count = int(new_count_raw) if new_count_raw else 1
        if new_count <= 0:
            new_count = 1
        ranges.append((new_start, new_start + new_count - 1))
    return ranges


def _truncate_doc_state(contents: str, diff: str) -> tuple[str, bool, str]:
    """D2 tiered truncation by file size.

    Returns ``(truncated_contents, was_truncated, strategy)``.

    Strategies:
        - ``"full"``         — file ≤8KB; pass through unchanged.
        - ``"head_region_tail"`` — file 8-32KB; head 30 + diff region
          ±20 + tail 10.
        - ``"region_only"`` — file >32KB; diff region ±10 only.
    """
    size = len(contents.encode("utf-8"))

    if size <= _TIER_FULL_MAX_BYTES:
        return contents, False, "full"

    lines = contents.splitlines()
    total = len(lines)
    ranges = _extract_hunk_line_ranges(diff)

    if size <= _TIER_MID_MAX_BYTES:
        head_n = 30
        tail_n = 10
        context = 20
        strategy = "head_region_tail"
    else:
        head_n = 0
        tail_n = 0
        context = 10
        strategy = "region_only"

    # Build the inclusive set of 1-based line indices to keep.
    keep: set[int] = set()
    if head_n:
        keep.update(range(1, min(head_n, total) + 1))
    if tail_n and total > 0:
        keep.update(range(max(1, total - tail_n + 1), total + 1))
    for start, end in ranges:
        lo = max(1, start - context)
        hi = min(total, end + context)
        keep.update(range(lo, hi + 1))

    if not keep:
        # No hunks parsed (diff didn't include any) — fall back to
        # head + tail so the LLM still has something useful.
        if strategy == "region_only":
            # Pull a tiny middle slice as a placeholder.
            mid = total // 2
            keep.update(range(max(1, mid - 5), min(total, mid + 5) + 1))
        else:
            keep.update(range(1, min(head_n, total) + 1))
            keep.update(range(max(1, total - tail_n + 1), total + 1))

    # Emit the kept lines in order with truncation markers inserted at
    # every gap boundary.
    sorted_keep = sorted(keep)
    output: list[str] = []
    prev: Optional[int] = None
    for line_no in sorted_keep:
        if prev is None and line_no > 1:
            output.append(_TRUNCATE_MARKER.strip("\n"))
        elif prev is not None and line_no > prev + 1:
            output.append(_TRUNCATE_MARKER.strip("\n"))
        output.append(lines[line_no - 1])
        prev = line_no
    if prev is not None and prev < total:
        output.append(_TRUNCATE_MARKER.strip("\n"))

    return "\n".join(output), True, strategy


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def _render_user_section(context: DriftInterpretationContext) -> str:
    """Render the per-event variable section as the user message.

    Lists ``doc_targets[].path`` explicitly so the LLM cannot
    hallucinate a path outside the input set. Each doc's contents
    is presented after truncation per D2.
    """
    target_paths = [t.path for t in context.doc_targets]

    parts: list[str] = []
    parts.append("## Drift event")
    parts.append(f"- event_id: {context.event_id}")
    parts.append(f"- timestamp_utc: {context.timestamp_utc}")
    parts.append(f"- baseline: {context.baseline}")
    parts.append(f"- mapping_id: {context.mapping_id}")
    parts.append("")
    parts.append("## Mapping rationale")
    parts.append(context.mapping_rationale)
    parts.append("")
    parts.append("## Diff (unified)")
    parts.append("```diff")
    parts.append(context.diff)
    parts.append("```")
    parts.append("")
    parts.append("## Allowed doc_path values for proposed_edit.doc_path")
    parts.append(
        "If you choose verdict=PROPOSED_EDIT, "
        "proposed_edit.doc_path MUST be one of these exact strings:"
    )
    for path in target_paths:
        parts.append(f"- {path}")
    parts.append("")
    parts.append("## Doc target current state")
    for target in context.doc_targets:
        parts.append(f"### {target.path}")
        parts.append(
            f"(truncation_strategy: {target.truncation_strategy}, "
            f"truncated: {target.truncated})"
        )
        parts.append("```")
        parts.append(target.contents)
        parts.append("```")
        parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("Return STRICT JSON in one of the three shapes. No prose.")
    return "\n".join(parts)


def _build_prompt(
    context: DriftInterpretationContext,
) -> str:
    """Render the user message (the system prefix is supplied by JudgmentClient).

    The cache-aware system block lives in ``PROMPT_PATH`` between the
    ``[CACHE_PREFIX_START]`` / ``[CACHE_PREFIX_END]`` markers and is
    sent by ``JudgmentClient.call`` with ``cache_control: ephemeral``.
    """
    return _render_user_section(context)


# ---------------------------------------------------------------------------
# Response parsing + schema validation
# ---------------------------------------------------------------------------


def _log_raw_response_if_debug(response_text: str, error_message: str) -> None:
    """Emit the raw LLM response body to the log when debug capture is enabled.

    Gated by the env var :data:`_DEBUG_CAPTURE_ENV_VAR` set to the exact
    string ``"1"`` (per R2). Truncates oversized bodies to
    :data:`_DEBUG_CAPTURE_MAX_BYTES` with a ``[truncated]`` suffix (per R4).
    Emits at WARNING level so the line surfaces in default journalctl
    output (per R1).

    Observation-only — does not raise, return values, or otherwise
    affect control flow (FR-006). Callers invoke this immediately
    before re-raising ``_RetrySchemaError`` to preserve the existing
    retry semantics unchanged.
    """
    import os  # local import: module-level imports are otherwise untouched.

    if os.environ.get(_DEBUG_CAPTURE_ENV_VAR) != "1":
        return
    if response_text is None:
        body = "<none>"
    else:
        raw = response_text.encode("utf-8", errors="replace")
        if len(raw) > _DEBUG_CAPTURE_MAX_BYTES:
            body = (
                raw[:_DEBUG_CAPTURE_MAX_BYTES].decode("utf-8", errors="replace")
                + "[truncated]"
            )
        else:
            body = response_text
    logger.warning(
        "drift_interpretation.schema_fail | %s | %s",
        error_message,
        body,
    )


def _parse_verdict(
    response_text: str,
    context: DriftInterpretationContext,
) -> DriftVerdict:
    """Parse + validate the LLM JSON response.

    Schema violations raise ``_RetrySchemaError`` (retry-eligible).
    Semantic violations (out-of-set ``doc_path``) raise
    ``DriftInterpretationError`` directly (NOT retry-eligible — exit 5).
    """
    text = (response_text or "").strip()
    if not text:
        _log_raw_response_if_debug(response_text, "empty LLM response")
        raise _RetrySchemaError("empty LLM response")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        _log_raw_response_if_debug(response_text, f"invalid JSON: {exc}")
        raise _RetrySchemaError(f"invalid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        _log_raw_response_if_debug(
            response_text,
            f"response must be a JSON object (got {type(parsed).__name__})",
        )
        raise _RetrySchemaError(
            f"response must be a JSON object (got {type(parsed).__name__})"
        )

    verdict_value = parsed.get("verdict")
    if verdict_value not in VALID_VERDICTS:
        _log_raw_response_if_debug(
            response_text,
            f"invalid verdict value {verdict_value!r}; "
            f"expected one of {sorted(VALID_VERDICTS)}",
        )
        raise _RetrySchemaError(
            f"invalid verdict value {verdict_value!r}; "
            f"expected one of {sorted(VALID_VERDICTS)}"
        )

    confidence_raw = parsed.get("confidence")
    # bool is an int subclass — reject explicitly so True/False don't slip through.
    if isinstance(confidence_raw, bool) or not isinstance(
        confidence_raw, (int, float)
    ):
        _log_raw_response_if_debug(
            response_text,
            f"confidence must be a JSON number (got {type(confidence_raw).__name__})",
        )
        raise _RetrySchemaError(
            f"confidence must be a JSON number (got {type(confidence_raw).__name__})"
        )
    confidence = float(confidence_raw)
    if not (0.0 <= confidence <= 1.0):
        _log_raw_response_if_debug(
            response_text,
            f"confidence out of range: {confidence!r} (expected [0.0, 1.0])",
        )
        raise _RetrySchemaError(
            f"confidence out of range: {confidence!r} (expected [0.0, 1.0])"
        )

    rationale = parsed.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        _log_raw_response_if_debug(response_text, "rationale missing or empty")
        raise _RetrySchemaError("rationale missing or empty")

    if verdict_value == "PROPOSED_EDIT":
        return _parse_proposed_edit(
            parsed, confidence, rationale, context, response_text
        )
    if verdict_value == "JUDGMENT_REQUIRED":
        return _parse_judgment_required(
            parsed, confidence, rationale, response_text
        )
    # verdict_value == "NO_CHANGE_NEEDED"
    return DriftVerdict(
        verdict="NO_CHANGE_NEEDED",
        confidence=confidence,
        rationale=rationale,
    )


def _parse_proposed_edit(
    parsed: dict,
    confidence: float,
    rationale: str,
    context: DriftInterpretationContext,
    response_text: str,
) -> DriftVerdict:
    """Validate a PROPOSED_EDIT shape.

    Out-of-set ``doc_path`` raises ``DriftInterpretationError``
    directly (no retry, exit 5).
    """
    proposed_edit = parsed.get("proposed_edit")
    if not isinstance(proposed_edit, dict):
        _log_raw_response_if_debug(
            response_text, "PROPOSED_EDIT requires a proposed_edit object"
        )
        raise _RetrySchemaError(
            "PROPOSED_EDIT requires a proposed_edit object"
        )

    for key in ("doc_path", "current_value", "proposed_value"):
        value = proposed_edit.get(key)
        if not isinstance(value, str) or not value.strip():
            _log_raw_response_if_debug(
                response_text,
                f"proposed_edit.{key} missing or not a non-empty string",
            )
            raise _RetrySchemaError(
                f"proposed_edit.{key} missing or not a non-empty string"
            )

    allowed_paths = {t.path for t in context.doc_targets}
    if proposed_edit["doc_path"] not in allowed_paths:
        raise DriftInterpretationError(
            "out-of-set proposed doc_path: "
            f"{proposed_edit['doc_path']!r} not in {sorted(allowed_paths)!r}"
        )

    return DriftVerdict(
        verdict="PROPOSED_EDIT",
        confidence=confidence,
        rationale=rationale,
        proposed_edit=dict(proposed_edit),
    )


def _parse_judgment_required(
    parsed: dict,
    confidence: float,
    rationale: str,
    response_text: str,
) -> DriftVerdict:
    """Validate a JUDGMENT_REQUIRED shape."""
    question = parsed.get("question")
    if not isinstance(question, str) or not question.strip():
        _log_raw_response_if_debug(
            response_text, "JUDGMENT_REQUIRED requires a non-empty question"
        )
        raise _RetrySchemaError(
            "JUDGMENT_REQUIRED requires a non-empty question"
        )
    if len(question) > QUESTION_MAX_CHARS:
        _log_raw_response_if_debug(
            response_text,
            f"question exceeds {QUESTION_MAX_CHARS} chars (got {len(question)})",
        )
        raise _RetrySchemaError(
            f"question exceeds {QUESTION_MAX_CHARS} chars (got {len(question)})"
        )
    return DriftVerdict(
        verdict="JUDGMENT_REQUIRED",
        confidence=confidence,
        rationale=rationale,
        question=question,
    )


def _demote_low_confidence(
    verdict: DriftVerdict, threshold: float
) -> DriftVerdict:
    """Demote PROPOSED_EDIT / NO_CHANGE_NEEDED below threshold to JUDGMENT_REQUIRED.

    The original rationale is folded into the new rationale so the
    operator sees the LLM's reasoning. The original proposed_edit is
    NOT carried into the new dataclass (E1 invariant: proposed_edit
    iff verdict == PROPOSED_EDIT), but the rationale captures it for
    human review.
    """
    if verdict.verdict not in {"PROPOSED_EDIT", "NO_CHANGE_NEEDED"}:
        return verdict
    if verdict.confidence >= threshold:
        return verdict

    new_rationale = (
        f"Demoted from {verdict.verdict} "
        f"(confidence {verdict.confidence} < {threshold}). "
        f"Original rationale: {verdict.rationale}"
    )
    if verdict.verdict == "PROPOSED_EDIT" and verdict.proposed_edit:
        new_rationale += (
            f" Original proposed_edit: "
            f"{json.dumps(verdict.proposed_edit, ensure_ascii=False)}"
        )

    new_question = (
        f"Original verdict was {verdict.verdict} but confidence was below "
        f"threshold {threshold}. Please review and decide."
    )

    return DriftVerdict(
        verdict="JUDGMENT_REQUIRED",
        confidence=verdict.confidence,
        rationale=new_rationale,
        question=new_question,
    )


# ---------------------------------------------------------------------------
# Retry policy (D6)
# ---------------------------------------------------------------------------


def _call_with_retry(
    fn: Callable[[], DriftVerdict],
    *,
    no_retry: bool = False,
) -> DriftVerdict:
    """Invoke ``fn`` with the D6 retry policy.

    Retryable exceptions: ``_RetrySchemaError`` plus anthropic
    transient errors. ``DriftInterpretationError`` raised by ``fn`` is
    propagated immediately (semantic violations are not retryable).

    Sleep is invoked through ``time.sleep`` at call time (NOT bound as
    a default arg) so test monkeypatches on the module-level ``time``
    attribute take effect.
    """
    # Import locally so test environments that stub the SDK don't
    # require the real package at import time.
    try:
        import anthropic  # noqa: WPS433
        retry_anthropic: tuple[type[BaseException], ...] = (
            anthropic.APIError,
            anthropic.APITimeoutError,
            anthropic.RateLimitError,
            anthropic.APIConnectionError,
        )
    except Exception:  # pragma: no cover - defensive
        retry_anthropic = ()

    retryable: tuple[type[BaseException], ...] = (
        _RetrySchemaError,
        json.JSONDecodeError,
    ) + retry_anthropic

    delays = (0,) if no_retry else (0, *RETRY_DELAYS_SECONDS)
    last_exc: Optional[BaseException] = None
    attempts = 0

    for delay in delays:
        if delay:
            logger.info(
                "drift_interpretation retry sleeping %ds before attempt %d",
                delay,
                attempts + 1,
            )
            # Resolve at call time so tests can monkeypatch
            # ``doc_audit.judgment.drift_interpretation.time.sleep``.
            time.sleep(delay)
        attempts += 1
        try:
            return fn()
        except DriftInterpretationError:
            # Semantic violation; never retry.
            raise
        except retryable as exc:
            last_exc = exc
            logger.info(
                "drift_interpretation attempt %d failed (%s); will retry if budget remains",
                attempts,
                type(exc).__name__,
            )
            continue

    raise DriftInterpretationError(
        "retry exhausted",
        cause=last_exc,
        attempts=attempts,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def interpret(
    client: JudgmentClient,
    context: DriftInterpretationContext,
    *,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    no_retry: bool = False,
) -> DriftVerdict:
    """Moment 0 LLM judgment for a single drift event.

    Builds the cache-aware prompt, calls the Anthropic API via the
    shared ``JudgmentClient``, parses + validates the response, and
    returns a ``DriftVerdict`` satisfying every E1 invariant.

    Args:
        client: shared ``JudgmentClient`` instance.
        context: drift event input package (E2).
        model: Anthropic model identifier (default Haiku 4.5).
            The actual model is configured on the ``JudgmentClient``;
            this parameter is exposed for future overrides and for the
            CLI surface.
        timeout: per-attempt timeout in seconds (NFR-002 budget).
        confidence_threshold: gate for PROPOSED_EDIT / NO_CHANGE_NEEDED
            demotion (default 0.80).
        no_retry: skip the retry policy (testing only).

    Returns:
        ``DriftVerdict`` guaranteed to satisfy E1 invariants.

    Raises:
        DriftInterpretationError: after retry exhaustion OR on a
            semantic violation (out-of-set ``proposed_edit.doc_path``).
    """
    del model, timeout  # The shared JudgmentClient owns these.

    user_section = _build_prompt(context)

    def _attempt() -> DriftVerdict:
        response = client.call(PROMPT_PATH, user_section)
        return _parse_verdict(response.content, context)

    verdict = _call_with_retry(_attempt, no_retry=no_retry)
    return _demote_low_confidence(verdict, confidence_threshold)


# ---------------------------------------------------------------------------
# CLI surface (per contracts/cli.md)
# ---------------------------------------------------------------------------


class _ArgparseError(Exception):
    """Raised by ``_StructuredArgumentParser.error()`` so ``main()`` returns exit 3.

    argparse's default ``error()`` calls ``sys.exit(2)``, but
    ``contracts/cli.md`` defines no exit-2 code for this CLI — bad
    flags map to exit 3. Mirrors the WP03 pattern from mission #309.
    """


class _StructuredArgumentParser(argparse.ArgumentParser):
    """Argparse subclass that raises instead of ``sys.exit(2)`` on bad flags.

    ``--help`` still exits 0 (argparse's help path uses ``parser.exit``,
    not ``error()``).
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _StructuredArgumentParser(
        prog="drift_interpretation",
        description=(
            "Moment 0 drift-event LLM judgment. Reads a "
            "DriftInterpretationContext JSON document from --input-file "
            "or stdin and writes a DriftVerdict JSON document to "
            "--output-file or stdout."
        ),
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        default=None,
        help="Path to a JSON DriftInterpretationContext (default: stdin).",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=None,
        help="Path to write the DriftVerdict JSON (default: stdout).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Anthropic model identifier (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--api-key-path",
        type=Path,
        default=DEFAULT_API_KEY_PATH,
        help=(
            "Path to the Anthropic API key file "
            f"(default: {DEFAULT_API_KEY_PATH})."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=(
            "Per-attempt timeout in seconds "
            f"(default: {DEFAULT_TIMEOUT_SECONDS})."
        ),
    )
    parser.add_argument(
        "--no-retry",
        action="store_true",
        default=False,
        help="Disable retries (testing only).",
    )
    return parser


def _emit_stderr_error(step: str, error: str) -> None:
    """Emit a structured JSON error line on stderr."""
    msg = json.dumps({"step": step, "error": error}, ensure_ascii=False)
    print(msg, file=sys.stderr)


def _parse_context_document(raw: str) -> DriftInterpretationContext:
    """Deserialize a CLI input JSON into a DriftInterpretationContext.

    Raises:
        ValueError: on malformed JSON or schema mismatch (caller maps to exit 3).
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"input JSON parse failure: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"input must be a JSON object (got {type(data).__name__})"
        )

    required = (
        "event_id",
        "timestamp_utc",
        "baseline",
        "mapping_id",
        "mapping_rationale",
        "diff",
        "doc_targets",
    )
    for key in required:
        if key not in data:
            raise ValueError(f"input missing required field {key!r}")

    targets_raw = data["doc_targets"]
    if not isinstance(targets_raw, list) or not targets_raw:
        raise ValueError("input.doc_targets must be a non-empty list")

    targets: list[DocTarget] = []
    for idx, target in enumerate(targets_raw):
        if not isinstance(target, dict):
            raise ValueError(
                f"input.doc_targets[{idx}] must be an object"
            )
        for sub_key in ("path", "contents", "truncated", "truncation_strategy"):
            if sub_key not in target:
                raise ValueError(
                    f"input.doc_targets[{idx}] missing {sub_key!r}"
                )
        targets.append(
            DocTarget(
                path=str(target["path"]),
                contents=str(target["contents"]),
                truncated=bool(target["truncated"]),
                truncation_strategy=str(target["truncation_strategy"]),
            )
        )

    return DriftInterpretationContext(
        event_id=str(data["event_id"]),
        timestamp_utc=str(data["timestamp_utc"]),
        baseline=str(data["baseline"]),
        mapping_id=str(data["mapping_id"]),
        mapping_rationale=str(data["mapping_rationale"]),
        diff=str(data["diff"]),
        doc_targets=targets,
    )


def _verdict_to_dict(verdict: DriftVerdict) -> dict[str, Any]:
    """Serialize a DriftVerdict to a JSON-friendly dict.

    ``None`` shape-dependent fields are dropped so the output exactly
    matches the contract (no extra null keys).
    """
    out: dict[str, Any] = {
        "verdict": verdict.verdict,
        "confidence": verdict.confidence,
        "rationale": verdict.rationale,
    }
    if verdict.proposed_edit is not None:
        out["proposed_edit"] = verdict.proposed_edit
    if verdict.question is not None:
        out["question"] = verdict.question
    return out


def _build_cli_client(api_key_path: Path, model: str) -> JudgmentClient:
    """Build a ``JudgmentClient`` for CLI invocations.

    The CLI bypasses the on-disk ``config.toml`` and injects a
    minimal in-memory ``Config`` shape so callers can pass any
    ``api_key_path`` / ``model`` per invocation.
    """
    from doc_audit.config import Config, GitHubConfig, LLMConfig, PathsConfig, SignalsConfig

    cfg = Config(
        llm=LLMConfig(
            model=model,
            api_key_path=str(api_key_path),
            max_tokens=DEFAULT_MAX_TOKENS,
        ),
        paths=PathsConfig(
            prompts_dir=str(PROMPT_PATH.parent),
            drift_events="/tmp/drift-events.jsonl",
            drift_cursor="/tmp/.drift-events.cursor",
            drift_unmapped="/tmp/unmapped-events.jsonl",
            signal_to_doc_map="/tmp/signal-to-doc-map.json",
            doc_domain_map="/tmp/doc-domain-map.json",
            activity_log_dir="/tmp/activity",
            tick_signal_path="/tmp/last-tick.json",
        ),
        signals=SignalsConfig(sources=["drift_event"]),
        github=GitHubConfig(
            repo="kentonium3/kg-automation",
            bot_identity="kg-felix-bot",
        ),
    )
    return JudgmentClient(cfg)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point.

    Exit codes per ``contracts/cli.md``::

        0 -- Success — verdict written
        1 -- Operational error (API failure after retries, key file unreadable, ...)
        3 -- Invalid input JSON (schema violation in E2)
        5 -- Out-of-set proposed edit (semantic violation)
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _ArgparseError as exc:
        _emit_stderr_error(step="argparse", error=str(exc))
        return 3

    # Read input JSON from --input-file or stdin.
    if args.input_file is not None:
        try:
            raw = args.input_file.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            _emit_stderr_error(step="input_read", error=str(exc))
            return 3
        except OSError as exc:
            _emit_stderr_error(step="input_read", error=str(exc))
            return 3
    else:
        raw = sys.stdin.read()

    try:
        context = _parse_context_document(raw)
    except ValueError as exc:
        _emit_stderr_error(step="input_parse", error=str(exc))
        return 3

    try:
        client = _build_cli_client(args.api_key_path, args.model)
    except (FileNotFoundError, OSError, ValueError) as exc:
        _emit_stderr_error(step="client_build", error=str(exc))
        return 1

    try:
        verdict = interpret(
            client,
            context,
            model=args.model,
            timeout=args.timeout,
            no_retry=args.no_retry,
        )
    except DriftInterpretationError as exc:
        msg = str(exc)
        if "out-of-set" in msg:
            _emit_stderr_error(step="llm_validate", error=msg)
            return 5
        _emit_stderr_error(step="llm_call", error=msg)
        return 1
    except (FileNotFoundError, OSError) as exc:
        _emit_stderr_error(step="config", error=str(exc))
        return 1

    payload = _verdict_to_dict(verdict)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    if args.output_file is not None:
        try:
            args.output_file.write_text(serialized, encoding="utf-8")
        except OSError as exc:
            _emit_stderr_error(step="output_write", error=str(exc))
            return 1
    else:
        sys.stdout.write(serialized)

    return 0


__all__ = [
    "interpret",
    "DriftVerdict",
    "DriftInterpretationContext",
    "DocTarget",
    "DriftInterpretationError",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "DEFAULT_MAX_TOKENS",
    "RETRY_DELAYS_SECONDS",
    "PROMPT_PATH",
    "VALID_VERDICTS",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
