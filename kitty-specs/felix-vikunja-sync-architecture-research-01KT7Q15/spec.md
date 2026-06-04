# Research Specification: Felix-Vikunja Sync Architecture Design

**Mission ID**: `01KT7Q15NKQFW1J276F4KN2JFG`
**Mission slug**: `felix-vikunja-sync-architecture-research-01KT7Q15`
**Created**: 2026-06-03
**Status**: Draft
**Research Type**: Case Study (mixed methods: live API probing + codebase analysis + doc/memory review)
**Source issue**: [kentonium3/kg-automation#508](https://github.com/kentonium3/kg-automation/issues/508)
**Parent epic**: [kentonium3/kg-automation#507](https://github.com/kentonium3/kg-automation/issues/507)

## Research Question & Scope

**Primary Research Question**: How should Felix bi-directionally synchronize with Vikunja such that the operator constraints (automatic, silent, accurate, ~5-minute latency) are met across all seven use cases enumerated in Epic #507, without coupling to the broader observability framework still being scoped in #516?

**Sub-Questions** (these drive the WPs and findings):

1. **RQ-1 — Vikunja API surface**: What capabilities does the live Vikunja API expose for read access (REST CRUD, batch ops, filtering, subscribe), and which fields are suitable as stable identifiers for sync re-identification across reconciliation cycles?
2. **RQ-2 — Felix touchpoint inventory**: Which Felix code callsites currently read from or write to Vikunja, and what state-freshness assumptions does each make?
3. **RQ-3 — Conflict policy + log shape**: When Felix's computed state diverges from Vikunja's actual state, how is the conflict detected, classified (`auto_resolved` vs `unsafe_to_auto_resolve`), logged, and surfaced — and what log shape is forward-compatible with #516's three possible framework outcomes (sender-contract-only / router-contract-only / both)?
4. **RQ-4 — Use-case → layer mapping**: Map each of Epic #507's seven operator use cases (a–g) to the proposed three-layer model (`status` / `task` / `project`), with detection mechanism, Felix-side response, and worst-case convergence latency under polling.
5. **RQ-5 — Existing-pattern fit**: For each existing Felix pattern (signal-driven monitoring pipeline #59/#490, felix-doc-auditor driver, `schedule_loader.py` reconciliation, `habits-history.jsonl` ledger), assess fit for the sync architecture.
6. **RQ-6 — ADR-0003 scope**: Does ADR-0003 supersede ADR-0002 entirely or extend it? Document the supersede-vs-extend decision with rationale, including the interaction-model diagram update from "webhooks + polling" to polling-only.

**Scope**:

- **In Scope**: Live read-only API probes against Vikunja; exhaustive Felix codebase grep; review of ADR-0001 / ADR-0002 / Epic #507 / Issue #516; cross-reference of operational memory entries (Vikunja gotchas, existing patterns, output discipline); architectural recommendation; draft ADR-0003; roadmap of 2–4 follow-on implementation missions filed as GitHub sub-issues under #507.
- **Out of Scope**: Implementation work of any kind (Python code, systemd units, OpenClaw agents, schema changes); Vikunja upstream changes (e.g., RRULE PR per #506); migration of existing Felix capabilities to the new pattern (those become follow-on missions); implementation of the broader #516 emission framework; any read-write probes against Vikunja.
- **Boundaries**: One Vikunja instance (`https://office2.tail0f5f56.ts.net/api/v1`); current Felix codebase as of mission start; spec-kitty 3.1.8 research-mission conventions.

**Expected Outcomes**:

- Operator can read `findings.md` + `recommendation.md` + draft `adr-0003.md` cold and make an accept-or-reject decision.
- If accepted, 2–4 follow-on missions are pre-scoped and ready for the spec-readiness flip (`spec: brief` → `spec: ready`) before `/spec-kitty.specify` runs on them.
- Architectural decisions are recorded in `adr-0003.md` (canonical record) and reproducible from the source-register + evidence-log.

## Research Methodology Outline

### Research Approach

- **Method**: Case study with mixed-methods evidence collection. Three substrates: (a) live Vikunja API probes (read-only GETs), (b) exhaustive Felix codebase grep, (c) doc/memory review (existing ADRs, Epic body, memory entries).
- **Data Sources**:
  - **Primary**: Live Vikunja instance at `https://office2.tail0f5f56.ts.net/api/v1`; current Felix codebase under `/Users/kentgale/repos/kg-automation/`.
  - **Secondary**: `docs/design/architecture/adr/0001-google-workspace-via-gog.md`, `docs/design/architecture/adr/0002-felix-vikunja-task-model.md`, [Epic #507](https://github.com/kentonium3/kg-automation/issues/507), [Issue #516](https://github.com/kentonium3/kg-automation/issues/516); operational memory entries (`reference_vikunja_id_vs_identifier`, `reference_vikunja_filter_gotchas`, `reference_felix_doc_auditor_ops`, `feedback_signal_driven_doc_audit`, `feedback_vikunja_sync_polling_not_webhooks`, `feedback_idle_pings_acceptable_for_now`, others).
- **Analysis Approach**: Per-sub-question structured analysis populating `research/evidence-log.csv` with confidence-tagged findings; cross-RQ synthesis into `findings.md` (in the deliverables path); architectural recommendation in `recommendation.md`; ADR-0003 draft in `docs/design/architecture/adr/`.

### Success Criteria

- **SC-001**: ADR-0003 draft's supersede-vs-extend choice is explicit with rationale sourced to specific ADR-0002 decisions.
- **SC-002**: `findings.md` contains six sourced sub-sections (RQ-1 through RQ-6); none stubbed; all citing rows in `evidence-log.csv`.
- **SC-003**: RQ-2 touchpoint inventory enumerates every file from the broad codebase grep, with reproducible grep commands documented verbatim.
- **SC-004**: All seven Epic #507 use cases mapped in the RQ-4 table with every column populated (layer / detection / Felix-action / worst-case-latency).
- **SC-005**: 2–4 GitHub sub-issues filed under Epic #507, ordered by dependency, labeled `spec: brief`.
- **SC-006**: The conflict-event log shape has a written compatibility analysis against each of #516's three framework outcomes (sender-only, router-only, both).
- **SC-007**: Operator review on issue #508 records `accept` or `reject + feedback` as a comment, with the merge commit hash.

## Research Requirements

### Functional Requirements

Functional requirements split into Data Collection (FR-001..005), Analysis (FR-006..012). The research-kitty spec-template names these `DR-###` / `AR-###`, but spec-kitty's `map-requirements` CLI only accepts `FR-###` / `NFR-###` / `C-###`. The semantic split is preserved via the subheadings below.

#### FR — Data Collection (formerly DR)

- **FR-001**: Research MUST collect Vikunja API surface evidence (server version, task and project schemas, identifier fields, filter behavior, batch capability, subscribe capability) via read-only GETs against `https://office2.tail0f5f56.ts.net/api/v1`. No write probes.
- **FR-002**: All sources MUST be documented in `kitty-specs/felix-vikunja-sync-architecture-research-01KT7Q15/research/source-register.csv` with citation, URL, accessed_date, relevance, and status.
- **FR-003**: All findings MUST be logged in `kitty-specs/felix-vikunja-sync-architecture-research-01KT7Q15/research/evidence-log.csv` with timestamp, source_type, citation, key_finding, confidence (high/medium/low), and notes.
- **FR-004**: Felix touchpoint inventory MUST be exhaustive (every callsite, not representative); reproducible grep commands MUST be pasted verbatim into the evidence trail.
- **FR-005**: Live-probe transcripts MUST be captured separately (raw HTTP request and response) so that every API claim can be retraced. Token redacted if it appears.

#### FR — Analysis (formerly AR)

- **FR-006**: Findings MUST be synthesized into `findings.md` (located at the deliverables path; default `docs/research/felix-vikunja-sync-architecture/`) with one section per sub-question (RQ-1 through RQ-6).
- **FR-007**: Methodology MUST be documented in `plan.md` with per-sub-question source plan, probe sequence, acceptance gate, and stop conditions — reproducible by a second researcher.
- **FR-008**: Limitations MUST be explicitly identified per sub-question (e.g., live instance unreachable, token permission gap, missing patterns).
- **FR-009**: The architectural recommendation MUST be captured in `recommendation.md` (deliverables path) AND in draft `adr-0003.md` (canonical record at `docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md`); the two MUST agree on architectural decisions but may differ in tone (recommendation = explainer; ADR = record).
- **FR-010**: The proposed conflict-event log shape MUST include a forward-compatibility analysis against each of #516's three possible framework outcomes (sender-only, router-only, both). Each outcome gets at least one paragraph naming a load-bearing schema field.
- **FR-011**: Every operator use case from Epic #507 (a–g) MUST be mapped to the proposed three-layer model with detection mechanism, Felix-side action, and worst-case convergence latency under polling. Latency MUST be ≤ 5 minutes per NFR-002 below.
- **FR-012**: The roadmap of 2–4 follow-on implementation missions MUST be filed as GitHub sub-issues under Epic #507 with explicit `Depends on #N` declarations and no dependency cycles.

### Non-Functional Requirements (formerly QR)

- **NFR-001**: Every load-bearing claim in `findings.md` MUST be cited to a row in `evidence-log.csv` (per `feedback_signal_driven_doc_audit` discipline). Zero unsourced load-bearing claims.
- **NFR-002**: The architectural recommendation MUST satisfy the latency budget from Epic #507: Felix converges to the latest Vikunja state within 5 minutes for any use case in the RQ-4 mapping. If not, the recommendation must surface the gap.
- **NFR-003**: Conflict-event-log volume in the recommended architecture MUST stay well below the existing OpenClaw whatsapp noise floor (currently 4× daily inbox-cron IDLE pings per `feedback_idle_pings_acceptable_for_now`). Back-of-envelope volume estimate ≤ 1/day unsafe-class WhatsApp pings; guard mechanism (rate limit, batching, threshold) documented.
- **NFR-004**: ADR-0003 draft MUST be readable cold — operator reads it without working notes and makes an accept/reject decision in ≤1 round (per the Felix output-discipline pattern, memory `reference_felix_output_discipline_pattern`).
- **NFR-005**: Filed sub-issues MUST use "Depends on #N" syntax explicitly; the dependency DAG MUST be acyclic.
- **NFR-006**: Every API claim in `findings.md` MUST be tagged either `observed (probe transcript row in evidence-log)` or `documented (URL)`. Where the two diverge, the divergence is itself a finding.
- **NFR-007**: Alternative interpretations MUST be considered for any architectural decision where a reasonable alternative exists (e.g., webhooks-instead-of-polling — dropped per C-001; GitHub-issue-instead-of-log surfacing — dropped per C-003).

## Constraints (Locked Policy Inputs)

These are not research requirements — they are operator decisions made before the research started and carry into every WP without being re-litigated.

- **C-001**: **Polling-only, not webhooks.** RQ-1's webhook sub-question closes early in the research (memory `feedback_vikunja_sync_polling_not_webhooks`).
- **C-002**: **Vikunja wins conflicts.** When Felix's computed state and Vikunja's actual state diverge, Vikunja is canonical.
- **C-003**: **Conflict surfacing is silent in steady-state.** Felix writes conflict events to a log (canonical sender-side emission). Unsafe-to-auto-resolve conflicts (criteria-to-develop in RQ-3) emit a succinct WhatsApp ping via OpenClaw's whatsapp router. No GitHub-issue auto-file as primary surface for conflicts.
- **C-004**: **Operator constraints**: automatic, silent, accurate; latency budget ~5 minutes. "Accurate" implies idempotency must be a first-class property of the proposed model.
- **C-005**: **Mission type is `research`.** No code lands from this mission. Outputs are markdown and filed GitHub sub-issues.
- **C-006**: **Out-of-scope**: Vikunja upstream changes (e.g., RRULE PR per #506); migration of existing Felix capabilities to the new pattern; implementation of the broader #516 emission framework; any read-write probes against Vikunja.
- **C-007**: **Codex paused** (memory `feedback_codex_paused`). Review of WP outputs is Claude self-review or operator review; do not dispatch codex.
- **C-008**: **Two-stage spec lifecycle** (memory `feedback_spec_lifecycle`). Filed sub-issues land at `spec: brief` (NOT `spec: ready`). Operator formalization is a separate gate.

## Key Concepts & Terminology

- **Sync Layer**: One of `status` / `task` / `project`. Each layer has its own Vikunja state surface, reconciliation cadence, and latency budget within the overall 5-min ceiling.
- **Touchpoint**: A Felix code callsite that reads from or writes to Vikunja. Each touchpoint is owned by a component (e.g., habits-sweeper, inbox-capture agent) and operates on one or more layers.
- **Conflict Event**: A structured log record emitted when Felix's computed state diverges from Vikunja's actual state. Consumed by zero-or-more routers (initially: log + WhatsApp for unsafe-class only).
- **Unsafe-to-Auto-Resolve Conflict**: A subclass of conflict events where automatic reconciliation could lose operator intent or produce incorrect downstream behavior. Criteria defined by this research (RQ-3).
- **Reconciliation Cycle**: One polling pass that reconciles Felix's view with Vikunja's actual state. Cadence and trigger decided by the recommendation.
- **Stable Identifier**: The field(s) Felix uses to refer to a Vikunja entity across reconciliation cycles. Memory `reference_vikunja_id_vs_identifier` flags the UI's `identifier` (e.g., `#10`) vs the API's `id` (e.g., `73`) — both candidates with different stability properties.
- **Deliverables Path**: The location where research OUTPUT lands (separate from `kitty-specs/` planning artifacts). Default for this mission: `docs/research/felix-vikunja-sync-architecture-research-01KT7Q15/`. Confirmed during planning.

## Evidence Tracking Guidance

- Log every reviewed source in `research/source-register.csv` with citation, URL, relevance, and status. Source types include: live API endpoint (use endpoint path as identifier), codebase file (use repo-relative path), existing ADR (URL or repo path), memory entry (use memory name), GitHub issue (use issue number).
- Capture each load-bearing finding in `research/evidence-log.csv` with confidence (high if directly observed in a probe transcript or a single grep hit; medium if synthesized from multiple sources; low if relying on memory not re-verified). Notes column captures caveats (e.g., "API version 2026.5 — re-verify on upgrade").
- Reference evidence row IDs (use the `timestamp` column as a stable anchor) when making claims in `findings.md` or any per-RQ analysis. The reviewer of a WP should be able to walk from any claim back to its evidence row in one hop.

## Assumptions

- The Vikunja instance at `https://office2.tail0f5f56.ts.net/api/v1` is the canonical instance the architecture will sync against (operator-owned, on office2, behind Tailscale). No multi-instance considerations.
- The `vikunja-api` token's permissions are sufficient for the read-only API surface needed for RQ-1. If a probe reveals a permission gap, the research documents the gap but does not propose a token rotation (token rotation is operator scope).
- Felix's existing storage substrates (JSONL ledgers, last-tick pointer files, state files on office2) are available for the architecture to reuse. The research does not need to propose a new persistence layer unless none fit.
- Operator review of the draft ADR happens synchronously with Kent in a future session, not asynchronously via GitHub comment.
- The default deliverables path (`docs/research/<mission-slug>/`) is acceptable unless Kent prefers a custom path during planning.

## References

- **Parent epic**: [kentonium3/kg-automation#507](https://github.com/kentonium3/kg-automation/issues/507) — Felix↔Vikunja bi-directional sync foundation.
- **Cross-referenced spike**: [kentonium3/kg-automation#516](https://github.com/kentonium3/kg-automation/issues/516) — Felix-wide observability and status-emission framework. The conflict-event log shape proposed by this research must be forward-compatible with #516's eventual framework decision (FR-010, SC-006).
- **Existing ADR (base for ADR-0003)**: `docs/design/architecture/adr/0002-felix-vikunja-task-model.md`.
- **Format reference**: `docs/design/architecture/adr/0001-google-workspace-via-gog.md`.
- **Source incident**: mission #408 WP01 task_id mis-binding — the bug that surfaced the need for a sync architecture.
- **Memory cross-references**: see DR/AR/QR sections and Constraints for in-context citations.

## Notes on Mission Mechanics (not requirements)

- This mission's gate to "real done" is **operator review on #508 as a comment**, not the spec-kitty merge. SC-007 codifies this. The spec-kitty merge promotes the artifacts to `main` but does not promote the recommendation to accepted.
- This mission produces no running code. Implementation lands in the 2–4 follow-on missions filed by FR-012.
- The session that produced this mission previously ran a software-dev-typed attempt of the same work; that attempt was aborted (commits reset, mission directory removed) when a structural artifact-layout mismatch was discovered. The current mission is the clean re-run with `--mission-type research` declared at create time. The aborted prior session's spec.md content informed this rewrite.
