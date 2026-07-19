# Contracts

No API surface. This mission authors OpenClaw agent workspace prompt files (markdown) — there are no endpoints, schemas, or externally callable contracts to define.

The behavioral "contracts" for this mission are:
- The #587 workspace authoring standard (`docs/design/openclaw-workspace-authoring-standard.md`) — the concern→file ownership rules.
- The `validate_workspace.py` invariant checks (privacy enforceable home; Output Discipline presence).
- The content move-table in `../data-model.md`.

This directory exists to satisfy the accept/merge gate's expectation of a `contracts/` folder (the #584 precedent).
