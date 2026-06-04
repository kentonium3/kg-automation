# Tasks: Felix-Vikunja Sync Architecture Research

**Mission ID**: `01KT7Q15NKQFW1J276F4KN2JFG`
**Mission slug**: `felix-vikunja-sync-architecture-research-01KT7Q15`
**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Methodology details**: see plan.md per-sub-question sections · **Data model**: [data-model.md](data-model.md) · **Decision log**: [research.md](research.md)
**Source issue**: [kentonium3/kg-automation#508](https://github.com/kentonium3/kg-automation/issues/508)
**Deliverables path**: `docs/research/felix-vikunja-sync-architecture/` (from `meta.json`)

## Branch Strategy

- **Planning / base branch**: `main`
- **Final merge target**: `main`
- All WPs run in the single `lane-planning` lane (research-kitty's default for `planning_artifact` execution-mode).

## Artifact Layout (per research-kitty conventions)

Two-location split:

**Sprint planning artifacts** in `kitty-specs/felix-vikunja-sync-architecture-research-01KT7Q15/`:
- `research/source-register.csv` — shared across WPs (append-only by all). Every WP adds sources as they consult them.
- `research/evidence-log.csv` — shared across WPs (append-only by all). Every WP adds findings as they accumulate.

**Research deliverables** in `docs/research/felix-vikunja-sync-architecture/` (`meta.json`'s `deliverables_path`):
- `findings/rq-1-vikunja-api.md` (WP01)
- `findings/rq-2-touchpoints.md` (WP01)
- `findings/rq-5-pattern-fit.md` (WP01)
- `findings/probe-transcripts.md` (WP01 — raw HTTP appendix for NFR-006 reproducibility)
- `findings/rq-3-conflict-policy.md` (WP02)
- `findings/rq-4-use-case-mapping.md` (WP02)
- `findings/conflict-event-log.sketch.md` (WP02 — the only "contract" this mission produces)
- `findings/rq-6-adr-scope.md` (WP03)
- `findings.md` (WP03 — synthesis/index, operator-cold readable)
- `recommendation.md` (WP03 — operator-facing architectural proposal)

**Canonical ADR** outside both:
- `docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md` (WP03)

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Scaffold deliverables path; create `findings/` subdir + per-RQ-1/2/5 skeletons + `probe-transcripts.md` | WP01 | — | [D] |
| T002 | Execute RQ-1 Vikunja API probes (read-only); populate source-register + evidence-log; write `findings/rq-1-vikunja-api.md`; append raw transcripts | WP01 | [D] |
| T003 | Execute RQ-2 touchpoint inventory; populate source-register + evidence-log; write `findings/rq-2-touchpoints.md` | WP01 | [D] |
| T004 | Execute RQ-5 existing-pattern fit analysis; populate source-register + evidence-log; write `findings/rq-5-pattern-fit.md` | WP01 | [D] |
| T005 | NFR-001 / NFR-006 enforcement on WP01 outputs; flag deferred-to-implementation sub-questions | WP01 | — | [D] |
| T006 | Execute RQ-3 conflict-policy analysis; write `findings/rq-3-conflict-policy.md` | WP02 | — | [D] |
| T007 | Draft `findings/conflict-event-log.sketch.md` (FR-equivalent FR-010 log shape) | WP02 | — | [D] |
| T008 | Write #516-framework forward-compatibility analysis (sender-only / router-only / both) per SC-006 | WP02 | — | [D] |
| T009 | Execute RQ-4 use-case → layer mapping; write `findings/rq-4-use-case-mapping.md` | WP02 | [D] |
| T010 | NFR-002 (≤5-min for all 7 use cases) and NFR-003 (WhatsApp volume guard) enforcement; document volume estimate | WP02 | — | [D] |
| T011 | Execute RQ-6 ADR-0003 scope decision; write `findings/rq-6-adr-scope.md` | WP03 | — |
| T012 | Write `findings.md` synthesis/index across all per-RQ files | WP03 | — |
| T013 | Write `recommendation.md` (operator-readable cold per NFR-004) | WP03 | — |
| T014 | Draft `docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md`; replace polling-only interaction-model diagram | WP03 | — |
| T015 | Decide on 2–4 follow-on mission scopes + dependencies | WP03 | — |
| T016 | File 2–4 sub-issues under Epic #507 via `gh api graphql addSubIssue`; back-fill cross-references in findings.md and recommendation.md | WP03 | — |
| T017 | NFR-004 / NFR-005 / SC-001 / SC-007 readiness check; document operator-review-pending status | WP03 | — |

**[P]** marks subtasks safely parallelizable within a single WP.

**Shared resources (NOT in any WP's owned_files)**: `kitty-specs/felix-vikunja-sync-architecture-research-01KT7Q15/research/source-register.csv` and `evidence-log.csv`. Per research-kitty convention these CSVs are append-only across all WPs. Each WP's prompt instructs the agent to append rows without altering rows owned by other WPs.

---

## WP01 — Gathering substrate: independent RQs + evidence registration

**Estimated prompt size**: ~400 lines.
**Subtasks**: 5 (T001–T005).
**Dependencies**: none.
**MVP scope**: yes — this WP delivers the substrate (Vikunja API surface, Felix touchpoints, pattern fit) that WP02 and WP03 read.

**Goal**: Produce sourced research findings for RQ-1, RQ-2, RQ-5 (no inter-RQ dependencies); populate `source-register.csv` and `evidence-log.csv` with every consulted source and every load-bearing finding; satisfy NFR-001 / NFR-006 per WP05 quality gate.

**Independent test**: A reviewer can re-run the documented Vikunja API probes and codebase grep commands and reproduce every claim in the three per-RQ files.

**Subtasks**:
- [x] T001 Scaffold deliverables path; create `findings/` subdir + per-RQ skeletons + `probe-transcripts.md` (WP01)
- [x] T002 Execute RQ-1 Vikunja API probes; populate source-register + evidence-log; write `findings/rq-1-vikunja-api.md`; append raw transcripts (WP01)
- [x] T003 Execute RQ-2 touchpoint inventory; populate source-register + evidence-log; write `findings/rq-2-touchpoints.md` (WP01)
- [x] T004 Execute RQ-5 existing-pattern fit analysis; populate source-register + evidence-log; write `findings/rq-5-pattern-fit.md` (WP01)
- [x] T005 NFR-001 / NFR-006 enforcement on WP01 outputs; flag deferred-to-implementation sub-questions (WP01)

**Implementation sketch**:
1. T001 — Create `docs/research/felix-vikunja-sync-architecture/findings/` directory and four skeleton files. Each per-RQ file has frontmatter declaring `rq_id`, `title`, `depends_on`, `wp`. `probe-transcripts.md` starts with one heading per RQ-1 probe (filled by T002).
2. T002 (parallelizable with T003, T004) — Execute the RQ-1 probe sequence from plan.md verbatim. Capture raw HTTP request + response into `probe-transcripts.md`; summarize into `findings/rq-1-vikunja-api.md` with observed/documented tagging per NFR-006. For every source consulted (API endpoint, doc URL, memory entry), append a row to `source-register.csv`. For every load-bearing finding, append a row to `evidence-log.csv` with confidence level.
3. T003 (parallelizable with T002, T004) — Execute the RQ-2 grep sequence verbatim. Document every grep command in `findings/rq-2-touchpoints.md` (reproducibility per FR-004). Enumerate every callsite (not just every file) per `data-model.md` § Touchpoint columns. Add rows to source-register (file paths) and evidence-log (touchpoint findings).
4. T004 (parallelizable with T002, T003) — For each existing pattern (signal pipeline, doc-auditor driver, schedule_loader, habits-history.jsonl), apply the fit-assessment template. Write verdict + rationale into `findings/rq-5-pattern-fit.md`. Add memory entries and code paths to source-register; add fit assessments to evidence-log.
5. T005 — Walk each per-RQ file. Verify: every load-bearing claim cites an evidence-log row (NFR-001); every API claim is observed/documented-tagged (NFR-006). For each per-RQ file, add a final section **Deferred to implementation** with any sub-questions parked for follow-on missions per C-006.

**Parallel opportunities**: T002, T003, T004 are independent — different substrates (live API, codebase, existing patterns). Can interleave within the lane.

**Dependencies in this WP**: T002/T003/T004 require T001 (skeletons). T005 requires T002/T003/T004.

**Risks**:
- Live Vikunja unreachable → fall back to docs only; flag as caveat (plan.md RQ-1 stop conditions).
- Token permission gap → document gap, no rotation.
- Grep misses unusual import patterns → mitigated by FR-004 reproducibility.

---

## WP02 — Dependent RQs (RQ-3, RQ-4) + conflict-event log sketch

**Estimated prompt size**: ~400 lines.
**Subtasks**: 5 (T006–T010).
**Dependencies**: WP01.
**MVP scope**: extends WP01's substrate into the policy + use-case mapping decisions that drive the recommendation.

**Goal**: From WP01's substrate findings, produce conflict-resolution policy + unsafe-class criteria + log shape with #516 forward-compat (RQ-3, FR-010, SC-006); produce use-case → layer mapping (RQ-4) with ≤5-min worst-case latency (NFR-002); enforce WhatsApp noise-floor guard (NFR-003).

**Independent test**: A reviewer reading the WP02 outputs can answer for each Epic #507 use case: which layer changes, how does Felix detect it, what action does Felix take, what's the worst-case latency? — without referring back to spec.md or Epic #507's body.

**Subtasks**:
- [x] T006 Execute RQ-3 conflict-policy analysis; write `findings/rq-3-conflict-policy.md` (WP02)
- [x] T007 Draft `findings/conflict-event-log.sketch.md` (FR-010 log shape) (WP02)
- [x] T008 Write #516-framework forward-compatibility analysis (sender-only / router-only / both) per SC-006 (WP02)
- [x] T009 Execute RQ-4 use-case → layer mapping; write `findings/rq-4-use-case-mapping.md` (WP02)
- [x] T010 NFR-002 + NFR-003 enforcement; document volume estimate (WP02)

**Implementation sketch**:
1. T006 — Read WP01's RQ-1 (Vikunja write semantics) and RQ-2 (touchpoint write-sets). For each write-set, identify what Vikunja state can conflict. Propose unsafe-class criteria; each testable from conflict-event fields alone (per `data-model.md` § Unsafe-Class). Document the detection mechanism + WhatsApp ping format. Cite WP01 rows in evidence-log.
2. T007 — Draft schema in `findings/conflict-event-log.sketch.md` using `data-model.md` § Conflict Event dimensions. Include `schema_version`. Show one worked example per `conflict_class`. Document `event_id` derivation (idempotency anchor).
3. T008 — For each of #516's three framework outcomes (sender-only, router-only, both), write a paragraph naming at least one load-bearing schema field. Land as the final section of `findings/conflict-event-log.sketch.md`. Cross-link from `findings/rq-3-conflict-policy.md`.
4. T009 (can parallelize with T006 if WP01 outputs settled) — Extract Epic #507's 7 use cases verbatim. Populate the layer / detection / Felix-action / worst-case-latency columns per `data-model.md` § Sync Layer.
5. T010 — Walk the RQ-4 table; confirm every worst-case-latency ≤ 5 min (NFR-002). Compute the WhatsApp volume estimate (criteria × use cases × frequency); document guard mechanism keeping unsafe-class pings ≤ 1/day (NFR-003).

**Parallel opportunities**: T009 can run alongside T006 if WP01 outputs are settled. T007 + T008 are sequential.

**Dependencies in this WP**: T006 → T007 → T008. T009 depends on WP01 RQ-1/RQ-2 outputs. T010 depends on T006-T009.

**Risks**:
- Vikunja lacks stable identifier (from WP01 RQ-1): escalate (conflict detection unsound).
- Sub-1-min latency required for any use case: escalate.
- Volume estimate exceeds noise floor even with guards: tighten criteria; document tension.

---

## WP03 — Synthesis + ADR-0003 draft + follow-on sub-issue filing

**Estimated prompt size**: ~550 lines.
**Subtasks**: 7 (T011–T017).
**Dependencies**: WP01, WP02.
**MVP scope**: produces the operator-facing outputs (synthesis, recommendation, ADR, sub-issue roadmap) and closes the mission deliverables.

**Goal**: Synthesize all per-RQ findings into `findings.md`; produce operator-readable `recommendation.md` (NFR-004); draft ADR-0003 with supersede-vs-extend choice per SC-001 + RQ-6; file 2-4 follow-on sub-issues with explicit dependency declarations (FR-012, NFR-005); document operator-review-pending state per SC-007.

**Independent test**: Operator reads `recommendation.md` + draft `adr-0003.md` cold (no working notes) and makes accept/reject decision in one round (NFR-004 verifiable via NFR-equivalent check in T017).

**Subtasks**:
- [ ] T011 Execute RQ-6 ADR-0003 scope decision; write `findings/rq-6-adr-scope.md` (WP03)
- [ ] T012 Write `findings.md` synthesis/index across all per-RQ files (WP03)
- [ ] T013 Write `recommendation.md` (operator-readable cold per NFR-004) (WP03)
- [ ] T014 Draft `docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md`; replace polling-only interaction-model diagram (WP03)
- [ ] T015 Decide on 2–4 follow-on mission scopes + dependencies (WP03)
- [ ] T016 File 2–4 sub-issues under Epic #507 via `gh api graphql addSubIssue`; back-fill cross-references (WP03)
- [ ] T017 NFR-004 / NFR-005 / SC-001 / SC-007 readiness check; document operator-review-pending status (WP03)

**Implementation sketch**:
1. T011 — Read ADR-0002 in full. Enumerate each architectural decision. For each, classify the proposed sync architecture's stance (override/extend/preserve). Apply tally rule from plan.md RQ-6. Write verdict + rationale into `findings/rq-6-adr-scope.md`.
2. T012 — Synthesize across all six per-RQ files into `findings.md`. One paragraph per RQ summary; links to each per-RQ file; link to recommendation.md and ADR-0003. Footer: **Operator review pending on #508** with exact criterion (per SC-007).
3. T013 — Write `recommendation.md` operator-readable. Sections: Summary, Sync layers, Polling cadence, Conflict resolution, Log shape summary, Identifier choice, What this changes, What this defers. No jargon undefined on first use; no implicit reliance on working notes.
4. T014 — Draft ADR-0003 in ADR-0001 format. Front matter declares supersedes-or-extends per T011. Sections: Status (Draft), Context, Decision, Consequences (positive/negative/risks), Alternatives considered (webhooks dropped per C-001, GH-issue conflict surfacing dropped per C-003, #516 framework dropped per C-006). Interaction-model diagram: replace Epic #507's "webhooks + polling" with polling-only (Mermaid format per project convention).
5. T015 — Scope 2-4 follow-on missions. Default tilt: fewer-larger. Each must be bounded for one mission's worth of work. Capture predecessors via "Depends on #N" syntax.
6. T016 — Pre-flight: confirm `kg-felix-bot` token available (memory `project_kg_felix_bot_identity`); if not, surface as blocker. For each mission: `gh issue create` with structured body (feature/infra template per `.github/ISSUE_TEMPLATE/`); labels `area/task-intel`, `P1-feature`, `spec: brief` (NOT `spec: ready` per C-008); add Directive-8 symptom/observer/cost block per memory `feedback_operational_symptom_required`. After all filed: link via `gh api graphql` `addSubIssue` mutation. Add to Felix Roadmap project per memory `project_github_project_backlog`. Back-fill issue numbers into `findings.md` and `recommendation.md`.
7. T017 — Quality gate. Verify NFR-equivalent NFR-004 (ADR cold-readable); NFR-005 (no dependency cycles in filed sub-issues); SC-001 (supersede/extend rationale explicit); SC-007 readiness (operator review on #508 is next step). Document `Mission status` block in `findings.md` footer.

**Parallel opportunities**: T011 → T012 → T013 → T014 sequential (each builds on prior). T015 + T016 sequential. T017 depends on T011-T016.

**Dependencies in this WP**: T011 → T012 → T013 → T014. T015 → T016 → T017. T012/T013 can interleave with T011 if RQ-6 verdict is settled early.

**Risks**:
- `kg-felix-bot` token unavailable: blocker.
- Recommendation surfaces ADR-0002 tension requiring operator input: escalate.
- 2-4 mission count insufficient: file 4 and surface count-overrun in `findings.md`.
- Recommendation contradicts WP01/WP02 substrate: stop; surface contradiction.

---

## Dependency Graph

```
WP01 ──► WP02 ──► WP03
```

Single lane (`lane-planning`). Sequential within the lane. WP02 reads WP01 outputs; WP03 reads WP01 + WP02 outputs directly.

## MVP Scope

**WP01**. Substrate for everything downstream.

## Validation Status

- ✓ All WPs within ideal size range (5, 5, 7 subtasks).
- ✓ Each WP has a clear independent test.
- ✓ Dependencies form a linear chain (no cycles).
- ✓ MVP scope identified (WP01).
- ✓ Parallel opportunities marked at subtask level ([P]).
- ✓ Risks documented per WP.
- ✓ Shared CSV resources (source-register, evidence-log) handled per research-kitty convention (append-only across WPs, not in any WP's owned_files).

## Next Step

`/spec-kitty.implement` to claim WP01. Implementation handoff offered at the end of this command's report.
