# Tasks: Task-Intake Validation Loop

**Mission**: task-intake-validation-loop-01KXS06W · **Branch**: `feat/task-intake-validation-loop`
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Contracts**: [contracts/helpers.contract.md](./contracts/helpers.contract.md)

Tests are **required** for this mission (NFR-001/002/003; deterministic helpers).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Reconcile live #715 label ids (f:/q:/t:/loe:) via seam owner_token=kent | WP01 | |
| T002 | Declare labels in `vikunja_refs.json` (owner kent) | WP01 | |
| T003 | Extend `vikunja_refs_validate.py` drift/AST gate for new labels | WP01 | |
| T004 | Unit tests: `label_id(name,"kent")` per label + drift gate green | WP01 | |
| T005 | `scan_inbox.py`: enumerate not-done Inbox tasks (felix-bot read, seam id) | WP02 | |
| T006 | Tier-1 classification (project≠Inbox + schedulable f: + q:; f:4 excluded) | WP02 | |
| T007 | Immutable per-`digest_id` correlation record + `latest.json` + 48h expiry | WP02 | |
| T008 | Tick observability artifact + `--dry-run`/`--now-utc`/`--json` CLI | WP02 | |
| T009 | Unit tests: classification, correlation immutability, injectable clock, SC-009 | WP02 | |
| T010 | Sparse line grammar parser (`<n> [project] [f] [q] [tier2]`), line-independent | WP03 | [P] |
| T011 | Token resolution against seam + alias table (case-insensitive) | WP03 | [P] |
| T012 | Constrained `--unresolved {line,token,position,canonical_name}` re-resolution | WP03 | [P] |
| T013 | Unit tests: 100% documented-token coverage (NFR-002); aliases; sparse; echo-back | WP03 | [P] |
| T014 | Correlation selection (line-number set + title evidence, 48h) → task ids | WP04 | |
| T015 | kent-token RMW apply + readback diff; family-replace q:/f:; q:eliminate→done | WP04 | |
| T016 | Tier-2 compatibility matrix + non-blocking due follow-up; f:4 decomposition-pending | WP04 | |
| T017 | Per-line status set + refined noop + aggregates + apply ledger | WP04 | |
| T018 | `apply_reply.py` CLI (`--reply -`/`--state-dir`/`--window-hours`/`--unresolved`/`--dry-run`/`--json`); timeouts | WP04 | |
| T019 | Unit tests: family-replace non-clobber (NFR-003), Tier-2 cells, each status, idempotency | WP04 | |
| T020 | Capture `AGENTS.md`: run scan after route_and_finalize + emit digest (Output Discipline) | WP05 | |
| T021 | Main `AGENTS.md`/`TOOLS.md`: content-based correlate + invoke apply + confirm; LLM boundary | WP05 | |
| T022 | Verify AGENTS.md byte-cap headroom; no Directive-6 leak | WP05 | |
| T023 | `deploys/queued/<name>.yaml`: state dir + kent-token assert + self-pull + rebaseline not-required | WP06 | |
| T024 | Update `vikunja-configuration-design.md` (loop implemented) | WP06 | |
| T025 | Architecture data (service-inventory + data-flows JSON+md/view) + `docs/runbooks/intake-ops.md` + INDEX + DEVELOPER_PORTAL | WP06 | |
| T026 | felix-capability-roadmap status + #750 closure note | WP06 | |

## Work Packages

### WP01 — Seam label taxonomy declaration
**Goal:** declare the friction/Eisenhower/type/LOE label ids in the #748 seam so all resolution is fail-loud + drift-gated. **Priority:** foundational. **Independent test:** `label_id("f:3-edge","kent")` resolves; `vikunja_refs_validate.py` green. **Deps:** none. **Prompt:** ~200 lines.
- [x] T001 Reconcile live #715 label ids via seam owner_token=kent (WP01)
- [x] T002 Declare labels in `vikunja_refs.json` (owner kent) (WP01)
- [x] T003 Extend `vikunja_refs_validate.py` drift/AST gate (WP01)
- [x] T004 Unit tests: per-label resolution + drift gate (WP01)

### WP02 — Inbox scan, Tier-1 classification, correlation record
**Goal:** deterministic scan + classification + immutable per-digest correlation record + tick artifact + digest render. **Priority:** foundational. **Independent test:** scan a mocked Inbox → correct incomplete set + digest text + immutable record; SC-009. **Deps:** WP01. **Prompt:** ~320 lines.
- [x] T005 `scan_inbox.py` enumerate not-done Inbox tasks (WP02)
- [x] T006 Tier-1 classification incl. f:4 exclusion (WP02)
- [x] T007 Immutable per-`digest_id` record + `latest.json` + 48h expiry (WP02)
- [x] T008 Tick artifact + CLI flags (WP02)
- [x] T009 Unit tests (WP02)

### WP03 — Shorthand parser + token resolution
**Goal:** sparse-grammar parser + seam-backed token resolution + constrained LLM-fallback interface. **Priority:** foundational. **Independent test:** 100% documented tokens resolve without LLM; sparse lines parse; unresolved → echo-back. **Deps:** WP01. **Parallel with WP02.** **Prompt:** ~280 lines.
- [x] T010 Sparse line grammar parser (WP03)
- [x] T011 Token resolution + alias table (WP03)
- [x] T012 Constrained `--unresolved` re-resolution (WP03)
- [x] T013 Unit tests (WP03)

### WP04 — Apply engine
**Goal:** correlation selection + kent-token RMW apply with family-replace + Tier-2 matrix + per-line statuses + `apply_reply.py`. **Priority:** core. **Independent test:** apply a shorthand reply against a mocked task → correct family-replace, statuses, Tier-2, idempotency (NFR-003). **Deps:** WP01, WP02, WP03. **Prompt:** ~420 lines.
- [ ] T014 Correlation selection (WP04)
- [ ] T015 kent-token RMW + family-replace + q:eliminate→done (WP04)
- [ ] T016 Tier-2 matrix + due follow-up + f:4 disposition (WP04)
- [ ] T017 Per-line statuses + aggregates + ledger (WP04)
- [ ] T018 `apply_reply.py` CLI (WP04)
- [ ] T019 Unit tests (WP04)

### WP05 — Agent wiring (capture + main prompts)
**Goal:** capture agent runs scan + emits digest; main agent content-correlates + invokes apply + confirms; LLM-fallback boundary. **Priority:** integration. **Independent test:** prompt review shows single-command scan emit + reply-apply path; AGENTS.md under byte cap. **Deps:** WP02, WP04. **Prompt:** ~240 lines.
- [ ] T020 Capture `AGENTS.md` scan+digest (WP05)
- [ ] T021 Main `AGENTS.md`/`TOOLS.md` correlate+apply+confirm (WP05)
- [ ] T022 Byte-cap + Directive-6 leak check (WP05)

### WP06 — Deploy manifest + docs sync + #750 closure
**Goal:** deploy manifest (state dir + kent-token assert) + full doc synchronization + #750 closure. **Priority:** release. **Independent test:** manifest validates; docs updated per signal-to-doc-map; #750 closure note present. **Deps:** WP01–WP05. **Prompt:** ~230 lines.
- [ ] T023 `deploys/queued/<name>.yaml` (WP06)
- [ ] T024 `vikunja-configuration-design.md` update (WP06)
- [ ] T025 Architecture data + runbook + INDEX + DEVELOPER_PORTAL (WP06)
- [ ] T026 Roadmap status + #750 closure note (WP06)

## Dependencies
```
WP01 ─┬─ WP02 ─┬─ WP04 ── WP05 ── WP06
      └─ WP03 ─┘
```
WP02 and WP03 are parallel (both depend only on WP01). WP04 joins them. WP05 needs WP02+WP04. WP06 is last.

## MVP scope
WP01→WP02→WP03→WP04 deliver the deterministic engine (scan + digest + apply). WP05 wires the agents; WP06 deploys + documents + closes #750.
