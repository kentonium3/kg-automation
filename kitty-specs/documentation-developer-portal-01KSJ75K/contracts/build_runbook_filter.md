# Contract: `tooling/scripts/build_runbook_filter.py`

**Mission**: documentation-developer-portal-01KSJ75K

This is a behavior contract for the helper script. It is the source of truth
for the script's CLI surface, exit codes, and validation rules. Tests must
exercise every row.

---

## CLI

```
python tooling/scripts/build_runbook_filter.py            # default = drift check
python tooling/scripts/build_runbook_filter.py --check-only   # explicit alias for default
python tooling/scripts/build_runbook_filter.py --write        # rewrite block in place
python tooling/scripts/build_runbook_filter.py --help         # standard help
```

No other flags. No positional arguments.

## Inputs

- Walks `docs/runbooks/**/*.md` from the repository root (resolved relative to the script's parents, same strategy as `tooling/scripts/validate_docs.py`).
- Reads YAML frontmatter from each file. Frontmatter parsing follows the same convention used by `validate_docs.py` (top-of-file `---` … `---` block).
- Files that have no frontmatter block at all are reported as warnings to stderr but do not appear in any filter bucket.

## Bucket assignment

| `audience:` value | Bucket header |
|---|---|
| `agents` | `Agent-executable` |
| `humans` | `Human-only` |
| `agents_and_humans` | `Dual-audience` |
| (missing) | `Unclassified` |
| (any other value) | error — script exits non-zero with file path |

The allowed-values set is fetched from the same source `validate_docs.py`
uses (either by importing `ALLOWED_VALUES['audience']` or by replicating the
literal set; implementation chooses, but the set must stay in sync).

## Output block format

Between markers `<!-- begin:runbook-filter (generated; do not edit) -->`
and `<!-- end:runbook-filter -->`, the script emits:

```markdown
<!-- begin:runbook-filter (generated; do not edit) -->

### Agent-executable
- [<title>](<relative-path>)
- ...

### Dual-audience
- [<title>](<relative-path>)
- ...

### Human-only
- [<title>](<relative-path>)
- ...

### Unclassified
- [<title>](<relative-path>) — missing `audience:` frontmatter
- ...

<!-- end:runbook-filter -->
```

Rules:

1. Bucket order is fixed: Agent-executable → Dual-audience → Human-only → Unclassified.
2. Within each bucket, entries are sorted alphabetically by `<title>` (case-insensitive).
3. `<title>` is taken from the file's frontmatter `title:` field; if missing, the script reports an error.
4. `<relative-path>` is computed relative to `docs/DEVELOPER_PORTAL.md` (i.e., `runbooks/…`).
5. An empty bucket is emitted as the header followed by a single `- _(none)_` line so absence is visible.
6. There is exactly one blank line between buckets.
7. Trailing newline before `<!-- end:runbook-filter -->`.

## Behavior modes

### Default mode (drift check)

1. Locate `docs/DEVELOPER_PORTAL.md`. If it does not exist, exit non-zero with message "portal not found".
2. Locate the marker pair. Exit non-zero if zero or more than one pair found.
3. Read the current block content between the markers.
4. Build the expected block from the runbook frontmatter.
5. If they are byte-identical (after normalizing line endings), exit 0 with no output.
6. If they differ, print a unified diff to stdout and exit 1. The last line of stdout is the literal string `run: python tooling/scripts/build_runbook_filter.py --write` (so contributors can copy-paste the fix command).

### `--write` mode

1. Same setup as default.
2. Replace the content between the markers with the expected block.
3. Write the file back.
4. Exit 0.
5. If the file would not change (already up-to-date), exit 0 with message `up to date`.

### Error cases (all exit non-zero)

| Case | Exit code | Message |
|---|---|---|
| Portal file missing | 2 | `error: docs/DEVELOPER_PORTAL.md not found` |
| Marker pair missing | 3 | `error: marker pair not found in portal` |
| Marker pair appears more than once | 3 | `error: duplicate marker pair in portal` |
| A runbook has `audience:` outside allowed enum | 4 | `error: invalid audience '<value>' in <path>` |
| A runbook is missing a `title:` field | 4 | `error: missing title in <path>` |
| Drift detected (default mode only) | 1 | unified diff + `run:` hint |

## Tests required

Tests live in `tests/tooling/test_build_runbook_filter.py` (creating the path if absent). Each row maps to one test:

- Happy path drift check (no drift) → exit 0, no output
- Drift check with one added runbook → exit 1, diff includes the new file
- `--write` regenerates a stale block to match a fresh one
- Bucket order is preserved when input order varies
- Alphabetization within bucket is case-insensitive
- Missing `audience:` field lands in Unclassified with the explanatory suffix
- Invalid `audience:` value triggers exit 4 with file path in message
- Missing `title:` field triggers exit 4 with file path in message
- Missing portal file triggers exit 2
- Missing marker pair triggers exit 3
- Duplicate marker pair triggers exit 3
- Empty bucket renders as `_(none)_`

Tests use temporary directories to materialize a synthetic `docs/runbooks/` tree; no test reads the live repository's runbooks.

## Integration with `tooling/scripts/validate_docs.py`

`validate_docs.py` calls into the helper either by importing it
(`from build_runbook_filter import check_drift` or similar) or by spawning
a subprocess and checking the exit code. Implementation chooses. The effect
must be: a fresh `python tooling/scripts/validate_docs.py` run fails with a
clear, actionable message when the portal block is stale.

The drift check is gated on the portal existing; if `docs/DEVELOPER_PORTAL.md` is absent (e.g., on branches before this mission lands), the check is a no-op and `validate_docs.py` behaves as before.

## Non-goals

- No "auto-fix" inside `validate_docs.py`. It only reports drift; the contributor runs `--write` themselves. (Auto-mutation inside a validator is a footgun.)
- No watch mode. The script runs once per invocation.
- No reporting on `docs/runbooks/**/*` files that aren't markdown (e.g., images). Non-`.md` files are skipped silently.
