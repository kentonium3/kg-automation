# Contracts — author-capture-workspace-01KWPXBB

**No API/event contracts.** This is a prompt-authoring refactor mission: it relocates
content between OpenClaw agent workspace files (SOUL/USER/TOOLS/AGENTS) with zero behavior
change. There is no request/response surface, no schema, and no externally visible event to
contract. The verifiable contract for this mission is the #587 shared-invariant validator
(`scripts/openclaw/agents/validate_workspace.py`) plus the content-conservation checks in
`../quickstart.md`. This directory exists to satisfy the software-dev mission path convention.
