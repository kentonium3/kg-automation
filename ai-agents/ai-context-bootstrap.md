# AI Context Bootstrap — READ FIRST

> **Canonical guidance for all AIs (ChatGPT, Claude, Claude Code, Gemini, Copilot, etc.) working on _kg-automation_.**

## Operate GitHub-first
- **System of record:** GitHub `kentonium3/kg-automation`.
- **Read context** from Dropbox if available; **never edit** in Dropbox.
- **Edit/generate** only in Git branches or dev container.
- **Use Handoff Runner** for file creation/edits via JSON requests in `ai-agents/shared/handoffs/`.

## Start here (navigation)
- **Visual Docs Index:** `docs/README.md`
- **Diagrams:** `docs/diagrams/`
- **Handbooks:** `docs/handbooks/`

## Handoff Runner — quick start
1) Create a feature branch.
2) Add `*-chatgpt-to-handoff-runner-request.json` under `ai-agents/shared/handoffs/`.
3) Run **Actions → Handoff Runner** on that branch.
4) Open PR → Docs CI (`Docs CI / validate (pull_request)`) must pass → merge.

**Guards:** runner won’t run on `main`; it never edits `.github/workflows/**`.
