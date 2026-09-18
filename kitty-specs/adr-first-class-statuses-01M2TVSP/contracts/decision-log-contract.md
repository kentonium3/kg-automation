# Contract: ADR decision log

## Placement

Last section of the ADR, heading `## Decision log`. **Required in every ADR**; empty reads
`*No entries.*`.

## Shape

```markdown
## Decision log

| Date | Type | By | Summary | Refs |
|---|---|---|---|---|
| YYYY-MM-DD | <type> | <who> | <one line> | <adr/issue/commit> |
```

## `Type` vocabulary (the only machine-read column)

| Type | Meaning | Status effect |
|---|---|---|
| `erratum` | a stated reason is wrong; the conclusion stands | none |
| `amendment` | a detail changed; the decision stands | none |
| `superseded-by` | this decision has been replaced | pairs with `status: superseded` |
| `context` | a referenced fact changed | none |

## Rules

1. **An entry lives in the ADR it is about.** Cross-referencing another ADR is fine; filing the entry
   *there instead* is the defect this contract exists to prevent (FR-002).
2. **Append-only.** Never edit or delete an existing row.
3. **No authority.** An entry records that a decision was made elsewhere. It can never change what the
   ADR decides (C-003). An entry that would change what someone should *do* is a new ADR instead.
4. **Never contradicts the frozen body** (C-002).
5. `superseded-by` and `status: superseded` are set together; neither is meaningful alone.

## Optional blockquote preamble (added 2026-09-18, found by WP06)

A `## Decision log` section may open with a **blockquote note** before the table:

```markdown
## Decision log

> **Note.** Why this log exists, or anything a reader needs before the rows.

| Date | Type | By | Summary | Refs |
|---|---|---|---|---|
```

Only blockquotes, only *before* the table. Arbitrary prose is still rejected, and so is anything
after the table — trailing content would make the table's end ambiguous.

This was found by WP06's end-to-end check once the lanes merged: ADR-0004's canonical log needs a
note explaining the legacy/canonical split, and "table and nothing else" forbade it. Moving that one
note would have been the smaller fix, but every future author wanting to annotate a log hits the
same wall. A `>` line can never be confused with a `|` row, so the allowance costs no ambiguity.

## Escaping (narrowed 2026-09-18, review cycle 3)

A literal `|` inside any cell **must be escaped as `\|`** — including inside a code span. Only `\|`
is an escape; `\a` stays two characters.

This narrows the grammar deliberately rather than widening the parser. Three review rounds on a
hand-rolled Markdown tokenizer kept finding edge cases (multi-backtick spans, unmatched backticks,
escape-anything normalising `err\atum` into a valid Type), and this validator gates **every commit in
the repo** — a false positive there blocks all work. Since we author and generate this format, the
cheaper and safer fix is a stricter, unambiguous grammar. The cost is explicit: an unescaped pipe is
reported as a column-count error the author can see, never a silent misparse.

## Validation

Enforceable: section presence, table shape, `Type` in vocabulary, ISO date, `superseded-by` ⇔
`status: superseded` consistency.

Not enforceable, and deliberately left to authors: whether an entry *should* have been a new ADR. Rule
3 is doctrine, not a check — the ADR README must state it plainly.
