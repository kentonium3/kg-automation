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
~/.cache/arms849/run-env/        # git-archive export MINUS the excluded paths (FR-013); OUTSIDE the repo — the pre-commit secret scan walks build/ (WP02 live finding)
build/849-runs/                  # ledgers, grading views, seals; not committed (run record cites them)
docs/design/research/849-synthesis/
└── README.md                    # Run section + hand-off record
```

**Structure Decision**: extend the existing flat `scripts/research/` modules for the harness and loader (they are the mission's baseline, C-006) and add one package `scripts/research/arms849/` for the three arms and what they share, so the shared text form, prompt and serving configuration have exactly one definition each. Tests stay in `tests/research/` beside the existing ones and run against the real corpus.

## Complexity Tracking

*No Charter Check violations to justify.* The one deliberate addition of complexity — Graphiti as a runtime dependency rather than raw Cypher — is the design lead's ruling (Q1), because a G result must be a statement about Graphiti+FalkorDB; it is recorded in research.md, not here.

## Implementation Concern Map

> Concerns are not work packages. `/spec-kitty.tasks` decomposes them. Revised after the Codex
> post-plan checkpoint (7 blockers / 17 majors, dispositions in research.md §Codex checkpoint).

### IC-01 — Shared contracts: text form, prompt, question manifest, serving configuration

- **Purpose**: the things every arm must share have exactly one definition each, enforced at
  **final assembly**, or the comparison measures the definitions instead of the arms.
- **Relevant requirements**: FR-011, FR-003, C-002, NFR-005, SC-004
- **Affected surfaces**: `scripts/research/arms849/{text,prompt,questions,serving}.py`; tests
- **Sequencing/depends-on**: none
- **Risks**: the text form is applied at the point the arm hands text to the prompt slot (events,
  entities **and edges** all go through it — contracts/text-form.md); the prompt digest is
  computed over normalised bytes (UTF-8, `\n`, no trailing whitespace) of the registered text
  with the slot marker present, and that digest is written into the rubric by the design lead as
  the registered value (research.md D-14); question texts live in an oracle-free manifest with
  its own digest (D-14); the tokenizer is validated against the pinned server's `/tokenize` on the
  exact serialized request (D-11).

### IC-02 — Substrate lifecycle, run boundary and the sandbox note

- **Purpose**: pinned FalkorDB and llama-server on office4, health-checked; the arms execute
  inside a **container whose only mounted filesystem is the oracle-free export** (D-8); teardown;
  the envelope recorded before the first container runs.
- **Relevant requirements**: FR-016, FR-018, FR-013, NFR-004, C-004, C-005, SC-008
- **Affected surfaces**: `scripts/research/arms849/substrate.py`; research.md D-8/D-9; run record
- **Sequencing/depends-on**: none (parallel with IC-01)
- **Risks**: the runner container must reach the two services over the compose network and
  nothing else; a denied-access test proves the original checkout, the oracle and the seed
  commentary are unreachable from inside; FalkorDB digest re-verified against #976.

### IC-03 — Arm G: Graphiti typed writes, tripwire, deterministic hybrid retrieval

- **Purpose**: the arm under test, exactly as ruled (D-1..D-3), with **every resolution path A3
  names** and a **deterministic assembly** so repeats are byte-identical.
- **Relevant requirements**: FR-008, FR-012, FR-004, NFR-005, C-004, SC-007
- **Affected surfaces**: `scripts/research/arms849/{arm_g,embed}.py`; tests
- **Sequencing/depends-on**: IC-01, IC-02
- **Risks**: resolution = names/aliases → Person; Commitment and Outcome descriptions by exact
  or normalised (case-fold, whitespace-collapse, punctuation-strip) match; typed labels for the
  constraint pull; ambiguity keeps all candidates; zero anchors → search-only path recorded.
  Assembly order and cap allocation are fixed (D-15): typed pulls, then hybrid search hits, then
  anchored expansions, each ordered by (score desc, uuid asc), de-duplicated by uuid, cut at 60;
  the per-question assembled-context sha256 is recorded and must match across repeats and
  resumes. RQ-6a/6e/6d mitigations as before.

### IC-04 — Arm D: full dump (events, entities, edges), client-side context gate

- **Purpose**: the honest upper bound where it can run and a correctly classified non-result
  where it cannot — over the **whole** replay-visible view, edges included.
- **Relevant requirements**: FR-009, FR-006, FR-012, SC-002
- **Affected surfaces**: `scripts/research/arms849/arm_d.py`; tests
- **Sequencing/depends-on**: IC-01
- **Risks**: token gate compares the exact serialized request (prompt + context + question,
  chat-templated) against the **permitted** limit = configured `n_ctx` − `max_tokens` reserve,
  with the trained limit governing the primary only (D-11); layout asserted per cell.

### IC-05 — Arm R: index over events and records, deterministic k calibration

- **Purpose**: the realistic-deployment arm with its one free parameter derived by a fixed
  procedure from a complete calibration population.
- **Relevant requirements**: FR-010, FR-012, SC-007
- **Affected surfaces**: `scripts/research/arms849/arm_r.py`; harness calibration record; tests
- **Sequencing/depends-on**: IC-01, IC-03 (calibration needs all eight G repeat-1 `ok` cells)
- **Risks**: calibration (D-10) requires **all eight** G repeat-1 cells `ok`; if any is `error`
  after three attempts the run **halts** with `blocked: calibration_population_incomplete` and
  posts to the bus — never a partial population. k is chosen deterministically over all eight
  replayed R views (records overhead included, availability caps applied) as the smallest k whose
  median assembled tokens is ≥ 0.8 × G's median, ties to the smaller k; written as a single
  durable `calibration` record. The population question itself (events-only top-k + full records
  vs retrieval over both) is the design lead's pending ruling (research.md D-4 note).

### IC-06 — Harness core: binding, attempts, torn-tail recovery, telemetry, memory, lock

- **Purpose**: the existing resumable harness becomes the one the rubric's §5 and the NFRs
  describe, with every crash path explicit.
- **Relevant requirements**: FR-001–FR-007, FR-017, NFR-001–NFR-004, NFR-007, NFR-008
- **Affected surfaces**: `scripts/research/run_849_harness.py`; tests
- **Sequencing/depends-on**: IC-01
- **Risks**: header binds corpus + prompt digest + question manifest digest + serving config +
  **arm code content hashes** (D-16); `attempt_start` rows precede every attempt so a death
  mid-cell is counted (D-12); the reader tolerates exactly one torn final line under the lock and
  rejects interior corruption (D-12); llama.cpp `timings` fields are mapped explicitly and a
  scored row is refused when any required measurement is absent (D-13); cache state is classified
  from observed `prompt_n` vs `cache_n` per response, with server restarts recorded as events
  (D-13); memory = per-cell serving-process peak via `/metrics`/GTT sampling **and** a per-question
  FalkorDB RSS peak for G (D-13); R/G ratio is a row field on every R `ok` row with an explicit
  `unavailable` state when G's median is missing (D-10).

### IC-07 — Gates and preflight binding

- **Purpose**: oracle-dependent checks run once from the **full checkout** before export and
  their result is bound into the run; the run-boundary gates run inside the container.
- **Relevant requirements**: FR-001, FR-013, SC-004
- **Affected surfaces**: `run_849_harness.py --preflight`; contracts/gates.md
- **Sequencing/depends-on**: IC-01, IC-02, IC-06
- **Risks**: `check_849_freeze` and `check_849_oracle` load the oracle and pass **vacuously**
  when it is absent — they never run inside the export; the preflight writes a signed
  `preflight.json` (gate results + corpus fingerprints + export manifest content-sha) that the
  in-container run must find and match before writing a header.

### IC-08 — Grading export and secondary-run implementation (code only)

- **Purpose**: the blinded per-**cell** export with a sealed mapping, an administrative report for
  non-scored cells, and the `--secondary` mode with its own context gate — all implemented and
  tested against synthetic ledgers, without executing any run.
- **Relevant requirements**: FR-014, FR-015, NFR-006, SC-005, SC-006
- **Affected surfaces**: `scripts/research/arms849/grading.py`; `run_849_harness.py`
- **Sequencing/depends-on**: IC-06
- **Risks**: nine scored answers per question carry blinded ids that encode neither arm nor
  repeat; non-scored classifications never appear in the view (they would identify D).

### IC-09 — Execution: primary run, hand-off, secondary run

- **Purpose**: the live verification — preflight, primary 72 cells with one deliberate
  interrupt-and-resume, grading export and seal, then the secondary's gate and its 24 cells.
- **Relevant requirements**: FR-002, SC-001, SC-003, SC-005, SC-006
- **Affected surfaces**: `build/849-runs/`; the run record; README Run section
- **Sequencing/depends-on**: IC-02 through IC-08 (all code merged first)
- **Risks**: wall-clock as before; this concern contains no code and cannot cycle with IC-08.
