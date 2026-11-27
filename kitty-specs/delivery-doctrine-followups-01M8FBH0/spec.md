# Mission Specification: Delivery-doctrine follow-ups (#1146)

**Mission Branch**: `kitty/mission-delivery-doctrine-followups-01M8FBH0` (lands on `fix/1146-delivery-doctrine-followups`, then PR to `main`)
**Created**: 2026-11-27
**Status**: Draft
**Input**: kentonium3/kg-automation#1146 ("chore(openclaw): delivery-doctrine guard + wording follow-ups from #1143 reviews"), all six items. Kent confirmed the extracted requirement set on 2026-11-27, answered the one gap question (decision 01M8FBJ302DJXCQPGGGP9QFTFA: deny `conversations_*`, `sessions_*`, `message` and `automations`), and gave his go-ahead for the item 6 deploy manifest.

## Intent Summary

Felix's three scheduled **announce agents** (capture, escalation, habits) must deliver to Kent only through their **final reply**: OpenClaw posts that reply to WhatsApp. #1143 enforced this with a prompt **delivery doctrine** block and a deterministic **wording guard**, which checks the repo-source prompts. Its pre-merge reviews left the following gaps:
- the guard misses some forbidden wording and flags some harmless wording;
- the retry rule can silently drop a load-bearing helper call;
- two skills carry stale or inconsistent wording;
- the forbidden tools are still enabled for these agents.

This mission closes every gap, so the rule holds both in what the agents are told and in what they are able to call.

- **Primary actor:** an announce agent running a scheduled turn.
- **Trigger:** a cron turn that has something to report, or an idle turn.
- **Desired outcome:** the turn ends in exactly one final reply, which reaches Kent. No turn ends early because of a send or record attempt.
- **Invariant:** an announce agent never delivers, records a cron result or relays through any channel other than its final reply.

## Domain Language

| Term | Meaning | Avoid |
|------|---------|-------|
| Announce agent | An OpenClaw agent whose cron uses `delivery.mode: "announce"`: felix-admin-capture, felix-admin-escalation, felix-admin-habits | "WhatsApp agent", "notifier" |
| Delivery doctrine | The canonical block of delivery rules carried verbatim by every announce agent's prompt | "send rules" |
| Wording guard | The deterministic check that flags forbidden delivery wording in repo-source prompts and skills | "linter", "LLM check" |
| Final reply | The agent's last message of a turn, which OpenClaw posts | "the message", "the send" |
| Tool policy | The per-agent allow/deny configuration in office2's live OpenClaw config | "permissions" |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The guard catches every forbidden instruction (Priority: P1)

A maintainer edits an announce agent's prompt or a skill it reads. Wording that would steer the model to send, notify, relay or record a cron result outside the final reply is flagged before merge, whatever its typographic form. Ordinary prose that only mentions these words is not flagged.

**Why this priority**: the guard is the only automated defence for the wording half of the rule. Each false negative is a path back to the #1143 failure (no reply delivered). Each false positive trains maintainers to ignore the guard.

**Independent Test**: run the guard over a fixture set of each listed false-negative and false-positive phrase. Each phrase is classified correctly, and the current repo prompts still pass.

**Acceptance Scenarios**:

1. **Given** a prompt containing `Record **no_change** on an idle turn.` outside the doctrine block, **When** the guard runs, **Then** it reports a violation.
2. **Given** a prompt containing "the cron automations (inbox-7am, noon)", **When** the guard runs, **Then** it reports no violation for that line.
3. **Given** a prompt containing "Do not record no_change" outside the block, **When** the guard runs, **Then** it reports no violation for that line.

---

### User Story 2 - A skipped call is never silent (Priority: P1)

An announce agent makes a tool call that is rejected for invalid input. It either fixes the input or skips the call. If it skips, its final reply says so, so a skipped load-bearing helper (for example escalation's `record_completion`, which records `level_sent`) is visible to Kent.

**Why this priority**: a silent skip loses state, here the escalation level, with no trace.

**Independent Test**: the doctrine block and every announce agent's prompt carry the revised retry rule. A static check confirms the wording and the escalation prompt's size cap.

**Acceptance Scenarios**:

1. **Given** the deployed escalation prompt, **When** it is read, **Then** the retry rule tells the agent to skip a rejected call only while saying so in its final reply.

---

### User Story 3 - Skills an announce agent reads agree with the doctrine (Priority: P2)

Every skill an announce agent reads describes the current behaviour:
- the escalation skill's dedup text describes the JSONL dedup actually used;
- a failed WhatsApp delivery is handled by reporting it in the final reply, never by sending.

**Why this priority**: stale skill text contradicts the prompt, and the model may follow either.

**Independent Test**: the wording guard (in skill mode, with no block required) passes over every such skill. A reviewer confirms the dedup text matches the code.

**Acceptance Scenarios**:

1. **Given** the task-intelligence and vikunja-api skills, **When** the guard runs in skill mode, **Then** no violation is reported, and neither skill instructs a send on delivery failure.

---

### User Story 4 - Forbidden tools are unavailable, not just discouraged (Priority: P2)

On office2, the three announce agents' tool policy no longer exposes `conversations_*`, `sessions_*`, `message` or `automations`. Even if the wording fails, the model cannot reach those tools.

**Why this priority**: it is the enforcement half of the rule. It is held to P2 because the prompt doctrine already works, as the #1143 D5 runs show.

**Independent Test**: a read-only inspection of office2's live config after deploy shows the deny entries for exactly those three agents, with no other agent's policy changed. The next scheduled run of each agent is ok and delivered.

**Acceptance Scenarios**:

1. **Given** the deploy has applied, **When** the live tool policy is read, **Then** each announce agent denies the four tool groups, and every other agent's policy is byte-identical to before.
2. **Given** the deploy has applied, **When** each announce agent's next scheduled run completes, **Then** it is ok and delivered with zero calls to a denied tool.

### Edge Cases

- A forbidden phrase split across a Markdown line break, a table cell or a list marker.
- A legitimate mention of a tool name in a negation ("never call `automations`") outside the canonical block.
- A skill that is shared with a non-announce agent: the guard's skill mode must not demand the doctrine block there.
- Escalation's prompt sits about 120 UTF-16 units under its cap, so the longer retry wording must fit or be offset elsewhere.
- Removing a tool group that one of the three agents genuinely uses for non-delivery work. The plan must confirm none does before the deny lands.
- The OpenClaw config is live state that is not tracked in the repo. The change must be reversible and recorded through the deploy pipeline.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status | Delivery | No-op passable? |
|----|-------|------------|----------|--------|----------|-----------------|
| FR-001 | Close guard false negatives | As a maintainer, I want the guard to flag each item-1 form outside the doctrine block: Markdown emphasis (`**no_change**`), "use the automations tool", `catalog.search("automations")`, `automations.record({...})`, "Mark the run no_change", "Recording no_change", "set outcome to no_change", and mid-sentence "then notify …" variants, so that no forbidden instruction slips through. | High | Open | [build] | no |
| FR-002 | Remove guard false positives | As a maintainer, I want the guard not to flag the item-2 forms: prose such as "the cron automations (inbox-7am, noon)", a mention of a `record_result` field, and a negated "do not record no_change" outside the block, so that the guard stays trusted. | High | Open | [build] | yes — paired with the FR-001 fixtures on the same text, which must still be flagged |
| FR-003 | Retry rule names the skip | As Kent, I want the retry rule to read "…fix the input from the error, or skip it and say so in your final reply" in the canonical block and in every announce agent's prompt, so that a skipped load-bearing helper is never silent. | High | Open | [build] | no |
| FR-004 | Escalation dedup wording is current | As a maintainer, I want the escalation skill's dedup text (about L280–285) to describe the JSONL dedup the agent uses, not comment-based dedup, so that the skill does not contradict the code. | Medium | Open | [build] | no |
| FR-005 | Skills report delivery failure in the final reply | As Kent, I want every skill an announce agent reads (at least task-intelligence and vikunja-api) to handle a failed WhatsApp delivery by reporting it in the final reply, never by sending, with the guard run over those skills in skill mode, so that no skill re-opens a send path. | Medium | Open | [build] | no |
| FR-006 | Tool policy denies the forbidden tools | As Kent, I want office2's live tool policy for felix-admin-capture, felix-admin-escalation and felix-admin-habits to deny `conversations_*`, `sessions_*`, `message` and `automations`, with every other agent unchanged, so that the doctrine is enforced by capability and not only by wording. | Medium | Open | [build] | no |
| FR-007 | Everything ships through the pipeline | As Kent, I want every repo-source change and the tool-policy change applied to office2 through the deploy manifest pipeline, with the deployed files byte-identical to the repo and the security baselines reset for the changed audited surfaces, so that office2 state stays traceable. | High | Open | [build] | no |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Red-then-green per guard change | Every FR-001 and FR-002 case has its own test. 100% of those tests fail before the fix and pass after it, and each FR-002 case has a same-fixture positive control. | Reliability | High | Open |
| NFR-002 | Prompt size caps hold | Each announce agent's deployed prompt stays at or under its cap: escalation ≤ 17,900 UTF-16 units; capture and habits under the caps their existing tests assert. | Reliability | High | Open |
| NFR-003 | Guard stays deterministic | The guard uses string and regex matching only, with no model call. A full run over all announce prompts and skills completes in under 2 seconds on office4. | Performance | Medium | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | No other behaviour change | Agent behaviour changes only as the FRs state. No delivery mode, cron schedule or non-announce agent changes. | Technical | High | Open |
| C-002 | Tier 2 protocol for the tool policy | FR-006 is a Tier 2 change: a Restic backup no older than 24 hours before applying, plus pre- and post-change verification. Kent gave the go-ahead for this manifest on 2026-11-27. | Business | High | Open |
| C-003 | Upstream fix pending | The no-`record_result` rule stays in force while openclaw/openclaw#206884 is open. This mission does not relax it. | Technical | High | Open |

## Assumptions

- Not a bulk edit (DIRECTIVE_035 check, 2026-11-27). The retry wording changes one canonical constant whose copies a test already requires to match byte for byte. No identifier, path or key is renamed, so a missed copy fails that test rather than breaking silently.
- The set of announce agents is the three named in the guard's constant. Plan re-confirms this against office2's live cron delivery modes, read-only.
- None of the three agents needs `conversations_*`, `sessions_*`, `message` or `automations` for non-delivery work. Plan confirms this from the prompts and recent run transcripts before FR-006 is built.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the item-1 and item-2 phrases are classified correctly by the guard (all flagged and all passed as specified), and 0 current repo prompts or skills newly fail. — [build] · no-op passable: no
- **SC-002**: After deploy, the next scheduled run of each of the 3 announce agents is ok and delivered, with 0 calls to a denied tool and 0 tool-loop stops. — [build] · no-op passable: no
- **SC-003**: 0 skills read by an announce agent instruct sending on delivery failure. — [build] · no-op passable: no
- **SC-004**: 0 agents other than the three announce agents have a changed tool policy after deploy. — [ratchet] · no-op passable: yes — paired with SC-002's check that the three announce agents' policies did change
