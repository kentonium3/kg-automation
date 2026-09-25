# Tasks — 849 Lattice Arms and Decisive Run

**Branch**: `feat/849-arms-run` → mission merge lands here; `feat → main` after the post-merge Codex review.
**Plan**: [plan.md](./plan.md) @aa30c122 (+ corrections @51707915) · **Spec**: [spec.md](./spec.md) @a34f12cc · **Research**: [research.md](./research.md) (D-1..D-16, Codex dispositions)

Decomposes the Implementation Concern Map (IC-01…IC-09) into 9 work packages with
non-overlapping ownership. The harness is split into modules under `scripts/research/arms849/`
so no two WPs own `run_849_harness.py`. WP01 and WP02 are the foundations; WP03–WP07 fan out
from them; WP08 integrates; WP09 documents and executes (no code). Tests are explicitly
demanded by the spec (Testing standard in plan.md Charter Check; "every check paired with an
injected defect"), so every code WP carries its tests.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | `arms849/text.py`: frozen event lines by ref, canonical record lines produced once by the loader, `render_block` concatenation only | WP01 | |
| T002 | `arms849/prompt.py`: registered §3.2 text with literal slots, normalisation, digest constant, `Prompt.render(block, question_text)` | WP01 | |
| T003 | `arms849/questions.py`: the eight-question manifest + A4 digest constant | WP01 | |
| T004 | `arms849/serving.py`: `ServingConfiguration` (primary/secondary), request serialisation, `count_tokens`, `complete` with explicit `timings` mapping, tokenizer-equivalence check | WP01 | |
| T005 | Tests for T001–T004 against the real corpus and the rubric constants; injected-defect cases | WP01 | |
| T006 | `arms849/substrate.py setup`: pinned installs, image digests, FastEmbed + tokenizer caches with recorded shas, no-torch assertion | WP02 | [P] |
| T007 | `substrate.py up/down/health` + `compose/compose.yaml`: project `arms849`, 127.0.0.1-only ports, `--yarn` variant, teardown verification | WP02 | [P] |
| T008 | `substrate.py export`: git-archive of the mission branch minus the excluded paths; content-manifest sha | WP02 | [P] |
| T009 | `substrate.py run` + `compose/runner.Dockerfile`: runner container with allowlisted mounts on the compose network; denied-access self-test | WP02 | [P] |
| T010 | Tests for T006–T009 (static + `live` marker for container tests) | WP02 | [P] |
| T011 | `arms849/ledger.py`: header binding (corpus, prompt/question digests, serving, code hashes, export + preflight shas), immutable header | WP03 | |
| T012 | `ledger.py`: `attempt_start` rows, attempt counting, per-attempt timeout, retry-after-health-check policy hooks | WP03 | |
| T013 | `ledger.py`: fsync append, `fcntl` single-writer lock, torn-tail recovery, interior-corruption rejection | WP03 | |
| T014 | `ledger.py`: `summarise` over `ok` rows only (observed cache state, cold/warm, `r_g_ratio`, counts of other outcomes) | WP03 | |
| T015 | Ledger tests incl. kill-mid-write and second-writer refusal | WP03 | |
| T016 | `arms849/preflight.py`: run the four checkers from the full checkout → `preflight.json` (results, fingerprints, record-line digest, export sha) | WP04 | [P] |
| T017 | `arms849/gates.py`: in-container gates (preflight match, prompt/question digests vs constants, oracle_absent + static scan, boundary, env_clean, tokenizer_equivalence, substrate_health, code_hashes) | WP04 | [P] |
| T018 | `arms849/sampler.py`: 1 Hz GTT sampler beside a request; FalkorDB RSS sampler over a window | WP04 | [P] |
| T019 | `arms849/calibration.py`: deterministic k (two-sided 0.8×–1.2× band, availability caps, `parity`), `calibration` record, halt rule when a G repeat-1 cell is terminal `error` | WP04 | [P] |
| T020 | Tests for T016–T019 with injected defects (vacuous-pass guard, wrong digest, missing telemetry, incomplete population); NFR-003 gate wall-clock, NFR-004 ceiling flag | WP04 | [P] |
| T021 | `arms849/embed.py`: FastEmbed bge-small (one definition for G and R) + #974 cosine reranker | WP05 | |
| T022 | `arms849/arm_g.py` writes: typed `EntityNode`/`EntityEdge`/`EpisodicNode`/`EpisodicEdge` saved directly, tripwire LLM client, `valid_at`/`created_at` from `at`, `build_graph`/`drop_graph`, `group_id = arms_<Q>` | WP05 | |
| T023 | `arm_g.py` retrieval: anchor resolution (aliases → Person; commitment/outcome descriptions exact/normalised; ambiguity keeps all), hybrid `search(group_ids=[…])`, one typed pull per label, anchored expansion via `get_by_entity_node_uuid`, no BFS | WP05 | |
| T024 | `arm_g.py` assembly: D-15 order, dedupe by uuid, 60-cap, search-only path on zero anchors, PlanRecord, `assembled_context_sha256`, `llm_calls` | WP05 | |
| T025 | G tests: static scans (`add_episode`, `valid_at` filters, `oracle`), resolution paths, determinism across repeats, `live` FalkorDB tests | WP05 | |
| T026 | `arms849/arm_d.py`: full dump (events, entities, edges) via `render_block`, layout assertion, context gate with `limit_applied`, cache telemetry | WP06 | [P] |
| T027 | D tests: prefix property across the eight questions, `ContextExceeded` on exactly six with the real tokenizer, entities+edges after events, secondary limits | WP06 | [P] |
| T028 | `arms849/arm_r.py`: event index with the shared embedder, records block (entities + edges), top-k re-sorted to ask_time, rank order recorded | WP07 | [P] |
| T029 | `arm_r.py`: `r_tokens_for(question, k)` + `availability_cap(question)` — the only inputs WP04's single D-10 implementation calls | WP07 | [P] |
| T030 | R tests: k determinism, band checks incl. `unattainable`, chronological assembly, ratio unavailable state | WP07 | [P] |
| T031 | `run_849_harness.py` rewrite on the modules: execute loop (attempt_start → arm → row), `arm_view`, `ContextExceeded(limit_applied)`, retry via health check, sampler wiring | WP08 | |
| T032 | CLI: `--preflight`, `--status`, `--grading-view`, `--secondary --primary <ledger>`; four-gate precondition retained; bus/status events | WP08 | |
| T033 | Secondary binding: refuses unless the primary is complete; its own context gate; header differs in exactly the four rope/n_ctx fields | WP08 | |
| T034 | `arms849/grading.py`: per-cell blinded ids, view / admin report / seal in three directories | WP08 | |
| T035 | Integration tests with fake arms: full 72-cell run, interrupt mid-cell + resume (NFR-002 < 30 s), torn tail, second writer, memory-ceiling refusal (NFR-004), grading forbidden-string scan, secondary refusal | WP08 | |
| T036 | README "Run" section + hand-off record skeleton; sandbox note copied from research.md D-9 | WP09 | [P] |
| T037 | `docs/INDEX.md` + `docs/DEVELOPER_PORTAL.md` entries for the run record | WP09 | [P] |
| T038 | Preflight from the full checkout, export, substrates up, in-container gates green (record the gate output) | WP09 | |
| T039 | §2 token table re-measured on final assembled bytes at code freeze; posted to the design lead for registration | WP09 | |
| T040 | Primary 72-cell run with one deliberate interrupt-and-resume; ledger complete; `summarise` output recorded | WP09 | |
| T041 | Grading export + seal; hand-off to the design lead on the bus | WP09 | |
| T042 | Secondary: YaRN substrate, its own context gate, 24 cells, own ledger | WP09 | |
| T043 | Teardown verified (SC-008); run record completed with every measurement and hash | WP09 | |

## Work Packages

### WP01 — Shared contracts: text form, prompt, questions, serving (IC-01)
- **Goal**: the things every arm shares have exactly one definition each, returning frozen bytes and registered constants.
- **Priority**: P0 (foundation). **Independent test**: unit tests against the real corpus and the A4 digests; a one-character prompt change is refused.
- Subtasks: T001 (WP01) · T002 (WP01) · T003 (WP01) · T004 (WP01) · T005 (WP01)
- **Deps**: none. **Est. prompt**: ~420 lines. **Prompt**: [tasks/WP01-shared-contracts.md](./tasks/WP01-shared-contracts.md)

### WP02 — Substrate lifecycle and the run boundary (IC-02, FR-013 mechanics, FR-018)
- **Goal**: pinned services up/down on office4, the oracle-free export, the runner container with allowlisted mounts and a denied-access self-test.
- **Priority**: P0. **Independent test**: static tests always; `live` tests bring the stack up and prove the boundary.
- Subtasks: T006 (WP02) · T007 (WP02) · T008 (WP02) · T009 (WP02) · T010 (WP02)
- **Deps**: none. **Est. prompt**: ~450 lines. **Prompt**: [tasks/WP02-substrate-and-boundary.md](./tasks/WP02-substrate-and-boundary.md)

### WP03 — Ledger: binding, attempts, durability, summaries (IC-06 core)
- **Goal**: the append-only ledger the whole run stands on — bound to one corpus/prompt/config/code, crash-safe, single-writer, never averaging a non-scored cell.
- **Priority**: P0. **Independent test**: kill-mid-write and resume; second writer refused; summarise excludes non-`ok`.
- Subtasks: T011 (WP03) · T012 (WP03) · T013 (WP03) · T014 (WP03) · T015 (WP03)
- **Deps**: WP01. **Est. prompt**: ~430 lines. **Prompt**: [tasks/WP03-ledger.md](./tasks/WP03-ledger.md)

### WP04 — Gates, preflight, samplers, calibration (IC-07 + IC-06 support)
- **Goal**: oracle-dependent checks run from the full checkout and bind into the run; every in-container gate compares to a registered constant; memory samplers; deterministic k with the halt rule.
- **Priority**: P0. **Independent test**: each gate proven to fail on its injected defect; calibration halts on an incomplete population.
- Subtasks: T016 (WP04) · T017 (WP04) · T018 (WP04) · T019 (WP04) · T020 (WP04)
- **Deps**: WP01, WP02 (calls its self-test), WP03. **Est. prompt**: ~470 lines. **Prompt**: [tasks/WP04-gates-preflight-calibration.md](./tasks/WP04-gates-preflight-calibration.md)

### WP05 — Arm G: Graphiti typed writes and deterministic hybrid retrieval (IC-03)
- **Goal**: the arm under test exactly as ruled — Graphiti's data model and retrieval, none of its extraction; every A3 resolution path; byte-identical assembly across repeats.
- **Priority**: P1. **Independent test**: static scans; resolution unit tests; `live` FalkorDB build/retrieve with `llm_calls == 0` and equal context hashes across repeats.
- Subtasks: T021 (WP05) · T022 (WP05) · T023 (WP05) · T024 (WP05) · T025 (WP05)
- **Deps**: WP01, WP02. **Est. prompt**: ~520 lines. **Prompt**: [tasks/WP05-arm-g.md](./tasks/WP05-arm-g.md)

### WP06 — Arm D: the full dump and the context gate (IC-04)
- **Goal**: the honest upper bound where it can run; `exceeds_model_context` where it cannot, decided client-side on the exact serialised request.
- **Priority**: P1. **Independent test**: exactly six of eight questions exceed the trained limit with the real tokenizer; prefix property holds; layout asserted.
- Subtasks: T026 (WP06) · T027 (WP06)
- **Deps**: WP01. **Est. prompt**: ~260 lines. **Prompt**: [tasks/WP06-arm-d.md](./tasks/WP06-arm-d.md)

### WP07 — Arm R: index, records, deterministic k (IC-05)
- **Goal**: the realistic-deployment arm; its one free parameter is derived by WP04's single D-10 implementation from token counts R supplies.
- **Priority**: P1. **Independent test**: same inputs → same k; band checks incl. `unattainable`; chronological assembly; ratio unavailable state.
- Subtasks: T028 (WP07) · T029 (WP07) · T030 (WP07)
- **Deps**: WP01, WP03, WP05 (imports `arms849.embed`). **Est. prompt**: ~330 lines. **Prompt**: [tasks/WP07-arm-r.md](./tasks/WP07-arm-r.md)

### WP08 — Harness integration, CLI, secondary binding, grading export (IC-06 orchestration + IC-08)
- **Goal**: `run_849_harness.py` rebuilt on the modules; the CLI the quickstart names; the secondary's binding; the blinded export — all proven with fake arms end to end.
- **Priority**: P1. **Independent test**: 72-cell fake run with interrupt/resume, torn tail, second writer; grading view forbidden-string scan; secondary refusal.
- Subtasks: T031 (WP08) · T032 (WP08) · T033 (WP08) · T034 (WP08) · T035 (WP08)
- **Deps**: WP03, WP04 (real arms are consumers of the registry, not prerequisites — E2). **Est. prompt**: ~500 lines. **Prompt**: [tasks/WP08-harness-integration.md](./tasks/WP08-harness-integration.md)

### WP09 — Documentation and execution (IC-09; planning artifact, no code)
- **Goal**: a cold-start reader can find, run and understand the harness; then the live verification — ledgers, grading view + seal, the re-measured §2 table, the run record.
- **Priority**: P1 (last). **Independent test**: `validate_docs.py` green; SC-001/002/003/005/006/008 observed on the real run.
- Subtasks: T036 (WP09) · T037 (WP09) · T038 (WP09) · T039 (WP09) · T040 (WP09) · T041 (WP09) · T042 (WP09) · T043 (WP09)
- **Deps**: WP02, WP05, WP06, WP07, WP08 (and the post-merge Codex review of the full diff before T038). **Est. prompt**: ~330 lines. **Prompt**: [tasks/WP09-docs-and-execution.md](./tasks/WP09-docs-and-execution.md)

## MVP / sequencing

- **Lane A (foundation)**: WP01 → WP03 → WP04 → WP08 (reaches the fake-arm MVP without any substrate).
- **Lane B (substrate)**: WP02 → (joins WP05 and WP09).
- **Lane C (arms)**: WP05 (needs WP01+WP02), WP06 (needs WP01), WP07 (needs WP01+WP03+WP05) — parallel once their deps land.
- **WP09** runs last: its docs subtasks land first, and T038 onward only after everything is merged and the post-merge Codex review of the full diff has passed (Kent's standing checkpoint) — it is the live verification, and it must run on reviewed code.
- MVP = WP01 + WP03 + WP08 with fake arms: a complete, resumable, blinded-exportable 72-cell run of `not_implemented` cells proves the harness before any substrate exists.
