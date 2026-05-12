# Tasks: Inbox Capture Dedup and Parser Hardening

**Mission**: `inbox-capture-dedup-and-parser-hardening-01KREZJ8`
**Generated**: 2026-05-12
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Research**: [research.md](./research.md) · **Data model**: [data-model.md](./data-model.md) · **Contracts**: [contracts/](./contracts/) · **Quickstart**: [quickstart.md](./quickstart.md)

**Branch contract**: current `main` · planning/base `main` · merge target `main` · matches: true.

---

## Subtask Index (reference only — not a tracking surface)

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create `tests/inbox/conftest.py` + fixture corpus (well-formed, leading-ws, BOM, missing-close, invalid-yaml) | WP01 | — |
| T002 | Implement `scripts/inbox/routing_log.py` (Reader + Writer) per `contracts/routing-log.md` | WP01 | — |
| T003 | Write `tests/inbox/test_routing_log.py` covering read / append / dedup / malformed-line handling | WP01 | [P] with T002 |
| T004 | Extend `scripts/inbox/prescan.py` classifier: add 4 parse-failure cases per `contracts/prescan-classifier.md` | WP02 | — |
| T005 | Extend prescan output JSON: add `parse_failures`, `dedup_skipped`, `marker_cleanup_needed` fields | WP02 | — |
| T006 | Wire routing-log dedup filter into prescan classifier (`unprocessed_paths` filtered post-classification) | WP02 | — |
| T007 | Write `tests/inbox/test_prescan_parse_failure.py` covering each parse-failure case + dedup + regression | WP02 | — |
| T008 | Implement `scripts/inbox/inject_parse_error_marker.py` per `contracts/callout-marker.md` | WP03 | — |
| T009 | Implement `scripts/inbox/strip_parse_error_marker.py` per same contract | WP03 | [P] with T008 |
| T010 | Implement `scripts/inbox/append_routing_entry.py` CLI wrapper per `contracts/routing-log.md` | WP03 | [P] |
| T011 | Write `tests/inbox/test_callout_marker.py` covering inject (insert / replace-in-place / preserve-content), strip (present / absent / preserve), atomic-write | WP03 | — |
| T012 | Implement `scripts/inbox/file_inbox_quality_issue.py` per `contracts/inbox-quality-issue-writer.md` | WP04 | — |
| T013 | Write `tests/inbox/test_inbox_quality_issue_writer.py` covering dedup (existing / fuzzy / empty) + new-issue path + title/body templating + failure paths | WP04 | — |
| T014 | Update `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` §Step 1 to consume `parse_failures` + `dedup_skipped` from prescan output | WP05 | — |
| T015 | Update AGENTS.md §Step 5 (and new sub-steps) to invoke `append_routing_entry.py` after route + invoke `inject_parse_error_marker.py` at end-of-turn | WP05 | — |
| T016 | Update AGENTS.md to invoke `file_inbox_quality_issue.py` at end-of-turn when parse_failures non-empty | WP05 | — |
| T017 | Update AGENTS.md to handle `marker_cleanup_needed` (invoke `strip_parse_error_marker.py` during Step 5 frontmatter write) | WP05 | — |
| T018 | Add `service-inventory.json` notes to `felix-admin-capture` agent entry mentioning the new routing log state file at `~/second-brain/agents/state/inbox-routing.jsonl` | WP06 | — |
| T019 | Update `service-inventory.md` narrative to reflect the new state file + behavioral summary | WP06 | [P] with T018 |
| T020 | Update `docs/runbooks/inbox-ops.md` with the new operator workflow ("when an Inbox quality issue appears, ...") | WP06 | [P] |

Total: **20 subtasks** across **6 WPs**, average ~3.3 per WP.

---

## Dependency graph

```
WP01 (foundation: routing-log module + fixtures)
 ├── WP02 (defensive parser in prescan — uses routing_log)
 │    └── WP05
 ├── WP03 (helper scripts: inject/strip marker + append-entry CLI)
 │    └── WP05
 ├── WP04 (inbox-quality issue writer — independent of WP02/WP03)
 │    └── WP05
 └── WP05 (AGENTS.md workflow — integrates all helpers)
      └── WP06 (architecture docs)
```

**Parallel opportunities**:

- WP02 ∥ WP03 ∥ WP04 after WP01 (different files, independent surfaces)
- WP06 mostly orthogonal to WP05 (different file scopes; sequenced for accuracy)

**MVP scope**: WP01 + WP02 + WP05 produces the dedup-via-routing-log fix and parse-failure halt. WP03 + WP04 + WP06 add the user-experience helpers (marker, batched issue, doc updates). Both groups are required to close #185 fully.

---

## Work Packages

### WP01 — Foundation: routing-log module + fixture corpus

**Goal**: Build `scripts/inbox/routing_log.py` and lay down the test fixture corpus that downstream WPs reuse.

**Priority**: Foundation. Every other WP either uses the routing log directly or tests against the fixtures.

**Independent test**: `pytest tests/inbox/test_routing_log.py -v` is green.

**Subtasks**:

- [ ] T001 Create `tests/inbox/conftest.py` + fixture corpus (well-formed, leading-ws, BOM, missing-close, invalid-yaml) (WP01)
- [ ] T002 Implement `scripts/inbox/routing_log.py` (Reader + Writer) per contracts/routing-log.md (WP01)
- [ ] T003 Write `tests/inbox/test_routing_log.py` covering read / append / dedup / malformed-line handling (WP01)

**Implementation sketch**: T001 lays fixtures the rest of the mission references. T002 implements the public API: `RoutingLogReader.routed_filenames()`, `RoutingLogReader.has(filename)`, `RoutingLogWriter.append(...)`. Atomic append via simple `open(path, "a")`. T003 wraps it with focused tests using `tmp_path` so the real `~/second-brain/agents/state/` path isn't touched.

**Risks**: tmp_path tests must NOT accidentally write to the real routing-log path on disk. Use `monkeypatch` to redirect `Path.home()` or pass paths explicitly.

**Dependencies**: none.
**Estimated prompt size**: ~280 lines.
**Prompt**: [`tasks/WP01-foundation-routing-log-and-fixtures.md`](tasks/WP01-foundation-routing-log-and-fixtures.md)

---

### WP02 — Defensive parser in prescan.py

**Goal**: Extend `scripts/inbox/prescan.py` to detect parse-failure cases and to consult the routing log when building `unprocessed_paths`.

**Independent test**: `pytest tests/inbox/test_prescan_parse_failure.py` is green.

**Subtasks**:

- [ ] T004 Extend prescan classifier: add 4 parse-failure cases per contracts/prescan-classifier.md (WP02)
- [ ] T005 Extend prescan output JSON: add `parse_failures`, `dedup_skipped`, `marker_cleanup_needed` fields (WP02)
- [ ] T006 Wire routing-log dedup filter into prescan classifier (`unprocessed_paths` filtered post-classification) (WP02)
- [ ] T007 Write `tests/inbox/test_prescan_parse_failure.py` covering each parse-failure case + dedup + regression (WP02)

**Implementation sketch**: T004 adds 4 new detection branches before the existing well-formed path. T005 mutates prescan's `main` JSON output shape additively. T006 wires `RoutingLogReader` in (imported from routing_log.py landed in WP01). T007 covers both happy-path regression (existing mission-027 behavior preserved) and the new failure paths.

**Risks**: Don't break mission-027's regression test — Kent's existing notes with a single blank line before `---` must still classify as `unprocessed`, NOT `parse_failure`. Test coverage must explicitly demonstrate this.

**Dependencies**: WP01 (uses `routing_log` for dedup filter; uses fixtures for tests).
**Estimated prompt size**: ~350 lines.
**Prompt**: [`tasks/WP02-defensive-parser-in-prescan.md`](tasks/WP02-defensive-parser-in-prescan.md)

---

### WP03 — Helper scripts (marker inject/strip + routing-log append CLI)

**Goal**: Three thin shell-invocable Python helpers that the agent calls at runtime: `inject_parse_error_marker.py`, `strip_parse_error_marker.py`, `append_routing_entry.py`.

**Independent test**: `pytest tests/inbox/test_callout_marker.py` is green; manual test that the append CLI writes a single JSONL line.

**Subtasks**:

- [ ] T008 Implement `scripts/inbox/inject_parse_error_marker.py` per contracts/callout-marker.md (WP03)
- [ ] T009 Implement `scripts/inbox/strip_parse_error_marker.py` per same contract (WP03)
- [ ] T010 Implement `scripts/inbox/append_routing_entry.py` CLI wrapper per contracts/routing-log.md (WP03)
- [ ] T011 Write `tests/inbox/test_callout_marker.py` covering inject (insert / replace-in-place / preserve-content), strip (present / absent / preserve), atomic-write (WP03)

**Implementation sketch**: T008/T009 use `tempfile.NamedTemporaryFile` + `os.replace` for atomic writes. T010 is a thin wrapper around `routing_log.RoutingLogWriter.append`. T011 uses tmp_path notes with realistic body content.

**Risks**: marker location detection (find frontmatter close OR top-of-file) must be defensive — files with unusual structures (e.g., entirely empty) shouldn't crash the helpers.

**Dependencies**: WP01 (uses `routing_log` module for append).
**Estimated prompt size**: ~320 lines.
**Prompt**: [`tasks/WP03-helper-scripts-marker-and-routing-entry.md`](tasks/WP03-helper-scripts-marker-and-routing-entry.md)

---

### WP04 — Inbox-quality issue writer

**Goal**: `scripts/inbox/file_inbox_quality_issue.py` — title-prefix-deduped GitHub issue writer that the agent invokes at end-of-turn.

**Independent test**: `pytest tests/inbox/test_inbox_quality_issue_writer.py` is green.

**Subtasks**:

- [ ] T012 Implement `scripts/inbox/file_inbox_quality_issue.py` per contracts/inbox-quality-issue-writer.md (WP04)
- [ ] T013 Write `tests/inbox/test_inbox_quality_issue_writer.py` covering dedup (existing / fuzzy / empty) + new-issue path + title/body templating + failure paths (WP04)

**Implementation sketch**: T012 mirrors the credential-health-check `github_writer.py` shape — shell out to `gh issue list` + `gh issue create`, post-filter for stable prefix, render markdown table body. T013 stubs `subprocess.run`.

**Risks**: title-prefix is a stable contract — any drift breaks dedup. Tests must lock the prefix.

**Dependencies**: WP01 (technically independent, but ordering keeps the helper-scripts WPs grouped).
**Estimated prompt size**: ~280 lines.
**Prompt**: [`tasks/WP04-inbox-quality-issue-writer.md`](tasks/WP04-inbox-quality-issue-writer.md)

---

### WP05 — AGENTS.md workflow update

**Goal**: Update `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` to integrate all the new helpers into the agent's turn-by-turn workflow.

**Independent test**: visual review of the diff + a redeploy via `scripts/office2/deploy/felix-admin-capture.sh`; the canary procedure in `quickstart.md` is the integration test.

**Subtasks**:

- [ ] T014 Update §Step 1 to consume `parse_failures` + `dedup_skipped` from prescan output (WP05)
- [ ] T015 Update §Step 5 (and new sub-steps) to invoke `append_routing_entry.py` after route + invoke `inject_parse_error_marker.py` at end-of-turn (WP05)
- [ ] T016 Add new step: invoke `file_inbox_quality_issue.py` at end-of-turn when parse_failures non-empty (WP05)
- [ ] T017 Update AGENTS.md to handle `marker_cleanup_needed` (invoke `strip_parse_error_marker.py` during Step 5 frontmatter write) (WP05)

**Implementation sketch**: AGENTS.md is the LLM agent's prompt. Edits are mostly natural-language with embedded bash commands. Be explicit about ordering: read prescan → process unprocessed_paths → for each, write Step 5 (which now includes strip-marker if needed + append-routing-log + atomic status:processed) → at end-of-turn, file Inbox-quality issue if any parse_failures + inject markers.

**Risks**: AGENTS.md is interpreted at runtime by the LLM — overly clever / ambiguous instructions will be misinterpreted. Keep each step concrete and step-by-step.

**Dependencies**: WP01, WP02, WP03, WP04 (all helpers must exist before AGENTS.md can reference them).
**Estimated prompt size**: ~380 lines.
**Prompt**: [`tasks/WP05-agents-md-workflow-update.md`](tasks/WP05-agents-md-workflow-update.md)

---

### WP06 — Architecture documentation

**Goal**: Update the live arch docs to reflect the new state file + agent behavior (per C-008).

**Independent test**: `python3 tooling/scripts/validate_docs.py` is OK; `jq '.services[] | select(.name | contains("inbox")) | .' service-inventory.json` shows the new notes.

**Subtasks**:

- [ ] T018 Add service-inventory.json notes to felix-admin-capture entry mentioning the new routing log state file at ~/second-brain/agents/state/inbox-routing.jsonl (WP06)
- [ ] T019 Update service-inventory.md narrative to reflect the new state file + behavioral summary (WP06)
- [ ] T020 Update docs/runbooks/inbox-ops.md with the new operator workflow ("when an Inbox quality issue appears, ...") (WP06)

**Implementation sketch**: Three doc edits operating on different files; can run in parallel within the WP. JSON entry follows existing service-inventory patterns (notes field, no schema changes). Markdown updates describe the new behavior in operator-friendly terms.

**Risks**: `docs/runbooks/inbox-ops.md` exists per the repo scan; verify before T020 starts. If it's structured differently than expected, adjust the update site.

**Dependencies**: WP05 (docs reflect deployed reality).
**Estimated prompt size**: ~200 lines.
**Prompt**: [`tasks/WP06-architecture-docs.md`](tasks/WP06-architecture-docs.md)

---

## Validation summary

- **6 WPs** total. All in the 2-4 subtask range; well under the 10-subtask hard limit.
- **20 subtasks** total. All 12 FRs + relevant NFRs/Cs covered.
- **Estimated prompt sizes**: 200–380 lines per WP. All within the 200-500 ideal range.
- **No charter violations** (charter is unresolved; no gates).
- **MVP**: WP01–WP05 produces the working fix; WP06 makes it visible in the architecture record.
