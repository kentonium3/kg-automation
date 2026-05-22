---
work_package_id: WP03
title: disambiguator (narrow LLM judgment)
dependencies:
- WP02
requirement_refs:
- FR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-22T16:30:00+00:00'
subtasks:
- T009
- T010
- T011
- T012
history:
- at: '2026-05-22T16:30:00+00:00'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/habits/judgment/
execution_mode: code_change
mission_id: 01KS86ZQE8GSZ77ZSGSSQMN08K
mission_slug: habits-checkin-reply-scripts-first-01KS86ZQ
owned_files:
- scripts/habits/judgment/__init__.py
- scripts/habits/judgment/disambiguate_reply.py
- scripts/habits/judgment/prompts/disambiguate_reply.prompt.md
- tests/habits/test_disambiguate_reply.py
tags: []
---

# WP03 — disambiguator (narrow LLM judgment)

## Objective

Implement the narrow LLM judgment surface that resolves ambiguous reply tokens (e.g., `"PT"` against multiple PT habits). Fires only when the parser emits `judgment_required`. Returns either a confident choice OR `clarify` (with a suggested question).

## Context

- **Spec**: FR-006 (narrow judgment surface)
- **Plan**: Phase 0 D4 (prompt structure), D5 (Haiku 4.5 model), D6 (API key path)
- **Data model**: Entity 3 (input), Entity 4 (output)
- **API contract**: `contracts/api.md` — `disambiguate`, `DisambiguationResult`, `DisambiguatorError`
- **CLI contract**: `contracts/cli.md` — flags, exit codes 0/1/3/5
- **Pattern source**: `scripts/doc_audit/judgment/client.py` (read it first; this mission mirrors the structure)
- **Dependencies**: WP02 (uses `JudgmentItem` dataclass)
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T009 — Module skeleton + dataclass + prompt template

**Purpose**: Establish the judgment subpackage + cache-aware prompt.

**Steps**:

1. Create `scripts/habits/judgment/__init__.py` (empty or with docstring).
2. Create `scripts/habits/judgment/prompts/` directory.
3. Write `scripts/habits/judgment/prompts/disambiguate_reply.prompt.md` (cache-aware structure):
   - System prompt section (large, stable, cacheable) explaining the task: "You are disambiguating a habit-tracker reply. Kent referenced an ambiguous token. Decide which one of the candidates he meant. Return STRICT JSON in one of two shapes: {'result': 'chosen', 'chosen_task_id': <int from candidates>, 'reason': '<short justification>'} OR {'result': 'clarify', 'reason': '<short>', 'suggested_question': '<one sentence ≤200 chars>'}."
   - Include examples of good vs. bad reasoning.
   - User prompt section (small, dynamic): the reply text + the ambiguous token + the candidates.
4. Create `scripts/habits/judgment/disambiguate_reply.py` with module docstring.
5. Imports: stdlib + `anthropic` SDK.
6. Module constants per contracts/api.md:
   ```python
   DEFAULT_API_KEY_PATH = Path("/data/services/openclaw/secrets/anthropic")
   DEFAULT_MODEL = "claude-haiku-4-5"
   DEFAULT_TIMEOUT_SECONDS = 30
   DEFAULT_MAX_TOKENS = 256
   PROMPT_PATH = Path(__file__).parent / "prompts" / "disambiguate_reply.prompt.md"
   ```
7. Define `DisambiguationResult` frozen dataclass per Entity 4.
8. Define `DisambiguatorError(Exception)`.
9. Import `JudgmentItem` from `scripts.habits.parse_morning_reply`.

**Files**:
- `scripts/habits/judgment/__init__.py` (small)
- `scripts/habits/judgment/disambiguate_reply.py` (~100 lines so far)
- `scripts/habits/judgment/prompts/disambiguate_reply.prompt.md` (~80 lines)

**Validation**:
- [ ] Prompt file is well-structured Markdown with clear system/user sections.
- [ ] Import smoke: `python3 -c "from scripts.habits.judgment.disambiguate_reply import disambiguate, DisambiguationResult, DisambiguatorError; print('ok')"` prints `ok`.

---

### T010 — disambiguate() function

**Purpose**: The HTTP call to Anthropic + response parsing + validation.

**Steps**:

1. Helper `_read_api_key(path: Path) -> str` — file read + strip; raises FileNotFoundError.
2. Helper `_load_prompt_template() -> tuple[str, str]` — read PROMPT_PATH, split into system / user template based on a known section marker (e.g., `## System` / `## User Template`).
3. `disambiguate(*, reply_text: str, ambiguity: JudgmentItem, model: str = DEFAULT_MODEL, api_key_path: Path = DEFAULT_API_KEY_PATH, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> DisambiguationResult`:
   - Load API key.
   - Load prompt template (system + user_template).
   - Build user message: format `user_template.format(reply_text=reply_text, token=ambiguity.token, candidates=...)` where candidates is a formatted block listing each candidate with `task_id: <id>, title: <title>`.
   - Construct Anthropic client: `anthropic.Anthropic(api_key=key)`.
   - Single-turn call: `client.messages.create(model=model, max_tokens=DEFAULT_MAX_TOKENS, system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}], messages=[{"role": "user", "content": user_message}], timeout=timeout)`.
   - Extract text response from `response.content[0].text`.
   - Parse JSON. On JSONDecodeError: raise DisambiguatorError("invalid JSON: ...").
   - Validate against Entity 4 shape: `result` in `{"chosen", "clarify"}`; required fields present.
   - If `result == "chosen"`: verify `chosen_task_id in ambiguity.candidate_task_ids`. If not, raise DisambiguatorError("out-of-set chosen_task_id").
   - Return `DisambiguationResult`.

**Files**: same module, +~150 lines.

**Validation**:
- [ ] No third-party imports beyond `anthropic`.
- [ ] All DisambiguatorError paths have clear error messages.
- [ ] Out-of-set chosen_task_id is rejected (defense against LLM drift).

---

### T011 — CLI surface

**Purpose**: Per contracts/cli.md.

**Steps**:

1. `def main(argv=None) -> int` with argparse:
   - `--input-file <path>` (optional; reads stdin if absent)
   - `--model <str>` (default DEFAULT_MODEL)
   - `--api-key-path <path>` (default DEFAULT_API_KEY_PATH)
   - `--timeout <int>` (default 30)
2. Read input JSON from `--input-file` or stdin. Schema per Entity 3 (`{schema_version, reply_text, ambiguity: {token, candidate_task_ids, candidate_titles, inferred_state}}`).
3. Build `JudgmentItem` from the input.
4. Call `disambiguate(...)`.
5. Emit `DisambiguationResult` as JSON to stdout.
6. Exit codes per contracts/cli.md: 0 / 1 / 3 / 5.
7. `if __name__ == "__main__": sys.exit(main())`.

**Files**: same module, +~60 lines.

**Validation**:
- [ ] `python3 -m scripts.habits.judgment.disambiguate_reply --help` exits 0.

---

### T012 — Tests

**Purpose**: ≥85% coverage; verify chosen + clarify + out-of-set paths.

**Steps**:

1. Create `tests/habits/test_disambiguate_reply.py`.
2. Mock the `anthropic` SDK (monkeypatch the `Anthropic` class or use `unittest.mock`).
3. Test cases:
   - **chosen happy path**: mock Anthropic to return `{"result": "chosen", "chosen_task_id": 19, "reason": "..."}`. Call disambiguate; assert DisambiguationResult.result == "chosen", chosen_task_id == 19.
   - **clarify happy path**: mock to return `{"result": "clarify", "reason": "...", "suggested_question": "Did you mean morning or evening?"}`. Assert correctly populated.
   - **out-of-set chosen_task_id raises**: mock to return `{"result": "chosen", "chosen_task_id": 999}` where 999 not in candidates. Assert DisambiguatorError raised with "out-of-set" in message.
   - **malformed JSON raises**: mock to return `"not JSON"`. Assert DisambiguatorError raised.
   - **missing required field raises**: mock returns `{"result": "chosen"}` (no chosen_task_id). Assert DisambiguatorError.
   - **invalid result value**: mock returns `{"result": "unknown"}`. Assert DisambiguatorError.
   - **API key file missing**: monkeypatch to FileNotFoundError. Assert FileNotFoundError propagates.
   - **API timeout**: mock Anthropic to raise on timeout. Assert exception propagates (caller's exit 1 path).
   - **Prompt template loading**: verify the prompt file is read and parsed into system + user sections.
   - **Cache-control marker present**: assert the messages.create call's system parameter includes the cache_control marker.
   - **CLI exit 0 on chosen**: invoke main with valid input + mocked Anthropic returning chosen → assert return 0.
   - **CLI exit 5 on out-of-set**: invoke main with mocked Anthropic returning out-of-set ID → assert return 5.
   - **CLI exit 3 on bad input JSON**: invoke main with malformed input → assert return 3.

**Files**: `tests/habits/test_disambiguate_reply.py` (~280 lines, ~16 tests).

**Validation**:
- [ ] All tests green; ≥85% coverage.
- [ ] No live Anthropic API calls in any test.
- [ ] Out-of-set rejection is explicitly tested.

---

## Branch Strategy

Planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Test Strategy

pytest with mocked `anthropic.Anthropic`. No live LLM calls. ≥85% coverage including all DisambiguatorError paths.

## Definition of Done

- [ ] All 4 subtasks complete.
- [ ] `pytest tests/habits/test_disambiguate_reply.py -v` ≥85%.
- [ ] No regression on existing habits tests.
- [ ] Out-of-set chosen_task_id raises DisambiguatorError (verified test).
- [ ] Prompt template has both system and user sections.

## Risks

- **Prompt drift**: tests must verify the system prompt produces strict JSON. If the LLM drifts to free-text responses, parsing fails. Mitigation: explicit "Return STRICT JSON" instruction in the prompt + max_tokens=256 keeps output bounded.
- **Anthropic SDK version drift**: pin SDK behavior expectations in tests; if SDK signature changes, tests must catch it.
- **API key file permissions**: mode 0600 on office2; tests use tmp_path with relaxed perms.

## Reviewer Guidance

1. Verify the prompt template is cache-aware (system block has cache_control marker).
2. Verify out-of-set chosen_task_id rejection — this is the load-bearing safety check.
3. Verify all DisambiguatorError paths have clear messages.
4. Coverage ≥85%.

## Implementation Command

```bash
spec-kitty agent action implement WP03 --mission habits-checkin-reply-scripts-first-01KS86ZQ --agent claude:opus:python-implementer:implementer
```
