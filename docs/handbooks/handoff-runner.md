---
id: HB-HANDOFF-RUNNER
title: Handoff Runner — GitHub Action Executor
doc_type: handbook
level: reference
status: approved
owners: [kent@intentional.biz]
last_validated: 2025-10-14
revision: 1.0
---

This GitHub Action processes `ai-agents/shared/handoffs/*-request.json` files and writes a corresponding response JSON. It lets handoffs run **without** relying on chat connectors or local shells.

## Triggers
- Push to any branch that touches `ai-agents/shared/handoffs/*.json`
- Manual: *Run workflow* (workflow_dispatch)
- Scheduled: every 30 minutes

## What it does
1. Checks out the branch where the request was pushed.
2. Validates the JSON (if the contract schema exists).
3. If the request contains `inputs.file_edits` with exact `path` and `content`, the runner writes those files and commits.
4. Otherwise, it writes a **plan-only** response summarizing next actions (no LLM keys required).

## Response location
For a request named `…-request.json`, the runner writes `…-github-runner-response.json` in the same folder.

## Optional LLM integration
Add `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` as repository **Actions secrets** if you want future steps to generate content. The current runner does not call LLMs; it only performs deterministic edits.

## Contract
- Request schema path (optional): `ai-agents/shared/contracts/ai-handoff.schema.json`
- Response fields: `type, handoff_id, from_agent, to_agent, status, branch, request_ref, outputs, notes`

## Limitations (v1)
- No cross-repo operations.
- No external APIs.
- Only performs file edits when explicit content is provided; otherwise records a plan.

## Local testing
```bash
python tooling/scripts/handoff_runner.py
```
If changes are written, the script will modify files under the current working copy (use a throwaway branch).