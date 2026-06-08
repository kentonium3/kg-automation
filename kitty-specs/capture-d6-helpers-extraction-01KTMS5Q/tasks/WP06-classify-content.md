---
work_package_id: WP06
title: classify_content helper
dependencies: []
requirement_refs:
- FR-007
- FR-014
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: lane-from-coordination
subtasks:
- T011
- T012
agent: claude
history: []
agent_profile: python-pedro
authoritative_surface: scripts/inbox/
execution_mode: code_change
mission_id: 01KTMS5QGXFJWQYVXB03SPYB48
mission_slug: capture-d6-helpers-extraction-01KTMS5Q
model: claude-sonnet-4-6
owned_files:
- scripts/inbox/classify_content.py
- tests/inbox/test_classify_content.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

## Objective

Implement `scripts/inbox/classify_content.py` — read a note (frontmatter + body), split body into blocks via heuristics, apply deterministic per-block classification (regex/keyword/heading-based), emit structured `ClassificationOutput` JSON on stdout. Blocks the helper can't classify confidently are emitted with `kind: "ambiguous"` and `flag: "needs-llm-disambiguation"`.

This is the most judgment-adjacent helper. Classification heuristics MUST be documented inline per FR-014 so the follow-on AGENTS.md rewrite has a stable reference.

CLI: `python3 -m scripts.inbox.classify_content --content-file <abs-path>`

## Context

| Document | Why |
|---|---|
| [../spec.md](../spec.md) § FR-007, FR-014 | Functional contract + inline heuristic documentation |
| [../research.md](../research.md) § R-003 | Block-splitting heuristic |
| [../data-model.md](../data-model.md) § ClassificationOutput, Block | Output JSON shape |
| [../contracts/helper-cli.md](../contracts/helper-cli.md) § `classify_content` | CLI surface |
| `tests/inbox/test_classifier_regression.py` | Existing classifier-test pattern (mirror for new tests) |

## Subtask Guidance

### T011 — Tests + Implementation

**Block kinds** (per FR-007):

- `journal` — first-person reflective content; keywords: "I feel", "today I", "noticed that", "reflecting on", etc.
- `calendar` — time/date references with a verb; patterns: `<weekday> at <time>`, `<MM/DD>`, `meet`, `lunch`, `call with`, etc.
- `someday` — aspirational; keywords: "someday", "would like to", "maybe", "curious about", "should explore", etc.
- `github_issue` — markers like `gh issue:`, `bug:`, `feature request:` at start of block
- `vikunja_task` — markers like `task:`, `TODO:`, `[ ]`, or imperative leading verb without time anchor
- `parse_failure` — block is malformed (e.g., starts with `> [!error] felix-capture:` callout)
- `ambiguous` — doesn't match any of the above with confidence

**Tests** (`tests/inbox/test_classify_content.py`):

- One test per block kind for clear high-confidence cases (7 tests)
- `test_journal_with_reflective_keywords_high_confidence`
- `test_calendar_with_weekday_time_high_confidence`
- `test_calendar_with_explicit_date_high_confidence`
- `test_someday_with_aspirational_keywords_high_confidence`
- `test_github_issue_with_explicit_marker`
- `test_vikunja_task_with_todo_marker`
- `test_parse_failure_with_callout_marker`
- Ambiguous cases (3 tests):
  - `test_block_without_clear_signals_ambiguous` — short generic text → ambiguous, flag set
  - `test_mixed_signals_ambiguous` — block has both calendar AND someday signals → ambiguous
  - `test_short_block_low_confidence`
- Boundary heuristics (3 tests):
  - `test_h1_heading_starts_new_block`
  - `test_double_blank_line_starts_new_block`
  - `test_topic_keyword_starts_new_block`
- Multi-block (2 tests):
  - `test_multi_block_note_returns_multiple_blocks`
  - `test_blocks_indexed_in_order`
- Output format (3 tests):
  - `test_output_is_valid_json`
  - `test_note_filename_in_output_matches_input_basename`
  - `test_each_block_has_all_required_fields`
- Refusal (1 test):
  - `test_private_path_input_exits_3`
- Error handling (1 test):
  - `test_missing_content_file_exits_1`

Total: ~20 tests covering the kind taxonomy + boundaries + output format + edge cases.

**Implementation** (`scripts/inbox/classify_content.py`):

- Imports: `argparse`, `json`, `re`, `sys`, `pathlib`
- Module-level CONSTANT dicts for regex patterns + keyword lists per kind. Document each pattern inline.
- Function `read_note(path: Path) -> tuple[dict, str]` — returns (frontmatter, body)
- Function `split_blocks(body: str) -> list[str]` — heuristic block splitter
- Function `classify_block(content: str) -> tuple[str, str, str | None]` — returns (kind, confidence, flag)
- Function `classify_note(note_filename: str, body: str) -> dict` — orchestrator returning ClassificationOutput dict
- `main(argv=None) -> int` — CLI entry, emits JSON

**FR-014 documentation requirement**: every regex pattern + keyword list MUST have a docstring or inline comment explaining what kind it indicates and why this heuristic was chosen. The follow-on AGENTS.md rewrite agent reads these as the reference.

### T012 — Coverage gate

```bash
pytest tests/inbox/test_classify_content.py \
  --cov=scripts.inbox.classify_content \
  --cov-branch --cov-fail-under=90
```

## Definition of Done

- [ ] `scripts/inbox/classify_content.py` exists, stdlib only
- [ ] Heuristics documented inline per FR-014 (verifiable via grep for docstrings + comments)
- [ ] `tests/inbox/test_classify_content.py` exists with all ~20 cases above
- [ ] `--help` exits 0
- [ ] Coverage gate passes
- [ ] Lane committed; WP moved to `for_review`

## Risks

- Classification heuristic quality — this is the most judgment-adjacent helper. The tests should cover Kent's actual inbox patterns where possible; if real data isn't available, use synthetic blocks that exercise each kind.
- The "ambiguous" output IS the load-bearing surface for the LLM to disambiguate later. Make sure the ambiguous output is COMPLETE (full content, position, surrounding context) so the prompt can disambiguate without re-reading the source note.
