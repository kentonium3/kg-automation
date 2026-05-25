"""Private helpers for parsing raw LLM responses in the doc-audit judgment pipeline.

Imported by sibling modules under ``scripts/doc_audit/judgment/``; not part of
the package's public API (single-underscore prefix).

Per WP01 of mission ``audit-judgment-fence-strip-hardening-01KSESPD``, this
module centralizes the fence-stripping helper that previously lived inline in
``drift_interpretation.py`` (mission #55). WP02 will re-point three additional
judgment scripts (``audit_interpretation``, ``cross_file_implication``,
``tier_classification``) at this canonical helper, preventing future divergence
between the four parse paths.
"""

from __future__ import annotations


def _strip_code_fence(text: str) -> str:
    """Strip markdown code fences from an LLM response.

    Returns the input unchanged if no fence is present. Otherwise drops the
    opening fence line (e.g. ``` ```json ``` or just ``` ``` ```) and the
    trailing fence line, then re-strips whitespace.

    Observed Haiku 4.5 behavior: every JSON response is wrapped in
    ``` ```json ... ``` ``` despite the prompt explicitly instructing the
    model to emit no code fences. See diagnostic doc
    ``docs/diagnostics/drift-interpretation-payload-shape.md``.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.splitlines()
    # Drop opening fence (e.g., ```json or just ```).
    # The ``lines`` non-empty and ``lines[0]`` starts-with-``\`\`\``` checks
    # are structurally guaranteed by the earlier early-return at line 30, so
    # the False branch is unreachable. ``# pragma: no branch`` documents that
    # the defensive form is preserved verbatim from drift_interpretation.py:436-458
    # but cannot be exercised by tests.
    if lines and lines[0].startswith("```"):  # pragma: no branch
        lines = lines[1:]
    # Drop trailing fence
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
