---
affected_files: []
cycle_number: 1
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T01:10:04Z'
reviewer_agent: claude
wp_id: WP02
---

[MAJOR] scripts/research/arms849/substrate.py:187 — Missing GGUF checksum silently bypasses verification — `expected=None` makes the comparison conditional false while setup succeeds — require exactly one valid SHA256SUMS entry matching the complete filename.
[MAJOR] scripts/research/arms849/substrate.py:278 — Health accepts unverified serving configuration — mocked `/props={}` returns `llama_ok=True`, a `.gguf.wrong` filename passes substring matching, and any occurrence of “yarn” determines rope mode — require valid properties, exact model basename, expected context size, and explicit rope settings.
[MAJOR] scripts/research/arms849/substrate.py:312 — Teardown reports clean when GTT cannot be read — reproduced `gtt_used_gib=None` with `clean=True`, although SC-008 requires verification below 2 GiB — report verification failure when the measurement is unavailable.
[MAJOR] tests/research/test_arms849_isolation.py:23 — The AST scan misses constructed forbidden strings — runtime concatenation, interpolated f-strings, and escaped bytes evade the source check and string-constant collection — handle statically resolvable constructions and add negative fixtures for each bypass.
[MAJOR] tests/research/test_arms849_substrate.py:142 — The claimed widened-mount negative test never widens a mount — it only asserts the ordinary self-test passes; an extra host mount at `/leak` is not checked by SELF_TEST — inspect the allowed bind mounts and add the required failing extra-mount test.
[MINOR] scripts/research/arms849/substrate.py:345 — File exclusions also remove unrelated filename extensions — `startswith(p)` excludes `849-traceability.md.backup` despite its absence from the exclusion list — match file entries exactly and directory entries by slash-delimited prefix.

Source: Codex read-only review (gpt-6-astra), WP02 cycle 1, 2026-09-25 01:08Z. VERDICT: REJECT. All six accepted as genuine; fixing in lane-b.
