---
work_package_id: WP04
title: Architecture Doc Updates
dependencies: []
requirement_refs:
- FR-015
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-027-inbox-pre-scan-helper
base_commit: 5a37041139b391e371347fb2fbb373422072569e
created_at: '2026-04-11T18:25:57.954299+00:00'
subtasks:
- T018
- T019
- T020
shell_pid: "50006"
agent: "claude:opus-4-6:docs-implementer:implementer"
history:
- date: '2026-04-11'
  event: created
authoritative_surface: docs/design/architecture/
execution_mode: code_change
mission_slug: 027-inbox-pre-scan-helper
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
tags: []
---

# WP04: Architecture Doc Updates

## Objective

Update the architecture documentation to reflect the new pre-scan helper as a component of the `felix-admin-capture` service. JSON is authoritative; the markdown view follows. This satisfies the standing directive in `CLAUDE.md` that any feature touching deployed services must update `docs/design/architecture/` in the same PR.

## Context

Read these first:
- `CLAUDE.md` — "Architecture Documentation" and "Documentation Standards" sections
- `docs/design/architecture/change-control.md` — protocol for updates
- `docs/design/architecture/data/service-inventory.json` — the file you'll edit
- `docs/design/architecture/data/schemas/` (if present) — schema for service-inventory.json
- `docs/design/architecture/service-inventory.md` — the markdown view
- `kitty-specs/027-inbox-pre-scan-helper/spec.md` — FR-015, SC-009
- `kitty-specs/027-inbox-pre-scan-helper/plan.md` — Architecture Impact table

## Branch Strategy

- **Planning base**: main
- **Final merge target**: main
- **Execution worktree**: assigned by `spec-kitty agent action implement WP04 --agent <name>`.

This WP is independent and can run in parallel with WP01, WP02.

## Subtasks

### T018 — Update `service-inventory.json`

**Purpose**: Record the pre-scan helper as a component of the `felix-admin-capture` service in the authoritative JSON source.

**Steps**:
1. Open `docs/design/architecture/data/service-inventory.json`
2. Locate the `felix-admin-capture` service entry. It likely has a structure something like:
   ```json
   {
     "id": "felix-admin-capture",
     "type": "openclaw-agent",
     "host": "office2",
     "owner": "@kentonium3",
     ...
   }
   ```
3. Add a `components` array (or extend an existing one) to reference the helper:
   ```json
   "components": [
     {
       "id": "inbox-prescan-helper",
       "type": "script",
       "language": "python",
       "source": "scripts/inbox/prescan.py",
       "deploy_path": "/home/claude/kg-automation/scripts/inbox/prescan.py",
       "log_path": "/home/claude/second-brain/agents/logs/inbox-prescan-*.md",
       "dependencies": ["scripts/vault/paths.json"],
       "invoked_by": "felix-admin-capture step 1",
       "introduced_by": "027-inbox-pre-scan-helper"
     }
   ]
   ```
4. Update the service entry's `updated_by` field to `"027-inbox-pre-scan-helper"` and `updated_at` to today's date (UTC).
5. If the JSON has a schema version or top-level `updated_at`, bump those too.
6. **Validate schema**: if `docs/design/architecture/data/schemas/service-inventory.schema.json` exists, run any existing validation tool (e.g., `python tooling/scripts/validate_docs.py` or `jsonschema -i service-inventory.json schemas/...`). If the schema rejects the `components` extension, adjust the representation — for example, add the helper as a sibling service entry with `parent_service: "felix-admin-capture"` instead.
7. If no explicit schema exists, maintain consistency with the existing file's conventions (same indentation, same field naming style, same casing).

**Files**:
- `docs/design/architecture/data/service-inventory.json`

**Validation**:
- [ ] The `felix-admin-capture` entry references the helper
- [ ] `updated_by` is set to this mission slug
- [ ] JSON parses cleanly (`python3 -c "import json; json.load(open('...'))"`)
- [ ] Schema validation (if applicable) passes

### T019 — Update `service-inventory.md` markdown view

**Purpose**: Sync the markdown view with the JSON changes.

**Steps**:
1. Open `docs/design/architecture/service-inventory.md`
2. Locate the `felix-admin-capture` section
3. Rewrite it to describe the new pre-scan-then-act pattern. Something like:

```markdown
### felix-admin-capture

**Type**: OpenClaw agent (Haiku, `sessionTarget: isolated`)
**Host**: office2
**Trigger**: 4x/day via `openclaw cron` (`inbox-7am`, `inbox-noon`, `inbox-5pm`, `inbox-10pm`)
**Purpose**: Routes Obsidian inbox captures into Vikunja tasks, journal entries, vault writes, and other downstream destinations per Kent's routing rules.

**Components**:

- **inbox-prescan-helper** (Python script, `scripts/inbox/prescan.py`) — Introduced by mission 027 (issue #149). Deployed to `/home/claude/kg-automation/scripts/inbox/prescan.py` on office2. The agent's Step 1 runs this helper before any cognitive work. The helper:
  1. Resolves `{{VAULT_INBOX}}` and `{{VAULT_INBOX_PROCESSED}}` via the vault path registry (`scripts/vault/paths.json`)
  2. Lists files in the inbox with `status: unprocessed`
  3. Archives stale (>7 day) processed files to `{{VAULT_INBOX_PROCESSED}}`
  4. Returns a JSON result with unprocessed paths, archived entries, and warnings

  When the helper reports zero unprocessed files, the agent replies with the single token IDLE and takes no further action. This bounds empty-run cost to ≤500 tokens and eliminates agent-side inbox scanning.

  Helper logs to `/home/claude/second-brain/agents/logs/inbox-prescan-YYYY-MM-DD.md` (daily rotation, append-only).

**Dependencies**:

- Vault path registry: `scripts/vault/paths.json` (#150, #152)
- OpenClaw cron scheduler with `failureAlert` WhatsApp notifications
- Vault folders `01-Inbox` and `02-Inbox-Processed` (created by mission 026)

**Observability**:

- Agent processing log: `/home/claude/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`
- Pre-scan helper log: `/home/claude/second-brain/agents/logs/inbox-prescan-YYYY-MM-DD.md`
- OpenClaw run history: `openclaw cron runs <uuid>` per inbox cron
```

4. Preserve any other `service-inventory.md` content unchanged. Do not fix unrelated drift in this WP.

**Files**:
- `docs/design/architecture/service-inventory.md`

**Validation**:
- [ ] `felix-admin-capture` section reflects the new pre-scan-then-act pattern
- [ ] Helper component is documented with path, trigger, contract, logs
- [ ] Other sections of `service-inventory.md` are unchanged

### T020 — Verify JSON ↔ markdown consistency

**Purpose**: Ensure the markdown view does not contradict the JSON source.

**Steps**:
1. Run any existing doc-sync tooling:
   - `python tooling/scripts/validate_docs.py` if it exists
   - `python tooling/scripts/kg_sync_docs.py docs/design/architecture/service-inventory.md --check` if that's the pattern
2. If no tooling exists, do a manual consistency check:
   - Every field mentioned in the markdown is sourced from the JSON (service id, type, host, component id, deploy path, log path)
   - Every JSON change from T018 is reflected in T019's markdown
   - No fields in markdown contradict the JSON (e.g., different deploy path, different language)
3. Record the verification method in the WP runlog so the reviewer can reproduce it.

**Files**:
- No file changes — verification only.

**Validation**:
- [ ] JSON + markdown agree on every fact about the helper component
- [ ] Tooling (if present) reports consistent or clean
- [ ] Manual diff (if no tooling) confirms consistency

## Definition of Done

- [ ] `service-inventory.json` references the inbox-prescan-helper component under `felix-admin-capture`
- [ ] `updated_by` field = `027-inbox-pre-scan-helper`
- [ ] `service-inventory.md` describes the pre-scan-then-act pattern
- [ ] JSON parses cleanly
- [ ] JSON + markdown consistency verified
- [ ] Conventional commit: `docs(WP04): architecture — inbox-prescan-helper component`

## Risks

- **Schema strictness**: if `service-inventory.json` has a strict schema that rejects a new `components` field, adjust the representation. Don't force a schema violation.
- **Markdown drift**: the markdown view may have been out of date before this mission. Do NOT try to fix unrelated drift. Only touch the `felix-admin-capture` section.
- **Doc validation tooling**: if `tooling/scripts/validate_docs.py` exists but has its own quirks, follow its error messages — don't argue with the tool.
- **JSON structure mismatch**: the existing schema may treat services as a top-level map vs an array. Match whatever pattern is already in the file.

## Reviewer Guidance

- Verify `updated_by` field was set correctly
- Verify the markdown view matches the JSON (every fact cross-referenced)
- Verify no unrelated drift was introduced — the diff should be tight
- Verify the JSON is valid (no trailing commas, no comments)
- Verify the helper component's `source` field points at the repo path and `deploy_path` points at the office2 path (they should be different)
- If the architecture has multiple JSON files (data-flows.json, network-topology.json, credential-manifest.json), verify none of them needed changes in this mission (helper is local-only, no new network path, no new credential)

## Implementation command

```bash
spec-kitty agent action implement WP04 --mission 027-inbox-pre-scan-helper --agent <tool>:<model>:<profile>:<role>
```

## Activity Log

- 2026-04-11T18:25:58Z – claude:opus-4-6:docs-implementer:implementer – shell_pid=50006 – Assigned agent via action command
- 2026-04-11T18:28:30Z – claude:opus-4-6:docs-implementer:implementer – shell_pid=50006 – Ready for review: service-inventory.json + md updated with prescan helper component
