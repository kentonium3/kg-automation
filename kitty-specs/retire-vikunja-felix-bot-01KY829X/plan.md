# Implementation Plan: Retire Vikunja felix-bot (single client, single kent identity)

**Branch**: `fix/860-retire-vikunja-felix-bot` | **Date**: 2026-07-23 | **Spec**: [spec.md](./spec.md)
**Input**: `kitty-specs/retire-vikunja-felix-bot-01KY829X/spec.md` | **Source issue**: kentonium3/kg-automation#860 (Epic #531)

## Summary

Consolidate **all** Felix→Vikunja access onto the shared `VikunjaClient`, then flip its one
default to the kent token and eliminate felix-bot's Vikunja view. The real work is the
**consolidation**: ~6 runtime domains (sync, escalation, enrichment, habits, credential-health)
currently talk to Vikunja with hand-loaded tokens + **raw HTTP** and must be migrated onto the
client — extending `VikunjaClient` where it lacks an operation they need. Once every consumer is
on the client, "single identity = kent" is a one-line default change, and the #748 validator
draws that same default (convergence). This establishes the Epic #531 boundary / EA-§11 task
seam **without** a formal abstract port (deferred until a second backend justifies it).

## Technical Context

**Language/Version**: Python 3 (office2 python3-only). Docs Markdown + JSON.
**Primary Dependencies**: the shared `scripts/common/vikunja_client.py` (the boundary — extended
here); the #748 seam (`vikunja_refs.py` / `vikunja_refs.json`, validator `validate_refs.py`).
**Storage**: office2 secret files `/data/services/openclaw/secrets/{vikunja-api,vikunja-api-kent}`.
**Testing**: per-consumer behavior-preserving tests (each migrated module's Vikunja effects
unchanged except widened kent visibility); new `VikunjaClient` method tests; validator drift test
under the shared default; live before/after connectivity at deploy.
**Target Platform**: office2. Runtime scripts are **checkout-resident** (self-pulled) — the cutover
lands via `git pull`; clients read the token per-call (no restart). SKILL.md via skill-sync.
**Project Type**: single (scripts + docs + architecture data).
**Constraints**: single boundary + single identity (C-003); no abstract port (C-004); Tier-1/2
snapshot + before/after connectivity (C-005).
**Scale/Scope**: ~13 runtime consumers (6 raw-HTTP modules to rewrite onto the client + client
extensions) + validator + inverse probe + ~5 docs/units + manifest. **This is a large mission.**

### Environment probe results (DIR-015 — verified live on office2, 2026-07-23)

- Both secret files present + non-empty (`vikunja-api` felix-bot; `vikunja-api-kent` kent), `0600`.
- Consumer inventory (grep-confirmed): raw-HTTP direct-token consumers = `sync/cycle.py`,
  `escalation/{record_completion,reconcile_completions}.py`, `enrichment/{record_completion,
  reconcile_completions}.py`, `habits/{sweeper,set_due_dates,record_completion,exclude_completed,
  identify_workout_task,migrate_schedule,backfill_jsonl_from_comments}.py`,
  `security/credential_health_check/vikunja_writer.py`. `intake/apply_reply.py` **already** uses
  `VikunjaClient`. Admin/one-shot scripts (`provision_felix_bot`, `validate_felix_bot`,
  `swap_vikunja_secrets`, `reconcile_projects`, `create_saved_filters`, `migrate_tasks`) are not
  runtime consumers.
- The #748 validator already reads the kent token via a parallel constant; FR-006 routes it through
  the shared default so it can't re-diverge.
- **ADR-0004** (0003 taken). `credential-manifest.json` holds `vikunja-api` (retire) + `vikunja-api-kent`
  (keep) + `vikunja-admin` (keep) + two `kg-felix-bot-*` GitHub PATs (out of scope).

### Deploy & rebaseline analysis (Codex-adjudicated)

- Code = checkout-resident (self-pull; no restart). SKILL.md via skill-sync.
- **Rebaseline**: `scripts/**` and `credential-manifest.json` match no audited-surface pattern.
  Codex correction: **if** a `deploys/queued/*.yaml` is added it matches the deploy-pipeline surface
  (`rebaseline_required: true`, empty `affected_baselines`) → then record the deploy-pipeline
  rebaseline outcome. **Decision**: this cutover needs no imperative deploy action (self-pull +
  skill-sync), so **omit the deploy manifest** and record `Rebaseline: not required — no audited
  surface matched`. Live-verify is done in the attended step, not via a manifest hook.

## Charter Check

*GATE: passed (compact charter).*
- **DIR-006 (deterministic)**: config + mechanical migration → deterministic. ✅
- **DIR-014 (doc-sync)**: ADR-0004 + identity-model + credentials-and-secrets + SKILL/TOOLS/unit + manifest. ✅
- **DIR-015 (probe)**: office2 probe + full consumer inventory done. ✅
- **Single source of truth / boundary**: C-003 (one client, one identity). ✅
- **§11 discipline**: seam via `VikunjaClient`, no premature abstract port (C-004). ✅
- **Tier-1/2 (C-005)**: attended snapshot + before/after connectivity is an explicit HOLD. ✅

## Project Structure

```
scripts/common/vikunja_client.py                 # MODIFIED — extend methods (FR-002) + DEFAULT_TOKEN_PATH → kent (FR-003)
scripts/sync/cycle.py                            # MIGRATE — raw HTTP → VikunjaClient
scripts/escalation/{record_completion,reconcile_completions}.py     # MIGRATE
scripts/enrichment/{record_completion,reconcile_completions}.py     # MIGRATE
scripts/habits/{sweeper,set_due_dates,record_completion,exclude_completed,identify_workout_task,migrate_schedule,backfill_jsonl_from_comments}.py  # MIGRATE
scripts/security/credential_health_check/vikunja_writer.py          # MIGRATE
scripts/inbox/route_someday.py                   # MODIFIED — remove felix-bot 403 fail-soft (FR-004, #750)
scripts/vikunja/validate_refs.py + scripts/common/vikunja_refs.py   # MODIFIED — draw shared default (FR-006)
scripts/vikunja/{provision_felix_bot,validate_felix_bot}.py         # RETIRE/ARCHIVE — obsolete with felix-bot
docs/design/architecture/adr/0004-*.md           # NEW (supersede 0002); 0002 Superseded-by: 0004
docs/design/architecture/{identity-model,credentials-and-secrets}.md  # MODIFIED — single client/identity
docs/design/architecture/data/credential-manifest.json               # MODIFIED — retire vikunja-api
scripts/openclaw/skills/vikunja-api/SKILL.md      # MODIFIED — kent token + v2.4.0 + health-check (#831, FR-007)
scripts/openclaw/skills/escalation/SKILL.md · agents/felix-admin-tasker/TOOLS.md · sync/systemd/felix-vikunja-sync.service  # MODIFIED (FR-007)
```

## Implementation Concern Map

### IC-01 — `VikunjaClient` boundary completeness (FR-002)

- **Purpose**: make the client cover every operation the raw-HTTP consumers need, so migration
  loses no capability.
- **Relevant requirements**: FR-002; C-003.
- **Affected surfaces**: `vikunja_client.py` — inventory the HTTP ops in the 6 raw modules
  (comments, completion toggles, label attach/detach, bulk reads, etc.); add missing methods to
  the client contract + error model; unit-test each.
- **Sequencing/depends-on**: none (foundation).
- **Risks**: subtle behavior differences (pagination, partial-update POST semantics — the known
  Vikunja read-modify-write quirk); the client must preserve each consumer's exact effect.

### IC-02 — Migrate raw-HTTP consumers onto the client (FR-001, NFR-003)

- **Purpose**: replace hand-loaded-token + raw HTTP with `VikunjaClient` in every runtime consumer.
- **Relevant requirements**: FR-001; NFR-001, NFR-003.
- **Affected surfaces**: sync/cycle, escalation ×2, enrichment ×2, habits ×7, credential-health writer.
- **Sequencing/depends-on**: IC-01.
- **Risks**: this is the bulk of the mission; do it behavior-preserving with per-consumer tests;
  `sync/cycle.py` (bidirectional sync) is the highest-stakes — migrate + test carefully.

### IC-03 — Single-identity flip + validator convergence (FR-003, FR-004, FR-006)

- **Purpose**: set the one identity (kent) and make the validator share it; drop moot felix-bot paths.
- **Relevant requirements**: FR-003, FR-004, FR-006; SC-003.
- **Affected surfaces**: `vikunja_client.py` `DEFAULT_TOKEN_PATH` → kent; `route_someday.py`
  (remove 403 fail-soft); `validate_refs.py`/`vikunja_refs.py` (draw shared default; single-token).
- **Sequencing/depends-on**: IC-01, IC-02 (everyone on the client first, else split-brain).
- **Risks**: ordering — the flip must not land before all consumers are on the client.

### IC-04 — Inverse probe + felix-bot data migration (FR-005, SC-004)

- **Purpose**: ensure nothing felix-bot-only is stranded when its view is eliminated.
- **Relevant requirements**: FR-005; SC-004.
- **Affected surfaces**: a probe enumerating projects/tasks/labels/filters as felix-bot vs kent,
  diffing `felix-bot-only`; migrate live items to kent (esp. Inbox 14) or record as abandoned.
- **Sequencing/depends-on**: none (can run early, read-only); its migration writes are attended.
- **Risks**: Inbox(14) contents — capture routing must land in kent's inbox post-cutover.

### IC-05 — Docs / ADR / manifest (FR-007, FR-008, FR-009)

- **Purpose**: record the decision + reconcile every two-token reference + retire the credential.
- **Relevant requirements**: FR-007, FR-008, FR-009; DIR-014.
- **Affected surfaces**: NEW `adr/0004`; `0002` Superseded-by; `identity-model.md`;
  `credentials-and-secrets.md`; SKILL.md (#831) + escalation SKILL + TOOLS.md + service unit;
  `credential-manifest.json` (retire vikunja-api; note token left valid + user dormant, FR-009).
- **Sequencing/depends-on**: none (parallel).
- **Risks**: catch every two-token reference (grep `felix-bot`, `vikunja-api\b`, `two-token`).

### IC-06 — Attended Tier-2 deploy + verify (FR-010, C-005)

- **Purpose**: cut over live with the operator present and verify no regression.
- **Relevant requirements**: FR-010; NFR-001, NFR-002; C-005.
- **⛔ ATTENDED HOLD (Tier-2)**: before any live change — confirm a recent Restic snapshot
  (trigger if none in 24h) + capture the **before** connectivity baseline of **every** migrated
  consumer; operator present for the merge/self-pull cutover; then verify projects 16–20 return +
  every consumer green (SC-002/NFR-001/NFR-003) before closing #860/#831. Rebaseline: not required.
- **Sequencing/depends-on**: IC-01–05.
- **Risks**: the one irreversible-feeling step — mitigated by leaving the felix-bot token valid
  (revert → prior behavior).

## Codex adjudications folded (post-plan review)

- **HIGH (consumer completeness)** → the whole reframe: FR-001/IC-02 migrate all raw-HTTP consumers;
  no one-line pivot. Partial cutover is a split-brain and is prohibited (NFR-001).
- **MED (superset unproven)** → FR-005/IC-04 inverse probe + migrate/abandon felix-bot-only data.
- **MED (rebaseline)** → omit the deploy manifest → `Rebaseline: not required — no audited surface`.
- **LOW (validator test)** → add a construction-level test that the CLI's no-`--token-file` client
  uses the same shared default as `VikunjaClient` (FR-006).
- **LOW (rollback)** → quickstart rollback = revert the full commit (client + consumers + validator +
  docs + manifest); the felix-bot token stays valid.
