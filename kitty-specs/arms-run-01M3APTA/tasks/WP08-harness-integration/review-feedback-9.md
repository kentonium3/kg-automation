# WP08 review — cycle 8 (lane-h @e759d518): REJECT

Reviewer: Codex gpt-6-astra (OpenAI), read-only, 2026-09-26. Implementer: Claude Opus 5.5. 242 tests passed.

Codex confirmed:
- Both c7 inputs (undecodable bytes, a directory) now give the actionable ConfigUnavailable.
- A permission-denied file, a 10 MB malformed first line, and NUL bytes all classify False.
- A development header classifies True, and a real header False.
- Each gate field on its own triggers both the exporter's refusal and the primary's refusal.
- There is a single predicate, and the mtime assertion is present.

## [MAJOR] A symlink loop at --ledger is classified as absent, so it is treated as development
`_is_development_ledger` (run_849_harness.py ~L810) uses `path.exists()`, which follows symlinks. For a self-referential symlink it returns False, so the helper returns True (the "fresh ledger" case). With a skipped GGUF, the CLI goes past the ConfigUnavailable protection and later fails with LedgerWriteFailed.

## Required fix
"Absent" means there is no directory entry at all: test existence without following symlinks, i.e. lexists. Any entry at the path — a symlink loop, a dangling symlink, anything — goes to header inspection or is conservatively False. Wrap every filesystem inspection so that an OSError gives False. Add a symlink-loop regression and a dangling-symlink regression.

## Notes (non-blocking, post-merge list)
`open_existing()` (~L792) still raises UnicodeDecodeError on b'\xff\n' and IsADirectoryError on a directory. That is outside this rider.
