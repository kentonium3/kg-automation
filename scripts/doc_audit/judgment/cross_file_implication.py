"""Cross-file implication judgment moment.

Per spec FR-002 / SKILL.md §4.2 #5 / contract Moment 3.

Contract: ``kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/judgment-prompts.contract.md``
Prompt: ``scripts/doc_audit/prompts/cross_file_implication.prompt.md``

Detects implied drift in non-touched in-scope docs. The LLM receives
only the *paths* of in-scope files (not their contents) and reasons
from the triggering event + diff excerpt + per-baseline priors.

Schema validation (safe default ``[]``)
---------------------------------------
The contract says: "If no implications are detected: ``implications: []``.
The driver consumes the implications list to file debt issues for any
non-empty entries (with ``suggested_action == judgment`` always —
these are not auto-edits)."

On any of the following the module returns ``[]``:
- Response is not valid JSON.
- ``implications`` field missing or not a list.
- Individual entry malformed (missing required field, wrong type) —
  that entry is dropped; valid entries are still returned.

Per contract Moment 3, ``untouched_file`` MUST be an in-scope, untouched
path. Entries whose ``untouched_file`` is outside ``in_scope_files``
(when an in-scope list is provided) are dropped — the LLM hallucinated
a target outside the audit surface and we must not trust it. Entries
whose ``untouched_file`` is in ``touched_files`` are also dropped (not
actually "untouched").
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from doc_audit.judgment.client import JudgmentClient, JudgmentResponse


logger = logging.getLogger(__name__)


PROMPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "cross_file_implication.prompt.md"
)


_REQUIRED_KEYS = {
    "untouched_file",
    "implication",
    "evidence",
    "suggested_action",
}


def detect(
    client: JudgmentClient,
    *,
    triggering_event_kind: str,
    triggering_event_summary: str,
    diff_excerpt: str,
    touched_files: list[str],
    in_scope_files: list[str],
    domain_labels: list[str],
) -> tuple[list[dict], JudgmentResponse]:
    """Detect implied drift on non-touched in-scope files.

    Returns ``(implications, response)``. ``implications`` is a list
    of validated dicts; each dict has the four required keys from the
    contract. Empty list means no implications detected (safe default).
    """

    variable_section = _render_inputs(
        triggering_event_kind=triggering_event_kind,
        triggering_event_summary=triggering_event_summary,
        diff_excerpt=diff_excerpt,
        touched_files=touched_files,
        in_scope_files=in_scope_files,
        domain_labels=domain_labels,
    )

    response = client.call(PROMPT_PATH, variable_section)
    implications = _parse_response(
        response.content,
        touched_files=touched_files,
        in_scope_files=in_scope_files,
    )
    return implications, response


# ---------------------------------------------------------------------------
# Input rendering
# ---------------------------------------------------------------------------


def _render_inputs(
    *,
    triggering_event_kind: str,
    triggering_event_summary: str,
    diff_excerpt: str,
    touched_files: list[str],
    in_scope_files: list[str],
    domain_labels: list[str],
) -> str:
    return (
        "## Triggering event\n"
        f"- kind: {triggering_event_kind}\n"
        f"- summary: {triggering_event_summary}\n"
        "\n"
        "## Diff excerpt (up to 300 lines of relevant diff)\n"
        f"{diff_excerpt}\n"
        "\n"
        "## Files touched by the triggering event\n"
        f"{touched_files}\n"
        "\n"
        "## In-scope files (paths only — no contents)\n"
        f"{in_scope_files}\n"
        "\n"
        "## Domain labels\n"
        f"{domain_labels}\n"
        "\n"
        "---\n"
        "\n"
        "Return the JSON. Empty list if no implications.\n"
    )


# ---------------------------------------------------------------------------
# Response parsing + schema validation
# ---------------------------------------------------------------------------


def _parse_response(
    content: str,
    *,
    touched_files: list[str],
    in_scope_files: list[str],
) -> list[dict]:
    """Validate the LLM JSON response. Safe default ``[]`` on any error."""

    text = content.strip()
    if not text:
        logger.warning("cross_file_implication empty response; returning []")
        return []

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "cross_file_implication non-JSON response: %s; returning []",
            exc,
        )
        return []

    if not isinstance(parsed, dict):
        logger.warning(
            "cross_file_implication JSON not an object: %r; returning []",
            parsed,
        )
        return []

    implications = parsed.get("implications")
    if not isinstance(implications, list):
        logger.warning(
            "cross_file_implication implications missing or not a list; returning []",
        )
        return []

    touched_set = set(touched_files)
    in_scope_set = set(in_scope_files)
    valid: list[dict] = []

    for entry in implications:
        if not isinstance(entry, dict):
            logger.warning(
                "cross_file_implication entry not an object: %r; dropping",
                entry,
            )
            continue

        missing = _REQUIRED_KEYS - set(entry.keys())
        if missing:
            logger.warning(
                "cross_file_implication entry missing keys %s: %r; dropping",
                sorted(missing),
                entry,
            )
            continue

        # Type checks on string fields.
        if not all(
            isinstance(entry[k], str) and entry[k].strip()
            for k in _REQUIRED_KEYS
        ):
            logger.warning(
                "cross_file_implication entry has non-string field: %r; dropping",
                entry,
            )
            continue

        # Defense-in-depth: drop entries that target a touched file
        # (the contract says ``untouched_file`` must NOT appear in
        # ``touched_files``; the LLM should have excluded these but we
        # enforce here too).
        if entry["untouched_file"] in touched_set:
            logger.warning(
                "cross_file_implication entry targets touched file %r; dropping",
                entry["untouched_file"],
            )
            continue

        # Strict scope check (per contract Moment 3): ``untouched_file``
        # MUST be in the in-scope list. Out-of-scope targets are LLM
        # hallucinations and are dropped — we never file debt for docs
        # outside the scoped audit surface.
        if (
            in_scope_set
            and entry["untouched_file"] not in in_scope_set
        ):
            logger.warning(
                "cross_file_implication entry targets out-of-scope file %r; dropping",
                entry["untouched_file"],
            )
            continue

        # Defense-in-depth: force suggested_action to "judgment" per
        # the contract — these are NEVER auto-edits.
        normalized = dict(entry)
        normalized["suggested_action"] = "judgment"
        valid.append(normalized)

    return valid


__all__ = ["detect", "PROMPT_PATH"]
