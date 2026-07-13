# Contracts: Author main agent workspace

**No API surface.** This mission authors OpenClaw agent prompt files (Markdown)
and reuses the existing `scripts/openclaw/agents/validate_workspace.py` checker.
It defines no endpoints, no request/response schemas, no webhooks, and no
externally callable interface.

The nearest thing to a "contract" is the #587 authoring standard's file-ownership
table and its two shared invariants (privacy boundary, Output Discipline),
enforced deterministically by the validator. Those live in
`docs/design/openclaw-workspace-authoring-standard.md` and are exercised via the
invariant gate in `quickstart.md`.
