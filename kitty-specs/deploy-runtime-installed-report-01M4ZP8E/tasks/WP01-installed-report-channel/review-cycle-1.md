---
affected_files: []
cycle_number: 1
mission_slug: deploy-runtime-installed-report-01M4ZP8E
reproduction_command:
reviewed_at: '2026-10-15T12:13:47Z'
reviewer_agent: reviewer-renata
wp_id: WP01
---

# WP01 review cycle 1: REQUEST-CHANGES (reviewer-renata, claude-sonnet-5-5, 2026-10-15)

1. **HIGH:** `read_report` can raise. A deeply nested JSON line (~500k `[`, under MAX_BYTES) makes `json.loads` raise `RecursionError`, which the `except ValueError` does not catch. Fix: a broad except around the parse loop → `_reject`. Add a test.
2. **MED:** a NUL byte in `source` or `dest` is accepted, and the mapper may then raise. Fix: reject `\x00` in the reader.
3. **LOW:** `splitlines()` also splits on `\x0b`, `\x0c`, `\x1c`–`\x1e`, `\x85`, ` ` and ` `. Use `split("\n")` and strip a trailing `\r`.
4. **LOW:** duplicates are not counted against MAX_ENTRIES. That is correct, but pin it in a test or the contract.
5. **LOW:** the producer's path-based open (already hardened in the lane: O_NONBLOCK, O_NOFOLLOW, regular-file check).
