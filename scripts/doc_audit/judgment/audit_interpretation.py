"""Moment 0 commit-audit interpretation LLM judgment.

Mirror of :mod:`doc_audit.judgment.drift_interpretation` adapted for
commit-derived `Doc audit:` issues. Per mission
``audit-interpretation-moment0-01KSBGBS`` (#400).

This module is the load-bearing judgment surface for the commit-audit
path. :func:`interpret_audit` consumes an
:class:`AuditInterpretationContext` (one audit issue + commit diff + a
list of in-scope docs) and returns one :class:`AuditVerdict` PER doc.
The routing layer (``handle_audit_routing.py``) translates each
verdict into one of four outcomes per doc:

- ``PROPOSED_EDIT`` (conf ≥0.80): translate to ``ProposedEdit`` and
  pass to ``tier_classification`` (Moment 1).
- ``PROPOSED_EDIT`` (conf <0.80): demoted to ``JUDGMENT_REQUIRED``
  with the proposed edit folded into the rationale.
- ``JUDGMENT_REQUIRED``: append the LLM's question to a consolidated
  comment on the audit issue (per research D3).
- ``NO_CHANGE_NEEDED`` (conf ≥0.80): record a ledger entry only;
  auto-close the audit when ALL docs return this verdict.
- ``NO_CHANGE_NEEDED`` (conf <0.80): demoted to ``JUDGMENT_REQUIRED``.

Per-doc isolation
-----------------
The LLM is invoked ONCE PER in-scope doc. A failure on doc N (after
retries exhaust) must NOT prevent docs N-1 and N+1 from being
evaluated. :func:`interpret_audit` catches :class:`DriftInterpretationError`
per-doc and emits a synthetic ``JUDGMENT_REQUIRED`` verdict carrying
``confidence=0.0`` and ``rationale="LLM retry exhausted"`` for the
affected doc; the audit as a whole proceeds.

Out-of-scope guardrail
----------------------
The single in-scope doc path is supplied verbatim in the user message.
The LLM is instructed to copy it. If the LLM returns a
``proposed_edit.doc_path`` that differs from the supplied path, the
verdict is demoted to ``JUDGMENT_REQUIRED`` with the divergence noted
in the rationale (FR-005 spirit — never trust out-of-set paths).

Truncation
----------
Reuses :func:`doc_audit.judgment.drift_interpretation._truncate_doc_state`
unchanged. Same D2 tier strategy: full ≤8KB; head+region+tail ≤32KB;
region-only >32KB.

Retry policy (D6)
-----------------
Three retries with delays ``(30, 60, 120)`` seconds per doc. After
all retries are exhausted for a given doc, a synthetic
``JUDGMENT_REQUIRED`` verdict is emitted for that doc.

Cache contract
--------------
The system-prompt portion of the call MUST be ≥80% of total prompt
tokens and is sent with ``cache_control: ephemeral`` via the shared
:class:`doc_audit.judgment.client.JudgmentClient`. The variable
per-doc section is the user message.

Pattern source: :mod:`doc_audit.judgment.drift_interpretation`.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from doc_audit.judgment._llm_response import _strip_code_fence
from doc_audit.judgment.client import JudgmentClient
from doc_audit.judgment.drift_interpretation import (
    DocTarget,
    DriftInterpretationError,
    _truncate_doc_state,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Default Anthropic model.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

#: Per-attempt HTTP timeout (NFR-002 single-attempt P95 budget).
DEFAULT_TIMEOUT_SECONDS = 30

#: Confidence floor below which PROPOSED_EDIT / NO_CHANGE_NEEDED demote
#: to JUDGMENT_REQUIRED (FR-005, FR-007 boundary).
DEFAULT_CONFIDENCE_THRESHOLD = 0.80

#: Max output tokens for one verdict JSON.
DEFAULT_MAX_TOKENS = 512

#: Retry delays in seconds (D6). First attempt immediate; sleep before
#: each retry. Total max wait = 30 + 60 + 120 = 210s per doc.
RETRY_DELAYS_SECONDS: tuple[int, ...] = (30, 60, 120)

#: Default API key path on office2 (mode 0600).
DEFAULT_API_KEY_PATH = Path("/data/services/openclaw/secrets/anthropic")

#: Cache-aware prompt template path.
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "audit_interpretation.prompt.md"
)

#: Allowed verdict values (case-sensitive).
VALID_VERDICTS = frozenset({"PROPOSED_EDIT", "JUDGMENT_REQUIRED", "NO_CHANGE_NEEDED"})

#: Max length of a ``JUDGMENT_REQUIRED.question``.
QUESTION_MAX_CHARS = 500

#: Conservative input-token guard threshold for audit_interpretation prompts.
#:
#: Haiku 4.5's context window is 200,000 input tokens. We reserve ~10% margin
#: (20,000 tokens) for system prompt, output (DEFAULT_MAX_TOKENS=512), and
#: estimation conservatism. If the estimated input exceeds this threshold,
#: :func:`_interpret_one_doc` short-circuits to a synthetic
#: ``JUDGMENT_REQUIRED`` rather than burning 4 × ~50s retries on a
#: 400-guaranteed API call. See issue #402 for diagnostic + rationale.
INPUT_TOKEN_GUARD_THRESHOLD: int = 180_000


def _estimate_input_tokens(text: str) -> int:
    """Estimate input token count for an LLM prompt.

    Uses a conservative char-based heuristic: ceiling-divide character
    count by 4 (Anthropic's English-text approximation). Conservative
    on purpose — for prompts near or over the guard threshold we want
    to over-estimate (triggers the guard earlier, safer behavior).

    Returns at least 1 to avoid degenerate empty-prompt edge cases.

    See issue #402.
    """
    if not text:
        return 1
    return max(1, (len(text) + 3) // 4)


# ---------------------------------------------------------------------------
# Dataclasses (per data-model E1, E2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditVerdict:
    """LLM-produced verdict for one in-scope doc within an audit (E1).

    Invariants (enforced by :func:`_parse_verdict`):
        - ``verdict`` in :data:`VALID_VERDICTS`
        - ``confidence`` in [0.0, 1.0]
        - ``rationale`` non-empty
        - ``proposed_edit`` present iff ``verdict == "PROPOSED_EDIT"``
        - ``question`` present iff ``verdict == "JUDGMENT_REQUIRED"``
        - ``doc_path`` always populated with the in-scope doc the
          verdict applies to (mirrors the supplied target path)
    """

    doc_path: str
    verdict: str
    confidence: float
    rationale: str
    proposed_edit: Optional[dict] = None
    question: Optional[str] = None


@dataclass(frozen=True)
class AuditInterpretationContext:
    """Input to Moment 0 commit-audit LLM judgment (E2).

    Assembled by ``handle_audit_routing.py`` from one ``Doc audit:``
    issue payload + the commit diff identified by the
    issue's triggering SHA + the current contents of each in-scope
    doc (truncated per D2 if needed). Reuses
    :class:`DocTarget` from drift_interpretation.
    """

    audit_issue: int
    commit_sha: str
    diff: str
    in_scope_docs: list[DocTarget]


# ---------------------------------------------------------------------------
# Internal errors
# ---------------------------------------------------------------------------


class _RetrySchemaError(Exception):
    """Internal-only — raised by :func:`_parse_verdict` for retry-eligible schema violations.

    Distinct from :class:`DriftInterpretationError` so the retry wrapper
    can distinguish between "LLM produced bad JSON; try again" and
    semantic errors. (Audit interpretation has no semantic-violation
    raise path: out-of-scope doc_path is demoted via
    :func:`_demote_low_confidence`-style logic in
    :func:`_parse_proposed_edit`, not raised.)
    """


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def _render_user_section(doc: DocTarget, context: AuditInterpretationContext) -> str:
    """Render the per-doc variable section as the user message.

    Lists the single in-scope ``doc.path`` explicitly so the LLM can
    copy it verbatim into ``proposed_edit.doc_path``. The doc's
    contents is presented after D2 truncation.
    """
    parts: list[str] = []
    parts.append("## Audit")
    parts.append(f"- audit_issue: {context.audit_issue}")
    parts.append(f"- commit_sha: {context.commit_sha}")
    parts.append("")
    parts.append("## In-scope doc under evaluation")
    parts.append(f"- doc_path: {doc.path}")
    parts.append(
        "If you choose verdict=PROPOSED_EDIT, "
        "proposed_edit.doc_path MUST equal this exact string:"
    )
    parts.append(f"- {doc.path}")
    parts.append("")
    parts.append("## Commit diff (unified)")
    parts.append("```diff")
    parts.append(context.diff)
    parts.append("```")
    parts.append("")
    parts.append("## Doc current state")
    parts.append(
        f"(truncation_strategy: {doc.truncation_strategy}, "
        f"truncated: {doc.truncated})"
    )
    parts.append("```")
    parts.append(doc.contents)
    parts.append("```")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("Return STRICT JSON in one of the three shapes. No prose.")
    return "\n".join(parts)


def _build_prompt(doc: DocTarget, context: AuditInterpretationContext) -> str:
    """Render the user message (the system prefix is supplied by JudgmentClient).

    The cache-aware system block lives in :data:`PROMPT_PATH` between
    ``[CACHE_PREFIX_START]`` / ``[CACHE_PREFIX_END]`` markers and is
    sent by ``JudgmentClient.call`` with ``cache_control: ephemeral``.
    """
    return _render_user_section(doc, context)


# ---------------------------------------------------------------------------
# Response parsing + schema validation
# ---------------------------------------------------------------------------


def _parse_verdict(
    response_text: str,
    doc: DocTarget,
) -> AuditVerdict:
    """Parse + validate the LLM JSON response for a single doc.

    Schema violations raise :class:`_RetrySchemaError` (retry-eligible).
    Out-of-scope ``proposed_edit.doc_path`` is NOT raised — instead the
    verdict is constructed and the caller demotes it to
    ``JUDGMENT_REQUIRED`` (per WP01 prompt spec: "demote, don't fail"
    for the audit path, distinct from drift where the LLM has a wider
    candidate set).
    """
    text = (response_text or "").strip()
    if not text:
        raise _RetrySchemaError("empty LLM response")

    try:
        parsed = json.loads(_strip_code_fence(text))
    except json.JSONDecodeError as exc:
        raise _RetrySchemaError(f"invalid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise _RetrySchemaError(
            f"response must be a JSON object (got {type(parsed).__name__})"
        )

    verdict_value = parsed.get("verdict")
    if verdict_value not in VALID_VERDICTS:
        raise _RetrySchemaError(
            f"invalid verdict value {verdict_value!r}; "
            f"expected one of {sorted(VALID_VERDICTS)}"
        )

    confidence_raw = parsed.get("confidence")
    # bool is an int subclass — reject explicitly so True/False don't slip through.
    if isinstance(confidence_raw, bool) or not isinstance(
        confidence_raw, (int, float)
    ):
        raise _RetrySchemaError(
            f"confidence must be a JSON number (got {type(confidence_raw).__name__})"
        )
    confidence = float(confidence_raw)
    if not (0.0 <= confidence <= 1.0):
        raise _RetrySchemaError(
            f"confidence out of range: {confidence!r} (expected [0.0, 1.0])"
        )

    rationale = parsed.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise _RetrySchemaError("rationale missing or empty")

    if verdict_value == "PROPOSED_EDIT":
        return _parse_proposed_edit(parsed, confidence, rationale, doc)
    if verdict_value == "JUDGMENT_REQUIRED":
        return _parse_judgment_required(parsed, confidence, rationale, doc)
    # verdict_value == "NO_CHANGE_NEEDED"
    return AuditVerdict(
        doc_path=doc.path,
        verdict="NO_CHANGE_NEEDED",
        confidence=confidence,
        rationale=rationale,
    )


def _parse_proposed_edit(
    parsed: dict,
    confidence: float,
    rationale: str,
    doc: DocTarget,
) -> AuditVerdict:
    """Validate a PROPOSED_EDIT shape for a single in-scope doc.

    If the LLM returns a ``proposed_edit.doc_path`` that differs from
    the supplied in-scope ``doc.path``, the verdict is demoted to
    ``JUDGMENT_REQUIRED`` (NOT raised) so the audit can still record a
    useful question for the operator.
    """
    proposed_edit = parsed.get("proposed_edit")
    if not isinstance(proposed_edit, dict):
        raise _RetrySchemaError(
            "PROPOSED_EDIT requires a proposed_edit object"
        )

    for key in ("doc_path", "current_value", "proposed_value"):
        value = proposed_edit.get(key)
        if not isinstance(value, str) or not value.strip():
            raise _RetrySchemaError(
                f"proposed_edit.{key} missing or not a non-empty string"
            )

    if proposed_edit["doc_path"] != doc.path:
        # Out-of-scope doc_path: the LLM proposed editing a doc OTHER
        # than the one we asked about. Demote to JUDGMENT_REQUIRED so
        # the operator sees the LLM's reasoning without us auto-acting
        # on a path we didn't sanction.
        new_rationale = (
            f"LLM proposed an edit to {proposed_edit['doc_path']!r} but we "
            f"asked about {doc.path!r}. Original rationale: {rationale} "
            f"Original proposed_edit: "
            f"{json.dumps(proposed_edit, ensure_ascii=False)}"
        )
        question = (
            f"LLM proposed editing {proposed_edit['doc_path']!r} when we "
            f"asked about {doc.path!r}. Should this audit be re-scoped to "
            "include that doc, or is the LLM's suggestion off-target?"
        )
        return AuditVerdict(
            doc_path=doc.path,
            verdict="JUDGMENT_REQUIRED",
            confidence=confidence,
            rationale=new_rationale,
            question=question,
        )

    return AuditVerdict(
        doc_path=doc.path,
        verdict="PROPOSED_EDIT",
        confidence=confidence,
        rationale=rationale,
        proposed_edit=dict(proposed_edit),
    )


def _parse_judgment_required(
    parsed: dict,
    confidence: float,
    rationale: str,
    doc: DocTarget,
) -> AuditVerdict:
    """Validate a JUDGMENT_REQUIRED shape."""
    question = parsed.get("question")
    if not isinstance(question, str) or not question.strip():
        raise _RetrySchemaError(
            "JUDGMENT_REQUIRED requires a non-empty question"
        )
    if len(question) > QUESTION_MAX_CHARS:
        raise _RetrySchemaError(
            f"question exceeds {QUESTION_MAX_CHARS} chars (got {len(question)})"
        )
    return AuditVerdict(
        doc_path=doc.path,
        verdict="JUDGMENT_REQUIRED",
        confidence=confidence,
        rationale=rationale,
        question=question,
    )


def _demote_low_confidence(
    verdict: AuditVerdict, threshold: float
) -> AuditVerdict:
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

    return AuditVerdict(
        doc_path=verdict.doc_path,
        verdict="JUDGMENT_REQUIRED",
        confidence=verdict.confidence,
        rationale=new_rationale,
        question=new_question,
    )


# ---------------------------------------------------------------------------
# Retry policy (D6)
# ---------------------------------------------------------------------------


def _call_with_retry(
    fn: Callable[[], AuditVerdict],
    *,
    no_retry: bool = False,
) -> AuditVerdict:
    """Invoke ``fn`` with the D6 retry policy.

    Retryable exceptions: :class:`_RetrySchemaError` plus anthropic
    transient errors. :class:`DriftInterpretationError` raised by ``fn``
    is propagated immediately (semantic violations are not retryable;
    audit interpretation has none today but the contract is kept for
    parity with drift_interpretation).

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
                "audit_interpretation retry sleeping %ds before attempt %d",
                delay,
                attempts + 1,
            )
            time.sleep(delay)
        attempts += 1
        try:
            return fn()
        except DriftInterpretationError:
            # Semantic violation; never retry. (No code path raises this
            # from inside audit_interpretation today, but kept for
            # symmetry with drift_interpretation.)
            raise
        except retryable as exc:
            last_exc = exc
            logger.info(
                "audit_interpretation attempt %d failed (%s); will retry if budget remains",
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


def _interpret_one_doc(
    client: JudgmentClient,
    doc: DocTarget,
    context: AuditInterpretationContext,
    *,
    confidence_threshold: float,
    no_retry: bool,
) -> AuditVerdict:
    """Run Moment 0 judgment for a single in-scope doc.

    Wraps the LLM call with the D6 retry policy and applies confidence
    demotion. Raises :class:`DriftInterpretationError` if all retries
    are exhausted — the caller (:func:`interpret_audit`) catches per-doc
    so other docs can still be evaluated.
    """
    user_section = _build_prompt(doc, context)

    estimated_tokens = _estimate_input_tokens(user_section)
    if estimated_tokens >= INPUT_TOKEN_GUARD_THRESHOLD:
        logger.warning(
            "audit_interpretation size-guard short-circuit: doc %s "
            "estimated %d tokens >= threshold %d; skipping LLM call",
            doc.path,
            estimated_tokens,
            INPUT_TOKEN_GUARD_THRESHOLD,
        )
        synthetic = AuditVerdict(
            doc_path=doc.path,
            verdict="JUDGMENT_REQUIRED",
            confidence=0.0,
            rationale=(
                f"oversized prompt: ~{estimated_tokens} tokens "
                f">= threshold {INPUT_TOKEN_GUARD_THRESHOLD}; "
                "operator review required (size-guard short-circuit)"
            ),
            question=(
                f"Automated audit interpretation skipped {doc.path!r} because "
                f"the assembled prompt (~{estimated_tokens} tokens) exceeds "
                f"the input-token guard threshold ({INPUT_TOKEN_GUARD_THRESHOLD}). "
                f"Please review this doc against commit {context.commit_sha} "
                "manually. See issue #402."
            ),
        )
        return _demote_low_confidence(synthetic, confidence_threshold)

    def _attempt() -> AuditVerdict:
        response = client.call(PROMPT_PATH, user_section)
        return _parse_verdict(response.content, doc)

    verdict = _call_with_retry(_attempt, no_retry=no_retry)
    return _demote_low_confidence(verdict, confidence_threshold)


def interpret_audit(
    client: JudgmentClient,
    context: AuditInterpretationContext,
    *,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    no_retry: bool = False,
) -> list[AuditVerdict]:
    """Moment 0 LLM judgment for a commit-derived audit.

    Iterates over ``context.in_scope_docs`` and makes ONE LLM call per
    doc. Each call yields one :class:`AuditVerdict`. Per-doc retry
    exhaustion is captured as a synthetic ``JUDGMENT_REQUIRED`` verdict
    (``confidence=0.0``, ``rationale="LLM retry exhausted"``) so other
    docs remain evaluable.

    Args:
        client: shared :class:`JudgmentClient` instance.
        context: audit input package (E2).
        model: Anthropic model identifier (the actual model is set on
            the ``JudgmentClient``; this parameter is exposed for
            future overrides and for the CLI surface).
        timeout: per-attempt timeout in seconds.
        confidence_threshold: gate for PROPOSED_EDIT / NO_CHANGE_NEEDED
            demotion (default 0.80).
        no_retry: skip the retry policy (testing only).

    Returns:
        List of :class:`AuditVerdict`, one per ``context.in_scope_docs``,
        in the same order. Length always equals ``len(in_scope_docs)``.
    """
    del model, timeout  # The shared JudgmentClient owns these.

    verdicts: list[AuditVerdict] = []
    for doc in context.in_scope_docs:
        try:
            verdict = _interpret_one_doc(
                client,
                doc,
                context,
                confidence_threshold=confidence_threshold,
                no_retry=no_retry,
            )
        except DriftInterpretationError as exc:
            logger.warning(
                "audit_interpretation: doc %s exhausted retries (%s); "
                "emitting synthetic JUDGMENT_REQUIRED",
                doc.path,
                exc,
            )
            verdict = AuditVerdict(
                doc_path=doc.path,
                verdict="JUDGMENT_REQUIRED",
                confidence=0.0,
                rationale="LLM retry exhausted",
                question=(
                    f"Automated audit interpretation could not evaluate "
                    f"{doc.path!r} after {exc.attempts} attempts "
                    f"({exc}). Please review this doc against commit "
                    f"{context.commit_sha} manually."
                ),
            )
        verdicts.append(verdict)
    return verdicts


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


class _ArgparseError(Exception):
    """Raised by :class:`_StructuredArgumentParser` so ``main()`` returns exit 3."""


class _StructuredArgumentParser(argparse.ArgumentParser):
    """Argparse subclass that raises instead of ``sys.exit(2)`` on bad flags.

    ``--help`` still exits 0 (argparse's help path uses ``parser.exit``,
    not ``error()``).
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _StructuredArgumentParser(
        prog="audit_interpretation",
        description=(
            "Moment 0 commit-audit LLM judgment. Reads an "
            "AuditInterpretationContext JSON document from --input-file "
            "or stdin and writes a JSON array of AuditVerdict objects "
            "to --output-file or stdout."
        ),
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        default=None,
        help="Path to a JSON AuditInterpretationContext (default: stdin).",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=None,
        help="Path to write the AuditVerdict JSON array (default: stdout).",
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


def _parse_context_document(raw: str) -> AuditInterpretationContext:
    """Deserialize a CLI input JSON into an :class:`AuditInterpretationContext`.

    Raises:
        ValueError: on malformed JSON or schema mismatch (caller maps
            to exit 3).
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"input JSON parse failure: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"input must be a JSON object (got {type(data).__name__})"
        )

    required = ("audit_issue", "commit_sha", "diff", "in_scope_docs")
    for key in required:
        if key not in data:
            raise ValueError(f"input missing required field {key!r}")

    audit_issue_raw = data["audit_issue"]
    if isinstance(audit_issue_raw, bool) or not isinstance(audit_issue_raw, int):
        raise ValueError(
            f"input.audit_issue must be an int (got {type(audit_issue_raw).__name__})"
        )

    targets_raw = data["in_scope_docs"]
    if not isinstance(targets_raw, list) or not targets_raw:
        raise ValueError("input.in_scope_docs must be a non-empty list")

    targets: list[DocTarget] = []
    for idx, target in enumerate(targets_raw):
        if not isinstance(target, dict):
            raise ValueError(
                f"input.in_scope_docs[{idx}] must be an object"
            )
        for sub_key in ("path", "contents", "truncated", "truncation_strategy"):
            if sub_key not in target:
                raise ValueError(
                    f"input.in_scope_docs[{idx}] missing {sub_key!r}"
                )
        targets.append(
            DocTarget(
                path=str(target["path"]),
                contents=str(target["contents"]),
                truncated=bool(target["truncated"]),
                truncation_strategy=str(target["truncation_strategy"]),
            )
        )

    return AuditInterpretationContext(
        audit_issue=int(audit_issue_raw),
        commit_sha=str(data["commit_sha"]),
        diff=str(data["diff"]),
        in_scope_docs=targets,
    )


def _verdict_to_dict(verdict: AuditVerdict) -> dict[str, Any]:
    """Serialize an :class:`AuditVerdict` to a JSON-friendly dict.

    ``None`` shape-dependent fields are dropped so the output exactly
    matches the contract (no extra null keys).
    """
    out: dict[str, Any] = {
        "doc_path": verdict.doc_path,
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
    """Build a :class:`JudgmentClient` for CLI invocations.

    The CLI bypasses the on-disk ``config.toml`` and injects a minimal
    in-memory ``Config`` shape so callers can pass any
    ``api_key_path`` / ``model`` per invocation.
    """
    from doc_audit.config import (
        Config,
        GitHubConfig,
        LLMConfig,
        PathsConfig,
        SignalsConfig,
    )

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
        signals=SignalsConfig(sources=["gh_issue"]),
        github=GitHubConfig(
            repo="kentonium3/kg-automation",
            bot_identity="kg-felix-bot",
        ),
    )
    return JudgmentClient(cfg)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point.

    Exit codes::

        0 -- Success — verdicts written
        1 -- Operational error (API failure after retries, key file unreadable, ...)
        3 -- Invalid input JSON (schema violation in E2)
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _ArgparseError as exc:
        _emit_stderr_error(step="argparse", error=str(exc))
        return 3

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
        verdicts = interpret_audit(
            client,
            context,
            model=args.model,
            timeout=args.timeout,
            no_retry=args.no_retry,
        )
    except (FileNotFoundError, OSError) as exc:
        _emit_stderr_error(step="config", error=str(exc))
        return 1

    payload = [_verdict_to_dict(v) for v in verdicts]
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
    "interpret_audit",
    "AuditVerdict",
    "AuditInterpretationContext",
    "DocTarget",
    "DriftInterpretationError",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "DEFAULT_MAX_TOKENS",
    "RETRY_DELAYS_SECONDS",
    "PROMPT_PATH",
    "VALID_VERDICTS",
    "INPUT_TOKEN_GUARD_THRESHOLD",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
