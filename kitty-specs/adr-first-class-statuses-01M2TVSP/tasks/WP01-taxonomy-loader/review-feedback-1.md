# WP01 review feedback #1 — REQUEST CHANGES

**Reviewer**: Codex (read-only sandbox, no profile, advisory) · **Verdict recorded by**: orchestrator
**Diff reviewed**: `807cf318` · **Date**: 2026-09-18

Nine findings. Seven accepted, one downgraded with evidence, one folded into the others. The accepted
set is real: two of them let malformed input load successfully, which is precisely what "fail-closed"
was supposed to prevent.

## Accepted — must fix

**F2 (blocking) — duplicate JSON object keys silently last-value-wins.**
Verified: `json.loads('{"status":["a"],"status":["b"]}')` → `{'status': ['b']}`. Duplicate detection
covers duplicates *within* a vocabulary list but not duplicate *keys*. A file with two `status` keys
loads, and the one a human reads first is not the one enforced.
→ Use an `object_pairs_hook` that raises on repeated keys, at every nesting level.

**F4 (material) — `UnicodeDecodeError` escapes the promised API.**
Verified: it subclasses `ValueError`, not `OSError`, so the `except OSError` handler does not catch it
and the caller gets a raw decode error instead of `TaxonomyError`.
→ Catch `UnicodeError` and wrap with source context.

**F3 (material) — non-standard JSON constants.** `NaN` / `Infinity` / `-Infinity` are accepted by
Python's parser. → Reject via `parse_constant`.

**F5 (material) — non-canonical tokens.** `"draft "` is accepted and is a distinct value from
`"draft"`, so whitespace variants evade duplicate detection and produce a vocabulary entry no document
can ever match. → Reject any value that differs from its own `.strip()`.

**F6 (material) — the validated object is mutable.** Callers can clear `scoped_statuses` after
validation, bypassing every invariant. → Freeze the mapping.

**F7 (material) — the docstring over-promises.** It tells consumers never to parse the JSON directly,
but exposes only `status` and `doc_type`. WP03 also needs `level` and `audience`, so as written it
forces the next WP to either violate the rule or reopen this module. → Expose all vocabularies,
accommodating the mixed-type `level` values (`"1"` and `1` both appear).

**F9 (minor) — O(n²) duplicate detection** via `list.count()` per element. → One pass with a `seen` set.

**F8 (material) — test coverage follows.** Add a regression for each of the above, and assert errors
name the source file.

## Downgraded — already covered

**F1 (claimed blocking) — "missing or empty `status_by_doc_type` loads successfully, silently
reverting decisions to default statuses."**

The risk is real but the regression is **already caught**. `test_the_real_repo_taxonomy_loads`
asserts the exact decision tuple against the shipped file, so deleting or emptying the scope fails the
suite. Requiring the key *structurally* would be wrong: the loader validates **shape**, and which
doc_types carry overrides is **content policy**. Baking one taxonomy's content into a generic loader
would force an edit here every time the policy changes — the coupling this module exists to remove.

→ No structural change. The existing test is the guard; a comment will make that explicit so the next
reader does not re-derive this.

## Not a code finding

Codex noted its own run created an untracked `.spec-kitty/review-lock.json`, and that a Stop hook
inside its sandbox attempted to delete the parent run's autonomous-run sentinel
(`~/.claude/keep-going/ALL`). The read-only sandbox refused it. Neither is a defect in this WP; both
are captured in the run report.
