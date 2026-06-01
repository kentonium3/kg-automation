# Mission Spec: Signal-Driven Monitoring with Haiku Gate

**Mission ID**: `01KT22PCH03MTFYX1Q55KQVXRG`
**Mission slug**: `signal-driven-monitoring-haiku-gate-01KT22PC`
**Source issue**: [kentonium3/kg-automation#490](https://github.com/kentonium3/kg-automation/issues/490)
**Mission type**: software-dev
**Target branch**: `main`

---

## 1. Source Description

Felix's current observation pipeline relies on a single ~30-minute heartbeat that prompts the `main` agent (Sonnet 4.6) to read logs, judge significance, and act. On 2026-06-01 this pipeline mis-stated the scope of a real bug (#490 as originally filed claimed "two episodes" of WhatsApp `creds.json` corruption when there were 151 events across 16+ hours). The mis-report surfaced when Kent asked an interactive Claude Code session to investigate.

This mission replaces the conflated pipeline with a two-layer observation architecture. Deterministic signal extraction and threshold-driven issue filing move into `felix-core-digest` (existing Python service that runs every 15 minutes). A cheap-tier LLM gate fronts the OpenClaw heartbeat and only escalates to the expensive tier when there is novel or ambiguous signal worth judgment.

The load-bearing design call (captured on the source issue and validated in pre-spec discussion): **the things Felix should observe and act on are nameable in advance.** We accept narrowing coverage of unknown-unknown patterns in exchange for accurate, low-cost monitoring of named signals. Re-evaluation trigger: if real incidents start going uncaught because they don't match a defined signal.

---

## 2. User Scenarios & Testing

### 2.1 Primary actors

- **Felix observation pipeline** (autonomous system) — extracts signals, files issues, decides whether to escalate heartbeats.
- **Kent** (human stakeholder) — receives filed issues and escalated heartbeat outputs; reads digest summaries; can drop scheduled tasks into the heartbeat contract file.

### 2.2 Primary user flows

**Flow A — Deterministic signal trips threshold, issue filed:**
1. Observation cycle runs (existing 15-min cadence).
2. Cycle extracts a defined signal from logs (e.g., `whatsapp_creds_restore_count`).
3. Signal count over the rolling window crosses its threshold.
4. No matching open issue exists within the dedup window.
5. System files a new issue via `kg-felix-bot` identity, citing exact count + time range + representative log excerpt.
6. Kent sees an accurate report. **No LLM was invoked in this flow.**

**Flow B — Heartbeat tick with no signal, no scheduled task:**
1. OpenClaw heartbeat fires (~30 min cadence).
2. Cheap-tier gate reads the latest digest snapshot and the heartbeat contract file.
3. Gate finds no novel signal, no scheduled task, no escalation marker.
4. Gate returns `HEARTBEAT_OK`. No further LLM invocation.
5. Heartbeat audit log records the gate decision.

**Flow C — Heartbeat tick with novel signal, escalation to expensive tier:**
1. OpenClaw heartbeat fires.
2. Cheap-tier gate inspects the latest digest and detects a pattern not matched by any defined signal.
3. Gate emits `ESCALATE_TO_SONNET` with a structured one-paragraph reason.
4. Existing main-agent path invoked exactly once with the reason as context.
5. Expensive-tier agent judges and acts (file issue, send WhatsApp, edit heartbeat contract, etc.) per existing conventions.

**Flow D — Heartbeat tick with a scheduled task in the contract file:**
1. OpenClaw heartbeat fires.
2. Cheap-tier gate reads the heartbeat contract file and finds a checklist.
3. Gate honors the existing contract: simple tasks handled at the cheap tier; tasks needing judgment escalate to the expensive tier.
4. Behavior indistinguishable from current contract from the contract author's perspective.

### 2.3 Edge cases

- **State file missing or corrupt at cycle start** → cycle falls back to cold-start logic: re-reads recent log windows before trusting state; emits a one-time warning to the systemd journal.
- **Signal extraction error mid-cycle** → cycle logs the error, persists no new state for the failing signal, retries on the next cycle. Other signals in the same cycle proceed normally.
- **Cheap-tier gate failure (API error, timeout)** → heartbeat falls back to current expensive-tier path so observation is not lost. Failure visible in heartbeat audit log.
- **Threshold-crossing signal with existing open issue** → no new issue filed; existing issue may optionally receive a comment with the new count, scoped to one comment per cycle.
- **Heartbeat contract file is template-content (de-facto empty)** → gate treats as empty per the existing "empty = skip" rule.
- **Two cycles trip the same signal between gate runs** → dedup window enforced by signal-ID lookup, not by cycle count.

---

## 3. Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | The observation pipeline extracts each defined signal from its source data exactly once per cycle and persists a structured record (signal ID, count over rolling window, time range, representative excerpt). | Proposed |
| FR-002 | The pipeline files a new issue when a signal crosses its configured threshold AND no matching open issue exists within the configured dedup window. | Proposed |
| FR-003 | Filed issues use the existing template-compliant body builder (so deterministic and LLM-authored filings are structurally indistinguishable) and the `kg-felix-bot` identity. | Proposed |
| FR-004 | Per-signal counter state persists across pipeline restarts; cold-start logic re-reads the most recent N log windows before trusting state. | Proposed |
| FR-005 | Signal definitions (thresholds, dedup windows, source-data selector, log-excerpt extractor) live in a single configuration file editable without code changes. | Proposed |
| FR-006 | The initial signal set includes at minimum: WhatsApp credential-restore events, web-channel watchdog reconnect events, agent unhandled error events. | Proposed |
| FR-007 | The heartbeat gate inspects the latest digest snapshot and the heartbeat contract file, then returns one of three outcomes: `HEARTBEAT_OK`, `LOG_AND_SKIP`, `ESCALATE_TO_SONNET`. | Proposed |
| FR-008 | An `ESCALATE_TO_SONNET` outcome triggers the existing expensive-tier main-agent path exactly once per heartbeat tick, with the gate's structured reason supplied as context. | Proposed |
| FR-009 | Heartbeat outcomes (gate decision, reason, latency) are written to an audit log readable through `openclaw system heartbeat last` or an equivalent surface. | Proposed |
| FR-010 | The heartbeat gate honors the existing heartbeat contract file convention: scheduled tasks in the contract file are executed (cheap tier where feasible, escalated when judgment is required). | Proposed |
| FR-011 | When the gate cannot reach its model or returns a malformed response, the heartbeat falls back to the existing expensive-tier path so observation is never silently dropped. | Proposed |

---

## 4. Non-Functional Requirements

| ID | Requirement | Measurable Threshold | Status |
|---|---|---|---|
| NFR-001 | Reduced expensive-tier invocation cost | Expensive-tier invocations per day drop by ≥80% measured over a representative 7-day window vs the 7 days immediately preceding rollout. | Proposed |
| NFR-002 | Time-to-detection for defined signals | A signal that crosses its threshold within one observation cycle of the triggering event count is detected and filed within ≤1 additional cycle (worst-case ≤30 min from event onset given 15-min cadence). | Proposed |
| NFR-003 | Deterministic-path latency | The deterministic file-issue path does not invoke any LLM. Verified by absence of LLM API calls in the issue-filing code path. | Proposed |
| NFR-004 | Filed issue accuracy | For at least one validated replay (the 2026-06-01 `/tmp/openclaw/openclaw-2026-06-01.log`), the filed issue reports event count within ±2 of the actual ground-truth count and time-range bounds within ±1 cycle of the actual first/last event. | Proposed |
| NFR-005 | Failure observability | All pipeline errors and gate failures appear in either the systemd journal or the existing `last-tick.json` health signal within the cycle they occur. | Proposed |
| NFR-006 | No regression in time-to-action for genuine signals | Replay of the 2026-06-01 incident produces a filed issue at the cycle following onset (≤30 min lag), at least as fast as the current heartbeat-based path. | Proposed |

---

## 5. Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | Filings use the `kg-felix-bot` GitHub identity for clean audit-trail attribution. | Confirmed |
| C-002 | The pipeline reads only existing observation inputs (OpenClaw logs and current `felix-core-digest` inputs). No second-brain access (`~/second-brain/notes/04-Growth/_private/` absolute exclusion per CLAUDE.md). | Confirmed |
| C-003 | No changes to OpenClaw's heartbeat schedule or to the OpenClaw upstream code. The `web-channel` watchdog reconnect-loop bug is out of scope (file separately with the OpenClaw maintainer). | Confirmed |
| C-004 | The existing `felix-core-digest` 15-minute systemd timer remains the cadence floor. No increase in cadence without justification. | Confirmed |
| C-005 | Issue bodies must redact any credential material in log excerpts. | Confirmed |
| C-006 | The mission lands on `main` via spec-kitty merge (merge commit, not PR). Any GitHub Actions added by this mission trigger on `push` to `main`, not `pull_request`. | Confirmed |
| C-007 | The gate's cheap-tier model is `claude-haiku-4-5`; the escalation tier is `claude-sonnet-4-6`. Both already declared in `~/.openclaw/openclaw.json` on office2 — no new credentials required. | Confirmed |
| C-008 | Architecture documentation: any change that adds/modifies deployed services, credentials, or data flows updates the relevant files in `docs/design/architecture/data/` and their markdown counterparts in the same merge. | Confirmed |

---

## 6. Success Criteria

Measurable, technology-agnostic outcomes that define mission success:

1. **Accuracy beats the baseline incident.** A replay of the 2026-06-01 WhatsApp `creds.json` corruption pattern produces a filed issue whose reported event count matches actual ground truth within ±2 events and whose time-range bounds are within ±1 cycle.
2. **Cost drops by an order of magnitude on the common case.** Expensive-tier invocations per day drop by ≥80% over a 7-day post-rollout window vs the 7-day pre-rollout baseline.
3. **No silent misses on heartbeat contract.** Every scheduled task placed in the heartbeat contract file is executed within one heartbeat cycle, with no degradation vs the current expensive-tier behavior.
4. **Novel signal escalation works at least once.** During the post-rollout observation window, at least one heartbeat tick produces an `ESCALATE_TO_SONNET` decision with a structured reason, and the escalated tier completes an action. (Validates the escalation path; absence is also a valid outcome if no novel signal occurs in-window.)
5. **No observation loss on failure.** Induced gate-failure (mocked API error in a test cycle) results in fallback to the expensive-tier path with no dropped tick.
6. **Architecture documentation in sync at merge.** All affected `docs/design/architecture/data/*.json` files reference this mission's issue number in `updated_by`, and their markdown counterparts match.

---

## 7. Key Entities

| Entity | Purpose | Key attributes |
|---|---|---|
| **Signal** | Named, machine-defined observation extracted each cycle. | `signal_id`, `source_selector`, `threshold`, `dedup_window`, `excerpt_extractor` |
| **Signal state** | Persistent per-signal counter that survives cycles and restarts. | `signal_id`, `count_in_window`, `last_event_at`, `last_filed_issue_ref`, `cycle_id` |
| **Cycle record** | One observation cycle's output. | `cycle_id`, `started_at`, `signals_evaluated`, `issues_filed`, `errors` |
| **Heartbeat outcome** | One heartbeat tick's gate decision. | `tick_id`, `outcome` (OK/SKIP/ESCALATE), `reason`, `gate_latency_ms`, `escalated_to` |
| **Signal config** | Declarative source of truth for all signals. | List of signal definitions; editable without code change. |

---

## 8. Assumptions

These assumptions are inherited from #490 and validated through the spec-kitty plan phase via live-probe on office2 (per the `feedback_design_phase_research` pattern):

- **A1**: The existing 15-minute `felix-core-digest` cadence is fast enough for the signals in this mission. To be validated against the 2026-06-01 replay during plan.
- **A2**: OpenClaw's heartbeat surface supports either (a) per-invocation model switching or (b) a wrapper that intercepts the heartbeat trigger before invoking OpenClaw. Plan phase live-probes to determine which mechanism is supported and selects accordingly.
- **A3**: The `kg-felix-bot` PAT's scope already covers issue creation; no new credential needed for the deterministic filer.
- **A4**: The heartbeat contract file convention (current path `/data/services/openclaw/data/HEARTBEAT.md`, "empty = skip" rule) remains stable through the lifetime of this mission.
- **A5**: The signal-extraction digest format (FR-001..FR-006) will be defined within this mission and the heartbeat gate (FR-007..FR-011) will read it. Both layers ship in the same mission; the gate is designed against the actual digest output (per the single-mission scope decision).
- **A6**: Spec-kitty merges create merge commits directly to `main`, not PRs. Any GitHub Actions added in this mission trigger on `push` to `main`.

---

## 9. Out of Scope

- ❌ Fixing the OpenClaw `web-channel` watchdog reconnect-without-backoff loop. Upstream — file separately with the OpenClaw maintainer.
- ❌ Replacing or removing existing `felix-core-digest` observation/summary outputs. This mission is additive.
- ❌ Changing OpenClaw's heartbeat schedule itself.
- ❌ Expanding signal types beyond the initial three (FR-006). Additional signals added incrementally in follow-on work after the framework proves out.
- ❌ Cross-agent escalation routing (main → other felix-admin-* agents). Future work.
- ❌ Preserving the current expensive-tier general-purpose vigilance pass over unknown patterns. This is a deliberate narrowing — see Source Description for the design call and re-evaluation trigger.

---

## 10. Architecture Impact

Per CLAUDE.md standing requirement, any feature that changes deployed services, credentials, data flows, or topology updates the relevant files in `docs/design/architecture/data/` and their markdown counterparts in the same merge.

| File | Expected change |
|---|---|
| `docs/design/architecture/data/service-inventory.json` | `felix-core-digest` entry gains an issue-filing capability flag and a new state-directory path. |
| `docs/design/architecture/data/credential-manifest.json` | Confirm the existing `kg-felix-bot` PAT entry covers `felix-core-digest`'s new filing path (record-only change if scope already matches). |
| `docs/design/architecture/data/data-flows.json` | New flow: observation source → `felix-core-digest` signal extraction → GitHub issue (deterministic, zero-LLM). |
| Markdown views of the above three JSON files | Regenerate to match JSON. |

`updated_by` on all modified JSON files references this mission's source issue (#490).

---

## 11. Change-Risk Tier (per CLAUDE.md taxonomy)

| Component | Tier | Notes |
|---|---|---|
| `felix-core-digest` Python extension | Tier 3 (Standard logic/workflow) | Proceed with dry-run / replay validation against 2026-06-01 log. |
| Systemd state file path + permissions | Tier 2 (Application/state) | Confirm Restic backup currency before first deploy of new state directory. |
| OpenClaw heartbeat gate insertion | Tier 2–3 | If a wrapper is used, it's Tier 3; if heartbeat config is edited, Tier 2. Plan phase classifies definitively. |
| `kg-felix-bot` PAT scope (no change expected) | Tier 0 if changed | If scope change becomes required, generate the change script and present to Kent for manual execution. |

---

## 12. Constitutional Compliance (Felix Constitution)

- **Autonomy level**: Observed (Level 2). The deterministic filer files issues without per-instance approval (precedent: `felix-doc-auditor`). The gate makes a routing decision without escalation when signals are absent.
- **Scope boundary**: This mission governs Felix's own observation/monitoring layer. It does NOT touch agent business logic (inbox processing, habits, escalation routing, tasker).
- **Failure behavior**: Never silent. Signal-extraction failures log and retry next cycle. Gate failures fall back to the expensive-tier path. All errors surface via systemd journal and `last-tick.json`.
- **Privacy boundary**: Reads existing observation inputs only. No second-brain access. Issue bodies redact credential material.
- **Directive 6 (deterministic vs stochastic split)**: Explicit. Signal extraction, threshold check, dedup, issue body construction, GitHub filing — all deterministic. Routing decision over a digest snapshot — cheap-tier judgment. Narrative composition on escalated heartbeats — expensive-tier judgment.

---

## 13. Open Decisions for Plan Phase

These are deferred to plan phase live-probe research, not unresolved spec ambiguity:

- **OD-1**: Gate insertion mechanism — wrapper script vs per-invocation model switch in OpenClaw config. Resolution: plan-phase live-probe of `openclaw system heartbeat` surface and config schema.
- **OD-2**: Concrete initial threshold values for the three signals in FR-006. Resolution: plan phase calibrates against the 2026-06-01 replay and recent history.
- **OD-3**: First-week rollout shape — observation-only (file with a `felix-debug` label or as draft) vs direct cutover. Resolution: plan-phase risk decision based on threshold confidence.
