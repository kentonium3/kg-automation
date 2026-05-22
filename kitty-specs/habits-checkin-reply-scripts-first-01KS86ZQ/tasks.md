# Tasks: Habits check-in + reply scripts-first port

**Mission**: `habits-checkin-reply-scripts-first-01KS86ZQ`
**Mission ID**: `01KS86ZQE8GSZ77ZSGSSQMN08K`
**Branch**: `main` (planning + merge target)
**Generated**: 2026-05-22

5 work packages, 19 subtasks. Mirrors mission #309's lane structure (parallel implementation lanes; doc work in its own lane).

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | morning_checkin_list.py module skeleton + MorningList/MorningListHabit dataclasses + module constants | WP01 | | [D] |
| T002 | build_morning_list + persist_morning_list + render_morning_message functions | WP01 | | [D] |
| T003 | CLI surface for morning_checkin_list (argparse + exit codes 0/1/2/3) | WP01 | | [D] |
| T004 | Tests for morning_checkin_list — happy paths, atomic write, empty-habits, time-zone correctness | WP01 | | [D] |
| T005 | parse_morning_reply.py module skeleton + ParseResult/ParseTuple/JudgmentItem/ParseError dataclasses | WP02 | |
| T006 | parse_reply core logic — special tokens + tokenization + 3-tier matching (position → exact → substring) | WP02 | |
| T007 | load_morning_list + CLI surface for parse_morning_reply (exit codes 0/1/3/4/5) | WP02 | |
| T008 | Tests for parse_morning_reply — including the SC-002 fixture for 2026-05-22 ("Skipped 3,7,8 done") | WP02 | |
| T009 | Disambiguator module skeleton + DisambiguationResult dataclass + cache-aware prompt template | WP03 | |
| T010 | disambiguate() function — Anthropic HTTP call, response parse + validation | WP03 | |
| T011 | CLI surface for disambiguator (exit codes 0/1/3/5) | WP03 | |
| T012 | Tests for disambiguator — mocked Anthropic SDK; chosen + clarify + out-of-set rejection | WP03 | |
| T013 | Build new AGENTS.md following D10 cuts + Entity 5 skeleton (≤14K source chars) | WP04 | |
| T014 | Audit AGENTS.md for residual fuzzy-match prose; verify char count + grep clean | WP04 | |
| T015 | Update scripts/openclaw/agents/felix-admin-habits/AGENTS.md in repo | WP04 | |
| T016 | Update docs/design/architecture/data/service-inventory.json (3 new helpers + felix-admin-habits update) | WP05 | [P] |
| T017 | Update docs/design/architecture/data/data-flows.json (new write/read paths) | WP05 | |
| T018 | Update markdown architecture views to match JSON sources | WP05 | |
| T019 | Rewrite docs/runbooks/habits-ops.md for the v2 scripts-first flow | WP05 | [P] |

---

## Dependency Graph

```
WP01 (morning_checkin_list) ──┐
                              ├──> WP04 (AGENTS.md cut)
WP02 (parse_morning_reply) ───┼──> WP03 (disambiguator) ───┘
                              │
WP05 (docs)  [parallel — no code deps]
```

Lanes (post-finalize-tasks):
- **Lane A**: WP01 → WP04
- **Lane B**: WP02 → WP03 (feeds WP04)
- **Lane C**: WP05 (fully parallel)

MVP scope: WP01 + WP02 + WP04 delivers a working scripts-first flow. WP03 (disambiguator) is the narrow-LLM judgment layer; without it, ambiguous replies surface to Kent as clarifying questions immediately (acceptable degraded mode).

---

## Phase 1 — Helpers

### WP01 — morning_checkin_list helper

**Goal**: Implement the helper that emits today's ordered habit list both as the WhatsApp message text and as the persisted JSON artifact. This is the single source of truth that ordering bug #371 traces back to.
**Priority**: P0 (blocks WP04)
**Dependencies**: none
**Independent test**: `pytest tests/habits/test_morning_checkin_list.py -v` ≥85% coverage. `python3 -m scripts.habits.morning_checkin_list --dry-run` emits a valid formatted message.
**Estimated prompt size**: ~380 lines (4 subtasks)
**Prompt**: [WP01-morning-checkin-list.md](tasks/WP01-morning-checkin-list.md)

Included subtasks:
- [x] T001 Module skeleton + dataclasses + module constants (WP01)
- [x] T002 build_morning_list + persist_morning_list + render_morning_message (WP01)
- [x] T003 CLI surface (WP01)
- [x] T004 Tests (WP01)

Risks:
- Determinism of ordering — must use stable Vikunja task_id sort, not creation-time or any other potentially-shifting attribute.
- Atomic write — tmp + fsync + rename pattern; verify via test that partial-write scenarios don't leave a corrupt file.
- TZ correctness — date must be Kent-local (America/New_York), not UTC.

---

### WP02 — parse_morning_reply helper

**Goal**: Implement the deterministic reply parser. The single most important guarantee: byte-determinism (same inputs → same outputs).
**Priority**: P0 (blocks WP03 + WP04)
**Dependencies**: none (structurally independent of WP01; shares no Python types)
**Independent test**: SC-002 test scenario passes — "Skipped 3,7,8 done" against the 2026-05-22 fixture produces exactly the intent Kent expressed.
**Estimated prompt size**: ~420 lines (4 subtasks)
**Prompt**: [WP02-parse-morning-reply.md](tasks/WP02-parse-morning-reply.md)

Included subtasks:
- [ ] T005 Module skeleton + dataclasses (WP02)
- [ ] T006 parse_reply core logic (WP02)
- [ ] T007 load_morning_list + CLI (WP02)
- [ ] T008 Tests including SC-002 fixture (WP02)

Risks:
- Tokenization edge cases — what counts as a "token boundary" in `"Skipped 3,7,8 done"` vs `"skipping 3, 7, and 8"` vs `"skipping 3 7 8"`? Tests must cover.
- Substring uniqueness — `"PT"` against `["Morning shoulder PT", "Evening shoulder PT", "Morning hip PT"]` MUST yield judgment_required, not silent pick.
- State inference — must correctly attribute the verb (done/skipped/incomplete) to each token within a clause.

---

### WP03 — disambiguator (narrow LLM judgment)

**Goal**: Implement the LLM-judgment surface for ambiguous reply tokens. Fires only when the parser emits judgment_required. Returns chosen OR clarify.
**Priority**: P1 (blocks WP04 if we want AGENTS.md to invoke it; degraded mode possible without)
**Dependencies**: WP02 (uses JudgmentItem dataclass)
**Independent test**: `pytest tests/habits/test_disambiguate_reply.py -v` ≥85% coverage. Mocked Anthropic returns are validated against schema; out-of-set chosen_task_id raises.
**Estimated prompt size**: ~320 lines (4 subtasks)
**Prompt**: [WP03-disambiguator.md](tasks/WP03-disambiguator.md)

Included subtasks:
- [ ] T009 Module skeleton + dataclass + prompt template (WP03)
- [ ] T010 disambiguate() function — Anthropic call + validation (WP03)
- [ ] T011 CLI surface (WP03)
- [ ] T012 Tests (WP03)

Risks:
- Prompt drift — system prompt must produce strict JSON; small changes can break parsing. Tests must verify across edge cases.
- API key handling — same path as doc-auditor; verify file permissions and read pattern match the existing `scripts/doc_audit/judgment/client.py`.
- Cache invalidation — system prompt is cacheable; user prompt varies. Verify the cache-control marker is set correctly.

---

## Phase 2 — Agent integration

### WP04 — AGENTS.md cut + audit

**Goal**: Rewrite the felix-admin-habits AGENTS.md to invoke the three new helpers via CLI and remove the prose that caused the #371 bug. Target: ≤14,000 source chars (vs. current 24,383).
**Priority**: P0 (blocks WP05's runbook accuracy)
**Dependencies**: WP01, WP02, WP03 (CLI invocations must reference real, working helpers)
**Independent test**: `wc -c scripts/openclaw/agents/felix-admin-habits/AGENTS.md` returns ≤14000. Audit grep finds no imperative parsing prose. CLI examples match deployed helper `--help` output.
**Estimated prompt size**: ~260 lines (3 subtasks)
**Prompt**: [WP04-agents-md-cut.md](tasks/WP04-agents-md-cut.md)

Included subtasks:
- [ ] T013 Build new AGENTS.md following data-model.md Entity 5 (WP04)
- [ ] T014 Audit grep + char-count verification (WP04)
- [ ] T015 Update repo file at scripts/openclaw/agents/felix-admin-habits/AGENTS.md (WP04)

Risks:
- Over-cut — removing the wrong section breaks tick flow. Keep: identity, output discipline, tick skeleton, fallback behavior. The data-model Entity 5 skeleton is the floor.
- CLI accuracy — every example MUST match the actual `--help` output of WP01/WP02/WP03 helpers. Run `--help` in the worktree to confirm before commit.
- Truncation budget — the openclaw `~26% inflation` is empirical; 14K source might still hit the 20K hard limit if the inflation worsens. Test on office2 by deploying and watching journalctl.

---

## Phase 3 — Documentation

### WP05 — Architecture docs + ops runbook

**Goal**: Update arch JSON + markdown views + the ops runbook for the v2 flow. Implements C-007.
**Priority**: P1
**Dependencies**: none (can run parallel with everything)
**Independent test**: `tooling/scripts/validate_docs.py` (or project's standard validator) passes. Runbook walks end-to-end without ambiguity.
**Estimated prompt size**: ~340 lines (4 subtasks)
**Prompt**: [WP05-docs.md](tasks/WP05-docs.md)

Included subtasks:
- [ ] T016 service-inventory.json — register 3 new helpers + update felix-admin-habits entry (WP05)
- [ ] T017 data-flows.json — new write/read paths (WP05)
- [ ] T018 Markdown views match JSON (WP05)
- [ ] T019 docs/runbooks/habits-ops.md — rewrite for v2 flow (WP05)

Risks:
- JSON ↔ markdown drift — every JSON entry needs a markdown counterpart.
- Runbook accuracy — CLI examples must match contracts/cli.md exactly. Cross-reference quickstart.md (already in mission planning) so the operator has one source of truth.

---

## Estimated size summary

| WP | Subtasks | Est. lines |
|---|---|---|
| WP01 | 4 | ~380 |
| WP02 | 4 | ~420 |
| WP03 | 4 | ~320 |
| WP04 | 3 | ~260 |
| WP05 | 4 | ~340 |
| **Total** | **19** | **~1720** |

All WPs within ideal range (3-7 subtasks, 200-500 lines).

---

## Next step

Run `spec-kitty agent mission finalize-tasks --mission habits-checkin-reply-scripts-first-01KS86ZQ --json` to parse dependencies + commit. Then auto-drive via the spec-kitty-implement-review skill.
