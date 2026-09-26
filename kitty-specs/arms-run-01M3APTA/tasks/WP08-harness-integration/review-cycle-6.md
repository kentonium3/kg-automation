---
affected_files: []
cycle_number: 6
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-26T00:14:20Z'
reviewer_agent: claude
wp_id: WP08
---

REOPEN for cycle 6 (fix cycle on an approved WP; the approve @089f3f2d stands) — ONE design-lead rider (bus 20260926T001046518503Zf8dbf4b55a):
[MINOR] scripts/research/run_849_harness.py (load_setup_record) — keep the stricter rule that gguf_sha256 must be a VERIFIED 64-hex, BUT a "skipped" GGUF verification is permitted ONLY when the ledger being opened/created binds SKIP_GATES_SHA (the same principle as a skipped session_gates: a scored ledger requires verified provenance; a development ledger is already refused as a primary and by export). The refusal message must be actionable: name the field (gguf_sha256), say the verification was skipped, and say to re-run `substrate setup` with verification. Tests: skipped GGUF + real ledger → ConfigUnavailable with the actionable message, exit 1; skipped GGUF + --skip-gates → proceeds; verified GGUF → proceeds on both.
