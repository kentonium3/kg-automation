# WP08 review — cycle 6 (lane-h @4232f698): REJECT

Reviewer: Codex gpt-6-astra, read-only. 232 tests pass. Design lead delta read: APPROVE, conditional on the coupling below, which Codex then reproduced as a defect.

## [MAJOR] The development-ledger permission is keyed on the CLI flag, not the ledger's header binding

Reproduction, against the real code: resume a REAL (non-SKIP_GATES_SHA) ledger with `--skip-gates`, a setup record with `gguf_sha256="skipped"`, and no preflight.
- Observed: exit 3. `gate-container.json` is written, and a `session_gates` event is APPENDED to the real ledger.
- Required by the c6 rider: ConfigUnavailable, exit 1, with the actionable message, and NOTHING written.

`development_ledger=args.skip_gates and not (...)` (run_849_harness.py main, ~L1413) grants the skipped-GGUF exception from the flag. The flag and the header coincide only on a FRESH ledger. On a resume, the binding comparison does refuse, but only after the gate phase has already written.

## Required fix
1. Before `live_config`, derive `development_ledger` from the ledger. If none exists, a `--skip-gates` run creates a development ledger (True). If one exists, read its header, and the value is True only when it binds SKIP_GATES_SHA. `require_verified_gguf` then refuses before the preflight load, and before any gate or ledger write.
2. Regression tests. First, a real ledger resumed with `--skip-gates` and a skipped GGUF must give ConfigUnavailable, exit 1, and the actionable message. It must leave the ledger bytes unchanged and write no `gate-*.json`. Show this test failing on 4232f698. Second, a development ledger resumed with `--skip-gates` and a skipped GGUF must proceed.
3. `require_verified_gguf` docstring: the permission is keyed on the ledger header's binding. The flag decides only the fresh-ledger case. (Design lead's request, made deliberate so a later "simplification" can't remove it.)

Nothing else in the delta.
