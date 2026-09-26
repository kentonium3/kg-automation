# Contract: grading view, admin report and seal (FR-014, NFR-006)

- Produced only from a complete ledger (72 cells, zero `not_implemented`).
- **Blinded id per scored cell**: `q<Q>-<6 hex>` from `Random(f"{seed}:{question}:{arm}:{repeat}")`;
  the id encodes neither arm nor repeat; entries are ordered by id within a question.
- **View** (`views/`): per question `question_text`, `ask_time`, and per blinded id
  `{ "text", "truncated" }` — every `ok` cell, up to nine. Nothing else.
- **Admin report** (`admin/`): the non-scored cells with arm/question/repeat/token counts, for the
  run's reader; never merged into the view (a classification under a stable label would identify D).
- **Seal** (`seals/`): `{blinded_id: {arm, question, repeat}}`, the seed, the header hash.
- Forbidden in the view: the values `G`/`D`/`R` as arm identifiers, any repeat index, timing,
  token count, plan record, seed, outcome classification or ledger path. A test greps the produced
  view for every forbidden key and value and asserts the entry count equals the ledger's `ok` count.
- The three outputs live in three separate directories; the exporter never writes two into one.
