# Tasks: Prefix IDLE Cron Replies With Agent Slug

**Mission**: `idle-cron-reply-agent-prefix-01KV1BSS`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md) | **Contract**: [contracts/hard-rule-1.md](./contracts/hard-rule-1.md) | **Issue**: kentonium3/kg-automation#592
**Branch contract**: planning/base `feat/idle-cron-reply-agent-prefix` → merge target `feat/idle-cron-reply-agent-prefix` (PR to `main` opened at the GitHub layer after spec-kitty merge).

---

## Subtask Index

| Task | Description | Work Package | Parallel |
|---|---|---|---|
| T001 | Update `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (apply canonical block + in-text refs) | WP01 | [P] |
| T002 | Update `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (apply canonical block + in-text refs) | WP01 | [P] |
| T003 | Update `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` (apply canonical block + in-text refs) | WP01 | [P] |
| T004 | Update `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` (apply canonical block + in-text refs) | WP01 | [P] |
| T005 | Implementer self-check: NFR-001 shape parity + NFR-002 size budget across all 4 files | WP01 | |
| T006 | Update `docs/design/architecture/service-inventory.md` line 239-area — IDLE reply description | WP02 | |
| T007 | Confirm `agent-prompt-sync.service` synced new AGENTS.md to `/data/services/openclaw/<workspace>/` on office2 | WP02 | |
| T008 | SC-001 verification: `openclaw cron run --wait` for `inbox-7am` / `habits-morning-checkin` / `escalation-daily`; visual WhatsApp byte-format check | WP02 | |
| T009 | SC-006 verification: `openclaw systemPromptReport --agent felix-admin-tasker` in a fresh OpenClaw session | WP02 | |
| T010 | Rebaseline per `docs/runbooks/security-baseline-ops.md`; record `Rebaseline: completed at <ts>` in merge commit (SC-005) | WP02 | |

---

## Work Packages

### WP01 — Apply canonical Hard rule #1 across 4 AGENTS.md files

**Goal**: Replace the existing "Hard rule #1 — IDLE means the literal four-character string `IDLE`…" block in each of the 4 in-scope Felix sub-agent AGENTS.md files with the canonical block specified in [`contracts/hard-rule-1.md`](./contracts/hard-rule-1.md). Substitute `<agent-slug>` per file. Update any in-text references to the old "four characters" / "bare `IDLE`" wording to the new byte-format wording. Preserve unrelated prose (Hard rule #2/#3, incident-anchor narrative, examples not directly tied to the IDLE byte form).

**Priority**: P0 — entire mission rests here. Without WP01 there's nothing to verify in WP02.

**Independent test**: After WP01 lands, each updated AGENTS.md contains the canonical Hard rule #1 block with the correct per-file slug substitution, no stale references to "the four characters IDLE" or "the bare IDLE marker", no other diff outside the rule block + surgical in-text updates, and a `wc -c` size delta of ≤ +500 bytes per file vs. pre-mission baseline.

**Estimated prompt size**: ~420 lines (5 subtasks).

**Requirements**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, NFR-001, NFR-002, NFR-003, C-005

**Dependencies**: none.

**Included subtasks**:

- [ ] T001 Update `felix-admin-capture/AGENTS.md` rule block + in-text refs
- [ ] T002 Update `felix-admin-habits/AGENTS.md` rule block + in-text refs
- [ ] T003 Update `felix-admin-tasker/AGENTS.md` rule block + in-text refs
- [ ] T004 Update `felix-admin-escalation/AGENTS.md` rule block + in-text refs
- [ ] T005 Self-check NFR-001 shape parity + NFR-002 size budget (`diff` + `wc -c`) before submitting for review

**Parallel opportunities**: T001-T004 are independent per-file edits and could be parallel-laned if spec-kitty's lane allocator chooses. T005 is sequential after T001-T004.

**Risks**:
- **Surrounding prose deletion**: each file's pre-existing rule context (capture's incident-anchor narrative, habits/tasker/escalation's shorter context) must be preserved verbatim apart from the surgical in-text updates. The canonical block REPLACES the old rule lines, not the surrounding paragraphs. Reviewer must inspect each file's pre/post diff for incidental removal of unrelated prose.
- **Per-file size headroom is tight on capture** (15,288 → 15,788 max per NFR-002). If the rule block grows beyond ~+250 bytes, capture is at risk of exceeding the relative-growth threshold; implementer measures during T005.
- **`<agent-slug>` substitution must be exact** — typos or stray placeholder bytes will fail SC-001 byte-exact verification later.

---

### WP02 — Verify deployment + doc-sync + rebaseline closeout

**Goal**: After WP01 lands and the `agent-prompt-sync.service` 5-min timer has copied the new AGENTS.md files to office2, exercise the verification surface (SC-001 cron-run WhatsApp check; SC-006 systemPromptReport for tasker), update the one in-repo narrative doc that describes the IDLE reply (`docs/design/architecture/service-inventory.md`), and run the post-deploy rebaseline per #557. Record the rebaseline marker in the merge commit.

**Priority**: P0 — the mission is not done until verification + rebaseline complete. Without WP02, the change "works" but operational claim (operator can attribute every IDLE) and audit invariant (#557 baselines reset) are unverified.

**Independent test**: After WP02 lands:
- `docs/design/architecture/service-inventory.md` line 239-area describes the new byte format (no stale "single token `IDLE`" reference).
- WhatsApp received exactly `[felix-admin-capture]: IDLE`, `[felix-admin-habits]: IDLE`, `[felix-admin-escalation]: IDLE` from the three live cron runs in T008.
- `openclaw systemPromptReport --agent felix-admin-tasker` in a fresh session contains the new Hard rule #1 block.
- `ls /data/services/security-monitor/baselines/` on office2 shows fresh timestamps; the merge commit message contains `Rebaseline: completed at <ts>`.

**Estimated prompt size**: ~430 lines (5 subtasks).

**Requirements**: FR-008, NFR-003, C-002, C-003, C-007, SC-001, SC-003, SC-005, SC-006

**Dependencies**: WP01.

**Included subtasks**:

- [ ] T006 Update `docs/design/architecture/service-inventory.md` IDLE description line
- [ ] T007 Confirm office2 deployed AGENTS.md content via `wc -c` + grep over `/data/services/openclaw/<workspace>/AGENTS.md`
- [ ] T008 Run `openclaw cron run --wait <id>` for the 3 cron-firing in-scope agents; visual WhatsApp byte-format check
- [ ] T009 Run `openclaw systemPromptReport --agent felix-admin-tasker` in a fresh OpenClaw session
- [ ] T010 Run the rebaseline command on office2 + record `Rebaseline: completed at <ts>` marker in the merge commit

**Parallel opportunities**: T006 (doc edit) is independent of T007-T009 (office2 operations) and could parallelize. T007-T010 are sequential (T007 before T008, T010 only after deploy + observations).

**Risks**:
- **Cache-staleness gotcha** ([[reference_openclaw_gotchas]]): `systemPromptReport` may return stale content if invoked in a session that started before the deploy. T009 explicitly opens a fresh session.
- **`inbox-5pm` auth-error overlap** (research R-05): if the live auth issue is still firing at T008 time, use `inbox-7am` or `inbox-10pm` instead — any of capture's 4 cron jobs satisfies SC-001 for capture.
- **Rebaseline timing**: T010 must run AFTER `agent-prompt-sync.service` has copied the new AGENTS.md to office2. T007 establishes that precondition; T010 runs only after T007 returns clean.
- **24-hour soak (SC-002) is post-merge operator-observation**, not part of WP02. The mission-acceptance gate (`/spec-kitty.accept`) verifies SC-002 only after the 24-hour window elapses.
- **No mechanical enforcement** (C-004) — if cron output drifts after the soak window, that's a future-mission concern, not a WP02 failure.
