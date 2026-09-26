# Implementation Plan: 849 Arms Run Pre-Run Preconditions

**Branch**: `feat/849-preconditions` | **Date**: 2026-09-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/arms-preconditions-01M3FVRY/spec.md` (issue kentonium3/kg-automation#1023)

The planning questions were answered before this document was written. The Engineering Alignment was **confirmed with four corrections (A–D)** by the design lead under Kent's in-session delegation: Decision Moment `01M3FWQHRDZNFG98ND873Y1R8P`, bus reply `20260926T222035097212Zd8a3ed1773`. The design rulings (a)–(c) are bus `20260926T220353449460Z6a87ff79f3` and `20260926T220457953295Zd7af0f572f`. The rubric §5 amendment is `ea3fbfc8`, and C13 is registered in rubric §10 at `4bf375ef`.

## Summary

Make the merged #849 harness runnable and trustworthy on office4 by delivering the five registered pre-run preconditions (C4, C8, C9, C11, C13) and three ledger-schema items. The pieces already exist: the arms (including G's graph build), the series writer/reader and the gates. The work is integration, with failure semantics that fail closed:

- **Arms become registered.** G runs behind a persistent event-loop bridge.
- **The graph-store memory column becomes a real cgroup-charge series** (`falkordb_cgroup_peak_mib`) with recorded support.
- **A ceiling breach at send becomes its own ledger outcome.**
- **Resume is proven across real gate phases.**
- **The research suite's environment dependence becomes one stated, gated thing.**

The run itself is not in scope (spec C-007).

## Technical Context

**Language/Version**: Python 3.12 (office4 `.venv`, 3.12.3; CI runs 3.12 and 3.13)
**Primary Dependencies**: existing only — graphiti-core 0.30.2 with its FalkorDB async driver; fastembed (via `embed.Embedder`); the Qwen tokenizer (`serving.Tokenizer`); stdlib `asyncio`, `threading`, `json`, `pathlib`. **No new dependency** is added (C-003/C-004), so the supply-chain section is not triggered.
**Storage**:
- the append-only JSONL run ledger (`scripts/research/arms849/ledger.py`);
- the JSONL memory series at `RUNS_DIR/falkordb-cgroup.jsonl` (host-written, runner-read through the existing `/runs` mount);
- the gate records under `RUNS_DIR`.
**Testing**: pytest.
- Every FR is red-first (NFR-002).
- Office4 suite under `PYTHONHASHSEED` 0 and 3 (NFR-001).
- **Fresh-worktree CI simulation** (no `build/`, `graphiti_core` hidden behind a stub raising `ModuleNotFoundError`) before any merge.
- Live-stack tests gated on `ARMS849_LIVE=1`.
**Target Platform**: office4 (Linux Mint 22.3). The harness runs inside the runner container on the compose network. The substrate CLI and the memory-series writer run on the host.
**Project Type**: single project — the existing `scripts/research/` package and `tests/research/`.
**Performance Goals**: the series writer sustains its **recorded** interval (target 1.0 s) by reading the cgroup `memory.current` file directly. Freshness tolerances are multiples of the recorded interval (§5 @`ea3fbfc8`).
**Constraints**:
- fail closed everywhere (NFR-005);
- no rubric-value, corpus or oracle change (C-001);
- no `requirements.txt` or workflow change (C-003);
- one sequential lane (C-005);
- arms served identically, including `cache_prompt` (C-008).
**Scale/Scope**: about 350–500 production lines and 750–1,100 test lines (read-only sizing, 2026-09-26), across `run_849_harness.py`, `arms849/{ledger,sampler,substrate,serving,gates,arm_g,arm_d,arm_r,embed}.py`.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design: PASS.*

| Charter item | How this plan meets it |
|---|---|
| Python unit tests before merge | Every FR has red-first tests; NFR-002 records the evidence per WP. |
| Test fixtures mirror real inputs | The series tests use real writer output. C8 uses the real gate phases with injected probes (never timestamp-stable fakes). The ledger tests use real row shapes. |
| **No dead code** | This is the defect class behind C13 (a registry with tests and no production callers). Every WP's DoD greps for live callers. In particular `ARM_FACTORIES`, the series writer, `require_breached` and `before_send` must each be reached from the production path (`live_runtime` / `substrate.run`). |
| Integration verification (no-staging-aware) | Form (a), a pre-merge live exercise, IS feasible here: office4 runs the real stack. A live smoke on a throwaway ledger, NOT the run: `substrate up`, then one cell per arm with `--limit`, then the `ARMS849_LIVE=1` tests. It is defined in WP05 and recorded in the pre-merge record. |
| Self-review of diff; spec-kitty review rigor | Codex read-only review post-plan, per WP and post-merge. It is never the implementer. A fallback reviewer is a different model, and any same-model review is recorded as degraded. |
| Change-risk tier / rebaseline | N/A: office4 research sandbox. No audited surface changes (no dependency manifest, Docker stack or systemd change; `compose.yaml` untouched). |

No violations, so Complexity Tracking is omitted.

## Project Structure

### Documentation (this mission)

```
kitty-specs/arms-preconditions-01M3FVRY/
├── spec.md
├── plan.md              # this file
├── research.md          # decisions D-1..D-10 with rationale and alternatives
├── data-model.md        # outcomes, memory_support, attempt session_id, arm registration, halt record
├── quickstart.md        # how to verify each precondition, incl. the live smoke and the CI simulation
└── contracts/
    ├── arm-registration.md
    ├── ledger-deltas.md
    ├── memory-series.md
    └── before-send.md
```

### Source Code (repository root)

```
scripts/research/
├── run_849_harness.py          # ARM_FACTORIES, live_runtime, Runtime lifecycle, Session: halt, ceiling outcome, before_send wiring, --measure
└── arms849/
    ├── ledger.py               # new outcome, memory_support validation, attempt_start session_id, premise-violation refusal
    ├── sampler.py              # C12 UTC-only; cgroup reader for the series writer; column rename
    ├── substrate.py            # run(): host-side writer lifecycle, env_extra (container id, series path)
    ├── serving.py              # complete(..., before_send)
    ├── gates.py                # REQUIRED_MODULES (every module)
    ├── arm_g.py                # ArmRefusal, limit cross-check, halt-class errors, loop bridge support
    ├── arm_d.py / arm_r.py     # unified refusal class; fallbacks removed
    ├── embed.py                # unchanged interface; constructed once in live_runtime
    └── (a new small module only if needed, e.g. errors.py for the unified refusal; if added, REQUIRED_MODULES is updated in the same commit, per correction A)

scripts/research/check_849_premerge.py   # NEW (name provisional): writes the pre-merge record (office4 suite + fresh-worktree CI simulation)

tests/research/
├── conftest.py                 # NEW: one research-environment fixture (named, counted skips)
└── test_arms849_*.py           # extended per WP
```

**Structure Decision**: extend the existing package in place, with no new package. The one new script, the pre-merge record, lives beside the other `check_849_*` gates.

## Implementation Concern Map

> These concerns are not work packages. `/spec-kitty.tasks` decomposes them. The alignment fixes a **single sequential lane** (C-005), so the order below is binding.

### IC-01 — Ledger vocabulary and schema

- **Purpose**: give the ledger the words the later concerns need:
  - a ceiling-breach outcome;
  - `memory_support`;
  - the attempt's `session_id`;
  - a premise-violation halt record that makes the ledger unusable as a primary.
- **Relevant requirements**: FR-006, FR-008 (outcome half), FR-011, FR-012, FR-010; correction C.
- **Affected surfaces**: `ledger.py`, `grading.py` (the summariser/completeness refusal), `sampler.py` (C12), `gates.py` (C4); the ledger, grading, sampler and gates tests.
- **Sequencing/depends-on**: none. It goes first.
- **Risks**:
  - **Correction A:** C4's two-way test makes every later module addition a same-commit `REQUIRED_MODULES` update. State this in every later WP's DoD.
  - Replay must validate the new outcome and fields exactly as live writes do.

### IC-02 — Arm registration (C13)

- **Purpose**: register G, D and R with their real dependencies, so a live runtime answers cells.
- **Relevant requirements**: FR-001–FR-004; correction B.
- **Affected surfaces**: `run_849_harness.py` (`ARM_FACTORIES`, `Resources`, `live_runtime`, `Runtime` close hook, halt handling), `arm_g.py`, `arm_d.py`, `arm_r.py`, `embed.py` usage.
- **Sequencing/depends-on**: IC-01 (the halt record; the refusal outcome vocabulary).
- **Risks**:
  - The G loop bridge: cancellation must never leave a dirty driver for the next cell (correction B).
  - Lazy imports, so CI collection survives without `graphiti_core`.
  - Removing the fallbacks touches about 10 test ctx sites.

### IC-03 — Graph-store memory series (C9)

- **Purpose**: measure `falkordb_cgroup_peak_mib` end to end, with support.
- **Relevant requirements**: FR-005–FR-007; NFR-004; C-009.
- **Affected surfaces**: `substrate.py` (`run()` lifecycle, `env_extra`), `sampler.py` (the cgroup reader for the writer; rename), `run_849_harness.py` (bind the series sampler via `functools.partial`, `require_breached`, `memory_support` into the row), `ledger.py` (the field rename in `SCORED_ARM_FIELDS`).
- **Sequencing/depends-on**: IC-01 (the `memory_support` shape), IC-02 (G is registered, so a G cell exists to measure).
- **Risks**:
  - The first reading must exist before the first G cell.
  - Resolving the cgroup path from the container id (cgroup v2 scope path).
  - The recorded interval must be the real one.

### IC-04 — Ceiling guard at send (C11)

- **Purpose**: check the ceiling at the last point the protocol controls, and record a breach as its own outcome.
- **Relevant requirements**: FR-008; SC-003.
- **Affected surfaces**: `serving.py` (`complete(..., before_send)`), `run_849_harness.py` (`ServingFacade`, `Runtime.facade` signature, `_one_attempt`, the secondary probe), the arms' exception handling (they must not catch it); about 100 test facade fakes.
- **Sequencing/depends-on**: IC-01 (the outcome), IC-02 (registered arms), IC-03 (both touch `Runtime` / `_one_attempt`; done in sequence).
- **Risks**:
  - The new exception must not subclass `ContextExceeded` or `ArmRefusal`.
  - A breach must be distinguishable from an unreadable sampler.

### IC-05 — Resume proof, environment gating, measurement tool, pre-merge record

- **Purpose**: prove resume across real gate phases (C8), state the research environment once, build T039's `--measure` tool, and make the office4 run plus the CI simulation a recorded gate.
- **Relevant requirements**: FR-009, FR-013 (the tool only), FR-014, FR-015; NFR-001; the integration verification (live smoke).
- **Affected surfaces**: `tests/research/conftest.py` (new), a new C8 test module, `run_849_harness.py` (`--measure`, an injectable `PROCESS_START`), `scripts/research/check_849_premerge.py` (new).
- **Sequencing/depends-on**: all of IC-01–IC-04. C8 drives `live_runtime`, which IC-02/IC-03 change.
- **Risks**:
  - C8 drifting back to fixed-timestamp fakes.
  - The C8 test "passing" by skipping without the corpus: its execution must appear in the pre-merge record.
  - **Correction D:** T039's registration is a **freeze-time step after the last WP**, citing the final commit and `preflight_sha`. It is not an IC-05 deliverable.

## Freeze-time and post-merge steps (not work packages)

1. **T039 registration** (correction D): after the final WP's approval and before the post-merge checkpoint, run `--measure` on the final commit. Hand the §2 table to the design lead as a dated amendment citing the commit and `preflight_sha`.
2. **Post-merge Codex checkpoint** on the complete merged diff. Then the fresh-worktree CI simulation and the office4 suite, recorded, then feat → main.
3. **Then the run, as an operation** (out of this mission).
