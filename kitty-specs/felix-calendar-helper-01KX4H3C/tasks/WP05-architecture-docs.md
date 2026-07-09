---
work_package_id: WP05
title: Architecture documentation sync
dependencies: []
requirement_refs:
- FR-011
tracker_refs: []
planning_base_branch: feat/felix-calendar-helper
merge_target_branch: feat/felix-calendar-helper
branch_strategy: Planning artifacts for this mission were generated on feat/felix-calendar-helper. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-calendar-helper unless the human explicitly redirects the landing branch.
subtasks:
- T017
- T018
- T019
- T020
agent: "claude:opus:reviewer-renata:reviewer"
history: []
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/data/
create_intent:
- docs/runbooks/calendar-helper-ops.md
execution_mode: code_change
mission_id: 01KX4H3C4CZ2W0DRSHZHSNAY53
mission_slug: felix-calendar-helper-01KX4H3C
owned_files:
- docs/design/architecture/data/credential-manifest.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/credentials-and-secrets.md
- docs/design/architecture/data-flows.md
- docs/design/architecture/service-inventory.md
- docs/INDEX.md
- docs/design/felix-capability-roadmap.md
- docs/runbooks/calendar-helper-ops.md
role: implementer
tags: []
shell_pid: "52570"
---

# WP05 — Architecture documentation sync

## ⚡ Do This First: Load Agent Profile

Load `/ad-hoc-profile-load curator-carla` (role: implementer) first.

## Branch Strategy
- **Planning/base**: `feat/felix-calendar-helper` · **Merge target**: `feat/felix-calendar-helper`. Independent of WP01–WP04.

## Objective

Keep the live architecture record faithful to the shipped change (DIR-014). The
calendar surface now flows **Felix helper → Google API directly**, using a new
**personal** Google OAuth credential and a dedicated on-demand helper (venv). Use
`docs/design/architecture/data/signal-to-doc-map.json` to confirm the doc targets
for `credential-added-or-modified` and `data-flow-added-or-modified`.

**Read first**: each JSON's existing schema + its markdown view, and
`tooling/scripts/validate_architecture_data.py` (a blocking Docs-CI gate — edits
must pass it). Verify actual field names before editing (architecture-docs-first).

## Subtasks

### T017 — `credential-manifest.json` (+ credentials-and-secrets.md)
- Add the personal Google OAuth credential: name, type (OAuth authorized-user),
  scope (`calendar.events`), storage (`~/.config/felix/google/personal/`, 0600),
  used_by (calendar helper / felix-admin-calendar), expiry/review policy (durable per RFC #681).
- Reflect it in the markdown view. Note this is separate from the legacy `gog` credential (which stays).

### T018 — `data-flows.json` (+ data-flows.md / .view.md)
- Update/replace the calendar flow: previously `capture → felix-admin-calendar → gog → Google Calendar`;
  now `capture → route_calendar_event(--create) → calendar_helper → Google Calendar API` and the
  conversational `felix-admin-calendar → calendar_helper → Google` path. Mark the inbox→calendar hop as inline (no agent delegation).

### T019 — `service-inventory.json` (+ service-inventory.md)
- Record the external **Google Calendar API** dependency and the **calendar helper** as an on-demand
  invocation (no long-running service) running under the dedicated venv `/data/services/openclaw/felix-calendar/venv`.
- Reflect the felix-admin-calendar skill change (gog removed) if the inventory tracks agent skills.

### T020 — Navigation + roadmap + ops runbook
- `docs/INDEX.md`: add the new runbook + any new data surfaces.
- `docs/design/felix-capability-roadmap.md`: update status for #681 (calendar phase delivered), #699 (this mission), #679 (closed).
- New `docs/runbooks/calendar-helper-ops.md`: how to invoke the helper, per-account creds, re-mint on scope/auth failure, venv location, self-check, troubleshooting (exit codes).

## Definition of Done
- [ ] All three JSONs updated and pass `python tooling/scripts/validate_architecture_data.py`.
- [ ] Markdown views reflect the JSON changes; INDEX + roadmap updated; ops runbook created.
- [ ] Docs-CI green.

## Risks / reviewer guidance
- The architecture-data validator is blocking — verify schema/enum fields before committing.
- Do not remove the legacy gog credential/flow entirely (gog retains other surfaces; #572 residual open).
- Keep machine-readable JSON authoritative; markdown is the narrative view.

## Activity Log

- 2026-07-09T23:25:46Z – claude:opus:curator-carla:implementer – shell_pid=45865 – Assigned agent via action command
- 2026-07-09T23:38:14Z – claude:opus:curator-carla:implementer – shell_pid=45865 – Ready for review — arch data (credential-manifest/data-flows/service-inventory JSON) + narrative views + INDEX + roadmap + new calendar-helper-ops runbook updated; validate_architecture_data.py --strict, validate_docs.py, validate_privacy_boundary.py all pass. NOTE: also touched docs/DEVELOPER_PORTAL.md (single auto-generated runbook-filter line, forced by Docs-CI + build_runbook_filter.py) which is outside WP05 owned_files; and two out-of-scope .view.md files (service-dependencies.view.md, data-flows.view.md) have stale calendar->gog edges — flagged for follow-up.
- 2026-07-09T23:42:55Z – claude:opus:reviewer-renata:reviewer – shell_pid=52570 – Started review via action command
