# Implementation Plan: Delivery-doctrine follow-ups (#1146)

**Branch**: mission branch `kitty/mission-delivery-doctrine-followups-01M8FBH0`, which lands on `fix/1146-delivery-doctrine-followups`; that branch reaches `main` by one PR | **Date**: 2026-11-27 | **Spec**: [spec.md](spec.md)
**Input**: Mission specification from `kitty-specs/delivery-doctrine-followups-01M8FBH0/spec.md`

## Planning decisions (Kent, 2026-11-27)

Decision 01M8FC8T0WYHWPQ9MW7XHJWFYA, "Agreed on all":

- **FR-005 is verify-and-pin.** No skill an announce agent reads contains send-on-failure wording today (research Q6). So FR-005 is met by a test that runs the guard, in skill mode, over every skill each announce agent reads. No wording is added.
- **"then notify …" is flagged only with a channel.** The guard keeps its deliberate channel requirement, so "Tell Kent: …" and "then notify Kent when finished" stay allowed. "then notify Kent via WhatsApp" and similar are flagged.
- **The `record_result` field exemption depends on context.** "If the automation tool offers record_result, record no_change…" and "record a no_change result" must stay flagged. Only a mention of a field named `record_result` is exempt, not the bare word.
- The design below, including a new config-patch deploy entrypoint for FR-006, was accepted as stated.

## Summary

The mission closes the six #1146 follow-ups from the #1143 reviews:

1. The guard (`delivery_doctrine.py`) gains the missing patterns, built test-first. All 8 should-flag forms pass today, and all 5 should-pass forms are flagged today (research Q7).
2. Two false-positive classes are exempted, each with a same-fixture positive control.
3. The retry rule's tail becomes "…or skip it and say so in your final reply". This adds 25 UTF-16 units to each copy; escalation goes from 17,780 to 17,805 against its 17,900 cap.
4. The escalation skill's §7 dedup text is rewritten to describe the real JSONL `derive_state` check.
5. A new test pins every skill an announce agent reads as guard-clean.
6. A new Tier 2 deploy entrypoint plus manifest 0044 adds `tools.deny = ["conversations_*","sessions_*","message","automations"]` to the three announce agents in office2's live `openclaw.json`, through `openclaw config patch`. The manifest is queued unnumbered; the applier assigns its sequence.

Prompt and skill changes reach office2 through the existing sync timers within about 5 minutes of merging to `main`. Only the tool deny needs a manifest.

## Technical Context

**Language/Version**: Python 3.12 (repo `.venv`; CI also runs 3.13)
**Primary Dependencies**: standard library only (`re`, `json`, `subprocess`, `hashlib`); the repo's `scripts/deploy/lib` (`apply.dry_run_then_apply_gate`, `snapshot.verify_restic_recent`); the OpenClaw CLI on office2 (2026.11.7: `openclaw config patch`, `openclaw config validate`, `openclaw cron list`)
**Storage**: files only. Repo prompts and skills, office2's `/home/claude/.openclaw/openclaw.json`, and a timestamped config backup beside it
**Testing**: pytest. Guard unit tests in `scripts/openclaw/agents/tests/test_delivery_doctrine.py`, red first, green after. Deploy-entrypoint tests run against a fixture config shaped like the live `agents.entries.<id>` map. The stale `agents.list[]` fixture is corrected, and its existing consumer `test_openclaw_config_schema.py` is updated in the same change and run with the new tests (R1-5). The manifest is validated against `deploys/schema/manifest-v1.schema.json`, and the dry-run path is exercised
**Target Platform**: office2 (Ubuntu 24.04 LTS), OpenClaw gateway with Code Mode `auto`; tests on office4/CI Linux
**Project Type**: single repository (kg-automation)
**Performance Goals**: the guard runs over all announce prompts and skills in under 2 s (NFR-003)
**Constraints**: escalation `AGENTS.md` ≤ 17,900 UTF-16 units; capture and habits ≤ 18,000. Tier 2 protocol for the deny. Restic backup ≤ 24 h, checked through the deploy library's existing `claude`-readable backup-state file by the applier's mandatory snapshot gate. No `--backup-confirmed` fallback: that gate runs before the entrypoint, so the flag could not bypass it (post-plan review R1-6). Hot reload only: any "restart required" result is a failure. The no-`record_result` rule stays while openclaw/openclaw#206884 is open
**Scale/Scope**: 3 announce agents, 6 cron jobs (all announce), 4 skills, about 14 guard fixture phrases, 1 manifest

## Charter Check

| Gate (charter section) | Status |
|---|---|
| Testing Standards: pytest for non-trivial helpers; fixtures mirror real inputs | Pass. Guard fixtures use phrases quoted from the #1146 reviews; the config fixture copies the live key shape (keys only, no secrets) |
| Testing Standards: no dead code | Pass. The entrypoint is called by manifest 0044; the guard is called by the prompt tests |
| Quality Gates: defined, recorded live verification | Pass. A post-merge operator canary (SC-002), recorded on #1146 |
| Deployment Constraints: manifest discipline; strict order (pre-flight → change → verify) | Pass. FR-006 rides `deploys/queued/` through `dry_run_then_apply_gate` |
| Deployment Constraints: read the real `openclaw.json` paths | Pass. Research Q1 read the live key shape (`agents.entries.<id>`) |
| Change-Risk Taxonomy | Tier 3 for prompts, skills and guard. Tier 2 for the config deny (Kent's go-ahead, 2026-11-27) |
| Rebaseline Obligation | Agent prompts are not monitored (research Q2). The `openclaw-config` surface drifts with no signal in the commit range, so the manifest declares `expected_baselines: [openclaw-config.txt]`. Merge record: `Rebaseline: automated — felix-deployer (deferred-confirm) on the post-merge deploy` |
| Branch Strategy: merge commits | Mission consolidates onto `fix/1146-…`, then one PR to `main` (Kent's choice, 2026-11-27) |

No violations; Complexity Tracking is not needed.

## Architecture Impact

From `docs/design/architecture/data/signal-to-doc-map.json` (mission-architecture-impact):

- **agent-prompt-changed:**
  - `docs/design/architecture/data/service-inventory.json` and `service-inventory.md`: record the announce agents' tool deny;
  - `docs/runbooks/openclaw-agent-setup.md`: the announce-agent tool policy;
  - `docs/runbooks/agent-prompt-sync-ops.md`, `docs/runbooks/deploy/office2-deploy-paths.md`, `docs/design/architecture/data/audited-surfaces.json`: review; change only if they are now wrong.
- **deploy-manifest-added:** `docs/runbooks/deploy/discipline.md` and `scripts/deploy/lib/README.md`. Record the config-patch pattern, the first manifest-driven `openclaw.json` edit.
- **Security posture:** `docs/design/architecture/security-posture.md` notes the capability deny for announce agents.

## Project Structure

### Documentation (this mission)

```
kitty-specs/delivery-doctrine-followups-01M8FBH0/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0: evidence for every planning decision
├── data-model.md        # Phase 1: guard pattern classes, deny entry, manifest fields
├── quickstart.md        # Phase 1: how to verify each FR locally and live
└── checklists/requirements.md
```

No `contracts/`: the mission adds no external interface (`meta.json` records `contracts: none`).

### Source Code (repository root)

```
scripts/openclaw/agents/
├── delivery_doctrine.py                 # FR-001, FR-002, FR-003 (block text)
└── tests/
    ├── test_delivery_doctrine.py        # red-then-green cases; skill-coverage test (FR-005); size caps
    └── fixtures/openclaw-sample.json    # corrected to agents.entries.<id> shape
scripts/openclaw/agents/<agent>/AGENTS.md  # capture, escalation, habits: block copy (FR-003); exact paths per prompt-sync map
scripts/openclaw/skills/escalation/SKILL.md # FR-004 (§7 dedup text)
scripts/deploy/
├── deploy-announce-agent-tool-deny.py   # FR-006 entrypoint (new)
└── lib/                                 # reuse apply/snapshot; add a small openclaw-config-patch helper only if reuse is clean
tests/deploy/test_announce_agent_tool_deny.py  # entrypoint tests (new)
deploys/queued/announce-agent-tool-deny.yaml      # FR-006/FR-007 manifest (new; unnumbered — the applier assigns the sequence, R1-7)
```

**Structure Decision**: everything stays in the existing layout. The only new source files are the deploy entrypoint, its test and the manifest.

## Implementation Concern Map

### IC-01 — Guard coverage

- **Purpose**: make the wording guard classify every reviewed phrase correctly without weakening existing catches.
- **Relevant requirements**: FR-001, FR-002, NFR-001, NFR-003
- **Affected surfaces**: `scripts/openclaw/agents/delivery_doctrine.py`, `scripts/openclaw/agents/tests/test_delivery_doctrine.py`
- **Sequencing/depends-on**: none
- **Risks**:
  - **Block count:** the block search runs on the raw text. Normalisation applies only to the scanned remainder.
  - **Normalisation contract (R1-4):** remove *paired* formatting delimiters (`**x**`, `__x__`, `*x*`, `` `x` ``). Never remove underscores inside identifiers (`no_change` and `record_result` must survive). Treat table pipes and list markers as clause boundaries. Each form gets a fixture.
  - **Exemptions are clause-scoped, not line-scoped (R1-3):**
    - The existing `_FINAL_REPLY_EXEMPT` waiver is narrowed so it covers only the clause that routes content into the final reply. "Notify Kent via WhatsApp; include errors in your final reply." must be flagged; it passes today.
    - The new negation exemption attaches directly to the matched verb, so "Do not skip this: record no_change" stays flagged.
    - Negative controls cover two clauses sharing one line.
  - **Regexes stay linear** (no nested quantifiers) to hold NFR-003.

### IC-02 — Doctrine and skill wording

- **Purpose**: carry the revised retry rule into every announce prompt, and make the escalation skill's dedup text true.
- **Relevant requirements**: FR-003, FR-004, NFR-002
- **Affected surfaces**:
  - `DELIVERY_DOCTRINE_BLOCK`;
  - the three announce `AGENTS.md` sources;
  - `scripts/openclaw/skills/escalation/SKILL.md` §7 (L278–286);
  - the test clause that pins the old retry phrase.
- **Sequencing/depends-on**: IC-01, which owns the same module. Sequence them to avoid conflicts.
- **Risks**: escalation headroom falls from 120 to 95 units, so any further addition must be offset. The block is asserted byte for byte, so all copies change in one commit.

### IC-03 — Skill coverage pin

- **Purpose**: guarantee that no skill an announce agent reads can reintroduce a send path.
- **Relevant requirements**: FR-005, SC-003
- **Affected surfaces**: `test_delivery_doctrine.py`. The skill list is derived from each agent's configured `skills` and its prompt references, not hard-coded where it can drift.
- **Sequencing/depends-on**: IC-01, so the test uses the improved guard.
- **Risks**: the agent→skill map lives in office2 config. The test reads a committed mirror, and a mismatch with live config is checked in the canary.

### IC-04 — Capability deny on office2

- **Purpose**: remove the forbidden tool groups from the three announce agents in live config.
- **Relevant requirements**: FR-006, FR-007, C-001, C-002, SC-002, SC-004
- **Affected surfaces**:
  - new `scripts/deploy/deploy-announce-agent-tool-deny.py`, with its tests;
  - `deploys/queued/announce-agent-tool-deny.yaml`;
  - the Architecture Impact docs above.
- **Sequencing/depends-on**: none for the build. In deploy order it lands in the same merge as IC-01 to IC-03. Prompts sync first (about 5 min), and the deny applies on the deployer's next tick; either order is safe, because the doctrine already forbids the tools.
- **Risks**:
  1. The entrypoint must be idempotent: re-applying when the deny is already present is a no-op.
  2. It must back up the config and confirm that a hash of every other `agents.entries.*` and of the top-level `tools` is unchanged.
  3. It must refuse when the live shape differs from expected (missing entry, existing `tools.allow` that would conflict).
  4. **Reload is confirmed by three checks, not by read-back alone (R1-1):**
     - a bounded wait for the Gateway's reload acknowledgement in its log;
     - an unchanged gateway process identity (PID and start time), which proves hot reload rather than a restart;
     - `openclaw config get` read-back, which proves only what was persisted.
  5. **Capability removal needs its own evidence (R1-1):** a clean scheduled run proves nothing on its own, because runs were already clean before hardening (research Q3).
     - WP04 first finds a read-only way to list each target agent's *effective* tool catalog; the OpenClaw CLI or Gateway may offer one.
     - That inspection must show the four groups absent and `exec`/`wait` and the runtime tools present.
     - If no read-only path exists, the canary records that capability removal rests on the persisted config plus the documented policy order. That is a weaker check, and it is reported as such, not as a pass.
  6. **Rollback goes through the Gateway, scoped to the three keys (R1-2):**
     - If the manifest is still queued, remove it from `deploys/queued/` first, so the deployer does not re-apply it.
     - Then apply one validated `openclaw config patch` that restores only the three agents' original `tools` values. Those values come from a recovery receipt the entrypoint writes before its first change and keeps across retries; it distinguishes an absent key from an empty array.
     - Restoring the whole-file backup is the last resort only, because it can overwrite unrelated later config.

## Verification

- **Pre-merge:**
  - guard and entrypoint tests are green, and each new test is shown red first (NFR-001);
  - size-cap tests pass;
  - manifest schema validation passes;
  - the entrypoint dry-run runs against the fixture.
- **Post-merge operator canary (SC-002 and SC-004), recorded on #1146:**
  - deployed `AGENTS.md` and `SKILL.md` are byte-identical to the repo;
  - the applied record for `announce-agent-tool-deny` (found by name; it carries `apply_mode` and `applied_at`) shows a successful terminal rebaseline disposition (R1-7);
  - `openclaw config get agents.entries.<id>.tools.deny` returns the four entries for each agent, with a reload acknowledgement and an unchanged gateway PID;
  - the effective-catalog inspection shows the four groups absent and the runtime tools present, or records explicitly that no read-only path exists (R1-1);
  - the other entries' hashes are unchanged;
  - the next scheduled capture, escalation and habits runs are ok and delivered, with zero calls to a denied tool;
  - the deploy record shows a rebaseline outcome.

## Post-plan review

**Round 1, 2026-11-27.** Reviewer: Codex gpt-6.1-sol, read-only, independent of the planner (claude-opus-5-5). Verdict: PROCEED WITH CHANGES. No MAJOR findings, 6 MINOR and 1 NIT, all folded in above. Each fix is tagged R1-n where it appears.

| ID | Finding | Disposition |
|---|---|---|
| R1-1 | A clean canary run does not prove capability removal; read-back does not prove reload | Folded: effective-catalog inspection, or an explicit weaker-check record; reload acknowledgement plus unchanged gateway PID |
| R1-2 | Whole-file rollback bypasses Gateway ownership and can be re-applied by a still-queued manifest | Folded: dequeue first; a scoped Gateway patch from a recovery receipt |
| R1-3 | The line-wide final-reply exemption already hides a forbidden clause | Folded: clause-scoped exemptions with negative controls |
| R1-4 | The normalisation contract was incomplete (identifier underscores, table and list boundaries) | Folded: paired-delimiter removal only; boundary fixtures |
| R1-5 | Moving the fixture breaks `test_openclaw_config_schema.py` | Folded: in scope and run together |
| R1-6 | `--backup-confirmed` cannot reach the entrypoint | Folded: removed; the library's backup-state path is used |
| R1-7 | Queued manifests are unnumbered; applied records carry `apply_mode`/`applied_at` | Folded |
