---
affected_files: []
cycle_number: 10
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-26T01:31:37Z'
reviewer_agent: claude
wp_id: WP08
---

# WP08 review — cycle 9 (lane-h @575e6109): REJECT

Reviewer: Codex gpt-6-astra (OpenAI), read-only, 2026-09-26. Implementer: Claude Opus 5.5. 244 tests passed. The symlink loop and the dangling symlink now refuse.

## [MAJOR] `os.path.lexists` swallows OSError and ValueError, so an unreadable path reads as absent
`_is_development_ledger` (run_849_harness.py ~L814) relies on lexists. lexists returns False on ANY OSError or ValueError, not only on a missing entry. So the helper returns True (the fresh case) for all of these:
- an existing real ledger under a mode-000 parent (EACCES);
- a path through a looping parent symlink (ELOOP);
- a path containing a NUL byte (ValueError).
Each of these gets the skipped-GGUF exception instead of the actionable refusal.

## Required fix
Call `path.lstat()` directly. Only FileNotFoundError counts as the fresh case. Any other OSError (EACCES, ELOOP, ENOTDIR, …) or ValueError gives False. Add regressions for a mode-000 parent, a looping parent symlink, and a NUL path.

(Watcher note: a MINOR line in the grep output was the c6 rider text quoted from a feedback file Codex read, not a finding of this cycle.)
