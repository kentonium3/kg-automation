"""Narrow LLM judgment surface for the habits check-in / reply pipeline.

Subpackage of ``scripts.habits``. Contains:

* ``disambiguate_reply`` -- single-turn Anthropic call that resolves an
  ambiguous reply token (``JudgmentItem`` emitted by
  ``scripts.habits.parse_morning_reply``) to either a confident
  ``chosen_task_id`` OR a ``clarify`` request with a suggested
  clarifying question.

The surface is intentionally tiny: the parser already did all the
deterministic work; the LLM is only invoked when the parser surfaces
a ``judgment_required`` cluster. See FR-006 and the cache-aware
prompt pattern lifted from ``scripts.doc_audit.judgment.client``.
"""
