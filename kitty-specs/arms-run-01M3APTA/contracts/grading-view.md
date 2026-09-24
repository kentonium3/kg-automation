# Contract: grading view and seal (FR-014, NFR-006)

- Produced only from a complete ledger (72 cells, zero `not_implemented`).
- Labels: for each question, a permutation of `["X","Y","Z"]` drawn from
  `random.Random(f"{blinding_seed}:{question}")`; mapping written to the Seal only.
- The view file contains, per question: `question`, `question_text`, `ask_time`, and per label
  `{ "text": ..., "truncated": bool }` or `{ "outcome": "exceeds_model_context"|"error" }`.
- Forbidden in the view: the strings `"G"`, `"D"`, `"R"` as arm identifiers, any timing, token
  count, plan record, seed, or ledger path. A test greps the produced view for every forbidden
  key and for the arm names as JSON values.
- The Seal lives under `build/849-runs/seals/`, the view under `build/849-runs/views/`; the
  harness never writes both into one directory.
