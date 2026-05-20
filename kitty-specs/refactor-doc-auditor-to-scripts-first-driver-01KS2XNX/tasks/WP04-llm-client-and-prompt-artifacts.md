---
work_package_id: WP04
title: LLM client and prompt artifacts
dependencies:
- WP02
requirement_refs:
- FR-002
- FR-011
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T016
- T017
- T018
- T019
- T020
- T021
phase: Phase 2 — Components
assignee: ''
agent: "codex:gpt-5:spec-kitty-review:reviewer"
shell_pid: "67057"
history:
- timestamp: '2026-05-20T16:25:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/doc_audit/judgment/
execution_mode: code_change
owned_files:
- scripts/doc_audit/judgment/**
- scripts/doc_audit/prompts/**
- tests/doc_audit/judgment/**
tags: []
---

# Work Package Prompt: WP04 — LLM client and prompt artifacts

## Objective

Implement the Anthropic SDK wrapper (`judgment/client.py`) with prompt-cache support, the three checked-in judgment-prompt templates, and the three judgment-moment Python modules. This is the LLM surface the driver invokes at narrow points per spec FR-002 and `contracts/judgment-prompts.contract.md`.

## Context

- Three judgment moments per Q2=C: `tier_classification`, `debt_body_generation`, `cross_file_implication`.
- Each judgment moment is a separate `.prompt.md` file (FR-011 reviewability) AND a separate Python module (one function per moment).
- Prompt-cache layout per research D2: `[CACHE_PREFIX_START]` and `[CACHE_PREFIX_END]` markers split the template; the cached prefix gets `cache_control: {"type": "ephemeral"}` in the API call.
- Response parsing per contract: JSON for `tier_classification` and `cross_file_implication`; structured markdown for `debt_body_generation`.
- On malformed response: log, demote to docs-debt (safe default), continue.

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per lane; run `spec-kitty agent action implement WP04 --agent <name>`.

## Subtasks

### T016 — Implement `judgment/client.py`

**Purpose**: Single chokepoint for Anthropic SDK access. Handles authentication, prompt-cache marker placement, response shape, and retry semantics.

**Steps**:

1. Create `scripts/doc_audit/judgment/__init__.py` (empty for now).

2. Create `scripts/doc_audit/judgment/client.py`:

   ```python
   from anthropic import Anthropic
   from dataclasses import dataclass
   from pathlib import Path
   from doc_audit.config import Config

   @dataclass
   class JudgmentResponse:
       """Parsed result of one judgment LLM call."""
       content: str           # raw text response
       input_tokens: int
       cache_hit_input_tokens: int
       output_tokens: int
       stop_reason: str

   class JudgmentClient:
       def __init__(self, config: Config) -> None:
           self.config = config
           api_key = read_api_key(config)  # from config.py
           self.client = Anthropic(api_key=api_key)
           self.model = config.llm.model
           self.max_tokens = config.llm.max_tokens

       def call(self, prompt_template_path: Path, variable_section: str) -> JudgmentResponse:
           """Execute one judgment call with prompt caching on the boilerplate prefix."""
           template = prompt_template_path.read_text()
           cached_prefix, _ = self._split_cache_markers(template)

           response = self.client.messages.create(
               model=self.model,
               max_tokens=self.max_tokens,
               system=[
                   {
                       "type": "text",
                       "text": cached_prefix,
                       "cache_control": {"type": "ephemeral"}
                   }
               ],
               messages=[
                   {"role": "user", "content": variable_section}
               ],
           )
           return JudgmentResponse(
               content=response.content[0].text,
               input_tokens=response.usage.input_tokens,
               cache_hit_input_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
               output_tokens=response.usage.output_tokens,
               stop_reason=response.stop_reason,
           )

       def _split_cache_markers(self, template: str) -> tuple[str, str]:
           """Extract content between [CACHE_PREFIX_START] and [CACHE_PREFIX_END] markers."""
           start_marker = "[CACHE_PREFIX_START]"
           end_marker = "[CACHE_PREFIX_END]"
           start = template.index(start_marker) + len(start_marker)
           end = template.index(end_marker)
           cached = template[start:end].strip()
           rest = template[template.index(end_marker) + len(end_marker):].strip()
           return cached, rest
   ```

3. Module docstring cross-references the judgment-prompts contract.

4. Error handling:
   - On `anthropic.APIError`: re-raise (driver decides retry vs surface)
   - On malformed template (missing cache markers): wrap `_split_cache_markers`'s `ValueError` (from `.index()` lookup) and re-raise with the message `"Prompt template missing or misordered [CACHE_PREFIX_START]/[CACHE_PREFIX_END] markers: {template_path}"`. The default `.index()` error is too vague — caller needs the template path.

5. **Guardrail awareness — NOT in the client**: `JudgmentClient.call()` does NOT check guardrail status. The guardrail short-circuit lives in the `tier_classification` module (T020 step 5), invoked BEFORE `client.call()`. The client is a pure prompt-template-driven LLM caller — it has no awareness of doc-audit business rules. This is by design: keeps the client reusable for any future judgment moment.

**Files**:
- New: `scripts/doc_audit/judgment/__init__.py`
- New: `scripts/doc_audit/judgment/client.py` (~150 lines)

**Validation**:
- [ ] `JudgmentClient(config).call(prompt_path, vars)` returns a JudgmentResponse with all fields populated
- [ ] `_split_cache_markers()` works on a synthetic template with markers
- [ ] Missing markers raise ValueError
- [ ] Authentication: no key in logs

---

### T017 — Write `prompts/tier_classification.prompt.md`

**Purpose**: The cache-aware template for the `tier_classification` LLM call.

**Steps**:

1. Create `scripts/doc_audit/prompts/tier_classification.prompt.md` per `contracts/judgment-prompts.contract.md` Moment 1 specification.

2. Frontmatter:
   ```yaml
   ---
   name: tier_classification
   version: 0.1.0
   last_updated: 2026-05-20
   inherits_classification_from: scripts/openclaw/skills/doc-audit/SKILL.md §4
   ---
   ```

3. Boilerplate section content (between `[CACHE_PREFIX_START]` and `[CACHE_PREFIX_END]`) — **exact section list**:
   - SKILL.md §4.1.a — paste **only categories #1 (frontmatter `last_updated`/`last_validated`/`revision` updates) and #4 (`updated_by` references for new entries)**. Skip §4.1.a's intro prose if it adds tokens without classification value.
   - SKILL.md §4.1.b — paste **all of categories #2 (service version numbers), #3 (file paths after rename), #5 (removing dead references), #6 (agent registry entry add), #7 (autonomy level update)**. That's all 5 Tier-B categories.
   - SKILL.md §4.2 — paste all 5 judgment categories verbatim.
   - **DO NOT** include SKILL.md §4.3 (constitutional guardrails). Guardrails are enforced by the driver's deterministic path check BEFORE the LLM is called (T020 step 5). Putting them in the prompt wastes tokens AND risks the LLM mis-applying them.
   - Concrete output schema:
     ```
     Return a single JSON object on one line:
     {"tier": "tier_a" | "tier_b" | "judgment", "rationale": "<one-line>"}

     No prose before or after the JSON. No markdown fences.
     ```
   - One example per tier (Tier A: frontmatter date bump; Tier B: service version; judgment: prose rewrite)

4. Per-call inputs section (after `[CACHE_PREFIX_END]`):
   ```
   # Per-call inputs

   ## Proposed edit
   - doc_path: {{doc_path}}
   - change_type: {{change_type}}
   - current_value: {{current_value}}
   - proposed_value: {{proposed_value}}
   - evidence_source: {{evidence_source}}

   ## Context
   - audit_area_labels: {{audit_area_labels}}
   - guardrail_check_result: {{guardrail_check_result}}

   ## Doc frontmatter excerpt
   {{doc_frontmatter_excerpt}}

   ---

   Classify this edit. Return the JSON.
   ```

**Files**:
- New: `scripts/doc_audit/prompts/tier_classification.prompt.md` (~150 lines)

**Validation**:
- [ ] File has the two cache markers
- [ ] Frontmatter parses as YAML
- [ ] Includes all 7 categories enumerated in SKILL.md §4.1
- [ ] Output schema is unambiguous (reviewer can predict valid responses)

---

### T018 — Write `prompts/debt_body_generation.prompt.md`

**Purpose**: Template for composing docs-debt issue bodies per SKILL.md §8.

**Steps**:

1. Create with frontmatter per T017 pattern (name=`debt_body_generation`, version=`0.1.0`).

2. Boilerplate section content:
   - Verbatim SKILL.md §8 template requirements (the 6 sections explained)
   - Concrete output schema: structured markdown with all 6 H2 headers
   - One worked example from SKILL.md §11 Example C

3. Per-call inputs section:
   - `{{artifact_path}}` (doc path, existing or proposed)
   - `{{gap_description}}` (2-4 sentences)
   - `{{evidence_source}}`
   - `{{area_labels}}`
   - `{{originating_audit_number}}`
   - `{{cross_references}}` (additional refs beyond the audit)
   - Instruction: "Produce the issue body in markdown. Include all 6 H2 sections. The 'Draft outline' section is the most important — make it specific enough that a downstream Claude Code session can act without further research."

**Files**:
- New: `scripts/doc_audit/prompts/debt_body_generation.prompt.md` (~120 lines)

**Validation**:
- [ ] Cache markers present
- [ ] Output schema lists all 6 sections (Artifact, Gap description, Area, Cross-references, Draft outline, Success criteria)
- [ ] Worked example demonstrates the "Draft outline" load-bearing field

---

### T019 — Write `prompts/cross_file_implication.prompt.md`

**Purpose**: Template for detecting implied drift in non-touched in-scope docs.

**Steps**:

1. Create with frontmatter per T017 pattern (name=`cross_file_implication`, version=`0.1.0`).

2. Boilerplate section content:
   - Verbatim SKILL.md §4.2 #5 (interpretation-of-intent rules)
   - The signal-to-doc-map.json mappings (paste the file's `mappings` list as JSON; for drift-event triggers, the LLM uses these as priors for which docs are affected)
   - Output schema:
     ```json
     {
       "implications": [
         {
           "untouched_file": "docs/<path>",
           "implication": "<2-3 sentences>",
           "evidence": "<which part of the triggering event>",
           "suggested_action": "judgment"
         }
       ]
     }
     ```
   - Note: `implications` is empty if nothing applies
   - One worked example showing a commit that implies drift in a non-touched doc

3. Per-call inputs section:
   - `{{triggering_event_kind}}` ("commit" | "drift_event")
   - `{{triggering_event_summary}}` (one-line summary)
   - `{{diff_excerpt}}` (up to 300 lines of relevant diff)
   - `{{touched_files}}` (list)
   - `{{in_scope_files}}` (list — paths only, not contents)
   - `{{domain_labels}}`
   - Instruction: "Identify in-scope files NOT in touched_files that this event likely implies drift in. Be conservative — only flag if the evidence is clear. Return empty list if no implications."

**Files**:
- New: `scripts/doc_audit/prompts/cross_file_implication.prompt.md` (~130 lines)

**Validation**:
- [ ] Cache markers present
- [ ] Output schema enforces the implications array shape
- [ ] LLM receives only the PATHS of in-scope files (not their contents) — keeps context small

---

### T020 — Implement three judgment modules

**Purpose**: One Python module per judgment moment, providing a typed function that calls into `JudgmentClient` and parses the response.

**Steps**:

1. **`judgment/tier_classification.py`**:
   ```python
   from doc_audit.data_model import ProposedEdit, EditTier
   from doc_audit.judgment.client import JudgmentClient, JudgmentResponse
   from pathlib import Path
   import json

   PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "tier_classification.prompt.md"

   def classify(
       client: JudgmentClient,
       proposed_edit: ProposedEdit,
       audit_area_labels: list[str],
       doc_frontmatter_excerpt: str,
       guardrail_check_result: str,
   ) -> tuple[EditTier, str, JudgmentResponse]:
       """Returns (tier, rationale, usage_metrics)."""
       variable_section = _render_inputs(...)
       response = client.call(PROMPT_PATH, variable_section)
       parsed = _parse_response(response.content)  # JSON parse + validation
       return EditTier(parsed["tier"]), parsed["rationale"], response

   def _render_inputs(...) -> str: ...
   def _parse_response(content: str) -> dict: ...
   ```

2. **`judgment/debt_body_generation.py`**: same pattern with `generate(client, gap_info) -> tuple[str, JudgmentResponse]` returning the issue body markdown.

3. **`judgment/cross_file_implication.py`**: same pattern with `detect(client, event_info) -> tuple[list[dict], JudgmentResponse]` returning the implications list.

4. **Response parsing & validation**:
   - For JSON-returning prompts: try `json.loads()`; on failure, log + return safe default (`EditTier.JUDGMENT` for tier_classification; `[]` for cross_file_implication)
   - For markdown-returning prompt: validate all 6 H2 sections present; on missing section, log + insert stub

5. **Defense-in-depth on tier_classification**:
   - If guardrail_check_result is "guardrailed", short-circuit BEFORE the LLM call and return `EditTier.JUDGMENT` directly with rationale "guardrailed path — never auto-edited"
   - If LLM returns `tier_a` for a guardrailed path (shouldn't happen because of short-circuit), demote and log gate violation

**Files**:
- New: `scripts/doc_audit/judgment/tier_classification.py` (~120 lines)
- New: `scripts/doc_audit/judgment/debt_body_generation.py` (~100 lines)
- New: `scripts/doc_audit/judgment/cross_file_implication.py` (~110 lines)

**Validation**:
- [ ] Each module's main function callable from REPL with a mocked client
- [ ] Schema validation catches malformed responses and returns safe defaults
- [ ] Guardrail short-circuit works (no LLM call when guardrailed)

---

### T021 [P] — Unit tests with mocked Anthropic SDK

**Purpose**: Test each judgment moment in isolation against canned LLM responses.

**Steps**:

1. Create `tests/doc_audit/judgment/__init__.py`.

2. Create `tests/doc_audit/judgment/test_client.py`:
   - **test_call_splits_cache_markers**: synthetic template with markers → cached prefix and variable section extracted correctly
   - **test_call_missing_markers_raises**: template without markers → ValueError
   - **test_call_records_usage_metrics**: mock SDK returns response with usage; JudgmentResponse populated correctly

3. Create `tests/doc_audit/judgment/test_tier_classification.py`:
   - **test_classify_tier_a**: mock LLM returns `{"tier": "tier_a", "rationale": "frontmatter date"}` → returns `(EditTier.TIER_A, "frontmatter date", response)`
   - **test_classify_tier_b**: similar for tier_b
   - **test_classify_judgment**: similar for judgment
   - **test_classify_malformed_json_falls_back**: LLM returns garbage → returns `EditTier.JUDGMENT` (safe default)
   - **test_classify_guardrailed_shortcircuits**: guardrail_check_result="guardrailed" → no LLM call made, returns JUDGMENT
   - **test_classify_invalid_tier_value**: LLM returns `{"tier": "wrong"}` → falls back to JUDGMENT

4. Create `tests/doc_audit/judgment/test_debt_body_generation.py`:
   - **test_generate_complete_body**: mock LLM returns valid 6-section markdown → returns the body unchanged
   - **test_generate_missing_section_stubs**: LLM omits "Draft outline" → stub inserted with placeholder
   - **test_generate_includes_originating_audit_ref**: input has audit_number=320 → output body references "Refs #320"

5. Create `tests/doc_audit/judgment/test_cross_file_implication.py`:
   - **test_detect_empty**: LLM returns `{"implications": []}` → returns `[]`
   - **test_detect_one_implication**: LLM returns one implication → returned as-is
   - **test_detect_malformed_falls_back**: garbage → returns `[]`

**Files**:
- New: `tests/doc_audit/judgment/__init__.py`
- New: `tests/doc_audit/judgment/test_client.py` (~120 lines)
- New: `tests/doc_audit/judgment/test_tier_classification.py` (~150 lines)
- New: `tests/doc_audit/judgment/test_debt_body_generation.py` (~120 lines)
- New: `tests/doc_audit/judgment/test_cross_file_implication.py` (~110 lines)

**Validation**:
- [ ] All tests pass
- [ ] Coverage of `judgment/` modules ≥85%

---

## Definition of Done

- [ ] `JudgmentClient` instantiated from Config; uses Anthropic SDK with prompt caching
- [ ] Three prompt templates exist with cache markers, frontmatter, and complete I/O schemas
- [ ] Three judgment modules wrap the client + parse responses + validate schemas
- [ ] Guardrail short-circuit on tier_classification (defense in depth)
- [ ] Safe-default behavior on malformed LLM responses
- [ ] Unit tests pass with mocked Anthropic SDK
- [ ] FR-011 reviewability: a reader of the three `.prompt.md` files can enumerate everything the LLM is asked

## Risks

| Risk | Mitigation |
|---|---|
| LLM returns malformed JSON breaking the driver | Safe defaults documented + tested; one bad classification ≠ broken tick |
| Prompt-cache markers misplaced → invariant prefix changes per call → no cache hits | Template structure tested; integration test confirms cache_hit_input_tokens >0 on second call within a tick |
| Anthropic API key leaked via log/error message | Code search: NO `print(api_key)`, NO `logger.info(api_key)` anywhere; review carefully |
| `anthropic` SDK version drift breaks API call shape | Pin a specific version in any requirements file; document the version in module docstring |

## Reviewer Guidance

- Verify each `.prompt.md` file has both cache markers in correct position
- Verify the three judgment modules cite their respective prompt file paths
- Verify safe-default behavior (LLM returns garbage → no driver crash)
- Spot-check NO LLM call is made when guardrail short-circuit triggers (audit `tests/doc_audit/judgment/test_tier_classification.py::test_classify_guardrailed_shortcircuits`)
- Confirm API key never appears in logs or error messages

## Implementation Command

```bash
spec-kitty agent action implement WP04 --agent <name>
```

## Cross-references

- **Contract**: `contracts/judgment-prompts.contract.md`
- **Data model**: E-004 ProposedEdit, E-005 EditTier, E-006 DebtIssue
- **Research**: D1 (model + SDK), D2 (prompt caching), D12 (prompt template inventory)
- **Spec**: FR-002, FR-011, NFR-005

## Activity Log

- 2026-05-20T19:00:12Z – claude:opus-4.7:implementer:implementer – shell_pid=64832 – Started implementation via action command
- 2026-05-20T19:11:53Z – claude:opus-4.7:implementer:implementer – shell_pid=64832 – Ready for review: Anthropic SDK wrapper + 3 prompt artifacts + 3 judgment modules. 32 unit tests pass, coverage 86%-100% per module. Guardrail short-circuit verified.
- 2026-05-20T19:12:43Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=67057 – Started review via action command
- 2026-05-20T19:16:00Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=67057 – Moved to planned
