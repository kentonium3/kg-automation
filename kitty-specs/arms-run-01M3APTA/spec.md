# Mission Specification: 849 Lattice Arms and Decisive Run

**Mission Branch**: `feat/849-arms-run`
**Created**: 2026-09-24
**Status**: Draft
**Input**: User description: "Build the three retrieval arms and run the pre-registered #849 comparison — rubric `docs/design/research/849-rubric.md` @5dfda180 (§2 arms, §3.2 fixed prompt, §5 reporting, Amendments A1–A3), the 15-step map, the design lead's ledger requirements, frozen corpus `c0b35cd1`."

**Confirmed intent (discovery, 2026-09-24, four Decision Moments):** this office4 session, under auto-run, builds three arms and runs the primary matrix with the model resident on office4 at any hour, resuming from the ledger without asking; the mission is **done** when the primary ledger is complete, a blinded grading view is exported with a sealed label map, and the D-YaRN secondary has run in its own ledger. Grading and the §7 verdict stay with the design lead. An infrastructure failure on a cell is retried up to twice after a health check, then recorded and passed over. No arm can see the oracle — enforced structurally, twice.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run the primary matrix to a complete, resumable ledger (Priority: P1)

Kent (through the office4 session) starts the run. The harness verifies every precondition, brings the substrates up, and works through all 72 cells — three arms × eight questions × three repeats — arm-major, questions in ask-time order. The session limit ends the process mid-run; a later session resumes from the ledger and finishes without re-doing completed work or asking anyone anything. At the end the ledger holds one scored or classified row per cell, with every cost column the rubric's §5 reporting needs.

**Why this priority**: the ledger *is* the deliverable. Without it nothing else in the mission has value; with it alone the design lead can grade the primary comparison.

**Independent Test**: start a run, kill the process after several cells, start it again, and confirm the ledger ends with exactly 72 cells, each attempted at most three times, none repeated once scored, and every §5 column populated on scored cells.

**Acceptance Scenarios**:

1. **Given** a corpus, prompt text and serving configuration that match the registration, **When** the run starts, **Then** it proceeds; **Given** any of them differ, **Then** it refuses before any cell and states what differs.
2. **Given** a ledger with N completed cells, **When** a new session resumes, **Then** cells N+1…72 execute in protocol order and no completed cell is re-executed.
3. **Given** arm D's prompt for a question exceeds the model's trained context, **When** that cell is reached, **Then** the ledger records `exceeds_model_context` with the measured token count, no request is sent, and the cell is excluded from every average.
4. **Given** a cell fails for an infrastructure reason, **When** the substrate health check passes again, **Then** the cell is retried, at most twice; **Given** it still fails, **Then** `error` is recorded with the cause and the run continues; every attempt is a ledger row.
5. **Given** the run is complete, **When** the ledger is summarised, **Then** per (arm, question) the mean and range are computed from scored cells only, and non-scored outcomes are counted, never averaged.

---

### User Story 2 - Three arms, one prompt, one model (Priority: P2)

Each arm assembles context for a question from what it is allowed to see at that question's ask time, inserts it into the registered prompt at the single slot, and asks the same model. G reads the replayed graph and its episode links; D reads the whole event stream and entity set, entities after events; R retrieves from an index over the same material. Nothing else differs between arms.

**Why this priority**: the comparison is only valid if the arms differ in *retrieval* and in nothing else. This story is what makes User Story 1's numbers mean something.

**Independent Test**: for one question, run each arm once and confirm all three requests carry the identical prompt text (by hash) with only the assembled-context slot differing, that G's assembled items respect the 60-item cap, that D's context is the full replayed stream with entities last, and that R's k equals the value derived from G's repeat-1 medians.

**Acceptance Scenarios**:

1. **Given** any question, **When** any arm builds its request, **Then** the prompt text outside the context slot hashes to the registered §3.2 hash.
2. **Given** arm G, **When** it resolves anchors, **Then** they come from the question text by deterministic alias resolution against the loaded graph, never from a per-question list, and the resolved anchors, plan steps and item count are recorded on the cell.
3. **Given** arms D or R, **When** they load material, **Then** they receive no episode-to-entity links; **Given** arm G, **Then** it receives them.
4. **Given** the corpus replayed to a question's ask time, **When** any arm assembles context, **Then** nothing dated after the ask time appears in it.
5. **Given** G's repeat-1 cells are complete, **When** R starts, **Then** its single global k is set once from G's per-question median assembled context and recorded in the ledger header; **Given** R's median lands outside ±20 % of G's, **Then** the per-question ratio column makes the breach visible rather than silent.

---

### User Story 3 - Hand-off the design lead can grade blind, then the secondary (Priority: P3)

When the primary ledger is complete, the harness exports a grading view: per question, the three answers under labels re-randomised per question, with the label-to-arm mapping sealed in a separate file the grader does not open until scores are in. Only after the primary is complete does the D-YaRN secondary run — the same weights under a scaled-context serving configuration, all eight questions, its own ledger — so "what would a full dump have given" is answered without ever entering the §7 decision.

**Why this priority**: blind grading is what keeps the verdict honest; the secondary is what keeps the D result interpretable. Both matter; neither is worth anything without Stories 1 and 2.

**Independent Test**: export the grading view from a complete ledger and confirm the grader-facing file contains no arm names and no ledger metadata; confirm the seal file reproduces the mapping from the recorded seed; confirm the secondary ledger's header differs from the primary's in exactly the serving-configuration fields.

**Acceptance Scenarios**:

1. **Given** a complete primary ledger, **When** the grading view is exported, **Then** the grader file carries answers under per-question randomised labels only, and the seal file carries the mapping and the seed.
2. **Given** the primary is incomplete, **When** the secondary is requested, **Then** it refuses to start.
3. **Given** the secondary runs, **When** its ledger opens, **Then** its header records the scaled-context configuration and the harness refuses to append a secondary cell to the primary ledger or vice-versa.

---

### Edge Cases

- The corpus on disk is a re-render that reproduces different fingerprints → refused before any cell, with the three expected and observed hashes printed.
- The registered prompt text is edited by one character → the per-run hash check refuses.
- A resume is attempted against a ledger whose header fingerprints or serving configuration differ from the current environment → refused; the operator starts a new ledger, never overwrites.
- An arm module references the oracle directory, or the oracle directory exists in the execution environment → the run refuses to start.
- The model server accepts a context size beyond its trained limit (it will) → the harness never relies on server acceptance; the token count is measured client-side before any request.
- The substrate health check never passes within the retry budget → the cell records `error` after the second retry and the run continues; a run that ends with error cells is complete but flagged in status.
- A session limit ends the process during a cell → that cell has no row (or an `error` row) and is re-attempted on resume; an earlier `ok` row for the same key is never followed by another attempt.
- G resolves zero anchors for a question → the cell records `ok` with an empty plan and whatever context the typed constraint pulls alone yield; zero anchors is a result, not an error.
- R's derived k would exceed the material available for an early question → k is capped by availability for that cell and the cap is recorded.
- Two sessions attempt to resume the same ledger concurrently → the second refuses on a held lock; there is never a second writer.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status |
|----|-------|------------|----------|--------|
| FR-001 | Four-gate + prompt-hash precondition | As the operator, I want the run to refuse unless the corpus passes all four registered checks and the prompt text matches the registered hash, so that no number is produced from unregistered inputs. | High | Open |
| FR-002 | Resumable 72-cell primary run | As the operator, I want the run to complete all 72 cells arm-major with questions in ask-time order and to resume from the ledger across session limits without re-executing scored cells, so that a multi-hour run survives a session limit. | High | Open |
| FR-003 | Ledger header binds corpus, prompt and serving configuration | As the grader, I want each ledger's header to record the corpus fingerprints, prompt hash, model identity, model context, serving-configuration identity, and R's derived k with the G medians it came from, so that any cell is reproducible from the ledger alone and a ledger can never mix configurations. | High | Open |
| FR-004 | Per-cell cost and plan columns | As the grader, I want every scored cell to carry total prompt tokens, output tokens, the cache split (write / read / uncached), prefill and generation timings with generation rate, peak memory during the cell, and the arm's plan record (G: anchors, plan steps, items assembled; R: k; D: layout asserted), so that §5 reporting is computed from columns, not from free-text. | High | Open |
| FR-005 | Outcome kinds kept distinct and never averaged | As the grader, I want `ok`, `exceeds_model_context`, `error` and `not_implemented` to be distinct outcomes, with only `ok` cells entering any mean or range and the others counted, so that could-not-check never reads as verified-false. | High | Open |
| FR-006 | Arm D context-limit classification | As the operator, I want arm D to measure its prompt's token count client-side before sending and to record `exceeds_model_context` with that count when it exceeds the model's trained context, so that no degraded over-limit answer is ever recorded as a result. | High | Open |
| FR-007 | Bounded retry on infrastructure failure | As the operator, I want a cell that fails for an infrastructure reason to be retried at most twice after a substrate health check passes, then recorded as `error` with the cause, with every attempt written to the ledger, so that transient failures heal and persistent ones are visible. | High | Open |
| FR-008 | Arm G: typed graph retrieval | As the experimenter, I want arm G to build its graph per question by replaying the corpus to ask time, to pull one query per registered label, to resolve anchors from the question text by deterministic alias resolution, to expand each anchor to its episodes through the episode links, to apply the 60-item cap, and never to traverse breadth-first by default, so that G's retrieval is the one §2 registers. | High | Open |
| FR-009 | Arm D: full replayed dump, entities last | As the experimenter, I want arm D's context to be the complete replayed event stream followed by the entity set, with prompt caching on and the hit rate recorded, so that each D prompt is a literal prefix of the next and the cache measurement is a property of the protocol. | High | Open |
| FR-010 | Arm R: retrieval with one derived global k | As the experimenter, I want arm R to retrieve top-k over an index of the same replayed material, with k set once from G's repeat-1 per-question medians so R's median assembled context is within ±20 % of G's, and the per-question ratio recorded, so that a parity breach is visible. | High | Open |
| FR-011 | Registered prompt wired verbatim | As the experimenter, I want every arm to insert its assembled context into the registered §3.2 prompt at its single slot and to send nothing else, so that arms differ only in retrieval. | High | Open |
| FR-012 | Episode links are arm G's input only | As the experimenter, I want arms D and R to be handed material with no episode-to-entity links, and arm G to be handed them, so that the flat arms cannot receive the traversal the graph arm must earn. | High | Open |
| FR-013 | Oracle isolation enforced twice | As the experimenter, I want the run to refuse to start if any arm module references the oracle location, and arms to execute from an environment where the oracle directory does not exist, so that the hidden oracle cannot be read even by mistake. | High | Open |
| FR-014 | Blinded grading view with sealed label map | As the grader, I want a grading export per question with the three answers under labels re-randomised per question from a recorded seed, and the label-to-arm mapping written to a separate sealed file, so that I grade without knowing which arm produced which answer. | Medium | Open |
| FR-015 | D-YaRN secondary in its own ledger, after the primary | As the experimenter, I want the scaled-context D variant to run on all eight questions only after the primary ledger is complete, in a separate ledger whose header records the scaled configuration, so that it informs "what a full dump would have given" without entering the §7 decision. | Medium | Open |
| FR-016 | Substrate lifecycle and health | As the operator, I want the harness to bring each arm's substrate up, verify it with a health check before use, keep the model resident between cells, and tear everything down on completion, so that the run needs no manual setup and leaves the machine clean. | Medium | Open |
| FR-017 | Status and progress reporting | As the operator, I want a status command showing per-arm completion, outcome counts, and elapsed time, and a bus post at run start, resume, completion and any halt, so that other agents can see the run's state without reading the ledger. | Medium | Open |
| FR-018 | Sandbox note before any container runs | As the operator, I want the network, volumes, ports, resource ceiling and teardown command recorded in the mission record before the first container starts, so that the deploy discipline's carve-out is met on the record rather than assumed. | Medium | Open |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Ledger durability | A killed process loses at most the cell in flight; every completed cell is durable before the next begins (flushed and synced), and every ledger line parses. | Reliability | High | Open |
| NFR-002 | Resume cost | Resuming a run re-reads the ledger and reaches the next cell in under 30 seconds, excluding substrate start-up. | Performance | Medium | Open |
| NFR-003 | Precondition cost | The four gates plus prompt-hash check complete in under 5 minutes on office4. | Performance | Medium | Open |
| NFR-004 | Memory ceiling | Peak memory during any cell stays within the recorded 62.5 GiB budget with at least 5 GiB headroom, and the per-cell peak is recorded. | Performance | High | Open |
| NFR-005 | Determinism of what is not the model | Given the same ledger header, the assembled context for any cell is byte-identical across repeats; only the model's output may vary. | Reliability | High | Open |
| NFR-006 | Blinding integrity | The grader-facing file contains zero arm identifiers and zero ledger metadata; the mapping is recoverable only from the sealed file and the seed. | Security | High | Open |
| NFR-007 | Single writer | At most one process appends to a given ledger at any time; a second writer is refused, never silently interleaved. | Reliability | High | Open |
| NFR-008 | Per-cell wall-clock bound | A single cell, retries included, is bounded at 90 minutes; exceeding it records `error` with cause `timeout`. | Reliability | Medium | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | Frozen corpus | The corpus is registered at `c0b35cd1` with three fingerprints and is an immutable input; the mission changes no corpus file, no seed and no oracle. | Business | High | Open |
| C-002 | Registered rubric governs | Rubric @5dfda180 (§2, §3.2, §5, §7, A1–A3) is the specification of record for arm behaviour, the prompt, reporting and the reading rule; where this spec and the rubric disagree, the rubric wins and this spec is amended. | Business | High | Open |
| C-003 | Model of record | All arms use the ruled model in its native configuration (trained context 262,144 tokens) served on office4 per ADR-0009; the secondary uses the same weights under the documented scaled-context configuration and nothing else changes. | Technical | High | Open |
| C-004 | Substrates | Arm G runs on the typed graph substrate the design names (Graphiti over FalkorDB, structured writes, no LLM extraction); arm R's embedder is the locally-run small model named in #974; arm D and the reasoning model are served by the pinned image recorded in the model's SOURCE.md. | Technical | High | Open |
| C-005 | office4 is the only host | Nothing in this mission deploys to office2; office4 is Kent's attended machine and an unmanaged peer (ADR-0008), so the deploy-manifest pipeline does not apply, and the sandbox carve-out's note requirement does. | Technical | High | Open |
| C-006 | Existing loader and harness are the baseline | `load_849_corpus.py`, `check_849_loader.py` and `run_849_harness.py` are extended, not replaced; the fingerprint gate, replay rules, arm-input separation and outcome semantics already in them are preserved. | Technical | High | Open |
| C-007 | Reviews | Codex read-only reviews after plan and after the full merge, and per work package; a different-model reviewer only as the recorded fallback. | Business | High | Open |
| C-008 | Question order and arm order | Questions run in ask-time ascending order within every arm-repeat pass; arms run G, then D, then R, because R's k derives from G. | Technical | High | Open |
| C-009 | No secrets, no external calls | Every request stays inside the tailnet; no provider API key is required or used by the primary or secondary run. | Security | High | Open |

### Key Entities *(include if feature involves data)*

- **Cell**: one (arm, question, repeat) triple; the unit of execution and of the ledger. Exactly 72 in the primary; 24 in the secondary.
- **Ledger**: an append-only record of one run, bound by its header to one corpus, one prompt, one serving configuration; rows are cells with an outcome.
- **Outcome**: `ok` (scored), `exceeds_model_context` (classified, never scored), `error` (attempted, failed), `not_implemented` (could not attempt).
- **Arm view**: what one arm is permitted to read for one question at its ask time — events, entities, edges, and for G alone the episode links.
- **Grading view**: the blinded per-question export; **Seal**: the separate file holding the label-to-arm mapping and seed.
- **Serving configuration**: the identity of the model weights, server image, context size and any context-scaling setting; equal across all cells of one ledger.

### Domain Language

- **arm** — one of G, D, R. Avoid "baseline" for D or R; the rubric calls them arms.
- **cell** — arm × question × repeat. Avoid "run" for a single cell; a *run* is the whole matrix.
- **primary / secondary** — the native-configuration matrix vs the D-YaRN matrix. Never "phase 1/2".
- **exceeds_model_context** — the classified outcome; never "skipped", never "failed".
- **assembled context** — the tokens the arm placed in the prompt slot; distinct from **prompt tokens** (everything sent).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The primary ledger contains exactly 72 cells, each attempted at most three times, with zero `not_implemented` outcomes and every scored cell carrying all §5 columns populated.
- **SC-002**: Exactly six arm-D cells per repeat (18 total) are classified `exceeds_model_context`, each carrying a token count above 262,144 — matching the pre-registered expected result.
- **SC-003**: A run interrupted at any point and resumed reaches the same 72-cell ledger with no scored cell executed twice, demonstrated at least once on the real run.
- **SC-004**: Every request across all arms carries prompt text hashing to the registered value; a one-character change is refused before any cell.
- **SC-005**: The grading view for all eight questions is exported with no arm identifiers, and the seal reproduces the mapping from the recorded seed.
- **SC-006**: The secondary ledger completes 24 cells after the primary, with a header differing from the primary's in exactly the serving-configuration fields.
- **SC-007**: R's median assembled context lands within ±20 % of G's, or every breaching question is visible as a ratio outside that band.
- **SC-008**: Peak memory never exceeds the recorded budget; at completion office4 holds no resident model and no run-owned service, and its memory use is back within 2 GiB of the pre-run reading.

## Architecture Impact

- **office2**: none. No service, credential, port, data flow or cron changes on the managed host; no deploy manifest.
- **office4**: a research sandbox (graph database container, model-serving container, a Python environment) that exists for the run and is torn down after. Recorded per the sandbox carve-out (FR-018), not in the service inventory, because office4 is not a managed host (ADR-0008) and nothing here persists.
- **Docs touched by this mission**: `docs/design/research/849-synthesis/README.md` (harness section), a new run record under `docs/design/research/849-synthesis/` when the ledger is handed off, and the rubric only if the design lead amends it. Navigation docs (`docs/INDEX.md`, `docs/DEVELOPER_PORTAL.md`) are updated if a new research doc is added.
- **Rebaseline**: not required — no audited surface is touched.

## Assumptions

- office4's measured envelope holds: 62.5 GiB GTT, 51.3 GiB peak at full native context, the pinned server image, all substrate packages installable from the machine.
- #849 is the tracking issue; no separate issue is filed for the mission.
- The design lead grades from the grading view and posts §7 on the bus; nothing in this mission scores an answer.
- The four Decision Moments recorded in `decisions/` are the interview of record; no `[NEEDS CLARIFICATION]` markers remain.
