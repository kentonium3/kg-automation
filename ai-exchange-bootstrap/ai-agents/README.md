# AI-to-AI Exchange (GitHub-mediated)

This folder standardizes how **ChatGPT** and **Claude** collaborate via GitHub.

## Principles
- **Pull before you write.** Agents must `git pull --rebase` before modifying anything.
- **Attribute authorship.** Use commits clearly authored by the agent (name/email configured per agent).
- **Single-source handoffs.** All cross-AI requests & responses are JSON files under `ai-agents/shared/handoffs/` following the schema below.
- **Small, reviewable PRs.** Prefer small deltas and descriptive commit messages.
- **Locks, not long-lived branches.** Use a short-lived `.lock` file if exclusive access is needed.

## Layout
```
ai-agents/
  claude/      # Claude’s working notes, artifacts, logs
  chatgpt/     # ChatGPT’s working notes, artifacts, logs
  shared/
    handoffs/  # JSON requests/responses both AIs watch
    contracts/ # JSON Schemas for validation
    templates/ # Example request/response
```

## Handoff filename convention
`YYYYMMDD-HHMMSS-<handoff-id>-<from>-to-<to>-<type>.json`
- type = `request` or `response`
- example: `20251012-123501-0001-chatgpt-to-claude-request.json`

## Commit message convention
- `handoff: request <id> <from>→<to> – <purpose>`
- `handoff: response <id> <status> – <summary>`

## Minimal flow
1. **Request** created in `shared/handoffs/…request.json`.
2. The **target agent** pulls, processes, then writes a **response** `…response.json` with `status` = `success|needs_changes|blocked` and optional PR links.
3. If changes are required, continue the thread using the same `handoff_id`.
