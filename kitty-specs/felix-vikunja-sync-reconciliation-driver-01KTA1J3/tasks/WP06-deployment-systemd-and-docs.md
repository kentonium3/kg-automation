---
work_package_id: WP06
title: 'Deployment: systemd units + operator runbook + architecture docs'
dependencies:
- WP05
requirement_refs:
- FR-001
- FR-008
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T022
- T023
- T024
- T025
agent: "claude"
shell_pid: "92317"
history:
- at: '2026-06-04T19:53:57Z'
  by: spec-kitty.tasks
  note: Created WP06 from plan.md + quickstart.md + change-control.md doc-update protocol
authoritative_surface: scripts/sync/systemd/
execution_mode: code_change
owned_files:
- scripts/sync/systemd/felix-vikunja-sync.service
- scripts/sync/systemd/felix-vikunja-sync.timer
- docs/runbooks/sync-driver-ops.md
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/signal-to-doc-map.json
- docs/INDEX.md
- docs/DEVELOPER_PORTAL.md
tags: []
---

# WP06 — Deployment: systemd units + operator runbook + architecture docs

## Objective

Produce the systemd user units, the operator runbook, and the architecture-doc updates per the standing change-control protocol. The deployment to office2 (running bootstrap, enabling the timer) is operator-driven post-merge and is NOT part of this WP.

After this WP merges, the operator can:
- `cp scripts/sync/systemd/felix-vikunja-sync.{service,timer} ~/.config/systemd/user/` on office2
- Follow `docs/runbooks/sync-driver-ops.md` to bootstrap and enable
- Confirm registration in `docs/design/architecture/data/service-inventory.json`
- Find the driver in `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md`

## Context

The mission's "standing requirement" per `CLAUDE.md` is: "Any feature that changes deployed services, credentials, data flows, or network topology must update the relevant files in `docs/design/architecture/` and `docs/design/architecture/data/`." This WP discharges that obligation.

The driver is a new deployed service (a systemd user unit running a Python module). Per `change-risk-taxonomy.json` this is Tier 3 (Standard — Python script + cron job equivalent). Per `signal-to-doc-map.json`, the change classes are `service-added-or-modified`, `systemd-unit-added-or-modified`, and `runbook-added`. The union of `doc_targets` for those classes is the WP's owned-files list.

**Branch Strategy**: planning_base_branch = `main`; merge_target_branch = `main`. Lane worktree per WP.

## Implementation command

```bash
spec-kitty agent action implement WP06 --agent <name>
```

Depends on WP05 (the systemd unit references `python3 -m scripts.sync.driver`).

---

## Subtask T022 — `scripts/sync/systemd/felix-vikunja-sync.service`

**Purpose**: Define the systemd user service unit that runs one driver tick. The timer (T023) triggers the service.

**Steps**:

1. Create directory `scripts/sync/systemd/` (the WP creates it; finalize-tasks does not).

2. Create `felix-vikunja-sync.service` with the contents:

   ```ini
   [Unit]
   Description=Felix-Vikunja Sync Reconciliation Driver (one-shot tick)
   Documentation=https://github.com/kentonium3/kg-automation/blob/main/docs/runbooks/sync-driver-ops.md
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=oneshot
   WorkingDirectory=/home/claude/kg-automation
   ExecStart=/usr/bin/python3 -m scripts.sync.driver
   Environment=FELIX_WHATSAPP_RECIPIENT=+16179300916
   Environment=FELIX_VIKUNJA_API_BASE_URL=https://office2.tail0f5f56.ts.net/api/v1/
   Environment=FELIX_SYNC_CADENCE_SECONDS=300
   StandardOutput=journal
   StandardError=journal
   TimeoutStartSec=120s

   [Install]
   WantedBy=default.target
   ```

3. Comment block at the top of the file documenting:
   - The cadence-vs-timer relationship (timer fires; this service handles one tick)
   - The recipient hardcoding (intentional, matches sync-heartbeat.py precedent for operator number)
   - The 120s start timeout is generous; cycles complete in <5s normally
   - That the operator deploys this file by copying to `~/.config/systemd/user/`

**Files**:
- `scripts/sync/systemd/felix-vikunja-sync.service` (~40 lines including comments)

**Reference precedent**: existing systemd user units at `~/.config/systemd/user/` on office2 — look at `felix-doc-auditor-driver` or `felix-heartbeat-gate` units for the structure.

**Validation**:
- [ ] `systemd-analyze verify scripts/sync/systemd/felix-vikunja-sync.service` returns 0 (if systemd-analyze is available; document as manual check otherwise)
- [ ] Unit references the correct `WorkingDirectory` (`/home/claude/kg-automation`, the office2 git checkout)
- [ ] No secrets in environment variables (recipient is the phone number, not a credential)

---

## Subtask T023 — `scripts/sync/systemd/felix-vikunja-sync.timer` [P]

**Purpose**: The timer that triggers the service every 5 minutes.

**Steps**:

1. Create `felix-vikunja-sync.timer`:

   ```ini
   [Unit]
   Description=Felix-Vikunja Sync Reconciliation Driver (5-min cadence)
   Documentation=https://github.com/kentonium3/kg-automation/blob/main/docs/runbooks/sync-driver-ops.md

   [Timer]
   OnUnitInactiveSec=300s
   OnBootSec=120s
   Unit=felix-vikunja-sync.service
   Persistent=true

   [Install]
   WantedBy=timers.target
   ```

2. Comment block documenting:
   - `OnUnitInactiveSec` means "300s after the LAST tick exited" — guarantees no overlapping ticks even if a tick takes >5min (rare).
   - `OnBootSec=120s` delays the first tick by 2 minutes after boot to let the network and Vikunja settle.
   - `Persistent=true` ensures missed ticks (e.g., office2 was off) trigger one catch-up tick on resume — the reconciliation driver's design tolerates a stale freshness pointer.

**Files**:
- `scripts/sync/systemd/felix-vikunja-sync.timer` (~25 lines including comments)

**Validation**:
- [ ] `systemd-analyze verify scripts/sync/systemd/felix-vikunja-sync.timer` returns 0
- [ ] Cadence value matches FR-001's documented default of 300s

---

## Subtask T024 — `docs/runbooks/sync-driver-ops.md`: operator runbook [P]

**Purpose**: Produce a Felix-standard operator runbook for the new driver. Distill `quickstart.md` into the Felix runbook format (frontmatter + structured sections).

**Steps**:

1. Create `docs/runbooks/sync-driver-ops.md` with the Felix runbook frontmatter (look at `docs/runbooks/doc-auditor-driver-ops.md` for the canonical example):

   ```markdown
   ---
   title: Sync Driver Operations
   doc_type: runbook
   status: active
   last_updated: '2026-06-04'
   last_validated: '2026-06-04'
   updated_by: '#518'
   owners: ['kgale']
   ---
   ```

2. Sections (mirror `doc-auditor-driver-ops.md` structure):

   - **Overview**: what the driver does, why it exists (link to ADR-0003, link to #507, link to research artifacts)
   - **Install** (one-time, post-merge)
   - **Bootstrap** (first run with `--bootstrap`)
   - **Enable steady-state operation**
   - **Daily health check** (commands)
   - **Observe conflict events** (jq snippets)
   - **Recovery scenarios** (cache clean slate, daily cap tuning, silence specific tasks)
   - **SC verification** (per spec's SC-001 through SC-009)
   - **When to escalate** (file an issue criteria)
   - **References** (cross-links to spec, ADR-0003, contracts/)

3. Pull command examples from `quickstart.md`. Ensure all commands are single-line copy-pasteable per memory `feedback_command_formatting`.

4. Cross-reference contracts files: when explaining a behavior (e.g., G-3 daily cap), link to the relevant contract document.

5. Include a "Known soft edge" section documenting the Vikunja server-side auto-advance on recurring tasks (per `contracts/conflict-event-schema.md` § Soft edge). This is a real operational quirk the operator should know about.

**Files**:
- `docs/runbooks/sync-driver-ops.md` (~400 lines)

**Reference precedent**: `docs/runbooks/doc-auditor-driver-ops.md` for runbook structure, tone, and depth.

**Validation**:
- [ ] All 9 SC items from `spec.md` have a verification command in the runbook
- [ ] All commands are single-line copy-pasteable (no `\` line continuations except in code blocks)
- [ ] Frontmatter matches Felix runbook standards
- [ ] No broken cross-references

---

## Subtask T025 — Architecture data + INDEX updates per change-control [P]

**Purpose**: Discharge the standing architecture-doc-sync requirement. Add the new service to the inventory, the new runbook to the signal map, and the new entries to navigation docs.

**Steps**:

1. **`docs/design/architecture/data/service-inventory.json`**:
   - Add an entry for `felix-vikunja-sync` with:
     - `name`, `purpose`, `runtime` (Python systemd user unit)
     - `host` (office2)
     - `user` (claude)
     - `command` (`python3 -m scripts.sync.driver`)
     - `cadence` (300s)
     - `state_dir` (`/data/services/openclaw/state/sync/`)
     - `secrets` (references `vikunja-api`)
     - `consumes` (Vikunja API, openclaw CLI for WhatsApp delivery)
     - `produces` (conflict-events.jsonl, last-tick.json, WhatsApp messages)
     - `runbook` (`docs/runbooks/sync-driver-ops.md`)
     - `mission` (`#518`)
     - `added_at` (`2026-06-04`)
   - Update top-level `last_updated` and `updated_by` fields.
   - Look at existing entries for `felix-doc-auditor-driver` or `felix-heartbeat-gate` as templates.

2. **`docs/design/architecture/data/signal-to-doc-map.json`**:
   - Find the existing `runbook-added` mapping and add `docs/runbooks/sync-driver-ops.md` to its `doc_targets` list IF it's a documented-targets pattern (otherwise leave the mapping unchanged — the signal fires by class, not by enumeration).
   - More importantly: this WP IS the response to the `runbook-added` signal. The signal map already captures the rule; the work product (the new runbook) is what satisfies it.
   - Update top-level `last_updated` and `updated_by`.

3. **`docs/INDEX.md`**:
   - Add `docs/runbooks/sync-driver-ops.md` under the runbooks section.
   - One-line description matching the file's frontmatter title + a short purpose phrase.
   - Update top-level `last_updated`.

4. **`docs/DEVELOPER_PORTAL.md`**:
   - If the runbook is operator-facing (yes — observability and recovery are explicit concerns), add a link from the appropriate onboarding section.
   - If not (rare), document why omitted.

5. **Run `tooling/scripts/validate_docs.py`** from repo root and fix any failures before claiming WP done.

**Files**:
- `docs/design/architecture/data/service-inventory.json` (edit)
- `docs/design/architecture/data/signal-to-doc-map.json` (edit — small, may be no-op)
- `docs/INDEX.md` (edit)
- `docs/DEVELOPER_PORTAL.md` (edit)

**Validation**:
- [ ] `python3 tooling/scripts/validate_docs.py` returns 0 (no validation errors)
- [ ] `service-inventory.json` schema (per `data/catalog-schema.json` if present) passes
- [ ] INDEX and DEVELOPER_PORTAL both reference the new runbook
- [ ] The top-level `updated_by` field in each modified JSON includes `#518` (matching the issue-driven update convention)

---

## Test strategy

This WP produces deployment artifacts and documentation. There is no Python module to unit-test. Verification is:

- `systemd-analyze verify` on the unit files (if available)
- `python3 tooling/scripts/validate_docs.py` for the JSON schemas
- Manual review of the runbook against the spec's SC items
- Cross-reference check: every link in the runbook resolves to a file that exists at HEAD

---

## Definition of Done

- [ ] All 4 subtasks complete; all listed files committed in the WP06 worktree
- [ ] `python3 tooling/scripts/validate_docs.py` returns 0
- [ ] `systemd-analyze verify scripts/sync/systemd/felix-vikunja-sync.{service,timer}` returns 0 (or documented manual check passed)
- [ ] Runbook covers all 9 SC items with verification commands
- [ ] INDEX.md and DEVELOPER_PORTAL.md include the new runbook
- [ ] service-inventory.json includes the new service with `updated_by: "#518"`
- [ ] No edits to files outside the WP's `owned_files` list

---

## Risks and mitigations

- **Risk: Pre-existing modifications to `docs/INDEX.md` and `docs/research/.../recommendation.md` are present in the operator's working tree at mission start.** Mitigation: those modifications are unrelated to this mission. WP06 starts from the lane worktree (clean of operator's uncommitted changes); the implementer's edit lands on top of whatever is on the mission lane branch.
- **Risk: `service-inventory.json` schema drift between when the WP was planned and when it lands.** Mitigation: the implementer reads the latest catalog-schema.json before editing; if the schema changed in an incompatible way during the mission, surface it as a reviewer concern.
- **Risk: Runbook command snippets become stale as the driver CLI evolves in implement-phase WP05.** Mitigation: WP06 runs AFTER WP05 lands; the implementer reads the merged WP05 code and updates command examples to match. If WP05's CLI surface changed since the spec, the runbook reflects what WAS shipped.

---

## Reviewer guidance

When reviewing this WP, verify:
1. **Systemd unit correctness**: WorkingDirectory points to office2's checkout path; Environment vars match the driver's documented env-var contract; cadence matches FR-001.
2. **Runbook coverage**: cross-check every SC item in `spec.md` against a verification command in the runbook. Missing coverage is a rejection.
3. **Architecture data consistency**: the service-inventory entry's `consumes`, `produces`, `state_dir` fields match what the implementation actually does (cross-reference WP01..WP05 code).
4. **No secrets in systemd unit files**: the recipient is a phone number (not a secret); no Vikunja token or anthropic key in any Environment line.
5. **INDEX and DEVELOPER_PORTAL updates** are non-trivial — the runbook should be discoverable from onboarding flows.
6. **validate_docs.py passes** — this is the canonical check; the reviewer runs it.

Reject if the runbook is missing SC coverage, if systemd-analyze fails, if validate_docs fails, or if any owned-file boundary is violated.

---

## References

- Mission spec: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/spec.md`
- Mission plan: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/plan.md`
- Quickstart: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/quickstart.md`
- Contracts: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/`
- Change-control protocol: `docs/design/architecture/change-control.md`
- Signal-to-doc map: `docs/design/architecture/data/signal-to-doc-map.json`
- Risk taxonomy: `docs/design/architecture/data/change-risk-taxonomy.json`
- Existing runbook precedent: `docs/runbooks/doc-auditor-driver-ops.md`
- Existing systemd unit precedent: any existing entry under `~/.config/systemd/user/` on office2 (live-probe during implement)
- From WP05: `scripts/sync/driver.py` (the entry point the systemd unit invokes)

## Activity Log

- 2026-06-04T20:57:58Z – claude – shell_pid=90075 – Started implementation via action command
- 2026-06-04T21:01:59Z – claude – shell_pid=90075 – All 4 subtasks committed (a0bc9e99). systemd .service + .timer; sync-driver-ops.md runbook; service-inventory.json gains felix-vikunja-sync-driver entry (30 services); INDEX.md + DEVELOPER_PORTAL.md updated. 194 sync tests still pass — no Python changes.
- 2026-06-04T21:06:21Z – claude – shell_pid=92317 – Started review via action command
- 2026-06-04T21:09:02Z – claude – shell_pid=92317 – Moved to planned
