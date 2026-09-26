# WP08 review — cycle 7 (lane-h @c8f58515): REJECT

Reviewer: Codex gpt-6-astra (OpenAI), read-only, 2026-09-26. Implementer: Claude Opus 5.5. 235 tests passed. Mutation testing confirmed that the c6-regression test fails when the derivation is reverted to the flag.

## [MAJOR] Header inspection is not conservative on unreadable ledger paths
With `gguf_sha256="skipped"` and `--skip-gates`, two inputs raise an uncaught exception from `_is_development_ledger` / `peek_header` (run_849_harness.py ~L816) instead of the actionable ConfigUnavailable refusal:
- a ledger file containing `b'\xff\n'` raises UnicodeDecodeError;
- a ledger path that is a directory raises IsADirectoryError.

Result: a traceback, where the rider requires exit 1 with nothing written.

## Required fix
Guard the header inspection against OSError and UnicodeError (and the parse errors already caught). Any unreadable path counts as NOT a development ledger (False), so require_verified_gguf refuses with its actionable message. Add CLI regression tests for both inputs, asserting exit 1, the actionable message, no traceback, and no gate-*.json.
