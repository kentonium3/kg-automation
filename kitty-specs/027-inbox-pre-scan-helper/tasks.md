# Tasks: Inbox Pre-Scan Helper

**Mission**: 027-inbox-pre-scan-helper
**Source issue**: kentonium3/kg-automation#149
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)
**Data model**: [data-model.md](data-model.md)
**Research**: [research.md](research.md)
**Quickstart**: [quickstart.md](quickstart.md)

## Summary

Five work packages totaling 27 subtasks. WP01, WP02, and WP04 are independent and can run in parallel. WP03 depends on WP01 + WP02. WP05 depends on all others (it is the live office2 deploy + verification gate).

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create `prescan.py` skeleton with CLI entry point and args | WP01 | | [D] |
| T002 | Implement vault path registry resolver | WP01 | | [D] |
| T003 | Implement InboxFile classification (frontmatter + mtime rules) | WP01 | | [D] |
| T004 | Implement stale-processed archive move logic | WP01 | | [D] |
| T005 | Implement JSON stdout + stderr + daily log file output | WP01 | | [D] |
| T006 | Create test fixture files under `tests/scripts/inbox/fixtures/` | WP01 | [D] |
| T007 | Write pytest unit tests under `tests/scripts/inbox/test_prescan.py` | WP01 | | [D] |
| T008 | Identify which agent workspace file owns "Step 1" | WP02 | | [D] |
| T009 | Update that file with new Step 1 contract | WP02 | | [D] |
| T010 | Verify render through vault path registry deploy (no new markers) | WP02 | | [D] |
| T011 | Create `deploy-149.sh` skeleton with `--dry-run` and `--apply` flags | WP03 | | [D] |
| T012 | Implement pre-flight checks (Restic age, office2 reachability, repo file presence) | WP03 | | [D] |
| T013 | Implement helper deploy step (rsync) + `--self-check` verification | WP03 | | [D] |
| T014 | Implement agent workspace deploy step (rsync + diff verify) | WP03 | | [D] |
| T015 | Implement `openclaw cron edit` step for the 4 inbox cron UUIDs | WP03 | | [D] |
| T016 | Implement post-flight smoke test (trigger one cron, verify run history) | WP03 | | [D] |
| T017 | Implement rollback-instruction printer on failure (no auto-rollback) | WP03 | | [D] |
| T018 | Update `service-inventory.json` — add helper component under felix-admin-capture | WP04 | [D] |
| T019 | Update `service-inventory.md` markdown view to match JSON | WP04 | | [D] |
| T020 | Verify JSON ↔ markdown consistency | WP04 | | [D] |
| T021 | Pre-flight verification (Restic age, office2 up, run `--dry-run`) | WP05 | | [D] |
| T022 | Execute `deploy-149.sh --apply` | WP05 | | [D] |
| T023 | Smoke test empty run: trigger cron, verify IDLE + ≤500 tokens + helper log + no downstream writes | WP05 | | [D] |
| T024 | Smoke test non-empty run: plant an unprocessed file, trigger cron, verify agent processes correctly | WP05 | | [D] |
| T025 | Smoke test archive: plant a stale processed file, verify archive move on next helper run | WP05 | | [D] |
| T026 | Capture all 10 success criteria evidence into mission close-out artifact | WP05 | | [D] |
| T027 | Draft issue #149 closure comment (posted after /spec-kitty.merge) | WP05 | | [D] |

## Work Packages

### WP01: Helper Implementation + Unit Tests

**Priority**: Foundational
**Estimated prompt size**: ~450 lines
**Independent test**: `pytest tests/scripts/inbox/ -v` passes with no office2 contact
**Dependencies**: none
**Owned files**: `scripts/inbox/**`, `tests/scripts/inbox/**`
**Authoritative surface**: `scripts/inbox/`

**Subtasks:**
- [x] T001 Create `scripts/inbox/prescan.py` skeleton with CLI entry point, argparse for `--self-check`, module docstring, stdlib imports (WP01)
- [x] T002 Implement vault path registry resolver: read `scripts/vault/paths.json`, return absolute paths for `inbox` and `inbox_processed`; fail loud on missing or unreadable registry (WP01)
- [x] T003 Implement InboxFile classification per `data-model.md`: PyYAML frontmatter parsing, mtime-based age computation, classification rules (unprocessed / processed-recent / processed-stale / unknown-treated-as-unprocessed) (WP01)
- [x] T004 Implement stale-processed archive move: iterate classified files, move `processed-stale` entries to `{{VAULT_INBOX_PROCESSED}}`, collect warnings on destination-exists or permission errors, preserve filenames (WP01)
- [x] T005 Implement output layer: JSON `PrescanResult` to stdout, human-readable log lines to stderr, daily append-only log at `/home/claude/second-brain/agents/logs/inbox-prescan-YYYY-MM-DD.md`, and `--self-check` mode that exits early after registry resolution (WP01)
- [x] T006 Create 7 test fixture files under `tests/scripts/inbox/fixtures/`: `processed-recent.md`, `processed-stale.md`, `unprocessed.md`, `no-frontmatter.md`, `no-status.md`, `malformed-yaml.md`, `unknown-status.md` (WP01)
- [x] T007 Write pytest unit tests under `tests/scripts/inbox/test_prescan.py` covering all FR-001–FR-008 behaviors, edge cases (missing/malformed/unknown status, exactly-7-days boundary, idempotence, `_private/` defense-in-depth), and the `--self-check` mode (WP01)

**Parallel opportunities:**
- T006 (fixture creation) can run in parallel with T001–T005 (implementation) because fixtures are file-only and have no code dependencies. But T007 must run last.

**Risks:**
- PyYAML's `safe_load` may behave differently on Obsidian's `<% tp.file.cursor() %>` template placeholder. Test fixtures must include this case and assert the helper treats the file as unprocessed (the helper's contract is to never crash on content it doesn't understand).
- Timezone handling: mtime is in local timezone, the 7-day window must use UTC-aware math to avoid DST-boundary drift. Tests assert with a known-fixed mtime.

**Requirement refs**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-013, NFR-001, NFR-002, NFR-004, C-001, C-002, C-003, C-004

---

### WP02: Agent Workspace Step 1 Update

**Priority**: Foundational
**Estimated prompt size**: ~250 lines
**Independent test**: Grep of the updated file shows the new Step 1 contract; no references to the old "scan the inbox" wording remain; vault path registry deploy still renders the file cleanly.
**Dependencies**: none
**Owned files**: `ai-agents/felix-admin-capture/**`
**Authoritative surface**: `ai-agents/felix-admin-capture/`

**Subtasks:**
- [x] T008 Read `ai-agents/felix-admin-capture/` files (IDENTITY.md, SOUL.md, AGENTS.md, USER.md, TOOLS.md and their `.tmpl` counterparts) and identify which file owns the "Step 1: scan the inbox" instruction. Record the finding in the WP runlog. (WP02)
- [x] T009 Update the identified file(s) — likely `AGENTS.md.tmpl` or `SOUL.md.tmpl` — with the new Step 1 contract per `plan.md` design section. Preserve all other standing orders. Use the `{{VAULT_INBOX}}` and `{{VAULT_INBOX_PROCESSED}}` markers (already defined by mission 026) where vault paths are needed. Hardcode the helper path `/home/claude/kg-automation/scripts/inbox/prescan.py` (it is a deploy artifact, not a vault path). (WP02)
- [x] T010 Confirm the updated file renders correctly through the vault path registry deploy mechanism: no new `{{VAULT_*}}` markers introduced, existing markers preserved, no orphaned substitution placeholders. Spot-check by running the resolver locally against the file and diffing against a known-good render. (WP02)

**Parallel opportunities:** none (sequential within the WP)

**Risks:**
- If Step 1 lives in multiple files (redundant across SOUL.md and AGENTS.md), updating one without the other creates inconsistency. T008 must find ALL occurrences before T009 begins.
- If Step 1 is expressed as a narrative instead of a numbered step, the new contract must be phrased to match the existing tone and idiom.
- The helper path (`/home/claude/kg-automation/...`) is hardcoded. If the kg-automation repo location on office2 ever changes, this file must change with it. Add a comment noting the dependency.

**Requirement refs**: FR-009, FR-010, FR-011, FR-012

---

### WP03: Deploy Wrapper `deploy-149.sh`

**Priority**: Foundational
**Estimated prompt size**: ~480 lines
**Independent test**: `./scripts/deploy/deploy-149.sh --dry-run` prints each step cleanly, halts on no real errors, and shows exactly the changes that would be applied.
**Dependencies**: WP01 (wrapper references `scripts/inbox/prescan.py`), WP02 (wrapper rsyncs the agent workspace files)
**Owned files**: `scripts/deploy/deploy-149.sh`
**Authoritative surface**: `scripts/deploy/`

**Subtasks:**
- [x] T011 Create `scripts/deploy/deploy-149.sh` with shebang, `set -euo pipefail`, `--dry-run` / `--apply` flag parsing, step-numbered output, halt-on-error behavior (WP03)
- [x] T012 Implement pre-flight checks: Restic backup age ≤24h (via `restic snapshots --last 1 --json` or equivalent), `ssh office2-claude true` reachability, presence of `scripts/inbox/prescan.py`, `ai-agents/felix-admin-capture/`, and each of the files the wrapper will rsync (WP03)
- [x] T013 Implement Step 2 "copy helper": rsync `scripts/inbox/` to `/home/claude/kg-automation/scripts/inbox/` on office2; then Step 3 "verify helper": ssh and run `python3 .../prescan.py --self-check`, halt on non-zero exit or non-matching JSON (WP03)
- [x] T014 Implement Step 4 "copy agent workspace": rsync updated `ai-agents/felix-admin-capture/` files to `/home/claude/.openclaw/agents/felix-admin-capture/`; then Step 5 "verify agent workspace": ssh and diff deployed files vs. repo sources; halt on any diff beyond whitespace (WP03)
- [x] T015 Implement Step 6 "edit openclaw cron payloads": resolve the 4 inbox cron UUIDs by name via `openclaw cron list --json` (NOT hardcoded), then call `openclaw cron edit <uuid> --message "<new message>"` for each; halt on any edit failure; then Step 7 "verify cron state": `openclaw cron list --json` and confirm all 4 show the new payload message (WP03)
- [x] T016 Implement Step 8 "post-flight smoke test": `openclaw cron run <inbox-noon-uuid>` (debug trigger), wait for completion, confirm via `openclaw cron runs <uuid>` that the turn completed successfully; read the helper daily log file and confirm a new entry was written (WP03)
- [x] T017 Implement rollback-instruction printer: on any step failure, print a clear manual rollback recipe (which file to restore from git, which cron message to revert to, which ssh commands to run). Never auto-execute rollback. (WP03)

**Parallel opportunities:** none (each step depends on the previous)

**Risks:**
- `openclaw cron list --json` schema may change between openclaw versions. Parse defensively and fail loud with a clear message if the expected shape is missing.
- Restic backup age check: the exact restic invocation varies by repo layout. Use the documented command from `docs/runbooks/` if present, otherwise a `restic snapshots --latest 1 --json | python3 -c "..."` approach with a hardcoded 86400-second tolerance.
- The `--dry-run` mode must not touch office2 at all (no rsync, no openclaw calls). It must do the pre-flight checks (which are read-only) and print the planned changes.
- `ssh office2-claude` requires the SSH agent to be unlocked; if it isn't, the wrapper should halt early with a clear "unlock your SSH agent" message rather than generating confusing downstream errors.

**Requirement refs**: FR-014

---

### WP04: Architecture Doc Updates

**Priority**: Polish (can run in parallel with WP01–WP03)
**Estimated prompt size**: ~220 lines
**Independent test**: `service-inventory.json` validates against its schema; markdown view renders with the new helper component; `updated_by` field correctly references this mission.
**Dependencies**: none
**Owned files**: `docs/design/architecture/data/service-inventory.json`, `docs/design/architecture/service-inventory.md`
**Authoritative surface**: `docs/design/architecture/`

**Subtasks:**
- [x] T018 Update `docs/design/architecture/data/service-inventory.json`: locate the `felix-admin-capture` service entry, add `inbox-prescan-helper` as a component with owner, language (Python), deploy path (`/home/claude/kg-automation/scripts/inbox/prescan.py`), log path (`/home/claude/second-brain/agents/logs/inbox-prescan-*.md`), and dependency on `scripts/vault/paths.json`. Set the service's `updated_by` to `027-inbox-pre-scan-helper` and `updated_at` to the mission commit date. (WP04)
- [x] T019 Update `docs/design/architecture/service-inventory.md` to match the JSON: rewrite the `felix-admin-capture` section to describe the pre-scan-then-act pattern, referencing the helper component, the Step 1 contract, and the cron payload message change (WP04)
- [x] T020 Verify JSON ↔ markdown consistency: run any existing doc-sync tooling (`python tooling/scripts/validate_docs.py` or similar), or manually diff the section. Confirm the standing directive from `CLAUDE.md` ("JSON files are authoritative; markdown files are views") is satisfied. (WP04)

**Parallel opportunities:**
- T018 (JSON) and T019 (markdown) touch different files and can be drafted in parallel, but T020 must run after both.

**Risks:**
- Schema strictness of `service-inventory.json` — if the schema forbids adding fields to existing service entries, a different representation (new top-level component entry cross-linked to the service) may be needed. Read the schema first (`docs/design/architecture/data/schemas/` if present) before editing.
- The `service-inventory.md` file may have been hand-edited inconsistently with the JSON over time. Do not fix unrelated drift in this mission — only the `felix-admin-capture` section is in scope.

**Requirement refs**: FR-015, SC-009

---

### WP05: Office2 Deploy + Verification

**Priority**: Integration gate
**Estimated prompt size**: ~430 lines
**Independent test**: The mission close-out artifact demonstrates all 10 success criteria from `spec.md` with real evidence from live office2 state.
**Dependencies**: WP01, WP02, WP03, WP04
**Owned files**: `kitty-specs/027-inbox-pre-scan-helper/research/wp05-deploy-verification.md` (close-out artifact only — no other files)
**Authoritative surface**: `kitty-specs/027-inbox-pre-scan-helper/research/`

**Subtasks:**
- [x] T021 Pre-flight verification: confirm Restic backup age ≤24h; confirm `ssh office2-claude` works; run `./scripts/deploy/deploy-149.sh --dry-run` and capture its output into the runlog (WP05)
- [x] T022 Execute `./scripts/deploy/deploy-149.sh --apply`; capture full output into the runlog; confirm the wrapper's Step 8 post-flight smoke test passes (WP05)
- [x] T023 Empty-run smoke test: confirm the current inbox has 0 unprocessed files; trigger `openclaw cron run <inbox-noon-uuid>`; observe via `openclaw cron runs <uuid>` that the agent replied with IDLE, total token count ≤500; confirm no new Vikunja tasks, no new vault files, no WhatsApp sends happened during the run window; confirm the helper daily log recorded "0 unprocessed, 0 archived" (WP05)
- [x] T024 Non-empty smoke test: plant a known unprocessed test file in `01-Inbox/` (e.g., `Inbox 2026-04-11 1200 test.md` with `status: unprocessed`); trigger a cron; verify the agent processed only that file (check agent processing log); verify the file's status toggled to `processed` post-run; verify downstream effects were exactly what the test file's content instructed (WP05)
- [x] T025 Archive smoke test: plant a test file with `status: processed` and mtime 8 days ago (via `touch -d`); trigger a cron (or wait for a real one); verify the file moved from `01-Inbox/` to `02-Inbox-Processed/`; verify the helper log recorded the move with correct src/dst/age_days (WP05)
- [x] T026 Write mission close-out artifact at `kitty-specs/027-inbox-pre-scan-helper/research/wp05-deploy-verification.md` capturing: deploy timestamp, wrapper output, all 10 success criteria evidence (SC-001 through SC-010) with direct log/run-history quotes, any anomalies observed, any follow-on issues filed (WP05)
- [x] T027 Draft the issue #149 closure comment referencing the merge commit hash (to be filled in post-merge), the helper artifact path, the 10 success criteria results, and the "#158 close follow-on" note; store the draft in the close-out artifact so it's posted from the workflow immediately after `/spec-kitty.merge` (WP05)

**Parallel opportunities:** none (sequential gate)

**Risks:**
- Inbox may be non-empty at smoke-test time. If so, T023 is invalid and must be deferred until after the agent runs naturally or a manual cleanup is performed. Do not force-clean the inbox just for the smoke test — let the agent process naturally.
- #158 (Obsidian Sync silent failure) is risk-accepted for this mission. If the smoke test's artifacts do not propagate from office2 to Mac/phone, that is #158 territory and not a WP05 failure — document it, don't fix it.
- If T024's test file routing produces unexpected downstream effects (e.g., the agent creates a real Vikunja task from the test content), manually clean up after verification.
- T027 is a draft-only task — do NOT post the issue comment during WP05. The comment posts after `/spec-kitty.merge` as part of the merge workflow.

**Requirement refs**: SC-001, SC-002, SC-003, SC-004, SC-005, SC-006, SC-007, SC-008, SC-009, SC-010, NFR-001, NFR-003, NFR-005, NFR-006

---

## Dependency Graph

```
  WP01 ──┐
         ├──▶ WP03 ──▶ WP05
  WP02 ──┘             ▲
                        │
  WP04 ─────────────────┘
```

**Execution order** (assuming parallel where possible):
1. **Parallel**: WP01, WP02, WP04 (independent)
2. **Sequential**: WP03 (after WP01 + WP02)
3. **Sequential**: WP05 (after WP03 + WP04)

## MVP Scope

WP01 + WP02 + WP03 + WP05 (skipping WP04 architecture docs) would deliver a working helper and deployed system. But the architecture-doc standing directive from CLAUDE.md is mandatory, so WP04 is not actually skippable. Full scope = MVP.

## Prompt Size Validation

| WP | Subtasks | Est. lines | Status |
|---|---|---|---|
| WP01 | 7 | ~450 | ✓ ideal |
| WP02 | 3 | ~250 | ✓ acceptable (small but tight scope) |
| WP03 | 7 | ~480 | ✓ ideal |
| WP04 | 3 | ~220 | ✓ acceptable (small but tight scope) |
| WP05 | 7 | ~430 | ✓ ideal |

All within range. No splits required.

## Next Step

`/spec-kitty.implement` — dispatch implementation and review for each WP.
