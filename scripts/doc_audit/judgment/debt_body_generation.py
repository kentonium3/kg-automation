"""Docs-debt body generation judgment moment.

Per spec FR-002 / SKILL.md §8 / contract Moment 2.

Contract: ``kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/judgment-prompts.contract.md``
Prompt: ``scripts/doc_audit/prompts/debt_body_generation.prompt.md``

Returns structured markdown (NOT JSON) with all six SKILL.md §8 H2
sections. The driver feeds the body straight into ``gh issue create``.

Schema validation
-----------------
The LLM may omit one or more H2 sections. The contract says:

> On missing section: log error, file the debt issue ANYWAY with a
> stub for the missing section + a note that the LLM output was
> incomplete.

This module therefore returns a ``DebtBodyResult`` that exposes both
the (possibly stubbed) body markdown AND the list of section names
that were stubbed. The driver writes the body and surfaces the
stubbed-sections list in the activity log as a follow-up flag.

The originating audit number, when provided, MUST appear as a
``Refs #<N>`` link in the Cross-references section. If the LLM
omits it the helper inserts it before returning.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from doc_audit.judgment.client import JudgmentClient, JudgmentResponse


logger = logging.getLogger(__name__)


PROMPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "debt_body_generation.prompt.md"
)


_REQUIRED_SECTIONS = (
    "Artifact",
    "Gap description",
    "Area",
    "Cross-references",
    "Draft outline",
    "Success criteria",
)


_STUB_PLACEHOLDER = (
    "_LLM output was incomplete — section auto-stubbed by the driver. "
    "Replace this placeholder with the actual content before closing "
    "the issue._"
)


@dataclass(frozen=True)
class DebtBodyResult:
    """Result of one ``debt_body_generation`` call.

    ``body`` is always a complete six-section markdown body (with
    stubs inserted for any missing sections). ``stubbed_sections``
    lists the H2 headers that the LLM omitted; the driver surfaces
    this list in the activity log.
    """

    body: str
    stubbed_sections: list[str]


def generate(
    client: JudgmentClient,
    *,
    artifact_path: str,
    gap_description: str,
    evidence_source: str,
    area_labels: list[str],
    originating_audit_number: int,
    cross_references: list[str],
) -> tuple[DebtBodyResult, JudgmentResponse]:
    """Generate the body markdown for a docs-debt GitHub issue.

    Returns ``(result, response)``. The driver:
    - writes ``result.body`` via ``gh issue create``,
    - records ``result.stubbed_sections`` in the activity log if
      non-empty,
    - rolls token usage from ``response`` into the tick totals.
    """

    variable_section = _render_inputs(
        artifact_path=artifact_path,
        gap_description=gap_description,
        evidence_source=evidence_source,
        area_labels=area_labels,
        originating_audit_number=originating_audit_number,
        cross_references=cross_references,
    )

    response = client.call(PROMPT_PATH, variable_section)
    result = _parse_and_validate(
        response.content,
        artifact_path=artifact_path,
        originating_audit_number=originating_audit_number,
    )
    return result, response


# ---------------------------------------------------------------------------
# Input rendering
# ---------------------------------------------------------------------------


def _render_inputs(
    *,
    artifact_path: str,
    gap_description: str,
    evidence_source: str,
    area_labels: list[str],
    originating_audit_number: int,
    cross_references: list[str],
) -> str:
    return (
        "## Artifact path\n"
        f"{artifact_path}\n"
        "\n"
        "## Gap description (2-4 sentences)\n"
        f"{gap_description}\n"
        "\n"
        "## Evidence source\n"
        f"{evidence_source}\n"
        "\n"
        "## Area labels (apply to ## Area section)\n"
        f"{area_labels}\n"
        "\n"
        "## Originating audit number (use in Cross-references)\n"
        f"{originating_audit_number}\n"
        "\n"
        "## Additional cross-references (beyond the audit)\n"
        f"{cross_references}\n"
        "\n"
        "---\n"
        "\n"
        "Produce the issue body in markdown. Include all 6 H2 sections.\n"
    )


# ---------------------------------------------------------------------------
# Parsing + schema validation
# ---------------------------------------------------------------------------


def _parse_and_validate(
    content: str,
    *,
    artifact_path: str,
    originating_audit_number: int,
) -> DebtBodyResult:
    """Validate the LLM markdown response.

    - Confirm every required H2 section is present.
    - Stub any missing section with ``_STUB_PLACEHOLDER``.
    - Ensure the Cross-references section contains ``Refs #<N>``
      for the originating audit.
    """

    sections = _split_sections(content)
    stubbed: list[str] = []

    for name in _REQUIRED_SECTIONS:
        if name not in sections or not sections[name].strip():
            logger.warning(
                "debt_body_generation missing section %r for %s; stubbing",
                name,
                artifact_path,
            )
            sections[name] = _STUB_PLACEHOLDER
            stubbed.append(name)

    # Defense-in-depth: ensure the originating audit ref appears.
    # Use a word-boundary regex so e.g. "#3200" does NOT satisfy the
    # presence check for "#320" — a plain substring test would skip
    # the required Refs backlink whenever the LLM mentions any longer
    # issue number that happens to start with the audit's digits.
    refs_section = sections.get("Cross-references", "")
    audit_ref = f"#{originating_audit_number}"
    audit_ref_pattern = rf"#{re.escape(str(originating_audit_number))}\b"
    if not re.search(audit_ref_pattern, refs_section):
        logger.info(
            "debt_body_generation injecting missing Refs %s in Cross-references",
            audit_ref,
        )
        prefix = f"- Refs {audit_ref} (originating audit)\n"
        sections["Cross-references"] = prefix + refs_section.lstrip("\n")

    body = _reassemble(sections)
    return DebtBodyResult(body=body, stubbed_sections=stubbed)


_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _split_sections(content: str) -> dict[str, str]:
    """Split markdown into a dict keyed by H2 header text.

    Robust to leading/trailing whitespace and prose before the first
    H2 (any such prose is discarded — the boilerplate forbids it but
    we defend against it).
    """

    sections: dict[str, str] = {}
    matches = list(_H2_RE.finditer(content))
    if not matches:
        return sections

    for idx, match in enumerate(matches):
        name = match.group(1).strip()
        body_start = match.end()
        body_end = (
            matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        )
        sections[name] = content[body_start:body_end].strip("\n")

    return sections


def _reassemble(sections: dict[str, str]) -> str:
    """Reassemble the markdown body in canonical section order."""

    parts: list[str] = []
    for name in _REQUIRED_SECTIONS:
        body = sections.get(name, "").rstrip()
        parts.append(f"## {name}\n{body}\n")
    return "\n".join(parts).rstrip() + "\n"


__all__ = ["generate", "DebtBodyResult", "PROMPT_PATH"]
