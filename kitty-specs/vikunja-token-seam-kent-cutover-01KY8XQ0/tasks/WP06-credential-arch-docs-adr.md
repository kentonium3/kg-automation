---
work_package_id: WP06
title: Credential + architecture docs + ADR-0007
dependencies:
- WP01
requirement_refs:
- FR-006
tracker_refs: []
planning_base_branch: feat/vikunja-token-seam-kent-cutover
merge_target_branch: feat/vikunja-token-seam-kent-cutover
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-token-seam-kent-cutover. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-token-seam-kent-cutover unless the human explicitly redirects the landing branch.
subtasks:
- T014
- T015
- T016
phase: Phase 2 - Docs
history: []
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/
create_intent:
- docs/design/architecture/adr/0007-retire-vikunja-felix-bot.md
execution_mode: code_change
owned_files:
- docs/design/architecture/adr/0007-retire-vikunja-felix-bot.md
- docs/design/architecture/adr/0002-felix-vikunja-task-model.md
- docs/design/architecture/adr/README.md
- docs/design/architecture/data/credential-manifest.json
- docs/design/architecture/credentials-and-secrets.md
- docs/design/architecture/identity-model.md
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data-flows.md
- docs/design/architecture/data/data-flows.json
- docs/INDEX.md
- docs/DEVELOPER_PORTAL.md
role: implementer
tags: []
agent: "claude"
shell_pid: "72212"
shell_pid_created_at: "1784864197.958657"
---

# Work Package Prompt: WP06 — Credential + architecture docs + ADR-0007

## ⚡ Do This First: Load Agent Profile
Load your assigned agent profile (`agent_profile` frontmatter) via `/ad-hoc-profile-load` before anything else.

## Branch Strategy
- Planning/base + merge target: `feat/vikunja-token-seam-kent-cutover`. `/spec-kitty.implement` sets the worktree base.

## Objective
Record the dropped-attribution decision and reconcile the machine-readable + narrative architecture docs
to the **single kent-token runtime identity**. JSON files are the authoritative record; keep the narrative
markdown consistent with them (per repo doc standards). Do NOT deprovision felix-bot — it stays a dormant
Vikunja user (attribution history preserved).

## Subtasks

### T014 — ADR-0007 + index
- Author `docs/design/architecture/adr/0007-retire-vikunja-felix-bot.md` (follow the existing ADR format;
  Status: Accepted; Date 2026-07-23). Decision: retire the Vikunja felix-bot user + `vikunja-api` token
  from the runtime path; consolidate all Felix→Vikunja on the kent token (`vikunja-api-kent`). Context:
  per-user object scoping (#715/#717) made agent-vs-human attribution expensive and caused incomplete reads
  (#860). Consequences: runtime attributes to kent; felix-bot Vikunja user dormant; GitHub `kg-felix-bot`
  unaffected (out of scope). Supersedes ADR-0002's attribution rationale.
- Mark `adr/0002-felix-vikunja-task-model.md` **Superseded by ADR-0007** (add the status line; keep the
  historical body).
- Add ADR-0007 to `adr/README.md`, `docs/INDEX.md`, and `docs/DEVELOPER_PORTAL.md` (if it lists ADRs).

### T015 — Credential manifest (authoritative record)
- In `docs/design/architecture/data/credential-manifest.json`: mark the `vikunja-api` (felix-bot) credential
  **retired / dormant (non-runtime)** — not deleted; note the dormant felix-bot user + retained file. Update
  its consumers to drop runtime consumers (keep dormant/admin refs). Make `vikunja-api-kent` (kent) the
  **sole runtime** Vikunja credential and expand its consumer list to the runtime Felix→Vikunja paths.
- Ensure the architecture-data validator passes (`validate_architecture_data.py`).

### T016 — Narrative reconciliation
- `credentials-and-secrets.md`, `identity-model.md`, `service-inventory.md` + `data/service-inventory.json`,
  `data-flows.md` + `data/data-flows.json`: replace the two-token / felix-bot-runtime narrative with the
  single kent-token model. Keep JSON authoritative and markdown consistent with it.

## Definition of Done
- ADR-0007 authored + Accepted; ADR-0002 marked superseded; indices updated.
- credential-manifest marks felix-bot dormant/non-runtime, kent sole runtime; arch-data validator green.
- Credential/identity/service/data-flow docs reflect the single-token model; JSON ↔ markdown consistent.

## Reviewer guidance
- Verify JSON files are authoritative and markdown agrees (no contradiction).
- Verify felix-bot is marked **dormant, not deleted**, and Inbox(14)/user deprovision is explicitly out of scope.
- Verify the arch-data validator passes.

## Activity Log

- 2026-07-24T03:38:24Z – claude – shell_pid=72212 – Assigned agent via action command
