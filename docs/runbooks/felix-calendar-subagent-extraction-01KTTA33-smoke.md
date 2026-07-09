---
title: Smoke checklist — felix-admin-calendar extraction
doc_type: runbook
status: approved
owners: [kent]
audience: humans
last_validated: 2026-06-11
last_updated: '2026-06-11'
updated_by: '#579'
version: "1.0"
---

# Smoke checklist — felix-admin-calendar extraction (#579)

> **Purpose**: post-deploy operator verification for mission
> `felix-calendar-subagent-extraction-01KTTA33`. This is the behavioral
> layer the deploy script's automated checks (pytest + journal-grep) can't
> cover — the round-trip of "DM in → reply out" for each subagent, plus a
> 24h passive observation window for scheduled outbound flows.
>
> **Substrate**: I drive this myself from my phone. There is no synthetic
> message injector and no automated subagent invocation. Each row is a
> check with a binary outcome (per `feedback_live_integration_tests`).
>
> **Coverage**: SC-001 (habit DM), SC-002 (calendar DM + clarification
> round-trip), SC-004 (no truncation warning), SC-005 (other-subagent
> regression set), SC-006 (scheduled outbound), SC-007 (rebaseline +
> clean audit), SC-008 (architecture surfaces reflect new agent). SC-003
> (main/AGENTS.md < 12K) is verified by the deploy script's pytest and
> isn't repeated here.

---

## 1. Pre-conditions

Before I start ticking any boxes below, all of the following must be true.
If any of them fail, stop and resolve before running the smoke. False
negatives from a half-deployed system are worse than no run at all.

- [ ] Deploy script ([`scripts/deploy/deploy-felix-admin-calendar.sh`](<../archive/scripts/deploy/deploy-felix-admin-calendar.sh>))
      completed with exit code 0. The deploy script runs pytest and a
      journal-watch before exiting; if it didn't exit clean, don't continue.
- [ ] `journalctl --user -u openclaw-gateway --since "<deploy-start-ts>"`
      shows zero `truncating in injected context` hits for `agent:main:*`
      session-init events. The deploy script also checks this — confirm it
      stayed clean for at least one full session-init cycle post-deploy.
- [ ] Rebaseline command completed on office2 (per
      [`docs/runbooks/security-baseline-ops.md`](<./security-baseline-ops.md>)).
      The merge commit will need either `Rebaseline: completed at <ts>` or
      an explicit reason for omission — record the timestamp now.
- [ ] **Observation-start timestamp recorded**: ____________________________
      (ISO-8601, e.g. `2026-06-11T18:30:00-04:00`). I use this as the
      `--since` argument in the journal commands below and as the anchor
      for the 24h observation window.

---

## 2. DM round-trips

I send each DM from my phone via WhatsApp and confirm the reply arrives.
Latency target: ≤ 30 seconds for the relay segment (NFR-003). If a DM
fails, see § 5 Decision criteria — most likely outcome is "file regression
bug, do not mark mission complete."

| # | Subagent | DM I send | Expected reply | SC | Pass? | Observed at |
|---|---|---|---|---|---|---|
| 1 | `felix-admin-habits` | `mark habits 1, 3, 5 complete` (or whichever indices are current for today) | Confirmation message listing the habits marked. | SC-001 (the bug's originating regression) | ☐ | __________ |
| 2 | `felix-admin-capture` | A WhatsApp message that should be inbox-routed — I pick one matching current inbox usage (a stray thought, a link to capture, an item I want triaged). | Inbox classification + Vikunja task creation + structured reply with the disposition. | SC-005 | ☐ | __________ |
| 3 | `felix-admin-tasker` | `what's on my list today` | Task list reply (today's open Vikunja items, formatted for chat). | SC-005 | ☐ | __________ |
| 4 | `felix-admin-escalation` | An escalation trigger appropriate for the current state of the system (operator-specific — usually a follow-up nudge or a "what's blocking X" probe; the exact phrasing depends on what's escalable right now). | Escalation reply citing the rule/context that fired. | SC-005 | ☐ | __________ |
| 5 | `felix-admin-calendar` (NEW) — happy path | `schedule a 30-min check-in tomorrow at 2pm` | Either: (a) event-created success envelope ("event created on <calendar>, <date> 14:00–14:30 ET"), OR (b) clarification asked ("which calendar? attendees?"). Either outcome counts as pass for this row — both paths exercise the dispatch and the reply relay. | SC-002 | ☐ | __________ |
| 6 | `felix-admin-calendar` (NEW) — clarification round-trip | Reply to the clarification prompt from row 5 with the missing info (e.g. "personal calendar, no attendees"). Skip this row if row 5 returned the happy path directly. | Event-created success envelope. The point of this row is to confirm the multi-turn round-trip works, not just the first message. | SC-002 (round-trip variant) | ☐ | __________ |

**Why escalation and capture rows use "operator picks the DM" phrasing**:
the spec's regression set (SC-005) names these subagents but their
trigger conditions depend on current system state. I pick a real,
representative DM at smoke time rather than canning one — that's the
whole point of operator-driven verification.

---

## 3. Non-DM checks

Some Felix substrates don't have a WhatsApp round-trip. Their verification
paths are different — and one of them (`felix-doc-auditor`) is on a
separate substrate that this mission's changes don't touch, so a failure
there is NOT a mission regression.

### 3.1 felix-doc-auditor freshness (NOT a DM)

`felix-doc-auditor` runs as a Python driver on an hourly systemd user
timer, not as an OpenClaw subagent with a DM interface. Per
`reference_felix_doc_auditor_ops` and research.md F-05, its health signal
is `last-tick.json` freshness. I check it directly:

```bash
ssh office2-claude 'cat /data/services/openclaw/felix-doc-auditor-driver/last-tick.json | jq .'
```

- [ ] `last-tick.json` parses cleanly (jq exits 0).
- [ ] The most recent tick timestamp is within ~1h of now (the timer
      cadence is hourly).
- [ ] Tick `status` (or equivalent field — see
      [`doc-auditor-driver-ops.md`](<./doc-auditor-driver-ops.md>) for the
      canonical shape) reflects a clean run.

> **If this fails**: that's a separate substrate, not a regression caused
> by this mission. The doc-auditor driver is currently suspended (see
> [`doc-auditor-driver-ops.md`](<./doc-auditor-driver-ops.md>) banner);
> if it's running and stale, file a separate bug — see § 5.

### 3.2 Scheduled outbound flows (24h passive observation)

These fire on their own cadence. I observe over a 24h window from the
recorded observation-start timestamp and tick boxes as each one delivers.
The cadences are documented in
[`docs/design/architecture/data/service-inventory.json`](<../design/architecture/data/service-inventory.json>);
the summary I care about:

- [ ] **Morning checkin** — fires ~07:00 ET next morning; delivers normal
      message to WhatsApp. (SC-006)
- [ ] **IDLE pings** — fire on their normal cadence (multiple per day
      historically); each one delivers. (SC-006)
- [ ] **Periodic digests** — fire on the schedule per `service-inventory.json`;
      each delivers. (SC-006)

### 3.3 Truncation-warning absence (24h passive)

NFR-002 requires zero `truncating in injected context` warnings for
`agent:main:*` over the 24h window. The deploy script confirms the
first session-init is clean; this command extends that to 24h:

```bash
ssh office2-claude 'journalctl --user -u openclaw-gateway --since "<observation-start-ts>" | grep "truncating in injected context" | grep "agent:main:"'
```

- [ ] Command returns no output (grep exit 1 is fine; exit 0 with any line
      is a fail). (SC-004)

### 3.4 Post-rebaseline audit (next audit cycle)

The next security-monitor audit run on office2 (~24h cadence, 3 AM ET)
should complete with zero spurious drift alerts now that the baselines
have been reset against the post-deploy state.

- [ ] Audit log shows clean run with no surface-drift alerts attributable
      to this mission's changes. (SC-007)

---

## 4. 24h observation window

The full window is **24 hours from the observation-start timestamp** recorded
in § 1. SC-006 (scheduled outbound) and SC-004 (no truncation warning) both
require the full window before they're satisfied. SC-007 (clean audit)
requires the next audit cycle to complete cleanly, which is also within
this window for a typical deploy timing.

I don't need to babysit this — the checks above are passive. I tick boxes
as deliveries arrive on WhatsApp and check the journal/audit log at the
end of the window. The minimum decision point is observation-start +
24h.

**Window opens**: ____________________________
**Window closes**: ____________________________ (= +24h)

---

## 5. Decision criteria

At the end of the 24h window, one of three outcomes applies. Pick deliberately.

| Outcome | When it applies | Action |
|---|---|---|
| **Mark mission complete** | Every box in §§ 2, 3.2, 3.3, 3.4 is checked AND § 3.1 either passed or failed for a non-mission reason (see below). | Record `Rebaseline: completed at <ts>` (or an explicit omission reason) in the merge commit footer. Close mission. |
| **File regression bug** | One or more DM round-trips (§ 2 rows 1–6) failed. OR § 3.2 missed a scheduled flow that historically fires reliably. OR § 3.3 observed any truncation warning for `agent:main:*`. OR § 3.4 flagged drift attributable to this mission. | File a P1-bug issue citing this runbook + the observed symptom. Do NOT mark mission complete. Consider rollback (the deploy script prints rollback steps on any failure; same steps apply now). |
| **doc-auditor stale (not a mission regression)** | § 3.1 failed AND the doc-auditor driver was running at deploy time AND the failure is a stale `last-tick.json`, not a missing file. | Note the observation in the mission close-out but do NOT block mission. The doc-auditor driver runs on a separate substrate; this mission's changes don't touch its timer or its scripts. File a separate issue for the stale tick if the driver isn't already known-suspended. |
| **Rebaseline omitted** | Pre-conditions § 1 ran the rebaseline but it failed, or the operator forgot to run it. | Audit alerts will fire next cycle. Run the canonical rebaseline command (per [`security-baseline-ops.md`](<./security-baseline-ops.md>)) retroactively and add the footer to the merge commit. |
| **Truncation warning observed** | § 3.3 returned any output. | File a bug — main/AGENTS.md tightening was insufficient, or another section grew between merge and deploy. This is a hard fail; rollback is on the table. |

**Why doc-auditor stale ≠ mission regression**: the doc-auditor driver is
a Python script on a systemd timer, not an OpenClaw subagent. This
mission only touches OpenClaw agent prompts (`scripts/openclaw/agents/`)
and the openclaw.json registration. The doc-auditor's substrate
(`/data/services/openclaw/felix-doc-auditor-driver/`) is untouched. So a
stale tick is either a pre-existing driver issue or its current
suspension status — neither is caused by what we shipped here.

---

## 6. Verification record

I initial each row when the corresponding check has been verified. The
"Notes" column captures anything worth referencing in the merge commit
footer or follow-up issue.

| Check | Initial | Timestamp | Notes |
|---|---|---|---|
| Pre-conditions met (§ 1) | _____ | _________________ | |
| § 2 row 1 — felix-admin-habits DM | _____ | _________________ | |
| § 2 row 2 — felix-admin-capture DM | _____ | _________________ | |
| § 2 row 3 — felix-admin-tasker DM | _____ | _________________ | |
| § 2 row 4 — felix-admin-escalation DM | _____ | _________________ | |
| § 2 row 5 — felix-admin-calendar happy path | _____ | _________________ | |
| § 2 row 6 — felix-admin-calendar clarification round-trip | _____ | _________________ | |
| § 3.1 — doc-auditor last-tick.json freshness | _____ | _________________ | |
| § 3.2 — morning checkin delivered | _____ | _________________ | |
| § 3.2 — IDLE pings delivered | _____ | _________________ | |
| § 3.2 — periodic digest delivered | _____ | _________________ | |
| § 3.3 — no truncation warning over 24h | _____ | _________________ | |
| § 3.4 — clean audit next cycle | _____ | _________________ | |
| 24h observation window closed | _____ | _________________ | |
| Final decision (§ 5) | _____ | _________________ | |

---

## Cross-references

- Mission spec: [`kitty-specs/felix-calendar-subagent-extraction-01KTTA33/spec.md`](<../../kitty-specs/felix-calendar-subagent-extraction-01KTTA33/spec.md>)
- Plan: [`kitty-specs/felix-calendar-subagent-extraction-01KTTA33/plan.md`](<../../kitty-specs/felix-calendar-subagent-extraction-01KTTA33/plan.md>)
- Structure contract: [`kitty-specs/felix-calendar-subagent-extraction-01KTTA33/contracts/smoke-runbook-shape.md`](<../../kitty-specs/felix-calendar-subagent-extraction-01KTTA33/contracts/smoke-runbook-shape.md>)
- Deploy script: [`scripts/deploy/deploy-felix-admin-calendar.sh`](<../archive/scripts/deploy/deploy-felix-admin-calendar.sh>)
- Origin issue: [kentonium3/kg-automation#579](https://github.com/kentonium3/kg-automation/issues/579)
- Rebaseline procedure: [`security-baseline-ops.md`](<./security-baseline-ops.md>)
- Doc-auditor driver substrate: [`doc-auditor-driver-ops.md`](<./doc-auditor-driver-ops.md>)
- OpenClaw agent setup: [`openclaw-agent-setup.md`](<./openclaw-agent-setup.md>)
