# Quickstart: working with doc statuses and ADR decision logs

**Mission**: adr-first-class-statuses-01M2TVSP · **Phase**: 1

## I need to record that something about an approved ADR changed

Append a row to that ADR's **Decision log** — the one in the ADR the change is *about*.

```markdown
| Date | Type | By | Summary | Refs |
|---|---|---|---|---|
| 2026-08-29 | erratum | Kent | The `RunSSH: false` justification is backwards in direction; the conclusion stands. | ADR-0004 ACL changes log, #931 |
```

Do not edit the body. Do not change `status` — an erratum leaves standing untouched.

## I need to record that an ADR was replaced

Two edits, both in the replaced ADR: set frontmatter `status: superseded`, and append a
`superseded-by` row naming the successor. The successor is where the new decision actually lives.

## I need to add a new status value

Edit **only** `docs/design/standards/allowed-values.json`, then regenerate:

```bash
python3 tooling/scripts/generate_doc_standards.py
```

Never hand-edit `frontmatter.schema.json` or the generated region of `doc-standards.md` — they are
build output. CI fails if they are stale.

## I'm writing a new ADR

`doc_type: decision`, `status: proposed` (or `draft`), no `Status:` line in the body, and an empty
decision log section at the bottom:

```markdown
## Decision log

*No entries.*
```

## How do I know if an ADR is safe to act on?

Read its frontmatter `status`. That is the authoritative answer — you do not need to read the log to
learn it. Read the log to learn *why* it is in that state, or what has been corrected since approval.
