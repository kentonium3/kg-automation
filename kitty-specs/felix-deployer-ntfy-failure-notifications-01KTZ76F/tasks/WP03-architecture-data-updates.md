---
work_package_id: WP03
title: Architecture data updates — data-flow, service-inventory, credential
dependencies:
- WP02
requirement_refs:
- FR-011
tracker_refs:
- kentonium3/kg-automation#595
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T010
- T011
- T012
- T013
- T014
agent: "claude"
history: []
agent_profile: implementer-ivan
authoritative_surface: docs/design/
execution_mode: code_change
mission_slug: felix-deployer-ntfy-failure-notifications-01KTZ76F
owned_files:
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/credential-manifest.json
- docs/design/architecture/data-flows.md
- docs/design/architecture/data-flows.view.md
- docs/design/architecture/service-inventory.md
- docs/design/architecture/credentials-and-secrets.md
- docs/design/felix-capability-roadmap.md
role: implementer
tags: []
shell_pid: "89767"
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` before reading anything else.

## Objective

Update the canonical machine-readable architecture data files (JSON) and their narrative markdown counterparts to reflect the new substrate. felix-deployer gains:
- An outbound HTTPS POST data flow to ntfy.sh.
- A new env-file dependency at `/home/claude/.config/felix-deployer/env`.
- A new env credential `FELIX_DEPLOYER_NTFY_TOPIC`.
- A capability-roadmap row entry noting the substrate swap.

Per `CLAUDE.md`: "Machine-readable files (JSON) are the authoritative record for all operational data. Narrative markdown documents provide context and rationale. When machine-readable and narrative conflict, the machine-readable version wins." JSON edits drive markdown edits, not the reverse.

## Context

This mission ships a new outbound flow (felix-deployer → ntfy.sh) and a new env credential. The CLAUDE.md "standing requirement" says: "Any implementation that deploys, modifies, or removes a service, credential, port, or data flow MUST update the relevant files in `docs/design/architecture/data/` and their markdown counterparts as part of the same PR."

The signal-to-doc-map (`docs/design/architecture/data/signal-to-doc-map.json`) provides the exact list of docs each change class touches. The relevant mission change classes (from `data-model.md`):
- `data-flow-added-or-modified` → data-flows.json + data-flows.md + data-flows.view.md
- `service-added-or-modified` → service-inventory.json + service-inventory.md + service-dependencies.view.md (note: optional, only if topology changes) + felix-capability-roadmap.md
- `credential-added-or-modified` → credential-manifest.json + credentials-and-secrets.md + identity-model.md (note: identity-model only if credential affects identity surface — for felix-deployer-ntfy-topic, the answer is NO since it's a publish-only secret, not an authentication credential)

## Branch Strategy

- planning_base_branch: `main`
- merge_target_branch: `main`
- Execution worktree per computed lane. WP03 is third in the WP01→WP02→WP03 serial sequence; its lane base will include WP01 + WP02 changes.

## Subtask guidance

### T010 — Update `docs/design/architecture/data/data-flows.json`

Read the existing file first. Identify the canonical entry shape (likely an array of objects under a top-level key like `data_flows` or `entries`). Use a sibling existing felix-deployer-touching entry as your shape template — DO NOT invent fields.

Add a new entry (field names confirmed against the live schema; this is the intent):

```json
{
  "id": "felix-deployer-ntfy-egress",
  "source": "felix-deployer",
  "source_host": "office2",
  "destination": "ntfy.sh",
  "destination_host": "ntfy.sh (public)",
  "protocol": "HTTPS POST",
  "port": 443,
  "trigger": "queued deploy manifest fails apply",
  "data_classification": "operational alert; private topic; no PII",
  "trust_boundary_crossing": true,
  "best_effort": true,
  "added_in": "kentonium3/kg-automation#595",
  "notes": "Failure-notification substrate chosen for independence from openclaw/WhatsApp. Wire-shape contract: kitty-specs/felix-deployer-ntfy-failure-notifications-01KTZ76F/contracts/ntfy-notification-v1.md."
}
```

Critical: validate against the schema (`<file>.schema.json` sibling if present, or `tooling/scripts/validate_docs.py` if it covers this JSON). The exact field names depend on the live schema — confirm by reading a sibling entry first.

If the existing `dm-payload-v1`-related entry (from the parent mission) is present and references the now-retired openclaw cron dispatch path, mark it `superseded_by: "felix-deployer-ntfy-egress"` and add a `deprecated: true` field if the schema supports it. If the schema doesn't support it, leave the entry as-is and only ADD the new ntfy-egress entry; old entries remain as historical record per the project's data-archive practice.

### T011 — Update `docs/design/architecture/data/service-inventory.json`

Find the `felix-deployer` entry. Update:

- `outbound_dependencies` (or the schema's equivalent field name): add `ntfy.sh:443/tcp` (or the schema's outbound-dep shape — read a sibling first).
- `environment_files` (or equivalent): add `/home/claude/.config/felix-deployer/env`. If the schema uses `systemd_environment_files` or `service_env_files`, use the canonical field name.

Keep the rest of the felix-deployer entry intact. Do NOT touch other services' entries.

### T012 — Update `docs/design/architecture/data/credential-manifest.json`

Add a new entry for `FELIX_DEPLOYER_NTFY_TOPIC`. Shape (confirm against schema by reading a sibling entry):

```json
{
  "id": "felix-deployer-ntfy-topic",
  "name": "FELIX_DEPLOYER_NTFY_TOPIC",
  "kind": "private-topic-identifier",
  "category": "publish-only-secret",
  "storage_location": "systemd EnvironmentFile on office2: /home/claude/.config/felix-deployer/env",
  "in_repo": false,
  "rotation_policy": "manual, on suspicion of leak only — knowledge enables passive listening, not impersonation",
  "owner": "claude",
  "mode": "0640",
  "used_by": ["felix-deployer"],
  "added_in": "kentonium3/kg-automation#595"
}
```

Adjust field names to match the live schema's vocabulary. If a `category` enum exists and `publish-only-secret` isn't a value, pick the closest. The intent is: this is a low-rotation, read-passively-only credential; treating it as a high-rotation database password would be miscategorization.

### T013 — Update narrative markdown counterparts

Update each file with a narrative section that mirrors the JSON entry. Keep edits minimal — each file already has many entries; add ONE block per concern, near related existing content.

- `docs/design/architecture/data-flows.md`: a new flow entry (or row in an existing table) for felix-deployer → ntfy.sh. Include trigger ("deploy manifest fails apply") and reference the contract file.
- `docs/design/architecture/data-flows.view.md`: if this file contains a Mermaid diagram, add a new edge `felix-deployer --> ntfy.sh` with edge label `failure alert (best-effort)`. Update node count in any preamble that mentions "N flows".
- `docs/design/architecture/service-inventory.md`: in felix-deployer's row/section, add `EnvironmentFile=/home/claude/.config/felix-deployer/env` to the env-file list, and `ntfy.sh:443/tcp` to the outbound deps.
- `docs/design/architecture/credentials-and-secrets.md`: add `FELIX_DEPLOYER_NTFY_TOPIC` to the credentials list with the rotation-policy note ("manual, on suspicion of leak only").

If any of these files have schemas of their own (some are generated from JSON via tooling/scripts/), the generated file may be regenerated rather than hand-edited — check for a generator script before hand-editing. If a generator exists, run the generator and commit the regenerated output.

Frontmatter for any file you edit must remain valid (run `python tooling/scripts/validate_docs.py` after edits).

### T014 — Update `docs/design/felix-capability-roadmap.md`

Find the section/table row for the `pull-based-deploy-pipeline` capability (or `felix-deployer` capability). Update the status/notes to reflect:
- Substrate: ntfy.sh (was: WhatsApp DM via openclaw cron)
- Status delta: failure-notification path operational after #595 merges

Keep it tight (1-3 lines of change). The roadmap is for strategic visibility; this entry is a substrate detail, so it doesn't deserve a new section.

## Test strategy

- `python tooling/scripts/validate_docs.py` — passes on the touched markdown files.
- `python -c "import json; json.load(open('docs/design/architecture/data/data-flows.json'))"` — JSON parses.
- Same for service-inventory.json and credential-manifest.json.
- If schemas exist in `docs/design/architecture/data/*.schema.json`, validate each JSON against its schema:
  ```python
  from jsonschema import Draft202012Validator
  import json
  for name in ["data-flows", "service-inventory", "credential-manifest"]:
      data = json.load(open(f"docs/design/architecture/data/{name}.json"))
      schema = json.load(open(f"docs/design/architecture/data/{name}.schema.json"))
      Draft202012Validator(schema).validate(data)
  ```
- `make test` — no regressions (this WP touches no code).

## Definition of Done

- 3 JSON files contain the new entries with shapes consistent with sibling entries; each validates against its schema if one exists.
- 4 narrative markdown files reflect the new flow / env-file / credential.
- `felix-capability-roadmap.md` row updated for felix-deployer substrate.
- All touched markdown passes `validate_docs.py`.
- Frontmatter on all touched markdown remains valid.
- No file outside `owned_files` is modified.

## Risks

- **Schema field-name drift**: the field names in the JSON above are intent-statements, not literal copy-paste. Read each file's existing entries first and mirror the actual shape. Memory `feedback_wp_prompts_grep_codebase` applies: grep the actual schema/data before writing literal field names into the diff.
- **Generated narrative markdown**: some `.md` files under `docs/design/architecture/` are generated from JSON via `tooling/scripts/` (search for `# Generated` markers). Do not hand-edit a generated file; run the generator and commit the output.
- **Mermaid view files**: `data-flows.view.md` may have node-count assertions in its preamble or a "generated by N entries" line. Update the count if present.
- **identity-model.md**: per the data-model section, identity-model is NOT touched in this WP because the ntfy topic is a publish-only secret, not an authentication credential. If during review someone disagrees, the additive edit is small (one section pointing out that the topic is NOT an authentication mechanism).

## Reviewer guidance

- Confirm field-name fidelity to existing entries (grep for a sibling outbound flow's exact field shape and compare).
- Confirm JSON parses cleanly: `python -c "import json; json.load(open('<path>'))"`.
- Confirm the new entries' `id` fields are unique within their respective files (no collision with existing IDs).
- Confirm `validate_docs.py` passes on the touched markdown.
- Confirm `felix-capability-roadmap.md`'s edit is minimal and in the right section.
- Confirm `identity-model.md` is NOT touched (the credential is publish-only).

## Activity Log

- 2026-06-13T01:55:16Z – claude – shell_pid=86996 – Assigned agent via action command
- 2026-06-13T02:04:23Z – claude – shell_pid=86996 – Ready for review. T010-T014 done. 3 JSON files parse cleanly + carry new entries with sibling-consistent shapes. 4 markdown files updated with narrative + Mermaid view edits. felix-capability-roadmap.md untouched (no existing pull-based-deploy-pipeline row to update; doc-debt left for follow-up). identity-model.md untouched per prompt (publish-only secret). validate_docs OK; make test 3525 passed; no regressions.
- 2026-06-13T02:04:30Z – claude – shell_pid=89767 – Started review via action command
