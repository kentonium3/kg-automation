VERDICT: APPROVE — Codex read-only review (gpt-6-astra, OpenAI), WP08 cycle 10 on lane-h @f8451d1a, 2026-09-26. Implementer: Claude Opus 5.5 (independent vendors). Design-lead delta reads: APPROVE through c8. c9 and c10 were reported on the bus at 20260926T012915224179Z6356b3d411 and 20260926T014036345362Z80f68c8869.

Codex: 248 tests passed. Line-by-line exception audit of `_is_development_ledger`: no error other than FileNotFoundError reaches the True return. EACCES, ELOOP, NUL and ENOTDIR give False. A missing file or missing parent gives True, which is the fresh case; creation then succeeds and writes no real ledger or gate files. CLI probes exit 1 with the actionable message, and write nothing.

One MINOR, carried to the post-merge list and not folded: a header with about 10,000 nested JSON arrays makes the helper raise RecursionError. The CLI still refuses cleanly (exit 1, nothing written). It goes with the open_existing() hardening item, so that one pass makes every ledger-reading entry point fail closed.

Cycle record since the c5 approval:
- c6: the GGUF rider was implemented, then REJECTED because the permission was keyed on the flag.
- c7: the permission was keyed on the header. REJECTED: undecodable bytes or a directory gave a traceback.
- c8: that was guarded, and both design-lead riders landed (a single `grading.binds_skip_gates`, and an mtime assertion). REJECTED: a symlink loop was classified as absent.
- c9: switched to lexists. REJECTED: lexists swallows EACCES, ELOOP and NUL.
- c10: switched to lstat, where only FileNotFoundError counts as fresh. APPROVE.
