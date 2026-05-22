#!/usr/bin/env python3
"""Narrow LLM disambiguator for ambiguous habit-reply tokens (mission #371 / WP03).

When ``scripts.habits.parse_morning_reply.parse_reply`` cannot resolve a
reply token deterministically (e.g., ``"PT"`` matches three habits), it
surfaces a ``JudgmentItem`` instead of silently guessing (FR-004). This
module is the narrow LLM call that turns that ``JudgmentItem`` into
either:

  * a confident ``chosen_task_id`` (one of the candidate task_ids), OR
  * a ``clarify`` request with a one-sentence question for Kent.

The implementation mirrors ``scripts.doc_audit.judgment.client``
(mission #343):

  * **Cache-aware prompt** -- the system block (large, stable rules +
    examples) is sent with ``cache_control: {"type": "ephemeral"}``.
    The variable user message (Kent's reply + the ambiguous token +
    the candidate list) is small and per-call.
  * **Strict JSON validation** -- the response is parsed as JSON and
    validated against data-model Entity 4 (``result`` in
    ``{"chosen", "clarify"}``, required fields present per shape).
  * **Out-of-set rejection** -- if the LLM returns ``result=chosen``
    with a ``chosen_task_id`` not in the input's candidate set, we
    raise ``DisambiguatorError`` (LLM drift defense).
  * **Single-turn**, ``max_tokens=256`` to bound output -- a "chosen"
    response is ~50 tokens; ``clarify`` is ~80.

The prompt template lives at
``scripts/habits/judgment/prompts/disambiguate_reply.prompt.md`` and
follows the doc-audit cache-marker convention
(``[CACHE_PREFIX_START]`` / ``[CACHE_PREFIX_END]``).

See:
  - ``kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/contracts/api.md``
  - ``kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/contracts/cli.md``
  - ``kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/data-model.md`` Entity 4
  - ``scripts/doc_audit/judgment/client.py`` (pattern source)
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

import anthropic

from scripts.habits.parse_morning_reply import JudgmentItem


# ---------------------------------------------------------------------------
# Module constants (per contracts/api.md)
# ---------------------------------------------------------------------------

#: Default path to the Anthropic API key on office2 (mode 0600).
DEFAULT_API_KEY_PATH = Path("/data/services/openclaw/secrets/anthropic")

#: Default Anthropic model. Haiku 4.5 chosen per plan Phase 0 D5 -- cheap,
#: latency-sensitive, schema-following. Override via ``--model``.
DEFAULT_MODEL = "claude-haiku-4-5"

#: HTTP socket timeout for the Anthropic call.
DEFAULT_TIMEOUT_SECONDS = 30

#: Max tokens for the disambiguation response. 256 is generous: a ``chosen``
#: response is ~50 tokens; ``clarify`` is ~80. Bounding the output prevents
#: pathological prose drift from the LLM.
DEFAULT_MAX_TOKENS = 256

#: Path to the cache-aware prompt template.
PROMPT_PATH = Path(__file__).parent / "prompts" / "disambiguate_reply.prompt.md"

#: Cache markers in the prompt template (mirror doc_audit convention).
CACHE_PREFIX_START = "[CACHE_PREFIX_START]"
CACHE_PREFIX_END = "[CACHE_PREFIX_END]"

#: Schema version embedded in every ``DisambiguationResult``.
SCHEMA_VERSION = 1

#: Maximum allowed length of a clarify suggested_question (per data-model
#: Entity 4 validation rule: "≤200 chars for WhatsApp readability").
SUGGESTED_QUESTION_MAX_CHARS = 200


# ---------------------------------------------------------------------------
# Dataclasses (per contracts/api.md / data-model Entity 4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DisambiguationResult:
    """Result of one LLM disambiguation call.

    Per data-model Entity 4, EXACTLY one of two shapes:

      * ``result="chosen"``: ``chosen_task_id`` is required and MUST be
        in the input's ``candidate_task_ids`` (validated by ``disambiguate``).
        ``suggested_question`` is ``None``.

      * ``result="clarify"``: ``suggested_question`` is required (≤200 chars).
        ``chosen_task_id`` is ``None``.

    Both shapes carry ``reason`` (short justification, for audit trail).
    """

    schema_version: int
    result: Literal["chosen", "clarify"]
    chosen_task_id: Optional[int]
    reason: str
    suggested_question: Optional[str]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DisambiguatorError(Exception):
    """Raised when the LLM disambiguation response is malformed or invalid.

    Covers:

      * JSON parse failure on the LLM's response text.
      * Missing required field per the chosen-vs-clarify shape.
      * Invalid ``result`` value (not in {"chosen", "clarify"}).
      * ``chosen_task_id`` outside the input candidate set
        (the load-bearing LLM-drift safety check).
      * ``suggested_question`` longer than the WhatsApp budget.

    Callers in the CLI map this to exit code 3 (malformed response) or
    5 (out-of-set chosen_task_id) per ``contracts/cli.md``.
    """


# ---------------------------------------------------------------------------
# Internal helpers (I/O wrappers)
# ---------------------------------------------------------------------------


def _read_api_key(path: Path) -> str:
    """Read the Anthropic API key from a mode-0600 file.

    The key is read and stripped of trailing whitespace. We do NOT log,
    echo, or otherwise emit the key value in any exception path -- a
    failure path here only mentions the path, never the contents.

    Raises:
        FileNotFoundError: key file missing (caller maps to exit 1 +
            structured stderr line).
        OSError: key file unreadable.
        ValueError: key file is empty after strip.
    """
    try:
        content = Path(path).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise
    except PermissionError as exc:
        raise OSError(
            f"API key file not readable (permission denied): {path}"
        ) from exc
    except OSError as exc:
        raise OSError(f"Could not read API key file {path}: {exc}") from exc
    if not content:
        raise ValueError(f"API key file is empty: {path}")
    return content


def _load_prompt_template() -> tuple[str, str]:
    """Read PROMPT_PATH and split it into (cached_system_prefix, user_template).

    The template follows the doc_audit convention:

        [CACHE_PREFIX_START]
        <system / rules / examples -- cacheable across calls>
        [CACHE_PREFIX_END]

        <user template with {reply_text} / {token} / {candidates} / {inferred_state}
        placeholders -- format-substituted per call>

    Returns:
        (cached_system_prefix, user_template_raw)

    Raises:
        FileNotFoundError: template file missing.
        ValueError: cache markers missing or misordered.
    """
    template = PROMPT_PATH.read_text(encoding="utf-8")
    try:
        start = template.index(CACHE_PREFIX_START) + len(CACHE_PREFIX_START)
        end = template.index(CACHE_PREFIX_END)
    except ValueError as exc:
        raise ValueError(
            "Prompt template missing or misordered "
            f"{CACHE_PREFIX_START}/{CACHE_PREFIX_END} markers: {PROMPT_PATH}"
        ) from exc

    if end < start:
        raise ValueError(
            "Prompt template missing or misordered "
            f"{CACHE_PREFIX_START}/{CACHE_PREFIX_END} markers: {PROMPT_PATH}"
        )

    cached = template[start:end].strip()
    rest_start = template.index(CACHE_PREFIX_END) + len(CACHE_PREFIX_END)
    user_template = template[rest_start:].strip()
    return cached, user_template


def _format_candidates(ambiguity: JudgmentItem) -> str:
    """Render the candidate block as a list of ``task_id: <id>, title: <title>`` lines.

    Used to fill the ``{candidates}`` placeholder in the user template.
    Each candidate gets its own line so the LLM can pattern-match on
    individual rows. Order mirrors the parser's emission order
    (typically morning-list position ascending), which keeps audit logs
    stable across the parser->disambiguator boundary.
    """
    if len(ambiguity.candidate_task_ids) != len(ambiguity.candidate_titles):
        raise DisambiguatorError(
            "JudgmentItem has mismatched candidate_task_ids vs "
            "candidate_titles lengths"
        )
    lines = [
        f"- task_id: {tid}, title: {title}"
        for tid, title in zip(
            ambiguity.candidate_task_ids,
            ambiguity.candidate_titles,
        )
    ]
    return "\n".join(lines)


def _extract_response_text(response: Any) -> str:
    """Pull the first text block out of an Anthropic response.

    Mirrors ``scripts.doc_audit.judgment.client.JudgmentClient._extract_text``
    so test fixtures shaped for that client also work here.
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


# ---------------------------------------------------------------------------
# Response validation
# ---------------------------------------------------------------------------


def _validate_chosen(
    payload: dict[str, Any],
    candidate_task_ids: list[int],
) -> DisambiguationResult:
    """Validate a ``result=chosen`` response payload + return DisambiguationResult.

    Out-of-set ``chosen_task_id`` is rejected here. This is the
    load-bearing LLM-drift defense (FR-006, data-model Entity 4
    validation rule: "Disambiguator that returns an out-of-set ID is a
    hard-fail").
    """
    if "chosen_task_id" not in payload:
        raise DisambiguatorError(
            "response missing required field 'chosen_task_id' for "
            "result='chosen'"
        )
    chosen_raw = payload["chosen_task_id"]
    if not isinstance(chosen_raw, int) or isinstance(chosen_raw, bool):
        # ``isinstance(True, int) is True`` in Python; bool guard avoids
        # accepting ``True`` as task_id=1.
        raise DisambiguatorError(
            f"response field 'chosen_task_id' must be an int "
            f"(got {type(chosen_raw).__name__})"
        )
    if chosen_raw not in candidate_task_ids:
        raise DisambiguatorError(
            f"out-of-set chosen_task_id: LLM returned {chosen_raw!r} "
            f"but candidates were {candidate_task_ids!r}"
        )
    reason = payload.get("reason", "")
    if not isinstance(reason, str):
        raise DisambiguatorError(
            f"response field 'reason' must be a string "
            f"(got {type(reason).__name__})"
        )
    return DisambiguationResult(
        schema_version=SCHEMA_VERSION,
        result="chosen",
        chosen_task_id=chosen_raw,
        reason=reason,
        suggested_question=None,
    )


def _validate_clarify(payload: dict[str, Any]) -> DisambiguationResult:
    """Validate a ``result=clarify`` response payload + return DisambiguationResult.

    Enforces ``suggested_question`` presence and the ≤200-char WhatsApp
    budget. Long questions are rejected so the agent's downstream
    WhatsApp relay does not truncate mid-sentence.
    """
    if "suggested_question" not in payload:
        raise DisambiguatorError(
            "response missing required field 'suggested_question' for "
            "result='clarify'"
        )
    question = payload["suggested_question"]
    if not isinstance(question, str):
        raise DisambiguatorError(
            f"response field 'suggested_question' must be a string "
            f"(got {type(question).__name__})"
        )
    if not question.strip():
        raise DisambiguatorError(
            "response field 'suggested_question' must be non-empty for "
            "result='clarify'"
        )
    if len(question) > SUGGESTED_QUESTION_MAX_CHARS:
        raise DisambiguatorError(
            f"suggested_question exceeds {SUGGESTED_QUESTION_MAX_CHARS} "
            f"chars (got {len(question)}): WhatsApp readability budget"
        )
    reason = payload.get("reason", "")
    if not isinstance(reason, str):
        raise DisambiguatorError(
            f"response field 'reason' must be a string "
            f"(got {type(reason).__name__})"
        )
    return DisambiguationResult(
        schema_version=SCHEMA_VERSION,
        result="clarify",
        chosen_task_id=None,
        reason=reason,
        suggested_question=question,
    )


def _parse_and_validate_response(
    text: str,
    candidate_task_ids: list[int],
) -> DisambiguationResult:
    """Parse the LLM's response text as JSON + validate against Entity 4.

    Raises:
        DisambiguatorError: JSON parse failure, missing / wrong-typed
            fields, invalid ``result`` value, out-of-set
            ``chosen_task_id``, or over-long ``suggested_question``.
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DisambiguatorError(
            f"invalid JSON in LLM response: {exc.msg} "
            f"(at line {exc.lineno} col {exc.colno})"
        ) from exc

    if not isinstance(payload, dict):
        raise DisambiguatorError(
            f"LLM response must be a JSON object "
            f"(got {type(payload).__name__})"
        )

    result_value = payload.get("result")
    if result_value == "chosen":
        return _validate_chosen(payload, candidate_task_ids)
    if result_value == "clarify":
        return _validate_clarify(payload)
    raise DisambiguatorError(
        f"response field 'result' must be 'chosen' or 'clarify' "
        f"(got {result_value!r})"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def disambiguate(
    *,
    reply_text: str,
    ambiguity: JudgmentItem,
    model: str = DEFAULT_MODEL,
    api_key_path: Path = DEFAULT_API_KEY_PATH,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> DisambiguationResult:
    """Resolve an ambiguous reply token via a single-turn Anthropic call.

    Per data-model Entity 4 the response must be EXACTLY one of two
    shapes; this function enforces the shape and rejects out-of-set
    ``chosen_task_id`` values.

    Args:
        reply_text: Kent's full reply text (so the LLM can read
            context surrounding the ambiguous token).
        ambiguity: The ``JudgmentItem`` from the parser. Carries the
            ambiguous token, the candidate task_ids + titles, and the
            inferred state.
        model: Anthropic model name (default: ``claude-haiku-4-5``).
        api_key_path: Path to the API key file (mode 0600 on office2).
        timeout: HTTP timeout in seconds.

    Returns:
        A frozen ``DisambiguationResult``.

    Raises:
        FileNotFoundError: API key file missing.
        OSError: API key file unreadable.
        ValueError: API key file empty OR prompt template missing /
            misordered cache markers.
        DisambiguatorError: LLM response is malformed, has invalid
            shape, returns an out-of-set chosen_task_id, or violates
            the suggested_question length budget.
        anthropic.APIError: re-raised verbatim. Callers map to exit 1.
    """
    api_key = _read_api_key(api_key_path)
    system_prompt, user_template = _load_prompt_template()

    candidates_block = _format_candidates(ambiguity)
    user_message = user_template.format(
        reply_text=reply_text,
        token=ambiguity.token,
        candidates=candidates_block,
        inferred_state=ambiguity.inferred_state,
    )

    # Resolve ``anthropic.Anthropic`` at call time (NOT at import time)
    # so test monkeypatches on the module attribute take effect. This
    # matches the doc_audit.judgment.client convention so the same
    # ``mock_anthropic`` fixture pattern works for our tests too.
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=DEFAULT_MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
        timeout=timeout,
    )

    text = _extract_response_text(response)
    return _parse_and_validate_response(text, ambiguity.candidate_task_ids)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class _ArgparseError(Exception):
    """Raised by ``_StructuredArgumentParser.error()`` to let ``main()`` return exit 3.

    Mirrors the pattern from WP01/WP02 (``morning_checkin_list`` /
    ``parse_morning_reply``). argparse's default ``error()`` calls
    ``sys.exit(2)``, which would leak through ``main()`` and violate
    ``contracts/cli.md`` (no exit 2 defined for the disambiguator;
    bad flags map to exit 3).
    """


class _StructuredArgumentParser(argparse.ArgumentParser):
    """ArgumentParser subclass that raises ``_ArgparseError`` instead of ``sys.exit(2)`` on bad flags.

    ``--help`` is unaffected: argparse's help path uses ``parser.exit()``
    / ``parser._print_message``, not ``error()``, so help still exits 0.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the ``python3 -m`` entry point."""
    parser = _StructuredArgumentParser(
        prog="disambiguate_reply",
        description=(
            "Resolve an ambiguous habit-reply token via a narrow LLM "
            "call. Input is a JudgmentItem-wrapped JSON document (per "
            "data-model Entity 3): {'schema_version': 1, 'reply_text': ..., "
            "'ambiguity': {'token': ..., 'candidate_task_ids': [...], "
            "'candidate_titles': [...], 'inferred_state': ...}}. Output is "
            "a DisambiguationResult JSON document (Entity 4) -- either "
            "{'result':'chosen', 'chosen_task_id': <id>, ...} or "
            "{'result':'clarify', 'suggested_question': ..., ...}. "
            "Reads input from --input-file or stdin."
        ),
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        default=None,
        help=(
            "Path to a JSON file with the disambiguator input "
            "(default: read JSON from stdin)."
        ),
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Anthropic model name (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--api-key-path",
        type=Path,
        default=DEFAULT_API_KEY_PATH,
        help=(
            f"Path to the Anthropic API key file "
            f"(default: {DEFAULT_API_KEY_PATH})."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=(
            f"HTTP timeout in seconds for the Anthropic call "
            f"(default: {DEFAULT_TIMEOUT_SECONDS})."
        ),
    )
    return parser


def _emit_stderr_error(step: str, error: str) -> None:
    """Emit a single JSON line on stderr to keep error output structured."""
    msg = json.dumps({"step": step, "error": error}, ensure_ascii=False)
    print(msg, file=sys.stderr)


def _result_to_dict(result: DisambiguationResult) -> dict[str, Any]:
    """Convert a ``DisambiguationResult`` to a JSON-serializable dict.

    ``None`` values for the shape-dependent fields are preserved so the
    output shape is auditable -- consumers can branch on which fields
    are populated.
    """
    return dataclasses.asdict(result)


def _parse_input_document(raw: str) -> tuple[str, JudgmentItem]:
    """Parse the disambiguator input JSON (Entity 3) into (reply_text, JudgmentItem).

    Raises:
        ValueError: JSON parse failure or schema mismatch (missing /
            wrong-typed fields). Caller maps to exit 3.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"input JSON parse failure: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"input must be a JSON object (got {type(data).__name__})"
        )
    for key in ("reply_text", "ambiguity"):
        if key not in data:
            raise ValueError(f"input missing required field {key!r}")
    if not isinstance(data["reply_text"], str):
        raise ValueError(
            f"input field 'reply_text' must be a string "
            f"(got {type(data['reply_text']).__name__})"
        )
    ambiguity_raw = data["ambiguity"]
    if not isinstance(ambiguity_raw, dict):
        raise ValueError(
            f"input field 'ambiguity' must be a JSON object "
            f"(got {type(ambiguity_raw).__name__})"
        )
    for key in (
        "token",
        "candidate_task_ids",
        "candidate_titles",
        "inferred_state",
    ):
        if key not in ambiguity_raw:
            raise ValueError(
                f"input.ambiguity missing required field {key!r}"
            )
    if not isinstance(ambiguity_raw["candidate_task_ids"], list):
        raise ValueError("input.ambiguity.candidate_task_ids must be a list")
    if not isinstance(ambiguity_raw["candidate_titles"], list):
        raise ValueError("input.ambiguity.candidate_titles must be a list")
    if ambiguity_raw["inferred_state"] not in (
        "complete",
        "incomplete",
        "skipped",
    ):
        raise ValueError(
            "input.ambiguity.inferred_state must be one of "
            "'complete' / 'incomplete' / 'skipped' "
            f"(got {ambiguity_raw['inferred_state']!r})"
        )

    try:
        ambiguity = JudgmentItem(
            token=str(ambiguity_raw["token"]),
            candidate_task_ids=[
                int(tid) for tid in ambiguity_raw["candidate_task_ids"]
            ],
            candidate_titles=[
                str(title) for title in ambiguity_raw["candidate_titles"]
            ],
            inferred_state=ambiguity_raw["inferred_state"],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"input.ambiguity field type error: {exc}"
        ) from exc

    return data["reply_text"], ambiguity


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Exit codes per ``contracts/cli.md``::

        0 -- disambiguator returned a valid response (chosen or clarify)
        1 -- LLM API error (network / auth / rate-limit)
        3 -- validation error (bad input JSON, schema mismatch,
             malformed LLM response)
        5 -- LLM returned chosen_task_id outside the candidate set
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
        reply_text, ambiguity = _parse_input_document(raw)
    except ValueError as exc:
        _emit_stderr_error(step="input_parse", error=str(exc))
        return 3

    try:
        result = disambiguate(
            reply_text=reply_text,
            ambiguity=ambiguity,
            model=args.model,
            api_key_path=args.api_key_path,
            timeout=args.timeout,
        )
    except DisambiguatorError as exc:
        msg = str(exc)
        # Out-of-set chosen_task_id maps to exit 5 (a distinct failure
        # class per contracts/cli.md). All other DisambiguatorError
        # paths (malformed JSON, missing fields, etc.) map to exit 3.
        if "out-of-set chosen_task_id" in msg:
            _emit_stderr_error(step="llm_validate", error=msg)
            return 5
        _emit_stderr_error(step="llm_validate", error=msg)
        return 3
    except (FileNotFoundError, OSError, ValueError) as exc:
        # API key file errors, prompt template errors. These are
        # configuration / environment failures (exit 1: not the
        # caller's input problem).
        _emit_stderr_error(step="config", error=str(exc))
        return 1
    except anthropic.APIError as exc:
        _emit_stderr_error(step="llm_call", error=str(exc))
        return 1

    sys.stdout.write(
        json.dumps(_result_to_dict(result), ensure_ascii=False, indent=2)
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
