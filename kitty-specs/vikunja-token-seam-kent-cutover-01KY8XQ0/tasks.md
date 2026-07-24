# Tasks — Vikunja token seam + kent cutover (phase 2 of #860)

**Branch**: `feat/vikunja-token-seam-kent-cutover` → merges to `main`.
**Plan**: [plan.md](./plan.md) · **Spec**: [spec.md](./spec.md)

Decomposes the Implementation Concern Map (IC-01…IC-07) into 8 work packages with non-overlapping
ownership. WP01 is the foundation (all others depend on it). WP02–WP08 are independent of each other.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Add `get_vikunja_token_path()` to `vikunja_config.py` (env → default **kent**), fail-loud | WP01 | |
| T002 | Route `VikunjaClient` default-token load through the helper; drop the felix-bot literal | WP01 | |
| T003 | Single-point-flip proof test (SC-002) + config/client unit tests | WP01 | |
| T004 | Route the 6 habits consumers through the helper; drop their felix-bot literals | WP02 | [P] |
| T005 | Habits parity/affected tests stay green | WP02 | [P] |
| T006 | Route escalation `record_completion` + `reconcile_completions` through the helper | WP03 | [P] |
| T007 | Route enrichment `record_completion` + `reconcile_completions` through the helper | WP03 | [P] |
| T008 | Escalation/enrichment parity tests green | WP03 | [P] |
| T009 | Route `sync/{cycle,fetch}` through the helper; **preserve preamble `cycle_error`/exit 1** | WP04 | [P] |
| T010 | Route `credential_health_check/vikunja_writer` through the helper | WP04 | [P] |
| T011 | Sync failure-classification parity test | WP04 | [P] |
| T012 | Remove `route_someday` felix-bot 403 fail-soft branch (#750) + tests | WP05 | [P] |
| T013 | Converge `validate_refs.py` on the single-source token (#748, FR-005) | WP05 | [P] |
| T014 | Author ADR-0007; mark ADR-0002 superseded; update adr/README, INDEX, DEVELOPER_PORTAL | WP06 | [P] |
| T015 | Mark `vikunja-api` credential dormant/non-runtime in credential-manifest.json | WP06 | [P] |
| T016 | Reconcile credentials-and-secrets, identity-model, service-inventory, data-flows | WP06 | [P] |
| T017 | Update `vikunja-api`/escalation SKILL + tasker TOOLS/AGENTS token refs; SKILL v2.4.0 + health-check (#831) | WP07 | [P] |
| T018 | Reconcile obsolete in-code invariant comments (`scan_inbox._build_client`, sync systemd unit) | WP07 | [P] |
| T019 | `cutover_verify.py`: kent inverse probe (projects 16–20) + per-consumer connectivity + task-delta sizing | WP08 | [P] |
| T020 | `cutover_verify` unit test | WP08 | [P] |

## Work Packages

### WP01 — Token seam foundation (IC-01/IC-02/IC-04)
- **Goal**: one resolution point (`get_vikunja_token_path()`), client default routed through it, default = **kent** (end state), proven single-point.
- **Priority**: P0 (foundation). **Independent test**: config/client unit tests + SC-002 flip proof.
- Subtasks: - [ ] T001 (WP01) · - [ ] T002 (WP01) · - [ ] T003 (WP01)
- **Deps**: none. **Prompt**: [tasks/WP01-token-seam-foundation.md](./tasks/WP01-token-seam-foundation.md)

### WP02 — Habits consumers (IC-03)
- **Goal**: route the 6 habits scripts through the helper; behavior-preserving.
- Subtasks: - [ ] T004 (WP02) · - [ ] T005 (WP02)
- **Deps**: WP01. **Prompt**: [tasks/WP02-habits-consumers.md](./tasks/WP02-habits-consumers.md)

### WP03 — Escalation + enrichment consumers (IC-03)
- **Goal**: route escalation×2 + enrichment×2 through the helper (the post-plan Codex catch).
- Subtasks: - [ ] T006 (WP03) · - [ ] T007 (WP03) · - [ ] T008 (WP03)
- **Deps**: WP01. **Prompt**: [tasks/WP03-escalation-enrichment-consumers.md](./tasks/WP03-escalation-enrichment-consumers.md)

### WP04 — Sync + credential-health consumers (IC-03)
- **Goal**: route sync + credential-health through the helper; preserve sync's failure classification.
- Subtasks: - [ ] T009 (WP04) · - [ ] T010 (WP04) · - [ ] T011 (WP04)
- **Deps**: WP01. **Prompt**: [tasks/WP04-sync-credhealth-consumers.md](./tasks/WP04-sync-credhealth-consumers.md)

### WP05 — Retire felix-bot code path (IC-05)
- **Goal**: remove `route_someday` 403 fail-soft (#750); converge `validate_refs` (#748/FR-005).
- Subtasks: - [ ] T012 (WP05) · - [ ] T013 (WP05)
- **Deps**: WP01. **Prompt**: [tasks/WP05-retire-felix-bot-code.md](./tasks/WP05-retire-felix-bot-code.md)

### WP06 — Credential + architecture docs + ADR-0007 (IC-06)
- **Goal**: ADR-0007 + credential-manifest dormant + credential/identity/service/data-flow docs.
- Subtasks: - [ ] T014 (WP06) · - [ ] T015 (WP06) · - [ ] T016 (WP06)
- **Deps**: WP01. **Prompt**: [tasks/WP06-credential-arch-docs-adr.md](./tasks/WP06-credential-arch-docs-adr.md)

### WP07 — Agent surface + comment reconciliation (IC-06, #831)
- **Goal**: SKILL/TOOLS/AGENTS token refs + SKILL v2.4.0/health-check; obsolete in-code comments.
- Subtasks: - [ ] T017 (WP07) · - [ ] T018 (WP07)
- **Deps**: WP01. **Prompt**: [tasks/WP07-agent-surface-comments.md](./tasks/WP07-agent-surface-comments.md)

### WP08 — Cutover verification tooling (IC-07 / FR-007)
- **Goal**: a deterministic `cutover_verify.py` for the attended cutover (inverse probe + connectivity + delta).
- Subtasks: - [ ] T019 (WP08) · - [ ] T020 (WP08)
- **Deps**: WP01. **Prompt**: [tasks/WP08-cutover-verify-tooling.md](./tasks/WP08-cutover-verify-tooling.md)

## MVP / sequencing

WP01 first (foundation). WP02–WP08 all parallelizable after WP01 (disjoint file ownership). The
felix-bot→kent runtime transition is inert until merge→office2 pull (the attended Tier-2 cutover,
IC-07 — an operator step gated on Kent, not a WP). WP08 builds the tool that verifies that cutover.
