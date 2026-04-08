---
id: agent-handbook
title: Agent Handbook — Pre-PR Checklist
doc_type: runbook
level: reference
status: superseded
owners: [kent@intentional.biz]
last_validated: 2025-11-01
last_updated: '2025-10-29'
revision: v1.0
audience: humans
---

> **SUPERSEDED**: This handbook describes the multi-platform workflow
> (Mac + Windows + GitHub Actions runner + handoff JSON files) which
> was retired in April 2026. The content is retained as historical
> record only. For current workflow, see `docs/runbooks/repo-governance.md`.

# Agent Handbook — Pre-PR Checklist

Use this checklist before opening or updating any PR. It mirrors the enforced Docs CI and repo governance.

## 1) Sync and scope
- **Do:** fetch and ensure your task branch is up-to-date with its base.
- **Why:** avoids merge conflicts and failing “require up-to-date” checks.
- See: [Repo governance](<../governance/repo-governance.md>)

## 2) Validate docs & handoffs locally
- **Do:**
  ```bash
  python tooling/scripts/validate_docs.py
  ```
- **Why:** enforces front-matter, schema checks, handoff JSON filename/structure, and a basic secret scan.
- See: [CI handbook](<./ci-handbook.md>)

## 3) (Re)generate registries
- **Do:**
  ```bash
  python tooling/scripts/build_registries.py
  ```
- **Why:** keeps `systems/_registry.yaml`, `workflows/registry.yaml`, and `runbooks/registry.yaml` in sync. Generated files must not be hand-edited.

## 4) Render doc graph
- **Do:**
  ```bash
  python tooling/scripts/render_docgraph.py
  ```
- **Why:** maintains `.docgraph/*` artifacts consumed by tooling and other agents.

## 5) Ensure no hand-edits to generated artifacts
- **Do:** review the validator output; CI forbids edits to generated files.
- **Why:** generated outputs must come from their generators.

## 6) Handoff JSON contract
- **Do:** place request/response JSONs in `ai-agents/shared/handoffs/` using this pattern:
  `YYYYMMDD-HHMMSS-<id>-<from>-to-<to>-(request|response).json`
- **Why:** standardized names let agents and CI find them.
- See: `ai-agents/shared/contracts/ai-handoff.schema.json`

## 7) Commit message convention
- **Do:** prefixes like `docs:`, `ci:`, `feat:`, `fix:`, `chore:`, `handoff:`.
- **Why:** keeps history scannable and automatable.

## 8) Link hygiene
- **Do:** use relative links that resolve within the repo; avoid dead links.
- **Why:** CI runs a lightweight relative link check.

## 9) Bootstrap & execution context
- **Do:** on Windows/macOS, resolve Dropbox paths using resolver scripts; in containers use GitHub-only operations (API/PR files) instead of host paths.
- See: [ECI Path Resolution](<./eci-path-resolution.md>) and `ai-agents/ai-context-bootstrap.md`

---

### Quick commands (local dev)
```bash
python tooling/scripts/validate_docs.py
python tooling/scripts/build_registries.py
python tooling/scripts/render_docgraph.py
```

### References
- Repo governance: `../governance/repo-governance.md`
- CI handbook: `./ci-handbook.md`
- ECI path resolution: `./eci-path-resolution.md`
- Bootstrap: `../../ai-agents/ai-context-bootstrap.md`
