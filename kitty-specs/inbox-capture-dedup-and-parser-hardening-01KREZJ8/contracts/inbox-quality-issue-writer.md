# Contract: Inbox Quality Issue Writer

**Surface**: file (or dedupe against) the batched "Inbox quality" GitHub issue at end-of-cron-run when one or more notes have parse failures.

**Helper**: `scripts/inbox/file_inbox_quality_issue.py <parse_failures_json>` (new).

## Identity

`gh` CLI runs under the `claude` user's identity → `kg-felix-bot`. Consistent with the doc-auditor pattern.

## Inputs

- `parse_failures_json` — a JSON string (or `@<file>` to read from disk) containing a list of `{path, reason}` objects. The agent collects this from prescan's output during the cron tick and passes it to the helper.

## Behavior

1. **Dedup check**:
   ```
   gh issue list --repo kentonium3/kg-automation \
     --search 'in:title "Inbox quality"' --state open \
     --json number,title --limit 50
   ```
   Post-filter for titles starting with `Inbox quality:` (gh search is fuzzy; replicates the credential-health-check pattern).
2. **If an existing open issue is found**:
   - Print its number to stdout.
   - Exit 0.
   - Do NOT create a new issue. Do NOT update the body of the existing issue (it stays as-filed until Kent closes it).
3. **If no existing open issue is found**:
   - Construct title: `Inbox quality: <N> notes with parse errors — <YYYY-MM-DD>` where `<N>` is `len(parse_failures)`.
   - Construct body (see template below).
   - File via `gh issue create --repo kentonium3/kg-automation --label area/content --assignee kentonium3 --title <title> --body <body>`.
   - Parse the new issue number from gh's stdout URL.
   - Print the new issue number to stdout.
   - Exit 0.
4. **On gh failure**: exit 1 with stderr message. Agent logs the failure in its turn output. Per the spec, parse failures are still recorded in the per-run activity log even if the batched issue creation fails — so visibility is not zero.

## Body template

```markdown
The `felix-admin-capture` agent encountered <N> notes whose frontmatter could not be parsed on <YYYY-MM-DD>. Routing for these notes is halted until Kent fixes the frontmatter; each note has been tagged with a `> [!error] felix-capture:` callout marker referencing this issue.

| Filename | Reason |
|---|---|
| `<filename>` | <reason> |
| `<filename>` | <reason> |
| ... | ... |

Per-run activity log: `/home/kgale/second-brain/agents/logs/inbox-processing-<YYYY-MM-DD>.md`

### What to do

For each note, open it in Obsidian and inspect the top-of-file. The agent has injected an error callout indicating which malformation it detected. Common fixes:

- **Leading whitespace before `---`**: delete blank lines / spaces / BOM before the opening `---`.
- **UTF-8 BOM**: re-save the file in UTF-8 without BOM.
- **Missing closing `---`**: add the closing fence.
- **Invalid YAML inside frontmatter**: fix the YAML syntax (mismatched quotes, unescaped colons, etc.).

After fixing, the next cron tick will re-classify the note, strip the callout marker, and route normally.

### How to close this issue

Once all listed notes are fixed (or moved out of `01-Inbox/`), close this issue manually. The agent will file a new one on the next cron tick if more parse failures appear.

*Filed by `felix-admin-capture` on office2. Filed via `kg-felix-bot`.*
```

## Failure modes

- `gh` not installed: exit 1; agent surfaces.
- `gh` auth broken: exit 1; agent surfaces. Kent's manifest health-check would also flag the underlying `kg-felix-bot-pat` issue.
- Body too long (>65K chars): truncate the table and add `... and <N> more` footer. Unlikely in practice (would require >1000 parse failures in one run).

## Test coverage

`tests/inbox/test_inbox_quality_issue_writer.py`:

- Dedup detection: stub `gh issue list` returning an existing issue → helper prints existing number, no `gh issue create` called
- New issue path: stub `gh issue list` empty → helper calls `gh issue create` with expected argv shape
- Title format: variable `<N>` and `<YYYY-MM-DD>` correctly substituted
- Body table: each `{path, reason}` produces a row
- Fuzzy-search post-filter: stub `gh issue list` returning a non-prefix-matching issue → helper still creates new (treats fuzzy match as miss)
- Failure paths: subprocess error → exit 1
