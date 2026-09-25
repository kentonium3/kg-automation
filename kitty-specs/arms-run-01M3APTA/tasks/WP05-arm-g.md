---
work_package_id: WP05
title: Arm G — Graphiti typed writes and deterministic hybrid retrieval
dependencies:
- WP01
- WP02
requirement_refs:
- C-004
- FR-004
- FR-008
- FR-012
planning_base_branch: feat/849-arms-run
merge_target_branch: feat/849-arms-run
branch_strategy: Planning artifacts for this mission were generated on feat/849-arms-run. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-arms-run unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-arms-run-01M3APTA
base_commit: 1b9271f9762845d1c0536cd9289cf5e48d59d225
created_at: '2026-09-25T02:54:15.038767+00:00'
subtasks:
- T021
- T022
- T023
- T024
- T025
phase: Phase 2 - Arms
history: []
agent_profile: python-pedro
authoritative_surface: scripts/research/arms849/arm_g.py
create_intent:
- scripts/research/arms849/embed.py
- scripts/research/arms849/arm_g.py
- tests/research/test_arms849_embed.py
- tests/research/test_arms849_arm_g.py
execution_mode: code_change
owned_files:
- scripts/research/arms849/embed.py
- scripts/research/arms849/arm_g.py
- tests/research/test_arms849_embed.py
- tests/research/test_arms849_arm_g.py
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP05 — Arm G

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

The arm under test, built **exactly** as the design lead ruled (research.md D-1, D-2, D-3, D-15;
rubric §2 G row incl. the A3 query plan): Graphiti's data model and hybrid retrieval, **none** of
its extraction. Reference implementation: the #974 harness in the comments of
kentonium3/kg-automation#974 (`rq1_validate.py`, `rq6_engine.py`, the RQ-4/RQ-5 retrieval
scripts) — read them before writing a line; the engine constraints RQ-6a/6b/6d/6e (issue #976)
are the reason for three of the rules below. The ontology's Pydantic models are in
`docs/design/second-brain-graph-layer.md` §Pydantic Entity Models (the doc is in the export).

**Hard rules the tests enforce**: `add_episode` is never called; no LLM call ever succeeds; no
query-time `valid_at` filtering; `group_id` matches `^arms_[A-Z0-9]+$`; `search(group_ids=[…])`
always explicit; one typed pull per label; assembled context is byte-identical across repeats.

## Subtasks

### T021 — `embed.py`: one embedder, one reranker, shared with R

**Steps**:
1. `Embedder`: wraps fastembed `TextEmbedding("BAAI/bge-small-en-v1.5", cache_dir=ARMS849_CACHE)`
   with `HF_HUB_OFFLINE=1`; refuses if the cache is absent (never fetches at run time);
   `embed(texts: list[str]) -> list[list[float]]`, deterministic (same text → same vector; test it).
2. A Graphiti `EmbedderClient` adapter over it (see graphiti-core 0.30.2's embedder interface and
   #974's adapter) and a `CrossEncoderClient` adapter implementing the **cosine reranker** from
   #974 (rank passages by cosine similarity of their embeddings to the query embedding).
3. `TripwireLLMClient`: implements Graphiti's `LLMClient` interface; every method raises
   `LLMCallAttempted(method, args_summary)` and increments a counter the arm reads as `llm_calls`.

### T022 — Writes: the graph per question

**Steps**:
1. `build_graph(question, view: Loaded, driver) -> GraphStats`: `group_id = f"arms_{question.id}"`;
   for each entity in `view.entities` create `EntityNode(name=id, labels=[kind], attributes=…,
   group_id=…)` — pass the ontology Pydantic model as #974 did (remember: `name` is reserved by
   `EntityNode`; the design dropped it); for each edge in `view.edges` an `EntityEdge(name=<type>,
   source/target by uuid, fact=<record line>, valid_at=created_at=<made_at or effective time>,
   group_id)`; for each event an `EpisodicNode(name=ref, content=text.event_line(ref).decode(),
   source_description=event.get("source_description") or channel, reference_time=<at>, group_id)`;
   for each link in `view.links` an `EpisodicEdge(source=episode uuid, target=entity uuid)` — the
   `MENTIONS` wiring (D and R never see `view.links`; here they are the point). Save via the
   classes' `.save(driver)`; `driver.build_indices_and_constraints()` once per graph.
2. Embed node names/summaries and edge facts through the shared `Embedder` so hybrid search has
   vectors (as #974 did); never through an LLM.
3. `drop_graph(question, driver)`: delete everything with that `group_id`; idempotent.
4. `GraphStats`: nodes, edges, episodes, links loaded; `group_id`; build seconds. The harness
   records these per question and calls build once before repeat 1, drop after repeat 3.

### T023 — Retrieval: every A3 resolution path

**Steps**:
1. `resolve_anchors(question_text, view) -> Resolution`: (a) **names/aliases → Person**: tokenise
   the question text; match any `Person.aliases` entry and `Person.name` (case-insensitive, whole
   token/phrase); (b) **Commitment and Outcome descriptions**: exact match, then normalised match
   (case-fold, whitespace-collapse, strip punctuation) of the description against the question
   text and vice-versa (the question may contain a fragment; use the longest common normalised
   phrase ≥ 3 tokens); (c) typed labels for the constraint pull are not anchors. Ambiguity
   (two candidates for one mention) keeps **all**; record `ambiguous_mentions`. Deterministic:
   sort candidates by id. Never consult any per-question list.
2. `typed_pulls(driver, group_id)`: **one `search` per label** — `Capacity`, `Commitment`,
   `Principle`, `Interest` — using `SearchFilters(node_labels=[label])` (RQ-6e: a multi-label
   filter errors on FalkorDB), `group_ids=[group_id]` explicit (RQ-6b).
3. `hybrid_search(driver, group_id, question_text)`: Graphiti `search()` node+edge hybrid config
   (as #974's RQ-5 "node+edge hybrid" config; the reranker is our cosine adapter), `group_ids`
   explicit, `limit` = 60.
4. `anchored_expansion(driver, anchor_uuid)`: `EpisodicNode.get_by_entity_node_uuid(driver,
   anchor_uuid)` — the episodes that MENTION the anchor. **No BFS**: never expand from a retrieved
   node to its neighbours.

### T024 — Assembly, the plan record, determinism

**Steps**:
1. `assemble(pulls, hits, expansions) -> Block` in D-15 order: typed pulls (label order Capacity,
   Commitment, Principle, Interest), then hybrid hits, then expansions per anchor in resolution
   order; within each group sort by `(score desc, uuid asc)`; de-duplicate by uuid; cut at **60
   items** total (nodes + edges + episodes). Convert items back to `text.render_block` inputs —
   episodes by `ref`, nodes by entity id, edges by edge key — so the inserted bytes are the frozen
   lines (D-7).
2. **Zero anchors → search-only path**: skip expansions; `path = "search_only"`; typed pulls and
   hybrid search still run (A3: "Zero anchors → search-only path, recorded").
3. `PlanRecord` per data-model.md: `anchors_resolved`, `anchor_resolution_paths`,
   `ambiguous_mentions`, `path`, `plan_steps` (each with counts), `items_assembled`,
   `items_by_kind`, `llm_calls` (from the tripwire; must be 0 or the harness records `error`),
   `group_id`, `assembled_context_sha256` (of the Block bytes).
4. `arm_g(question, view, ctx) -> Answer` per contracts/arm-interface.md: uses the graph built
   for the question, assembles, renders through `ctx.prompt`, counts tokens, completes.

### T025 — Tests

**Files**: `tests/research/test_arms849_embed.py` (~60 lines: determinism; cosine reranker orders
by similarity; tripwire raises and counts), `tests/research/test_arms849_arm_g.py` (~260 lines).
**Static** (always run): the module contains no `add_episode`, no `valid_at` filter expression in
search code (AST scan of call kwargs), no `oracle`; `group_id` regex on every question id.
**Resolution** (no DB): Person alias hit ("Marcus" → PER_MARCUS; "@fred" → PER_FRED), commitment
description normalised hit, ambiguity keeps both, zero-anchor question yields `search_only`,
same question twice → identical `Resolution`. **Live** (`ARMS849_LIVE=1`, FalkorDB up): build
`arms_A` from `replay(A)` → stats match the view counts; `llm_calls == 0`; two assemblies of the
same question produce equal `assembled_context_sha256`; `items_assembled ≤ 60`; a search with a
hyphenated group id (`arms-A`) is refused by the regex before it can zero BM25 (RQ-6a).

## Definition of Done

- Static + resolution tests green in CI; live tests green on office4 with the WP02 stack up;
  `mark-status T021 T022 T023 T024 T025 --status done`.

## Risks / reviewer guidance

- Graphiti 0.30.2's direct-save API is what #974 used; if a signature differs, follow the
  installed package, record the difference in the module docstring, do **not** fall back to
  `add_episode`.
- Reviewer: run the live build for `arms_F1`; confirm `DEC_F_RESTART` is absent (replay), and that
  the graph for `arms_B2` contains it — that is the replay rule made visible in the substrate.
