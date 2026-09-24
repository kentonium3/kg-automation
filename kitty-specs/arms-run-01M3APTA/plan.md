# Implementation Plan: 849 Lattice Arms and Decisive Run

**Branch**: `feat/849-arms-run` | **Date**: 2026-09-24 | **Spec**: [spec.md](spec.md) @fd9e2eb6
**Input**: Feature specification from `kitty-specs/arms-run-01M3APTA/spec.md`

Planning interrogation: six Decision Moments, answered by the design lead at Kent's direction
(2026-09-24 23:43Z and 23:48Z, `stability: accepted`), all resolved, `decision verify` clean.
The rulings are reproduced in [research.md](research.md) and are the ground truth below.

## Summary

Build three retrieval arms over the frozen `#849` corpus (`c0b35cd1`) — **G** (Graphiti typed
writes on FalkorDB, tripwire LLM, Graphiti hybrid search), **D** (full replayed dump, native
262,144 context, `exceeds_model_context` on six questions), **R** (FastEmbed bge-small top-k over
events plus the full entity set, assembled chronologically) — all asking Qwen3-Next-80B with the
registered §3.2 prompt and one fixed sampling configuration; extend the existing harness so the
72-cell primary run completes into a ledger the design lead grades blind, then run the D-YaRN
secondary in its own ledger. Everything runs on office4 inside a torn-down sandbox; the existing
loader, gates and harness are the baseline and are extended, not replaced.

## Technical Context

**Language/Version**: Python 3.12.3 (the repo `.venv`; helpers invoked as `python3 -m scripts.research.<module>`)
**Primary Dependencies**: `graphiti-core==0.30.2`, `falkordb==1.7.1`, `fastembed==0.8.1` (BAAI/bge-small-en-v1.5, local), `openai==3.19.2` (client for llama.cpp's OpenAI-compatible endpoint), `transformers` (Qwen tokenizer only, for client-side token counts); FalkorDB server 4.20.1 and llama.cpp `server-vulkan` @sha256:063e88ae…, both as pinned Docker images. Supply-chain disposition in research.md §Supply chain.
**Storage**: FalkorDB (one graph per question, `group_id = arms_<Q>`, dropped after three repeats); append-only JSONL ledgers under `build/849-runs/`; FastEmbed index in memory per question; no database schema changes anywhere else.
**Testing**: pytest under `tests/research/` against the REAL frozen corpus (fixtures mirror real inputs); every check paired with an injected defect; static tests that grep arm modules (`add_episode`, `valid_at` filters, the oracle path); contract tests for the ledger schema and the shared text form; the primary run itself is the live verification, recorded (see Charter Check).
**Target Platform**: office4 only — Linux Mint 22.3, Strix Halo (Radeon 8060S via RADV), 62.5 GiB GTT, 125 GiB RAM; nothing on office2.
**Project Type**: single project (scripts + tests in the existing repo layout)
**Performance Goals**: precondition gates < 5 min; resume to next cell < 30 s; per-attempt bound 90 min; primary run completes across sessions with zero re-executed scored cells.
**Constraints**: peak GTT ≤ 57.5 GiB (62.5 budget − 5 headroom, NFR-004), measured 51.33 at n_ctx 262,144; single writer per ledger; no external network calls at run time; oracle directory absent from the execution environment; corpus fingerprints, prompt hash and serving configuration bound in the ledger header.
**Scale/Scope**: 72 primary cells + 24 secondary cells; 5,750 events / 66 entities / 22 links per replay; ~363k-token largest prompt; ~28 min per cold D cell.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Charter gate | Status | How |
|---|---|---|
| Self-documenting / cold-start discoverable | PASS | `docs/design/research/849-synthesis/README.md` gains a Run section; a run record is written at hand-off; every module carries the why in its docstring, matching the existing research modules. |
| Idempotent / replay-safe operations | PASS | Resume is ledger-driven (FR-002); graph build per question is drop-and-rebuild; every gate is read-only. |
| Loud failure into a recoverable state | PASS | Gates, prompt hash, ledger binding, oracle presence and second writers all REFUSE with the reason printed; infrastructure failures record `error` with cause after bounded retry (FR-007). |
| Testing standards (pytest; fixtures from real inputs; no dead code) | PASS | Tests run on the real corpus; every arm has a caller (the harness); static grep tests per the rulings. |
| Live verification, no staging | PASS (form b) | office4 is the runtime and there is no staging; the **primary run itself is the live verification**, recorded in the ledger and the run record; SC-003's interrupt-and-resume is demonstrated on the real run. |
| Branch strategy | PASS | Feature branch `feat/849-arms-run`, mission merge to it, `feat → main` after the post-merge Codex review. |
| Deployment constraints (office2-only production, Tailscale-only exposure, manifest discipline) | PASS — N/A by scope | Nothing deploys to office2; services bind to `127.0.0.1` on office4 only (never a tailnet interface); the sandbox carve-out's pre-run note is FR-018. |
| Change-risk tier | Tier 3 | Python scripts + tests; Docker containers on office4 (not a managed host, so the Tier-2 Restic rule is not engaged). |
| Rebaseline obligation | NOT REQUIRED | No audited surface touched. |
| Supply-chain install safety (DIRECTIVE 051 / advisory) | PASS with dispositions | Four new pip packages and one new image; registry authenticity, pins, lifecycle-script posture and the adversarial pass are recorded in research.md. |

Post-design re-check (after Phase 1): unchanged — the design added no service, no office2 surface, no unpinned dependency.

## Project Structure

### Documentation (this mission)

```
kitty-specs/arms-run-01M3APTA/
├── plan.md              # This file
├── research.md          # Phase 0: the six rulings, implementer calls, supply chain, adversarial pass
├── data-model.md        # Phase 1: Ledger, Cell, Outcome, Header, ArmView, ServingConfiguration, GradingView/Seal, PlanRecord
├── quickstart.md        # Phase 1: bring-up, gates, run, resume, hand-off, teardown
├── contracts/           # Phase 1: ledger-schema.md, arm-interface.md, text-form.md, grading-view.md, gates.md
└── tasks.md             # Phase 2 (/spec-kitty.tasks — not created here)
```

### Source Code (repository root)

```
scripts/research/
├── load_849_corpus.py           # existing — replay + fingerprint gate (extended: ARM_INPUTS already there)
├── check_849_loader.py          # existing — loader-side pass
├── run_849_harness.py           # existing — extended: header fields, per-cell columns, retry policy,
│                                #   attempt timeout, single-writer lock, GTT sampler, oracle refusal,
│                                #   grading_view export, secondary-ledger binding
├── arms849/                     # NEW package — the three arms and what they share
│   ├── __init__.py
│   ├── text.py                  # render_event_text / render_entity_text — ONE text form for every arm
│   ├── prompt.py                # §3.2 registered prompt, slot insertion, sha256 assertion
│   ├── serving.py               # ServingConfiguration (model, image, n_ctx, rope, sampling, seeds, max_tokens),
│   │                            #   llama.cpp client, token counting via the Qwen tokenizer
│   ├── substrate.py             # FalkorDB + llama-server lifecycle, health checks, sandbox note, teardown
│   ├── embed.py                 # FastEmbed bge-small — the one embedder G and R share; cosine reranker
│   ├── arm_g.py                 # Graphiti typed writes (tripwire LLM), per-question group, hybrid retrieval, plan record
│   ├── arm_d.py                 # dump assembly (events then entities), client-side token gate, cache hit rate
│   ├── arm_r.py                 # event index, k from G repeat-1 medians, top-k re-sorted chronologically
│   └── grading.py               # grading_view export + sealed label map
tests/research/
├── test_load_849_corpus.py      # existing
├── test_run_849_harness.py      # existing — extended
├── test_arms849_text.py         # NEW — one text form, byte-identical across arms
├── test_arms849_prompt.py       # NEW — hash assertion; one-char change refused
├── test_arms849_arm_g.py        # NEW — tripwire, no add_episode, no valid_at filter, group_id shape, 60-cap, plan record
├── test_arms849_arm_d.py        # NEW — entities after events, prefix property, ContextExceeded on six
├── test_arms849_arm_r.py        # NEW — k derivation, ±20% ratio column, chronological assembly
├── test_arms849_grading.py      # NEW — blinding integrity, seal reproduces mapping
└── test_arms849_isolation.py    # NEW — oracle absent in run env; static scan; second writer refused
build/849-run-env/               # git-archive export of the mission branch MINUS the oracle dir (FR-013); not committed
build/849-runs/                  # ledgers, grading views, seals; not committed (run record cites them)
docs/design/research/849-synthesis/
└── README.md                    # Run section + hand-off record
```

**Structure Decision**: extend the existing flat `scripts/research/` modules for the harness and loader (they are the mission's baseline, C-006) and add one package `scripts/research/arms849/` for the three arms and what they share, so the shared text form, prompt and serving configuration have exactly one definition each. Tests stay in `tests/research/` beside the existing ones and run against the real corpus.

## Complexity Tracking

*No Charter Check violations to justify.* The one deliberate addition of complexity — Graphiti as a runtime dependency rather than raw Cypher — is the design lead's ruling (Q1), because a G result must be a statement about Graphiti+FalkorDB; it is recorded in research.md, not here.

## Implementation Concern Map

> Concerns are not work packages. `/spec-kitty.tasks` decomposes them.

### IC-01 — Shared contracts: text form, prompt, serving configuration

- **Purpose**: the three things every arm must share have exactly one definition each, or the comparison measures the definitions instead of the arms.
- **Relevant requirements**: FR-011, FR-003, C-002, NFR-005, SC-004
- **Affected surfaces**: `scripts/research/arms849/{text,prompt,serving}.py`; `tests/research/test_arms849_{text,prompt}.py`
- **Sequencing/depends-on**: none — everything else depends on this
- **Risks**: the text form decides §5's token counts (research.md D-7: the JSON line is the text form; an NL rendering would re-measure §2 and is the design lead's to overturn at post-plan). The prompt hash must be computed over the registered text with the slot empty, so the slot marker itself is part of the contract.

### IC-02 — Substrate lifecycle and the sandbox note

- **Purpose**: bring FalkorDB and llama-server up on office4 from pinned images, health-check them before use, keep the model resident between cells, tear down on completion, and record the envelope before the first container runs.
- **Relevant requirements**: FR-016, FR-018, NFR-004, C-004, C-005, SC-008
- **Affected surfaces**: `scripts/research/arms849/substrate.py`; the sandbox note in `research.md` §Sandbox envelope (written now, before any container) and the run record
- **Sequencing/depends-on**: none (parallel with IC-01)
- **Risks**: FalkorDB image digest must be re-verified against #976's record; ports 16379/18080 must be free; `render` gid 992 for `/dev/dri`; everything binds to 127.0.0.1.

### IC-03 — Arm G: Graphiti typed writes, tripwire, hybrid retrieval

- **Purpose**: the arm under test, built exactly as the design lead ruled — Graphiti's data model and retrieval, none of its extraction.
- **Relevant requirements**: FR-008, FR-012, FR-004 (plan record), C-004, SC-007
- **Affected surfaces**: `scripts/research/arms849/{arm_g,embed}.py`; `tests/research/test_arms849_arm_g.py`
- **Sequencing/depends-on**: IC-01, IC-02
- **Risks**: RQ-6a (hyphenated group_id zeroes BM25 → `arms_<Q>` only), RQ-6e (multi-label filter errors → one query per label), RQ-6d (edge_type_map not enforced → the loader-side pass already validates pairs); Graphiti 0.30.2 API surface for direct saves is the #974 harness's, pinned; anchor resolution from question text is deterministic alias resolution against `Person.aliases` and entity ids — must never consult a per-question list.

### IC-04 — Arm D: dump assembly and client-side context gate

- **Purpose**: the honest upper bound on recall where it can run, and a correctly classified non-result where it cannot.
- **Relevant requirements**: FR-009, FR-006, FR-012, SC-002
- **Affected surfaces**: `scripts/research/arms849/arm_d.py`; `tests/research/test_arms849_arm_d.py`
- **Sequencing/depends-on**: IC-01
- **Risks**: token counting must use the Qwen tokenizer client-side (server acceptance proves nothing); entities-after-events is asserted per cell as `layout=events_first`; `cache_prompt` on with the hit rate read from llama.cpp's response timings.

### IC-05 — Arm R: event index, derived k, chronological assembly

- **Purpose**: the realistic-deployment arm, with its one free parameter derived from G rather than chosen.
- **Relevant requirements**: FR-010, FR-012, SC-007
- **Affected surfaces**: `scripts/research/arms849/arm_r.py`; `tests/research/test_arms849_arm_r.py`
- **Sequencing/depends-on**: IC-01, IC-03 (k derives from G's repeat-1 medians, so R cannot start before G's repeat-1 cells exist in the ledger)
- **Risks**: k is set ONCE and written to the header (H3) — a resume must read it back, never re-derive; the ratio column must be present even when parity holds.

### IC-06 — Harness extensions: header, columns, retry, timeout, lock, sampler, isolation

- **Purpose**: turn the existing resumable harness into the one the rubric's §5 and the spec's NFRs describe.
- **Relevant requirements**: FR-001–FR-007, FR-013, FR-017, NFR-001–NFR-004, NFR-007, NFR-008
- **Affected surfaces**: `scripts/research/run_849_harness.py`; `tests/research/test_run_849_harness.py`, `test_arms849_isolation.py`
- **Sequencing/depends-on**: IC-01 (header needs the prompt hash and serving configuration)
- **Risks**: the run environment is a `git archive` export minus the oracle directory (research.md D-8) — the harness must locate its repo root and refuse if the oracle path exists; the GTT sampler runs beside the request in a thread, not in the arm; the single-writer lock is a file lock on the ledger path, held for the session.

### IC-07 — Grading view, seal, secondary run, run record

- **Purpose**: the hand-off the design lead grades blind, and the labelled secondary that keeps D interpretable.
- **Relevant requirements**: FR-014, FR-015, NFR-006, SC-005, SC-006
- **Affected surfaces**: `scripts/research/arms849/grading.py`; `run_849_harness.py --secondary`; `docs/design/research/849-synthesis/README.md`; the run record
- **Sequencing/depends-on**: IC-06 (ledger complete), IC-04 (secondary is D under YaRN)
- **Risks**: the secondary's context-window gate at n_ctx 393,216 must run before its first cell (research.md D-6); the seal must never be written next to the grading view under a guessable name.

### IC-08 — Pre-run gate and the primary run (integration)

- **Purpose**: the live verification: all four checkers plus prompt hash green on `c0b35cd1`, then the 72 cells, with one deliberate interrupt-and-resume demonstrated.
- **Relevant requirements**: FR-001, FR-002, SC-001, SC-003
- **Affected surfaces**: the run itself; `build/849-runs/primary.jsonl`; the run record
- **Sequencing/depends-on**: IC-02 through IC-07
- **Risks**: wall-clock — G's 24 cells are minutes each, D's 6 native cells ~28 min cold and much less warm, R's 24 cells minutes; the whole primary fits in one long session or two; the secondary adds 24 D-YaRN cells at up to ~50 min cold each and must be planned as its own session(s).
