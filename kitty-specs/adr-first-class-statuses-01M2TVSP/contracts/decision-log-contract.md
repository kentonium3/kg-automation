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

## Validation

Enforceable: section presence, table shape, `Type` in vocabulary, ISO date, `superseded-by` ⇔
`status: superseded` consistency.

Not enforceable, and deliberately left to authors: whether an entry *should* have been a new ADR. Rule
3 is doctrine, not a check — the ADR README must state it plainly.
