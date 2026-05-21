# Tasks: Migrate escalation to JSONL state model

**Mission**: `migrate-escalation-to-jsonl-state-model-01KS5R4D`
**Mission ID**: `01KS5R4D79WQQWY2MCHZVCT85G`
**Branch**: `main` (planning + merge target)
**Generated**: 2026-05-21

Breakdown of the implementation plan into independently-deliverable work packages. Every subtask appears in exactly one work package. Tests are required (NFR-004 mandates ≥85% coverage).

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Extend DOMAIN_STATES["escalation"] in state_log_schema.py | WP01 | | [D] |
| T002 | Create scripts/escalation/ package skeleton (__init__.py) | WP01 | [D] |
| T003 | Implement scripts/escalation/schema.py (EVENT_TYPE_PARAMETERS + validators) | WP01 | | [D] |
| T004 | Create tests/escalation/__init__.py + conftest.py with shared fixtures | WP01 | [D] |
| T005 | Tests for schema.py — every event_type validation path | WP01 | | [D] |
| T006 | Implement scripts/escalation/derive_state.py (pure function + dataclasses) | WP02 | | [D] |
| T007 | Debug CLI for derive_state.py (--task-id + --project-id) | WP02 | [D] |
| T008 | Tests for derive_state — every event_type path, terminal states, snooze expiry | WP02 | | [D] |
| T009 | Implement scripts/escalation/record_completion.py with three-write ordering | WP03 | |
| T010 | CLI surface for record_completion (argparse + exit codes 0/1/2/3) | WP03 | |
| T011 | Tests for record_completion — happy paths + failure modes + idempotency | WP03 | |
| T012 | Implement scripts/escalation/hard_fail.py — bug body + dedup query | WP04 | |
| T013 | Integration with scripts/openclaw/agents/main/felix-file-issue.py | WP04 | |
| T014 | Tests for hard_fail — dedup hit/miss, double-fire prevention, re-fire on close | WP04 | |
| T015 | Implement scripts/escalation/reconcile_completions.py + ReconcileReport/HardFailEvent | WP05 | |
| T016 | CLI surface for reconcile (--project-id, --all, --dry-run, --max-tasks, --quiet) | WP05 | |
| T017 | Tests for reconcile — synthetic done, synthetic rescheduled, hard-fail integration | WP05 | |
| T018 | Implement scripts/escalation/backfill_jsonl_from_comments.py + snapshot writer | WP06 | |
| T019 | CLI surface for backfill (--project-id, --all, --dry-run, --include-resolved) | WP06 | |
| T020 | Tests for backfill — vocabulary mapping, malformed reporting, snapshot, dry-run | WP06 | |
| T021 | Update SKILL.md to invoke helpers via CLI + remove comment-parsing algorithm | WP07 | |
| T022 | Update AGENTS.md to call helpers + remove parsing logic | WP07 | |
| T023 | Audit both files for residual comment-parsing language + add v1→v2 transition note | WP07 | |
| T024 | Update docs/design/architecture/data/service-inventory.json (register scripts/escalation/*) | WP08 | [D] |
| T025 | Update docs/design/architecture/data/data-flows.json (new read/write paths) | WP08 | | [D] |
| T026 | Update markdown architecture views to match JSON sources | WP08 | | [D] |
| T027 | Rewrite docs/runbooks/escalation-ops.md with the new JSONL-based ops procedure | WP09 | |
| T028 | Verify quickstart.md matches deployed reality; pin commands/paths | WP09 | [P] |
| T029 | Add SOAK.md template + soak-monitoring checklist | WP09 | [P] |

---

## Dependency Graph

```
WP01 (schema foundation) ──┬──> WP02 (derive_state)
                           │
                           └──> WP08 (arch docs)     [parallel — no code deps]
                           
WP02 (derive_state) ───────┬──> WP03 (record_completion)
                           │
                           └──> WP04 (hard_fail)

WP03 + WP04 ───────────────┬──> WP05 (reconcile)
                           │
                           └──> WP06 (backfill)

WP03 + WP05 ──────────────────> WP07 (skill + AGENTS.md)

WP07 ─────────────────────────> WP09 (ops runbook)
```

Parallel lanes (post-finalize-tasks):
- **Lane A**: WP01 → WP02 → WP03 → WP05 → WP07 → WP09
- **Lane B**: WP04 (after WP02) — feeds WP05
- **Lane C**: WP06 (after WP03 + WP04)
- **Lane D**: WP08 (fully parallel — from WP01)

MVP scope: WP01 + WP02 + WP03 deliver record_completion + derive_state. That's the minimal slice where JSONL becomes canonical; downstream WPs are reconciliation, backfill, and agent prompt updates.

---

## Phase 1 — Foundation

### WP01 — Schema foundation + escalation package skeleton

**Goal**: Lay down the package structure, update DOMAIN_STATES["escalation"], and implement the per-event_type schema validator. Unblocks every downstream WP.
**Priority**: P0 (blocks all other code WPs)
**Dependencies**: none
**Independent test**: `pytest tests/escalation/test_schema.py -v` passes; the DOMAIN_STATES update is reflected by `python3 -c "from scripts.common.state_log_schema import DOMAIN_STATES; print(DOMAIN_STATES['escalation'])"`.
**Estimated prompt size**: ~340 lines (5 subtasks)
**Prompt**: [WP01-schema-foundation.md](tasks/WP01-schema-foundation.md)

Included subtasks:

- [x] T001 Extend DOMAIN_STATES["escalation"] in state_log_schema.py (WP01)
- [x] T002 Create scripts/escalation/ package skeleton (WP01)
- [x] T003 Implement scripts/escalation/schema.py with EVENT_TYPE_PARAMETERS + validate_event_params + EscalationSchemaError (WP01)
- [x] T004 Create tests/escalation/__init__.py + conftest.py with shared fixtures (WP01)
- [x] T005 Tests for schema.py — every event_type validation path (WP01)

Risks:
- Touching `scripts/common/state_log_schema.py` per amended C-003. Reviewer must verify diff scope is ONLY the DOMAIN_STATES["escalation"] frozenset — no other library code changed.
- Backwards compat: the old enum (`{triggered, level-1, level-2, resolved, dismissed}`) is removed in this WP. Pre-flight verified no records have ever been written under it; if any are found in the wild, halt the mission and triage.

---

### WP02 — derive_state pure function

**Goal**: Implement the pure function that converts a list of JSONL records into the current escalation state. All policy semantics (snooze expiry, next-level eligibility) live here. The single source of truth for state derivation.
**Priority**: P0 (blocks WP03, WP05)
**Dependencies**: WP01
**Independent test**: `pytest tests/escalation/test_derive_state.py -v` passes ≥85% coverage. `python3 -m scripts.escalation.derive_state --help` prints usage.
**Estimated prompt size**: ~340 lines (3 subtasks)
**Prompt**: [WP02-derive-state.md](tasks/WP02-derive-state.md)

Included subtasks:

- [x] T006 Implement scripts/escalation/derive_state.py with EscalationState dataclass + EscalationStateError (WP02)
- [x] T007 Debug CLI for derive_state.py (WP02)
- [x] T008 Tests for derive_state — every event_type path, terminal states, snooze expiry, error surface (WP02)

Risks:
- The policy walk has subtle ordering: terminal → snoozed-active → rescheduled-future → most-recent-level. Reviewer must verify each branch is reachable from at least one test fixture.

---

## Phase 2 — Write path

### WP03 — record_completion (atomic three-write)

**Goal**: Implement the atomic three-write helper used by the OpenClaw agent (and Kent's WhatsApp reply path) to record every escalation event. Vikunja side-effect first, JSONL second. Implements C-001 (write v1 comment AND JSONL during soak), FR-002 (atomic), FR-004 (snooze_until at write-time), FR-010 (felix-bot identity).
**Priority**: P0 (blocks WP05, WP06, WP07)
**Dependencies**: WP02
**Independent test**: `pytest tests/escalation/test_record_completion.py -v` passes ≥85% coverage. Manual smoke test via mocked Vikunja in conftest.
**Estimated prompt size**: ~480 lines (3 subtasks)
**Prompt**: [WP03-record-completion.md](tasks/WP03-record-completion.md)

Included subtasks:

- [ ] T009 Implement scripts/escalation/record_completion.py — record_event + idempotent_record_event with Vikunja-first ordering (WP03)
- [ ] T010 CLI surface for record_completion (argparse, flags per contracts/cli.md, exit codes 0/1/2/3) (WP03)
- [ ] T011 Tests for record_completion — happy paths, three-write ordering verified, Vikunja-failure path, JSONL-failure path, idempotency (WP03)

Risks:
- Three-write ordering is the safety invariant. If a reviewer-caught bug reorders writes (JSONL first, then Vikunja), the spec FR-002 / research D6 guarantees break. Test must verify the ordering explicitly via mock call sequence assertions.
- The v1 comment-write during soak (C-001) is easy to forget. The implementer must NOT skip the `[Felix-Escalation]` PUT step.

---

### WP04 — Hard-fail dedup + bug filing helper

**Goal**: Implement the helper module that renders the Q10 hard-fail bug body and queries gh for title-prefix dedup before filing. Used by WP05 (reconcile) and WP03 (record_completion on derive_state errors). Implements FR-009 (dedup keyed on Vikunja id).
**Priority**: P0 (blocks WP05, WP06)
**Dependencies**: WP02 (uses EscalationStateError taxonomy)
**Independent test**: `pytest tests/escalation/test_hard_fail.py -v` passes ≥85% coverage. Dedup query verified via mocked `gh` subprocess.
**Estimated prompt size**: ~320 lines (3 subtasks)
**Prompt**: [WP04-hard-fail-dedup.md](tasks/WP04-hard-fail-dedup.md)

Included subtasks:

- [ ] T012 Implement scripts/escalation/hard_fail.py — render bug body + dedup query via gh CLI (WP04)
- [ ] T013 Integration with scripts/openclaw/agents/main/felix-file-issue.py invocation (WP04)
- [ ] T014 Tests — dedup hit, dedup miss, double-fire prevention across two ticks, re-fire after issue closed (WP04)

Risks:
- The `gh` query template must use `--state open` to allow re-fire on premature issue close. Reviewer must verify against research D9.
- The bug body template must not include any second-brain paths (C-006).

---

## Phase 3 — Reconcile + backfill

### WP05 — reconcile_completions

**Goal**: Implement the reconciliation sweep that detects Vikunja state drift vs JSONL state and emits synthetic records. Implements FR-005 (detect UI-marking-done within one tick), NFR-001 (60-second budget for 50 tasks).
**Priority**: P1 (post-MVP — needed before cutover but not for the helpers themselves)
**Dependencies**: WP03, WP04
**Independent test**: `pytest tests/escalation/test_reconcile_completions.py -v` passes ≥85% coverage. CLI smoke: `python3 -m scripts.escalation.reconcile_completions --all --dry-run` returns exit 0 against a populated mock JSONL.
**Estimated prompt size**: ~400 lines (3 subtasks)
**Prompt**: [WP05-reconcile.md](tasks/WP05-reconcile.md)

Included subtasks:

- [ ] T015 Implement scripts/escalation/reconcile_completions.py — reconcile_project + ReconcileReport + HardFailEvent (WP05)
- [ ] T016 CLI surface (--project-id, --all, --dry-run, --max-tasks, --quiet) (WP05)
- [ ] T017 Tests — synthetic done emission, synthetic rescheduled emission, hard-fail integration via WP04, multi-project sweep (WP05)

Risks:
- The "rescheduled then UI-edited" handling (research D3) is subtle. Tests must cover: (a) due_date changes after the last `rescheduled` record, (b) due_date changes with no prior `rescheduled`, (c) due_date matches a `dismissed` record (terminal — no emit).

---

### WP06 — backfill_jsonl_from_comments

**Goal**: Implement the one-time replay of existing `[Felix-Escalation]` comments to JSONL records. Implements FR-006 (one-time backfill), SC-004 (all tasks backfilled).
**Priority**: P1 (needed before cutover)
**Dependencies**: WP03 (uses state_log.append via the same path), WP04 (no — backfill doesn't fire hard-fails; malformed comments are reported, not bug-filed)
**Independent test**: `pytest tests/escalation/test_backfill.py -v` passes ≥85% coverage. Dry-run on mocked Vikunja returns parsed/replayed counts.
**Estimated prompt size**: ~440 lines (3 subtasks)
**Prompt**: [WP06-backfill.md](tasks/WP06-backfill.md)

Included subtasks:

- [ ] T018 Implement scripts/escalation/backfill_jsonl_from_comments.py — backfill_project, snapshot writer, vocabulary mapping (WP06)
- [ ] T019 CLI surface (--project-id, --all, --dry-run, --include-resolved) (WP06)
- [ ] T020 Tests — vocabulary mapping per comment shape, malformed-comment reporting, snapshot writer, idempotency, dry-run (WP06)

Risks:
- The locked vocabulary mapping (data-model Entity 3) must be exact. Reviewer must verify every comment shape from SKILL.md is mapped.
- Idempotency depends on state_log.append's dedup behavior. Tests must verify a re-run produces zero new records on a clean JSONL.

---

## Phase 4 — Agent + ops + docs

### WP07 — Agent prompts (SKILL.md + AGENTS.md)

**Goal**: Update the deployed OpenClaw agent's standing orders to invoke the new helpers via CLI and stop parsing comments in-prompt. Implements FR-007, C-002 (policy unchanged), C-005 (autonomy unchanged).
**Priority**: P1 (required for cutover)
**Dependencies**: WP03 (CLI exists), WP05 (CLI exists)
**Independent test**: `grep -c "Felix-Escalation.*parse\|comment-parsing" scripts/openclaw/skills/escalation/SKILL.md scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` returns 0 for parsing-language matches; positive count for "v1 compatibility" notes referencing WP03's parity-write.
**Estimated prompt size**: ~280 lines (3 subtasks)
**Prompt**: [WP07-agent-prompts.md](tasks/WP07-agent-prompts.md)

Included subtasks:

- [ ] T021 Update scripts/openclaw/skills/escalation/SKILL.md — replace level-determination algorithm with helper invocation, remove comment-parsing (WP07)
- [ ] T022 Update scripts/openclaw/agents/felix-admin-escalation/AGENTS.md — call helpers via CLI, remove parsing logic (WP07)
- [ ] T023 Audit both files for residual comment-parsing language + add v1→v2 transition note (WP07)

Risks:
- The agent must still compose WhatsApp messages from JSONL state. The skill must explain HOW to render WhatsApp messages from `derive_state` output without re-introducing comment parsing.
- Easy to leave stale parsing language. T023 is the explicit audit step.

---

### WP08 — Architecture documentation

**Goal**: Update the JSON arch docs (service-inventory, data-flows) for the new scripts/escalation/* surfaces. Implements C-004 (in-mission doc updates), Felix Constitution Directive 5 (JSON authoritative).
**Priority**: P1
**Dependencies**: none (fully parallel)
**Independent test**: `python3 tooling/scripts/validate_docs.py docs/design/architecture/data/` returns exit 0.
**Estimated prompt size**: ~260 lines (3 subtasks)
**Prompt**: [WP08-arch-docs.md](tasks/WP08-arch-docs.md)

Included subtasks:

- [x] T024 Update docs/design/architecture/data/service-inventory.json — register scripts/escalation/* helpers (WP08)
- [x] T025 Update docs/design/architecture/data/data-flows.json — new write paths (record→Vikunja+JSONL), read paths (derive_state←JSONL) (WP08)
- [x] T026 Update markdown architecture views (services.view.md, data-flows.view.md) to match JSON sources (WP08)

Risks:
- Sub-doctrine: `updated_by` field on touched entries should read `#309`.
- Sub-doctrine: markdown ↔ JSON consistency. The kg-sync tooling will fail validation if they drift.

---

### WP09 — Operations runbook + soak monitoring

**Goal**: Rewrite the escalation ops runbook for the new JSONL-based flow. Add the SOAK.md template that operators populate during the 3-day post-cutover window. Implements FR-011 (soak), NFR-002 (95% gate), SC-006 (soak completion gate).
**Priority**: P1
**Dependencies**: WP07 (the runbook references the new SKILL.md/AGENTS.md surface)
**Independent test**: A new operator reading `docs/runbooks/escalation-ops.md` end-to-end can execute the cutover without consulting any other doc. Quickstart.md and the runbook agree on every CLI command + path.
**Estimated prompt size**: ~280 lines (3 subtasks)
**Prompt**: [WP09-ops-runbook.md](tasks/WP09-ops-runbook.md)

Included subtasks:

- [ ] T027 Rewrite docs/runbooks/escalation-ops.md with the new JSONL-based ops procedure (WP09)
- [ ] T028 Verify quickstart.md matches deployed reality; pin commands/paths (WP09)
- [ ] T029 Add SOAK.md template + soak-monitoring checklist (WP09)

Risks:
- Ops doc drift. Anyone touching ops procedures during the soak must update both this runbook AND quickstart.md — they are intentionally redundant.

---

## Estimated size summary

| WP | Subtasks | Est. lines |
|---|---|---|
| WP01 | 5 | ~340 |
| WP02 | 3 | ~340 |
| WP03 | 3 | ~480 |
| WP04 | 3 | ~320 |
| WP05 | 3 | ~400 |
| WP06 | 3 | ~440 |
| WP07 | 3 | ~280 |
| WP08 | 3 | ~260 |
| WP09 | 3 | ~280 |
| **Total** | **29** | **~3140** |

All WPs within ideal range (3-7 subtasks, 200-500 lines). No outliers.

---

## Next step

Run `spec-kitty agent mission finalize-tasks --json --mission migrate-escalation-to-jsonl-state-model-01KS5R4D` to parse dependencies into frontmatter and commit. Then `/spec-kitty.implement` (or `spec-kitty-implement-review` skill for full auto-drive).
