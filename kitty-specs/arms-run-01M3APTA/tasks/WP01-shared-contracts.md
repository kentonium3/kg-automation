---
work_package_id: WP01
title: Shared contracts — text form, prompt, questions, serving
dependencies: []
requirement_refs:
- C-002
- FR-003
- FR-011
- NFR-005
planning_base_branch: feat/849-arms-run
merge_target_branch: feat/849-arms-run
branch_strategy: Planning artifacts for this mission were generated on feat/849-arms-run. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-arms-run unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-arms-run-01M3APTA
base_commit: 1b9271f9762845d1c0536cd9289cf5e48d59d225
created_at: '2026-09-25T00:35:27.555569+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 0 - Foundation
history: []
agent_profile: python-pedro
authoritative_surface: scripts/research/arms849/
create_intent:
- scripts/research/arms849/__init__.py
- scripts/research/arms849/text.py
- scripts/research/arms849/prompt.py
- scripts/research/arms849/questions.py
- scripts/research/arms849/serving.py
- tests/research/test_arms849_text.py
- tests/research/test_arms849_prompt.py
- tests/research/test_arms849_questions.py
- tests/research/test_arms849_serving.py
execution_mode: code_change
owned_files:
- scripts/research/arms849/__init__.py
- scripts/research/arms849/text.py
- scripts/research/arms849/prompt.py
- scripts/research/arms849/questions.py
- scripts/research/arms849/serving.py
- tests/research/test_arms849_text.py
- tests/research/test_arms849_prompt.py
- tests/research/test_arms849_questions.py
- tests/research/test_arms849_serving.py
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP01 — Shared contracts

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load`
(profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope,
and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch**: `feat/849-arms-run`
- **Final merge target**: `feat/849-arms-run`
- `/spec-kitty.implement` populates the actual worktree `base_branch` from `lanes.json`.
- If human instructions contradict these fields, stop and resolve the landing branch.

## Objective

Create the four things every arm must share — the text form, the registered prompt, the question
manifest, the serving configuration — each with **exactly one definition**, so the three arms can
differ only in retrieval. Everything here returns **frozen bytes or registered constants**; nothing
here computes a value and then treats it as authoritative. Read first: `research.md` D-5, D-7,
D-11, D-13, D-14; `contracts/text-form.md`, `contracts/arm-interface.md`; rubric §2, §3, §3.2,
Amendment A4 (`docs/design/research/849-rubric.md`).

The existing code you build beside (do not modify in this WP): `scripts/research/load_849_corpus.py`
(`replay()`, `Loaded`, `ARM_INPUTS`, `REGISTRATION`), `scripts/research/run_849_harness.py`.
Helper modules are invoked as `python3 -m scripts.research.arms849.<module>`; keep the package
importable under `scripts.research.arms849`.

## Subtasks

### T001 — `arms849/text.py`: frozen bytes, never a re-dump

**Purpose**: the shared text form (contracts/text-form.md). An event's text is the exact line from
the frozen `stream.jsonl`; entities and edges get one canonical line each, produced once; blocks
are concatenation only.

**Steps**:
1. `class FrozenCorpusText` constructed from a corpus directory (default
   `load_849_corpus.DEFAULT_CORPUS`): reads `stream.jsonl` as **bytes**, splits on `\n`, and maps
   each line's `ref` (parse the JSON only to read `ref`) → the original line bytes (without the
   trailing newline). Never re-serialise an event.
2. Record lines: from `entities.json`, produce ONE canonical line per entity and per edge:
   `json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")`, keyed by
   `id` for entities and by `f"{from}-{type}->{to}"` for edges. Compute
   `record_lines_digest` = sha256 over all record lines in key order joined by `\n` + `\n`. This
   is the **only** serialisation in the whole arms package; WP04's preflight records the digest.
3. `event_line(ref) -> bytes`, `record_line(key) -> bytes`, both raising `KeyError` with the
   missing key named.
4. `@dataclass(frozen=True) class Block: event_refs: tuple[str,...]; record_keys: tuple[str,...];
   data: bytes` and `render_block(event_refs, record_keys) -> Block` = event lines in the given
   order, then record lines in the given order, each followed by `\n`. `Block.sha256` property.
5. `render_full_view(view: Loaded) -> Block`: helper for D — all event refs in view order, then
   entity keys in view order, then edge keys in view order (D-7: events, entities, edges).

**Files**: `scripts/research/arms849/__init__.py` (docstring: what the package is, what it must
never do — see FR-013), `scripts/research/arms849/text.py` (~150 lines).

**Validation**: `event_line(ref) == corpus line bytes` for every ref (5,750); `render_block`
output bytes == concatenation; a `Block` cannot be built from strings.

### T002 — `arms849/prompt.py`: the registered §3.2 prompt

**Purpose**: FR-011, D-14, contracts/gates.md `prompt_digest`.

**Steps**:
1. `REGISTERED_TEXT: str` — the §3.2 fenced text **copied verbatim** from the rubric (16 lines),
   including the literal slots `{assembled_context}` and `{question_text}`.
2. `REGISTERED_DIGEST = "0aa7ee77560b1f5cbbb04a6c3dfa90749dfd79305b4207134c62d9fdd733af45"` — a
   constant, cited to rubric §3.2 (A4). Never computed-then-stored.
3. `normalise(text) -> bytes`: UTF-8; CRLF→LF; per-line trailing whitespace stripped; exactly one
   trailing `\n`. `digest(text) -> str`.
4. `class Prompt`: `__init__` asserts `digest(REGISTERED_TEXT) == REGISTERED_DIGEST` and raises
   `PromptDriftError` naming both digests otherwise. `render(block: Block, question_text: str) ->
   bytes` substitutes the two slots exactly once each (the block's bytes decoded as UTF-8; refuse
   a `str` block), and returns the request body text as bytes. The slot text outside the block is
   never modified.
5. Module-level `verify() -> tuple[bool, str]` used by WP04's gate.

**Files**: `scripts/research/arms849/prompt.py` (~90 lines).

**Validation**: digest of the shipped text equals the constant (this is the test that must exist
and must fail when one character changes); render inserts the block and question exactly once.

### T003 — `arms849/questions.py`: the manifest and its digest

**Purpose**: the oracle-free question registry (rubric §3, A4); the harness never passes a bare id.

**Steps**:
1. `@dataclass(frozen=True) class Question: id: str; arc: str; ask_time: str; text: str`.
2. `QUESTIONS: tuple[Question, ...]` — the eight rows of the §3 table **verbatim**, in order
   (C1, A, F1, B1, E2, E1, F2, B2) with their ISO ask_times and texts.
3. `MANIFEST_DIGEST = "fe17beef263777261e5d623ed8362ebaaada60ffbb0fd20b10b1f4d7a820c462"`.
4. `manifest_bytes()`: the eight JSON lines `{"ask_time": …, "question": <id>, "question_text": …}`
   with `sort_keys=True`, default `json.dumps` escaping, LF-joined, trailing LF, UTF-8 — exactly
   the A4 rule. `verify()` compares its sha256 to the constant.
5. `by_id(q) -> Question`; `ask_time_dt(q) -> datetime` (aware).

**Files**: `scripts/research/arms849/questions.py` (~70 lines).

**Validation**: `verify()` is true against the shipped rows; changing one character of any text
fails it; ask_times ascend in manifest order (they are the protocol order).

### T004 — `arms849/serving.py`: the serving configuration and the client

**Purpose**: D-5, D-6, D-11, D-13; FR-003; contracts/arm-interface.md.

**Steps**:
1. `@dataclass(frozen=True) class ServingConfiguration` with every field in data-model.md
   §ServingConfiguration: `model, gguf_sha256, image_digest, n_ctx, rope_scaling, rope_scale,
   yarn_orig_ctx, parallel, cache_prompt, sampling (temperature 0.7, top_p 0.8, top_k 20,
   repeat_penalty 1.05, min_p 0), seed_policy "1000+repeat", max_tokens 2048, embedder, reranker,
   tokenizer`. Two constructors: `primary()` and `secondary_yarn()`; `as_header_dict()`;
   `differs_from(other) -> set[str]` (SC-006 asserts the secondary differs in exactly
   `{rope_scaling, rope_scale, yarn_orig_ctx, n_ctx}`).
2. `limits(kind: "primary"|"secondary") -> Limits(trained=262144, configured=n_ctx,
   permitted=n_ctx - max_tokens)`; `limit_applied` = `trained` for primary, `permitted` for
   secondary (D-11).
3. `Tokenizer`: loads the cached Qwen tokenizer (`transformers` tokenizer classes only; refuse if
   `torch` is importable — env_clean). `count(bytes) -> int`. `equivalence_check(server_url,
   sample_lines) -> (ok, detail)`: 100 corpus lines client-side vs the server's `/tokenize`; any
   difference is a failure naming the first differing line.
4. `serialize(prompt_bytes) -> dict`: the exact `/completion` request body (`prompt`, sampling
   fields, `seed`, `n_predict = max_tokens`, `cache_prompt`, `stream: false`). `count_tokens(body)`
   counts the exact `prompt` string that will be sent (the chat template is NOT applied by the
   harness — the registered prompt is sent raw to `/completion`; record that fact in the
   docstring so nobody later "fixes" it into `/v1/chat/completions` and changes the token count).
5. `complete(body, base_url="http://127.0.0.1:18080") -> Completion` with the **explicit timings
   mapping** (D-13): `prompt_n`, `cache_n`, `prompt_ms`, `predicted_n`, `predicted_ms`,
   `predicted_per_second` → `prompt_tokens, cache_read_tokens, uncached_tokens = prompt_n −
   cache_n, cache_write_tokens = uncached, prefill_s, output_tokens, generation_s,
   generation_tok_s, cache_state = "cold" if cache_n == 0 else "warm", cache_fraction =
   cache_n / prompt_n, finish_reason ("stop" | "length" from `stop_type`/`stopped_limit`),
   truncated`. Raise `TelemetryMissing(field)` if any required field is absent — a scored row is
   never produced without them. Refuse to construct if `OPENAI_API_KEY` is set in the environment
   or `base_url` is not loopback (adversarial A4).

**Files**: `scripts/research/arms849/serving.py` (~220 lines).

**Validation**: primary vs secondary differ in exactly four fields; `limits` arithmetic; a fake
server response missing `cache_n` raises `TelemetryMissing`; a set `OPENAI_API_KEY` refuses.

### T005 — Tests

**Files**: `tests/research/test_arms849_text.py`, `test_arms849_prompt.py`,
`test_arms849_questions.py`, `test_arms849_serving.py` (total ~300 lines). Follow the house
pattern in `tests/research/test_load_849_corpus.py`: real corpus (skip if `build/849-corpus` is
absent), every check paired with an injected defect, docstrings that say why.

Must include: (a) every event line equals the corpus bytes; (b) `render_block` is pure
concatenation; (c) the record-line digest is stable across two constructions; (d) prompt digest
equals the A4 constant and fails on a one-character change; (e) question manifest digest equals
the A4 constant; (f) manifest ask_times ascend; (g) serving `differs_from` exact set;
(h) `TelemetryMissing`; (i) loopback/API-key refusal; (j) `Tokenizer.count` on B2's full block
returns > 262,144 (using the cached tokenizer; skip if the cache is absent — WP02 installs it).

## Definition of Done

- All four modules importable as `scripts.research.arms849.*`; no module reads anything under
  `docs/design/research/849-synthesis/` except the corpus directory passed in; the string
  `oracle` appears nowhere in the package (WP04's static scan will enforce it).
- `python3 -m pytest tests/research/ -q` green; full suite green.
- `spec-kitty agent tasks mark-status T001 T002 T003 T004 T005 --status done`.

## Risks / reviewer guidance

- The re-serialisation trap: any `json.dumps` of an **event** anywhere in this package is a
  defect (D-7). Reviewer: grep the package for `json.dumps` — it may appear exactly once, in the
  record-line builder.
- Prompt drift: `REGISTERED_TEXT` must be byte-for-byte the rubric text; reviewer recomputes the
  digest from the rubric independently.
- Token counting must be over the exact `prompt` field that is sent — not the block alone.
