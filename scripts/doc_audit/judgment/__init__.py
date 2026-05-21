"""Judgment surface for the felix-doc-auditor scripts-first driver.

Three LLM judgment moments per spec FR-002 / contract
``contracts/judgment-prompts.contract.md``:

- ``tier_classification`` — Tier A / Tier B / judgment per SKILL.md §4.
- ``debt_body_generation`` — issue body markdown per SKILL.md §8.
- ``cross_file_implication`` — implied drift on non-touched in-scope docs.

Each moment is **one** ``.prompt.md`` template (under
``scripts/doc_audit/prompts/``) plus **one** Python module here. The
shared ``client.JudgmentClient`` is the only Anthropic SDK entry point;
business rules (e.g., guardrail short-circuit) live in the moment
modules, NOT in the client.
"""
