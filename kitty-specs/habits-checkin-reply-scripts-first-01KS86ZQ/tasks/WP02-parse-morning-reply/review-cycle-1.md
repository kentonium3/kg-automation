**Issue 1**: Reply-by-name parsing does not handle the required multi-word/title-token cases.

The parser currently tokenizes identifiers one word at a time (`scripts/habits/parse_morning_reply.py:228`) and then resolves each word independently (`scripts/habits/parse_morning_reply.py:537`). That means documented/spec examples do not produce deterministic tuples:

- `meditation done, skipped morning shoulder PT` against the 2026-05-22 fixture emits zero tuples, one `unparseable_reply` for `meditation`, and three separate ambiguity records for `morning`, `shoulder`, and `PT`.
- `skipped Morning shoulder PT` emits ambiguity records instead of resolving the exact title `Morning shoulder PT`.
- `Wake at 5:00 AM done` is split into `Wake`, `at`, `5`, `00`, `AM`, which produces duplicate tuples, an invalid position error, and ambiguity.

This violates FR-004 / SC-006-style reply-by-name behavior in the mission spec and the WP test requirement for exact title and substring matching. Fix by preserving phrase identifier candidates within a clause, or otherwise attempting longest deterministic phrase matches against morning-list titles before falling back to individual token ambiguity. Add tests for at least:

- `meditation done` against a list containing `Meditate` resolves uniquely.
- `skipped Morning shoulder PT` resolves to the exact title with state `skipped`.
- `meditation done, skipped morning shoulder PT` produces the two expected tuples with no errors or judgment items.

Keep the existing SC-002 behavior (`Skipped 3,7,8 done`) intact.

**Issue 2**: The current tests do not cover the required reply-by-name acceptance shape.

`tests/habits/test_parse_morning_reply.py:352` uses `Meditate done`, which exercises only a single-word exact-title case. The WP requested `meditation done` against `Meditate` as the unique substring case, and the spec gives `meditation done, skipped morning shoulder PT` as the representative reply-by-name scenario. Add the missing tests above so this cannot regress.

Downstream note: WP03 and WP04 depend on WP02; they should rebase after the parser fix lands.
