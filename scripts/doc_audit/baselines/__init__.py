"""Baseline measurement helpers for the doc-audit driver.

This sub-package contains the offline helper script
:mod:`scripts.doc_audit.baselines.measure_tokens` that consumes an
OpenClaw agent session JSONL and emits per-tick token counts in the
schema used by
``docs/design/architecture/baselines/felix-doc-auditor-pre-rework.json``.

The same helper is reused for the post-rework measurement in WP09 so
that pre- and post-rework numbers are computed by identical logic.
"""
