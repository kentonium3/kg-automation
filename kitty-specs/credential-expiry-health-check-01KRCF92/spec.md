# Credential Expiry Health Check

**Mission**: `credential-expiry-health-check-01KRCF92`
**Source**: [`kentonium3/kg-automation#115`](https://github.com/kentonium3/kg-automation/issues/115) — *Infra: Automated credential expiry health check (R-003)*
**Mission type**: `software-dev`
**Target branch**: `main`

---

## 1. Why this exists

Closes risk-register item **R-003**: API keys, tokens, and other rotation-bearing credentials in the system have no automated expiry or review-cadence tracking. Silent expiration causes agent failures with no advance warning, manifests as outages discovered only when an integration breaks, and creates ad-hoc rotation work under time pressure.

The data prerequisite is already in place — `credential-manifest.json` v1.1 carries `expiry_policy`, `review_cadence`, `expiry_notes`, and `last_reviewed` for each tracked credential. What's missing is the consumer: an automated process that reads those fields on a schedule, applies a warning window, and surfaces upcoming review boundaries on a surface Kent will actually see.

---

## 2. User Scenarios

The system has one user: **Kent**, in his role as system operator.

### Primary scenario — Credential approaching review cadence

1. Kent has rotated a credential in the past (e.g., the Anthropic API key on 2026-10-18). The manifest records `review_cadence: annual`, `last_reviewed: 2026-10-18`.
2. As that date plus one year approaches, the system detects that `last_reviewed + cadence` is within the warning window (30 days) and acts.
3. A GitHub issue is filed in this repo with a structured body identifying the credential, the boundary date, where it's stored, the rotation procedure (from the manifest), and a link to the Vikunja task.
4. A Vikunja task is created with `due_date = boundary - 7 days` (one week earlier than the actual rotation deadline, giving the escalation engine a 7-day pre-deadline pressure window).
5. Kent sees the GitHub issue's email notification and the Vikunja task in his daily review.
6. As the Vikunja task crosses its due date, the existing escalation engine fires WhatsApp nudges per its standard overdue-task cadence.
7. Kent rotates the credential, updates `last_reviewed` in the manifest, closes the GitHub issue, marks the Vikunja task done. The next daily check sees the credential as fresh and does not re-fire.

### Secondary scenario — Dedup across cycles

1. On day N, the check fires and creates issue + task for credential X.
2. On day N+1, the check fires again. It sees the existing open GitHub issue for credential X (matched by a stable title/identifier convention) and the existing open Vikunja task. It logs "already alerted, skipping" and exits.
3. This holds until Kent closes the issue and marks the task done (or until the credential's `last_reviewed` is bumped past the warning window).

### Tertiary scenario — First-run on a fresh manifest

1. After deploy, the very first daily run reads the manifest with no historical context.
2. It correctly handles credentials in any of these states: within-cadence (skip), approaching-boundary (alert), past-boundary (alert with overdue note), `review_cadence: monitor-activity` / `on-revocation` / `n/a` / `session` (skip per policy).
3. It does not generate spurious alerts for credentials that were intentionally not on a fixed cadence.

### Edge cases

- **`last_reviewed` is missing or malformed** on a credential entry: log a warning, file a single GitHub issue tagged as a manifest-quality problem (not a per-credential expiry alert), continue with the other credentials.
- **The manifest itself is unreadable** (invalid JSON, missing file): the check exits with a non-zero status; the systemd unit failure is visible in `journalctl --user`. No alerts are filed in that state (avoid notification storms on broken inputs).
- **GitHub or Vikunja is unreachable**: the check should fail closed for that surface — log the failure, retry on the next daily tick. Do not create partial state (issue without task, or vice versa) if possible to avoid; if not avoidable, log the inconsistency clearly.
- **`kg-felix-bot` PAT itself is the credential being alerted on**: the check uses that PAT to file the GitHub issue. A self-alert path must still work — the PAT must be valid through its own warning window. (Implementation will need to handle this; spec just flags it.)
- **`vikunja-api` token itself is the credential being alerted on**: same pattern as the GitHub PAT — the task can still be created with the existing token; rotation just needs to happen.

---

## 3. Functional Requirements (FR-###)

| ID | Status | Requirement |
|---|---|---|
| **FR-001** | mandatory | Every daily run reads `docs/design/architecture/data/credential-manifest.json` and iterates every entry in `credentials[]`. |
| **FR-002** | mandatory | For each credential whose `review_cadence` is a fixed-interval value (`annual`, or any future explicit interval), the system computes the cadence boundary as `last_reviewed + cadence_interval` and compares it to `today + 30 days`. If `boundary <= today + 30 days` AND no open alert exists for this credential, the system alerts. |
| **FR-003** | mandatory | For each credential whose `review_cadence` is `monitor-activity`, `on-revocation`, `n/a`, or `session`, the system does **not** create cadence-based alerts. (Activity-staleness checks for `monitor-activity` are out of scope for v1 unless the activity signal is already programmatically queryable; see Out of Scope.) |
| **FR-004** | mandatory | Alerting consists of two artefacts created in lockstep, with cross-references: (a) a GitHub issue in `kentonium3/kg-automation`, (b) a Vikunja task. |
| **FR-005** | mandatory | The GitHub issue body identifies the credential by `name`, states the cadence boundary date, summarises where the credential is stored (`storage` field), and reproduces the rotation procedure from `expiry_notes`. It links to the Vikunja task ID. The title carries a stable prefix that supports deterministic dedup (e.g., `Credential review: <name> due <YYYY-MM-DD>`). |
| **FR-006** | mandatory | The Vikunja task is created with `due_date = boundary - 7 days`. The task description links to the GitHub issue URL. |
| **FR-007** | mandatory | The system dedupes alerts across cycles: before filing, it checks for an existing open GitHub issue whose title matches the stable prefix for this credential. If one exists, no new issue or task is created on the current cycle. |
| **FR-008** | mandatory | After a credential's `last_reviewed` field is updated past the warning window, the next run treats the credential as fresh — it does not file new alerts. (Issue/task closure is Kent's manual action; the system does not auto-close past alerts.) |
| **FR-009** | mandatory | The system runs once per UTC day on a deterministic schedule. |
| **FR-010** | mandatory | The system runs as the `claude` user on office2 (consistent with `felix-doc-auditor` and other Felix runners). |
| **FR-011** | mandatory | The system exits with a non-zero status when the manifest is unreadable or malformed. It does not file alerts in that state. |
| **FR-012** | mandatory | The system files at most one "manifest quality" GitHub issue per cycle when one or more credential entries have missing or malformed required fields (`last_reviewed`, `review_cadence`). |
| **FR-013** | mandatory | Pre-deploy, the `kentonium3-pat` entry is added to `credential-manifest.json`. This brings the known-tracked credential set into completeness before the auditor's first run. |

---

## 4. Non-Functional Requirements (NFR-###)

| ID | Status | Requirement | Measurable threshold |
|---|---|---|---|
| **NFR-001** | mandatory | Single-cycle runtime, end-to-end, on the current ~9-entry manifest. | Under **10 seconds** wall-clock on office2. |
| **NFR-002** | mandatory | Cycle-to-cycle determinism. Given the same manifest contents and the same calendar day, two runs produce identical sets of alerts (same dedup decisions, same target counts). | Verified by manual replay on the office2 environment as part of acceptance. |
| **NFR-003** | mandatory | Failure isolation. A failure to reach GitHub OR Vikunja for one credential's alert does not silently drop alerts for the other credentials in the same cycle. | Demonstrated by injecting a transient failure during the controlled-failure canary in §6. |
| **NFR-004** | mandatory | Audit-trail visibility. Each cycle's actions (credentials checked, alerts filed, alerts deduped, errors) are recorded to a deterministic log location readable by the `claude` user without sudo. | Log written; `tail -50 <log>` returns a complete record of the most recent cycle. |
| **NFR-005** | mandatory | Authentication identities used by the check are explicit and auditable. GitHub actions appear as `kg-felix-bot`; Vikunja actions use the existing `vikunja-api` token. | Verified by inspecting commit author / issue author / task creator on the controlled-failure canary in §6. |
| **NFR-006** | mandatory | No credential value is ever written to a file, log, or alert body. The check reads metadata only. | Verified by inspecting the log file and any filed issue/task body for any credential-resembling string. |

---

## 5. Constraints (C-###)

| ID | Status | Constraint |
|---|---|---|
| **C-001** | mandatory | The check runs on office2 as the `claude` user. It cannot use sudo. Any operation requiring elevated privileges is out of scope. |
| **C-002** | mandatory | The check is a **data consumer** of `credential-manifest.json`, not a writer. It never mutates the manifest. (Kent updates `last_reviewed` manually after rotation.) |
| **C-003** | mandatory | The check operates exclusively against `kentonium3/kg-automation` on GitHub and the office2 Vikunja instance. No other repos or task stores. |
| **C-004** | mandatory | The schedule mechanism follows the pattern established by `felix-doc-auditor.{timer,service}` (systemd user timer + oneshot service under `~/.config/systemd/user/`, source units in `scripts/office2/`). This is a constraint for consistency, not a hard architectural rule — plan phase may justify an alternative. |
| **C-005** | mandatory | The GitHub authentication identity is `kg-felix-bot` (see `kg-felix-bot-pat` in the manifest, AGENT-REGISTRY.md §Service Accounts). The check shells through `gh` and `git` configured as that identity. |
| **C-006** | mandatory | The Vikunja authentication uses the existing `vikunja-api` token at `/data/services/openclaw/secrets/vikunja-api`. No new token is provisioned. |
| **C-007** | mandatory | Architecture documentation (`service-inventory.json`, `service-inventory.md` narrative + Scheduled Jobs row, `credentials-and-secrets.md` Security Posture cross-reference) is updated in the same change set that introduces the check. |

---

## 6. Success Criteria

Each criterion is measurable, technology-agnostic, and verifiable as part of acceptance.

| ID | Criterion |
|---|---|
| **SC-001** | After deploy, the check runs on its scheduled cadence without manual intervention for **at least 14 consecutive days**. |
| **SC-002** | A **controlled-failure canary** demonstrates the alert path end-to-end: a single credential's `last_reviewed` is temporarily backdated to push its boundary inside the warning window; the next run files exactly one GitHub issue and exactly one Vikunja task with the correct cross-references and the correct `due_date = boundary - 7 days`. The backdate is then reverted; the next run does not create a duplicate. |
| **SC-003** | Across the first 14 days post-deploy, the auditor produces **zero false-positive alerts** (no alert for a credential whose `last_reviewed + cadence` is still beyond the warning window). |
| **SC-004** | Across the first 14 days post-deploy, the auditor produces **zero missed alerts** for credentials whose boundary should have been inside the warning window during that period. Verified by manually replaying the cadence math against the manifest. |
| **SC-005** | Kent can describe the system's behaviour by reading **only** the operational runbook (does not need to read code, the manifest, or the check script). |
| **SC-006** | The `kentonium3-pat` credential is present in `credential-manifest.json` and is being tracked by the check. |
| **SC-007** | Risk-register item **R-003** is marked closed (in the active tracker — this issue — or wherever the active risk register lives post-#115). |

---

## 7. Key Entities

| Entity | Source of truth | Notes |
|---|---|---|
| **Credential** | `docs/design/architecture/data/credential-manifest.json` `credentials[]` entry | Authoritative metadata for one credential. The check reads `name`, `review_cadence`, `last_reviewed`, `storage`, `expiry_notes`. |
| **Cadence boundary** | computed: `last_reviewed + cadence_interval` | Not stored. Computed at check time. |
| **Warning window** | constant in the check (30 days) | Single global value across all fixed-cadence credentials. |
| **Pending alert** | tuple of `(GitHub issue, Vikunja task)` | Both must exist for the alert to be considered live; dedup checks issue presence. |
| **Cycle log** | log file in a deterministic path on office2 | Per-cycle audit trail. |

---

## 8. Assumptions

| ID | Assumption | Rationale / Recorded basis |
|---|---|---|
| **A-001** | The `vikunja-api` token has enough lifetime to cover the first months of operation without the auditor needing to alert on itself before it can do so. | The Vikunja API token has `expiry_policy: none` per the manifest; rotation is manual-only. |
| **A-002** | The escalation engine's existing overdue-task cadence is sufficient for the WhatsApp pressure path after Day −7. No new escalation tier is configured for this auditor's tasks. | Confirmed during discovery by Kent. |
| **A-003** | The "completeness audit" of the manifest (discovering credentials that aren't tracked yet, e.g., the known-missing Google AI Studio API key) is a follow-up Kent runs after this mechanism is in place. The auditor itself does not need a completeness-discoverer feature. | Confirmed during discovery by Kent. |
| **A-004** | Activity-staleness checks for `monitor-activity` credentials (e.g., `whatsapp-session`) require a programmatic activity signal. If one is already queryable at plan time, include it; otherwise defer. | Resolve in plan phase. |
| **A-005** | The system has no need to *auto-close* a GitHub issue or *auto-mark-done* a Vikunja task. Kent closes them manually after rotating. The dedup check (FR-007) is what prevents re-firing. | Confirmed during discovery by Kent. |

---

## 9. Dependencies

- `docs/design/architecture/data/credential-manifest.json` (read; v1.1 schema is sufficient — no migration required)
- GitHub repo `kentonium3/kg-automation` (read + write via `gh` CLI as `kg-felix-bot`)
- Vikunja instance on office2 (write via existing API token)
- office2 host: `claude` user, systemd user session, network reachability to GitHub and Vikunja
- The escalation engine (`felix-admin-escalation`) — consumed transitively via the Vikunja task's `due_date`; no direct integration

---

## 10. Out of scope (explicit)

| Item | Rationale |
|---|---|
| Discovering credentials that aren't yet in the manifest (e.g., Google AI Studio API key) | Per Kent: post-deploy completeness audit, not the auditor's job. |
| Restructuring the manifest schema | v1.1 carries all the fields needed. |
| Activity-staleness check for `monitor-activity` credentials when it requires new instrumentation | Defer to a follow-up issue if the programmatic signal isn't already in place. |
| Rotation automation | The auditor surfaces the work; Kent rotates manually. |
| Auto-closing GitHub issues or auto-completing Vikunja tasks | Kent closes manually after rotation per A-005. |
| Cross-repo coverage (any GitHub repo other than `kentonium3/kg-automation`) | Out of scope per C-003. |
| Promoting the check's autonomy level above its initial setting | Autonomy decisions are governance work, not implementation work. |

---

## 11. References

- Source issue: [`kentonium3/kg-automation#115`](https://github.com/kentonium3/kg-automation/issues/115)
- Risk register: `docs/archive/risk-register.md` (R-003); active tracking is this issue
- Credential manifest: `docs/design/architecture/data/credential-manifest.json` (schema v1.1)
- Credential narrative: `docs/design/architecture/credentials-and-secrets.md`
- Schedule mechanism prior art: `scripts/office2/felix-doc-auditor.{timer,service}` (delivered in #223)
- Service account identity: `docs/constitution/AGENT-REGISTRY.md` §Service Accounts (`kg-felix-bot`)
