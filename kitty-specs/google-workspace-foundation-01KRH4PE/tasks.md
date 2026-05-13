# Tasks: Google Workspace foundation

**Mission**: `google-workspace-foundation-01KRH4PE`
**Source**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [quickstart.md](quickstart.md)
**Source issue**: [#100](https://github.com/kentonium3/kg-automation/issues/100) Phase 2

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Add `docs/runbooks/google-workspace-ops.md` (full setup procedure + pitfalls + commands + future-account expansion + troubleshooting) | WP01 |  |
| T002 | Update `docs/design/architecture/service-inventory.md` + `data/service-inventory.json` with `google-workspace` entry | WP01 | [P with T001] |
| T003 | Update `docs/design/architecture/credentials-and-secrets.md` + `data/credential-manifest.json` (new creds + deprecate legacy) | WP01 | [P with T001] |
| T004 | Update `docs/design/architecture/identity-model.md` with Google Workspace accounts section | WP01 | [P with T001] |
| T005 | Move `scripts/google/authorize-calendar.py` to `docs/archive/scripts/authorize-calendar.py` via `git mv` with one-line deprecation header | WP01 |  |
| T006 | Update `docs/INDEX.md` (runbook + archive registration) and `data/doc-domain-map.json` (route runbook to area/ea; bump timestamps) | WP01 |  |
| T007 | Run `python3 tooling/scripts/validate_docs.py` — confirm OK | WP01 |  |

## Work Package WP01 — Google Workspace foundation docs and architecture state

**Goal**: Deliver the runbook + architecture-state artifacts that complete #100's foundation. Pure docs/architecture work; no new code; no agent prompt changes.

**Priority**: P1 (per #100 priority).

**Independent test (WP01 review scope)**: All 7 doc/state artifacts land per spec; `validate_docs.py` reports OK; legacy script is archived; INDEX and doc-domain-map registrations match the new state.

**Included subtasks (review scope — T001–T007)**:

- [ ] T001 Add `docs/runbooks/google-workspace-ops.md` (WP01)
- [ ] T002 Update service-inventory (WP01) [P with T001]
- [ ] T003 Update credentials-and-secrets + credential-manifest (WP01) [P with T001]
- [ ] T004 Update identity-model (WP01) [P with T001]
- [ ] T005 Archive legacy authorize-calendar.py (WP01)
- [ ] T006 Update INDEX.md + doc-domain-map.json (WP01)
- [ ] T007 Validate docs (WP01)

**Post-merge operator verification (out of WP01 review scope)**:

- SC-002 / SC-003 regression smoke tests: `openclaw skills info gog`, `gog auth list`, `gog calendar colors`, `gog gmail search`, `gog drive search`, `gog contacts list` (already verified live 2026-05-13; re-run as a post-merge regression guard per quickstart.md §4).

**Why the split**: Same scoping discipline as prior missions in the inbox/doc-auditor chain. Verification requires running against deployed code on `main`, which can't happen from an unmerged lane branch.

**Implementation sketch**:

1. T001 is the largest single deliverable. ~400 lines of runbook. Copy structure from plan.md §"Phase 1 Design → runbook structure". The three pitfalls section is load-bearing (NFR-002). [P with T002/T003/T004] because architecture-doc updates are independent files.
2. T002 + T003 + T004 are mechanical architecture-state updates per the plan's design section. Each touches a known-format file.
3. T005 uses `git mv` to relocate the legacy script. Add a one-line header comment marking deprecation date + replacement reference.
4. T006 captures the structural changes: runbook registration in INDEX.md, runbook entry in doc-domain-map's `area/ea` array, archive-script registration in INDEX.md if INDEX.md tracks archive contents.
5. T007 runs validate_docs.py. Failure stops the WP.

**Parallel opportunities**: T001 / T002 / T003 / T004 are independent files. T005, T006, T007 are sequential.

**Dependencies**: Builds on ADR-0001 (committed `a0a7660`). No inter-WP dependencies.

**Risks (review-scope)**:
- **Runbook completeness**: missing one of the three pitfalls = future operator re-derives the diagnosis. Reviewer must verify all three (Calendar MCP trap, headless keyring, per-user brew PATH) are present with symptom + cause + fix.
- **JSON schema drift**: service-inventory.json and credential-manifest.json have specific shapes. Reviewer should `jq empty <file>` to confirm validity after edits and confirm new entries match the field set of existing entries.
- **Deprecated-marker placement**: legacy `google-calendar-*` entries must NOT be deleted from credential-manifest.json — only marked deprecated. Reviewer should confirm presence + `status: deprecated`.
- **Archive move ergonomics**: `git mv` preserves history; a plain delete + new file does not. Reviewer should confirm `git log --follow docs/archive/scripts/authorize-calendar.py` shows the prior history.

**Estimated prompt size**: ~450 lines.

## MVP Scope

WP01 is the entire mission. No phase split necessary.

## Next Steps

After WP01 merges, the post-merge operator runs the verification recipe in quickstart.md §4. Issues #100 and #120 close on merge.
