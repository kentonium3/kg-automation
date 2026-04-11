# Implementation Plan: Inbox Pre-Scan Helper

**Branch**: `main` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/027-inbox-pre-scan-helper/spec.md`
**Source issue**: kentonium3/kg-automation#149
**Depends on**: #152 (merged), #161 fix (applied)
**Risk-accepted**: #158 (Obsidian Sync silent failure)

## Summary

Add a Python pre-scan helper that `felix-admin-capture` invokes as its first action on every cron run. The helper lists unprocessed inbox files via the vault path registry and archives stale (>7 day) processed files to `{{VAULT_INBOX_PROCESSED}}`. When the helper reports zero unprocessed files, the agent replies with an IDLE sentinel and takes no further action (bounded minimal-token cost, zero downstream side effects). When the helper reports one or more unprocessed files, the agent processes exactly those files.

The mission ships three deliverables as one atomic unit: (1) the `prescan.py` helper in `scripts/inbox/`, (2) updates to the `felix-admin-capture` agent workspace files that change Step 1 to the helper-driven contract, and (3) a one-shot deploy wrapper `scripts/deploy/deploy-149.sh` that pushes the helper, updates the agent workspace on office2, and rewrites the 4 openclaw `inbox-*` cron payload messages via `openclaw cron edit`.

## Technical Context

**Language/Version**: Python 3 (office2 has Python 3.10+ with PyYAML 6.0.1 installed)
**Primary Dependencies**: PyYAML (frontmatter parsing); stdlib `pathlib`, `shutil`, `datetime`, `os`, `json`, `sys` for everything else
**Storage**: Filesystem only — reads inbox files, moves whole files between registered directories, appends to a daily log file. No database, no network, no LLM calls.
**Testing**: `pytest` unit tests under `tests/scripts/inbox/` in the kg-automation repo. Test fixtures: synthetic frontmatter samples covering happy path, missing status, missing frontmatter, malformed YAML, status with unknown value, file age edge cases (exactly 7 days old).
**Target Platform**: office2 (Ubuntu 24.04 LTS). Helper runs as the `claude` user inside an openclaw agent turn. Deploy wrapper runs from the Mac via `ssh office2-claude`.
**Project Type**: Single — Python helper script + shell deploy wrapper + agent workspace patch. No new service, no new port, no new credential.
**Performance Goals**: Helper completes in ≤1s wall-clock on an inbox of up to 50 files (NFR-001). Helper consumes no tokens and makes no network calls (NFR-002). Empty cron runs stay within a 500-token agent budget (NFR-003).
**Constraints**: Tier 3 (script) + Tier 2 (openclaw cron payload edits = application config). Pre-flight: confirm Restic backup ≤24h. Post-flight: confirm one live empty run stays under budget, one live non-empty run processes correctly, one stale-processed-file archive move succeeds.
**Scale/Scope**: Current inbox: ~32 files. Expected steady-state: ~5–15 active files (growth bounded by 7-day archive rule). Cron runs: 4x/day.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter context loaded in compact mode. Governance summary:
- Template set: `software-dev-default`
- Paradigms: `c4-incremental-detail-modeling`
- Directives: `DIRECTIVE_034`
- Tools: `git`, `python`, `spec-kitty`

**Gate decisions:**

- **Paradigm (c4-incremental-detail-modeling)**: The mission is small enough that a single-level C4 sketch (the Summary section above) is sufficient. No container diagram, no component diagram. The "incremental detail" requirement is satisfied by staging spec → plan → research → data-model → tasks → implementation, each layer adding concrete detail to the layer above. PASS.
- **DIRECTIVE_034**: Directive resolved from the charter amendment during mission 026 specify; its binding content is represented in the spec's Success Criteria and the Definition of Done implicit in each work package. PASS.
- **Tools (git, python, spec-kitty)**: This mission is pure git + python + spec-kitty. PASS.

**Compliance notes:**
- Felix Constitution privacy boundary (`~/second-brain/notes/04-Growth/_private/`) is honored by construction: the helper only touches registry-resolved paths, and the registry does not resolve `_private/`. Encoded as C-001 in the spec.
- Change-risk taxonomy: Tier 2 + Tier 3 (see Technical Context). Pre-flight and post-flight checklists will be followed during WP execution.
- Architecture documentation standing directive: `data/service-inventory.json` + markdown view MUST be updated in the same mission (FR-015, SC-009).

## Project Structure

```
kg-automation/
├─ scripts/
│  ├─ inbox/                          ← NEW
│  │  ├─ prescan.py                   ← NEW (the helper)
│  │  └─ README.md                    ← NEW (usage, contract, troubleshooting)
│  └─ deploy/
│     └─ deploy-149.sh                ← NEW (one-shot wrapper)
├─ tests/
│  └─ scripts/
│     └─ inbox/
│        ├─ test_prescan.py           ← NEW
│        └─ fixtures/
│           ├─ processed-recent.md    ← NEW
│           ├─ processed-stale.md     ← NEW
│           ├─ unprocessed.md         ← NEW
│           ├─ no-frontmatter.md      ← NEW
│           ├─ no-status.md           ← NEW
│           ├─ malformed-yaml.md      ← NEW
│           └─ unknown-status.md      ← NEW
├─ ai-agents/                         (agent workspace source-of-truth files; plan verifies which file owns Step 1)
└─ docs/
   └─ design/
      └─ architecture/
         ├─ data/service-inventory.json ← EDITED (helper as component of capture service)
         └─ service-inventory.md         ← EDITED (markdown view)
```

**On office2 (deployed state, post-deploy-149.sh):**
```
/home/claude/kg-automation/scripts/inbox/prescan.py         ← deployed (git-synced + this mission)
/home/claude/.openclaw/agents/felix-admin-capture/AGENTS.md ← deployed (updated Step 1)
/home/claude/second-brain/agents/logs/inbox-prescan-*.md    ← NEW daily log, appended by helper
```

**OpenClaw cron state (post-deploy):**
```
inbox-7am   payload.message: "Run the pre-scan helper as your Step 1 per your standing orders..."
inbox-noon  payload.message: (same)
inbox-5pm   payload.message: (same)
inbox-10pm  payload.message: (same)
```

All 4 cron jobs retain their existing schedule, failureAlert config, session isolation, and delivery settings. Only the payload message changes.

## Architecture Impact

| File | Change |
|---|---|
| `docs/design/architecture/data/service-inventory.json` | Add `inbox-prescan-helper` as a component under the `felix-admin-capture` service entry. Record owner, language, deploy path, log location, dependency on `paths.json` registry. Set `updated_by` to `027-inbox-pre-scan-helper`. |
| `docs/design/architecture/service-inventory.md` | Rewrite the `felix-admin-capture` section to describe the pre-scan-then-act pattern. |
| `data/data-flows.json` | No change (helper is part of an existing flow, not a new one). |
| `data/network-topology.json` | No change. |
| `data/credential-manifest.json` | No change. |
| `data/hardware-inventory.json` | No change. |

## Phase 0: Outline & Research

**Prerequisite**: spec.md complete, Charter Check PASS.

Research scope: deferred-to-plan questions from the spec's Assumptions section. Most are resolved by investigation during the specify-to-plan transition (Kent signed off on B for the architecture question; the others are mechanical facts verified via office2 probes).

Research artifacts produced: `research.md` in the mission directory.

**Research decisions (summary):**

| Question | Decision | Rationale |
|---|---|---|
| Frontmatter `status` values in use | `status: processed` / `status: unprocessed` are the only observed values | 32 files sampled on 2026-04-11. Unknown/missing treated as unprocessed per safety default. |
| Age basis for the 7-day archive rule | File mtime | Frontmatter `date`/`time` fields record capture time, not processing time. |
| Helper runtime language | Python 3 + PyYAML | Both confirmed installed on office2. |
| Helper log file path | `/home/claude/second-brain/agents/logs/inbox-prescan-YYYY-MM-DD.md` | Parallel to existing `inbox-processing-*.md` files. |
| Architecture for pre-scan integration | Agent Step 1 runs the helper (option B) | Chosen by Kent; keeps openclaw cron features intact. |
| Deploy wrapper strategy | One-shot `deploy-149.sh` | Chosen by Kent; #136 not imminent. |
| Test approach | pytest unit tests with fixture files | Pure logic → trivially valuable tests. |
| Registry resolution from Python | Read the existing `scripts/vault/` resolver contract | Mission 026 delivered this. No registry extension. |

**Output**: `research.md`. All NEEDS CLARIFICATION markers resolved.

## Phase 1: Design & Contracts

**Prerequisite**: `research.md` complete.

### Data Model

See `data-model.md`. Summary entities:

- **InboxFile**: absolute path + parsed frontmatter + file mtime + computed classification (unprocessed / processed-recent / processed-stale / unknown)
- **PrescanResult**: timestamp, list of unprocessed paths, list of archived (src, dst) pairs, list of errors/warnings, exit code
- **LogEntry**: timestamp, event type (run-start, archive-move, warning, error, run-end), details

No API contracts (no REST/GraphQL) — the helper is a CLI script invoked by the agent. Its contract is stdin/stdout/exit-code.

### Helper CLI contract

**Invocation**: `python3 /home/claude/kg-automation/scripts/inbox/prescan.py`

**Exit codes:**
- `0` = success, JSON result on stdout
- `1` = error (missing registry, missing directory, unreadable file, etc.)
- `2` = reserved

**Stdout format (exit 0):** single JSON object, e.g.:
```json
{
  "unprocessed_count": 1,
  "unprocessed_paths": ["/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-04-11 0930.md"],
  "archived_count": 2,
  "archived": [
    {"src": "/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-04-03 1100.md",
     "dst": "/home/kgale/second-brain/notes/02-Inbox-Processed/Inbox 2026-04-03 1100.md"}
  ],
  "warnings": []
}
```

**Stderr format:** human-readable log lines for each step (informational, error, warning).

**Agent Step 1 contract:** The agent invokes the helper, parses the JSON on stdout, and branches:
- `unprocessed_count == 0` → reply with the single token `IDLE` and nothing else. Turn ends.
- `unprocessed_count > 0` → iterate over `unprocessed_paths` and process each file per the existing routing rules. The standing orders beyond Step 1 are unchanged.
- Non-zero exit → report the helper's stderr as the turn output and stop. Do not process any files.

### Agent Workspace Changes

Find the file that currently owns the "Step 1: scan the inbox" instruction (likely `AGENTS.md` or `SOUL.md` in `ai-agents/felix-admin-capture/`). Replace Step 1 with the new contract. Preserve all other standing orders unchanged.

The `.tmpl` variant (if the file is templated via the vault path registry) must be edited, not the rendered `.md`. Mission 026's `.tmpl` + substitution + render pattern applies.

### Deploy Wrapper Contract

`scripts/deploy/deploy-149.sh` accepts:
- `--dry-run` — print what would happen, change nothing
- `--apply` — execute the deploy

Ordered steps (each must succeed before proceeding):

1. **Pre-flight**: verify Restic backup within 24h; verify office2 reachable via `ssh office2-claude`; verify `scripts/inbox/prescan.py` exists in repo; verify agent workspace files exist in repo.
2. **Copy helper**: `rsync` or `scp` `scripts/inbox/prescan.py` to `/home/claude/kg-automation/scripts/inbox/prescan.py` on office2.
3. **Verify helper**: ssh office2-claude and run `python3 /home/claude/kg-automation/scripts/inbox/prescan.py --self-check` (a mode that exercises registry resolution and exits without doing work). Halt on error.
4. **Copy agent workspace files**: rsync updated workspace files to `/home/claude/.openclaw/agents/felix-admin-capture/`.
5. **Verify agent workspace**: ssh office2-claude and diff the deployed files against the repo sources. Halt on mismatch.
6. **Edit openclaw cron payloads**: for each of the 4 UUIDs (`cc9977fa-…`, `7fa9b299-…`, `4ea46768-…`, `cf53bfa0-…`), run `openclaw cron edit <uuid> --message "<new message>"`. The new message instructs the agent to run its standing Step 1 (which now invokes the helper). Halt on any failure.
7. **Verify cron state**: `openclaw cron list --json` and confirm all 4 inbox crons show the new message in their payload.
8. **Post-flight**: trigger one smoke test via `openclaw cron run <uuid-noon>` (debug trigger) against the current inbox. Verify the agent runs, the helper produces a valid JSON result, and the agent replies correctly. Verify via openclaw run-history that the turn completed.

**On any failure**: halt, print the step that failed, print manual rollback instructions (which file to restore, which cron message to revert). Do NOT auto-rollback.

### Quickstart

See `quickstart.md`. One-page runbook for implementing this mission end-to-end.

### Agent Context Update

The kg-automation repo's `CLAUDE.md` does not need changes. No new top-level directories introduced. `ai-agents/felix-admin-capture/` is the only agent workspace touched.

## Charter Check (Post-Design)

Re-evaluate after Phase 1 design:

- **Paradigm**: C4-incremental-detail satisfied. PASS.
- **DIRECTIVE_034**: Satisfied. PASS.
- **Privacy boundary**: Helper and agent Step 1 operate only on registry-resolved paths. PASS.
- **Change-risk tier awareness**: Plan identifies Tier 2 + Tier 3 and requires pre-flight/post-flight. PASS.
- **Architecture doc standing directive**: Plan calls out service-inventory update. PASS.

No new charter gaps.

## Artifacts Generated This Phase

- `kitty-specs/027-inbox-pre-scan-helper/plan.md` — this file
- `kitty-specs/027-inbox-pre-scan-helper/research.md` — Phase 0
- `kitty-specs/027-inbox-pre-scan-helper/data-model.md` — Phase 1
- `kitty-specs/027-inbox-pre-scan-helper/quickstart.md` — Phase 1

## Next Step

`/spec-kitty.tasks` — generate work packages. Proposed shape (final sizing happens in /spec-kitty.tasks):

- **WP01**: Helper implementation + unit tests (pure Python, no office2 contact)
- **WP02**: Agent workspace Step 1 update
- **WP03**: Deploy wrapper `deploy-149.sh`
- **WP04**: Architecture doc updates (service-inventory.json + md view)
- **WP05**: Deploy + verification on office2

WP01 and WP04 are independent. WP02 depends on WP01 for the helper path reference. WP03 depends on WP01 + WP02. WP05 depends on WP03 + WP04.
