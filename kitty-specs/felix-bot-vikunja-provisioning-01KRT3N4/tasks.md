# Tasks: Provision felix-bot Vikunja identity

**Mission**: `felix-bot-vikunja-provisioning-01KRT3N4`
**Target branch**: `main` (planning_base = merge_target)
**Source**: [spec.md](./spec.md) · [plan.md](./plan.md) · [research.md](./research.md) · [data-model.md](./data-model.md) · [contracts/](./contracts/) · [quickstart.md](./quickstart.md)

---

## Overview

5 work packages, 24 subtasks. The helpers are code-independent — each touches a different file in `scripts/vikunja/`, so all five WPs are implementation-parallel. Their RUNTIME sequence (operator-driven) is provision → validate → swap → docs → revoke; but their IMPLEMENTATION sequence has no inter-dependency.

| WP | Title | Subtasks | Est. prompt size | Dependencies | Parallel-safe |
|---|---|---|---|---|---|
| WP01 | `provision_felix_bot.py` — register + share + capture token | 5 | ~300 lines | — | ✓ |
| WP02 | `validate_felix_bot.py` — side-channel validation harness | 5 | ~300 lines | — | ✓ |
| WP03 | `swap_vikunja_secrets.py` — atomic cutover with auto-rollback | 6 | ~350 lines | — | ✓ |
| WP04 | `revoke_kent_tokens.py` — post-soak cleanup | 3 | ~200 lines | — | ✓ |
| WP05 | Operator runbook + 4 architecture doc updates | 5 | ~300 lines | — | ✓ |

**Total**: 24 subtasks across 5 WPs. All within ideal sizing (3-7 subtasks, 200-500 lines).

MVP scope: WP01–WP03 deliver the cutover capability (provision + validate + swap). WP04 (revoke) only runs after the 7-day soak. WP05 (runbook + docs) is required for operator execution.

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create scripts/vikunja/ + tests/vikunja/ scaffolding; provision_felix_bot.py argparse + identity gate | WP01 | | [D] |
| T002 | provision_felix_bot.py — user registration via POST /api/v1/register | WP01 | | [D] |
| T003 | provision_felix_bot.py — enumerate 12 real projects + share each at R/W | WP01 | | [D] |
| T004 | provision_felix_bot.py — post-share verification + capture operator-supplied API token | WP01 | | [D] |
| T005 | tests/vikunja/test_provision_felix_bot.py — pytest with mocked HTTP | WP01 | [D] |
| T006 | validate_felix_bot.py — argparse + token file reading + identity gate | WP02 | | [D] |
| T007 | validate_felix_bot.py — project access verification (read all 12 with felix-bot token) | WP02 | | [D] |
| T008 | validate_felix_bot.py — throwaway task creation + sample comment + readback + cleanup | WP02 | | [D] |
| T009 | validate_felix_bot.py — rollback smoke test mode (FR-015) | WP02 | | [D] |
| T010 | tests/vikunja/test_validate_felix_bot.py — pytest with mocked HTTP | WP02 | [D] |
| T011 | swap_vikunja_secrets.py — argparse + secrets path validation + atomic-file utility | WP03 | | [D] |
| T012 | swap_vikunja_secrets.py — atomic backup of existing secrets to .kent-pre-felix-bot.bak | WP03 | | [D] |
| T013 | swap_vikunja_secrets.py — atomic write of new token + chmod/chown + systemctl restart | WP03 | | [D] |
| T014 | swap_vikunja_secrets.py — post-swap attribution verification | WP03 | | [D] |
| T015 | swap_vikunja_secrets.py — --rollback-from-bak mode + auto-rollback on verify failure | WP03 | | [D] |
| T016 | tests/vikunja/test_swap_vikunja_secrets.py — pytest with mocked subprocess + HTTP | WP03 | [D] |
| T017 | revoke_kent_tokens.py — argparse + kent auth handling | WP04 | | [D] |
| T018 | revoke_kent_tokens.py — enumerate kent's API tokens + delete each (with UI fallback) | WP04 | | [D] |
| T019 | tests/vikunja/test_revoke_kent_tokens.py — pytest with mocked HTTP | WP04 | [D] |
| T020 | Write docs/runbooks/felix-bot-vikunja-provisioning.md (6-phase runbook with GO/NO-GO) | WP05 | | [D] |
| T021 | Update credential-manifest.json vikunja-api entry | WP05 | [D] |
| T022 | Update credentials-and-secrets.md narrative | WP05 | [D] |
| T023 | Update identity-model.md Agent Service Accounts | WP05 | [D] |
| T024 | Update service-inventory.json if vikunja entry tracks users | WP05 | [D] |

`[P]` indicates parallel-safe within the WP (different files). Cross-WP parallelism is full — all 5 WPs touch disjoint files.

---

## Work Packages

### WP01 — `provision_felix_bot.py` — Register felix-bot + share 12 projects + capture token

**Goal**: Implement the first-phase helper that registers the felix-bot Vikunja user, shares all 12 real projects with felix-bot at R/W, and captures the operator-supplied API token for downstream phases. Authenticates as `kent` (the still-active token) for the registration and sharing API calls.

**Priority**: P1 — foundational; nothing downstream can proceed without provision.

**Independent test**: Run `python3 scripts/vikunja/provision_felix_bot.py --help` displays a complete argparse interface. `pytest tests/vikunja/test_provision_felix_bot.py` passes all unit tests with mocked HTTP. Manual smoke: dry-run against a sandbox tenant or stage credentials.

**Estimated prompt size**: ~300 lines (5 subtasks @ 50-60 lines each plus boilerplate).

**Included subtasks**:

- [x] T001 Create scripts/vikunja/ + tests/vikunja/ scaffolding; provision_felix_bot.py argparse + identity gate (WP01)
- [x] T002 provision_felix_bot.py — user registration via POST /api/v1/register (WP01)
- [x] T003 provision_felix_bot.py — enumerate 12 real projects + share each at R/W (WP01)
- [x] T004 provision_felix_bot.py — post-share verification + capture operator-supplied API token (WP01)
- [x] T005 tests/vikunja/test_provision_felix_bot.py — pytest with mocked HTTP (WP01)

**Implementation sketch**:

1. Create directory scaffolding and argparse skeleton; identity-gate the helper to refuse running without an operator-provided kent token.
2. Implement registration via `POST /api/v1/register` with username/email/password from operator input.
3. Implement project enumeration (`GET /projects`) filtered to real projects (id>0, not archived), then per-project share grants (`PUT /projects/{id}/users`).
4. Verify all 12 shares applied via `GET /projects/{id}/users`. Capture the felix-bot API token via stdin or `--token-file` (operator generates via Vikunja UI logged in as felix-bot).
5. Pytest tests cover argparse validation, identity gate, registration request body shape, share-grant idempotency on conflict, and post-share verification.

**Parallel opportunities**:
- Cross-WP: all of WP02, WP03, WP04, WP05 in parallel (no code coupling).
- Within-WP: T005 (tests) [P] parallel with T001–T004 implementation since tests can be written test-first.

**Dependencies**: none.

**Risks**:
- Vikunja v0.24.6 may return 409 on duplicate share grant — confirmed empirically during implementation; helper treats as success.
- Operator-supplied token capture flow needs clean UX (clear prompts, validation, no token leak in logs).

**Files (owned_files)**:
- `scripts/vikunja/provision_felix_bot.py`
- `tests/vikunja/__init__.py`
- `tests/vikunja/test_provision_felix_bot.py`

**Requirement refs**: FR-001, FR-002, FR-003, NFR-005

**Prompt file**: [tasks/WP01-provision-felix-bot.md](./tasks/WP01-provision-felix-bot.md)

---

### WP02 — `validate_felix_bot.py` — Side-channel validation harness

**Goal**: Implement the second-phase helper that exercises felix-bot's new token end-to-end via a side-channel script BEFORE the production secrets file is rotated. Verifies project access for all 12 projects, writes/reads/deletes a sample comment on a throwaway task, and asserts attribution. Includes a rollback-procedure smoke test (FR-015) so the recovery path is proven before it is needed.

**Priority**: P1 — gates Phase 3 (cutover); failure here prevents the secrets file from being touched.

**Independent test**: `python3 scripts/vikunja/validate_felix_bot.py --help` displays a complete argparse interface. `pytest tests/vikunja/test_validate_felix_bot.py` passes. Live integration is the operator-driven run during pre-swap validation.

**Estimated prompt size**: ~300 lines.

**Included subtasks**:

- [x] T006 validate_felix_bot.py — argparse + token file reading + identity gate (WP02)
- [x] T007 validate_felix_bot.py — project access verification (read all 12 with felix-bot token) (WP02)
- [x] T008 validate_felix_bot.py — throwaway task creation + sample comment + readback + cleanup (WP02)
- [x] T009 validate_felix_bot.py — rollback smoke test mode (FR-015) (WP02)
- [x] T010 tests/vikunja/test_validate_felix_bot.py — pytest with mocked HTTP (WP02)

**Implementation sketch**:

1. Argparse with `--token-file`, `--target-project-id` (default 13 = Habits), `--dry-run`, `--rollback-smoke-test` flags.
2. Read felix-bot token from file; identity-gate confirms file is mode 600.
3. Validate project access: GET /projects with felix-bot token, assert all 12 project IDs returned.
4. Throwaway task probe: create task in target project, write `[Felix-Validation] <timestamp>` comment, read back, assert `created_by.username == felix-bot`, then DELETE comment + task.
5. `--rollback-smoke-test` mode exercises the rollback path symbolically without touching production state: validates the procedure documented in the runbook can be executed under timed pressure (<5 min per NFR-003).
6. Pytest covers: arg validation, idempotency, comment-attribution assertion, cleanup-failure soft-fail, dry-run skips network.

**Parallel opportunities**: All cross-WP parallel; within-WP T010 [P].

**Dependencies**: none.

**Risks**:
- Task creation may fail if felix-bot does not actually have write access (share grant from WP01 incomplete) — validation IS the check.
- Cleanup failure leaves a throwaway task in Vikunja UI — best-effort delete; operator can manually clean up.

**Files (owned_files)**:
- `scripts/vikunja/validate_felix_bot.py`
- `tests/vikunja/test_validate_felix_bot.py`

**Requirement refs**: FR-004, FR-015, NFR-001

**Prompt file**: [tasks/WP02-validate-felix-bot.md](./tasks/WP02-validate-felix-bot.md)

---

### WP03 — `swap_vikunja_secrets.py` — Atomic cutover with auto-rollback

**Goal**: Implement the third-phase helper that atomically rotates the secrets file from kent's token to felix-bot's token, restarts the gateway, and verifies post-swap attribution. Auto-rolls back to the .bak on any verification failure. Provides an explicit `--rollback-from-bak` mode for operator-triggered rollback.

**Priority**: P1 — the moment-of-truth helper. The redesign hinges on this swap working reliably.

**Independent test**: `python3 scripts/vikunja/swap_vikunja_secrets.py --help` displays argparse interface. `pytest tests/vikunja/test_swap_vikunja_secrets.py` passes (mocking subprocess for systemctl + urllib for HTTP). Manual smoke: dry-run mode + integration test occurs at operator execution.

**Estimated prompt size**: ~350 lines (6 subtasks).

**Included subtasks**:

- [x] T011 swap_vikunja_secrets.py — argparse + secrets path validation + atomic-file utility (WP03)
- [x] T012 swap_vikunja_secrets.py — atomic backup of existing secrets to .kent-pre-felix-bot.bak (WP03)
- [x] T013 swap_vikunja_secrets.py — atomic write of new token + chmod/chown + systemctl restart (WP03)
- [x] T014 swap_vikunja_secrets.py — post-swap attribution verification (WP03)
- [x] T015 swap_vikunja_secrets.py — --rollback-from-bak mode + auto-rollback on verify failure (WP03)
- [x] T016 tests/vikunja/test_swap_vikunja_secrets.py — pytest with mocked subprocess + HTTP (WP03)

**Implementation sketch**:

1. Argparse + path validation. Provides `--new-token-file`, `--secrets-path`, `--rollback-from-bak`, `--dry-run`.
2. Atomic-file utility: write-to-`.tmp`-then-rename pattern, explicit `chmod 600`, `chown claude:claude` (or verify via os.stat). Used for both .bak creation and new-token write.
3. Backup phase: copy existing `/data/services/openclaw/secrets/vikunja-api` to `vikunja-api.kent-pre-felix-bot.bak` atomically.
4. Rotate phase: write new token to `vikunja-api` atomically; `systemctl --user restart openclaw-gateway`; wait up to 30s for gateway health (poll `openclaw doctor` or equivalent).
5. Verify phase: invoke a sample Felix agent comment write via `openclaw agent` command; read back the comment; assert `created_by.username == felix-bot`.
6. Auto-rollback on verify failure: write `.bak` contents back to `vikunja-api`, restart gateway, re-verify reverted-to-kent state, exit nonzero with diagnostic.
7. `--rollback-from-bak` mode: manual rollback trigger for operator use during soak.
8. Pytest covers: atomic-file logic, mode/ownership preservation, rollback path, verification assertion, dry-run skips writes.

**Parallel opportunities**: All cross-WP parallel; within-WP T016 [P].

**Dependencies**: none (code-independent of other WPs).

**Risks**:
- Race condition during atomic rename (mitigated by os.rename being atomic on same filesystem).
- Gateway restart timing — must wait for healthy state before verification probe.
- Verification probe semantics: invokes a real Felix agent that may have its own state assumptions. Use a low-impact agent (e.g., felix-admin-habits with a no-op test invocation).

**Files (owned_files)**:
- `scripts/vikunja/swap_vikunja_secrets.py`
- `tests/vikunja/test_swap_vikunja_secrets.py`

**Requirement refs**: FR-005, FR-006, FR-007, FR-008, NFR-002, NFR-003, NFR-004

**Prompt file**: [tasks/WP03-swap-vikunja-secrets.md](./tasks/WP03-swap-vikunja-secrets.md)

---

### WP04 — `revoke_kent_tokens.py` — Post-soak cleanup

**Goal**: Implement the fourth-phase helper that revokes any remaining kent-attributed API tokens AFTER the 7-day soak passes. Confirms kent has zero active API tokens; felix-bot is the sole API identity.

**Priority**: P2 — runs only after soak; not on the critical path of the initial cutover.

**Independent test**: `python3 scripts/vikunja/revoke_kent_tokens.py --help`. `pytest tests/vikunja/test_revoke_kent_tokens.py` passes. Live exercise during Phase 6.

**Estimated prompt size**: ~200 lines.

**Included subtasks**:

- [x] T017 revoke_kent_tokens.py — argparse + kent auth handling (WP04)
- [x] T018 revoke_kent_tokens.py — enumerate kent's API tokens + delete each (with UI fallback) (WP04)
- [x] T019 tests/vikunja/test_revoke_kent_tokens.py — pytest with mocked HTTP (WP04)

**Implementation sketch**:

1. Argparse with `--kent-password-stdin` (operator types kent password from 1Password) OR `--kent-token` (if a residual kent token is still available). Helper obtains a fresh JWT via `POST /api/v1/login` using kent credentials.
2. Enumerate kent's API tokens via `GET /api/v1/tokens` (Vikunja v0.24.6 endpoint TBD — confirm during implementation). For each token: `DELETE /api/v1/tokens/{id}`. If API endpoint unavailable, helper exits with explicit operator instructions for UI-based revocation.
3. Pytest covers: arg validation, both auth modes, enumeration parsing, delete-call sequencing, UI-fallback path.

**Parallel opportunities**: All cross-WP parallel; within-WP T019 [P].

**Dependencies**: none.

**Risks**:
- Vikunja v0.24.6 may not expose the token enumeration/deletion endpoints. Fallback to UI revocation is documented; helper exits nonzero with clear instructions if API path unavailable.
- Authenticating with kent password is operator-time work — flow needs clean prompting and no password echo.

**Files (owned_files)**:
- `scripts/vikunja/revoke_kent_tokens.py`
- `tests/vikunja/test_revoke_kent_tokens.py`

**Requirement refs**: FR-014

**Prompt file**: [tasks/WP04-revoke-kent-tokens.md](./tasks/WP04-revoke-kent-tokens.md)

---

### WP05 — Operator runbook + 4 architecture doc updates

**Goal**: Write the operator-facing runbook that sequences the four helpers, and update the four architecture documentation files to reflect felix-bot ownership. The runbook is the operator's primary reference during execution.

**Priority**: P1 — required for operator to execute the mission cleanly.

**Independent test**: `markdownlint docs/runbooks/felix-bot-vikunja-provisioning.md` passes. JSON files parse-validate (`python3 -c "import json; json.load(open('...'))"`). Manual review: operator reads runbook end-to-end and confirms it sequences clearly with GO/NO-GO criteria at each phase boundary.

**Estimated prompt size**: ~300 lines (5 subtasks; one large doc-writing task plus 4 smaller doc edits).

**Included subtasks**:

- [x] T020 Write docs/runbooks/felix-bot-vikunja-provisioning.md (6-phase runbook with GO/NO-GO) (WP05)
- [x] T021 Update credential-manifest.json vikunja-api entry (WP05)
- [x] T022 Update credentials-and-secrets.md narrative (WP05)
- [x] T023 Update identity-model.md Agent Service Accounts (WP05)
- [x] T024 Update service-inventory.json if vikunja entry tracks users (WP05)

**Implementation sketch**:

1. Runbook structure: Pre-flight (Restic backup, kent presence, deps healthy) → Phase 1 (provision) → Phase 2 (validate) → Phase 3 (swap) → Phase 4 (doc commit) → Phase 5 (7-day soak with daily monitoring) → Phase 6 (revoke + cleanup). Each phase has explicit invocation, expected SUMMARY output, GO/NO-GO criteria, and rollback trigger.
2. `credential-manifest.json` `vikunja-api` entry: bump `last_reviewed` to rotation date, prepend `#304-felix-bot-rotation` to `updated_by`, update `notes`.
3. `credentials-and-secrets.md`: bump frontmatter `last_updated` and `updated_by`; update Active Credentials table `vikunja-api` row to reflect felix-bot ownership.
4. `identity-model.md`: add felix-bot (Vikunja) to Agent Service Accounts section alongside kg-felix-bot (GitHub).
5. `service-inventory.json`: verify if `vikunja` entry tracks per-user accounts. If yes, add felix-bot to user list. If no (no such field exists today), this is a no-op — document why in the doc update commit.

**Parallel opportunities**: All cross-WP parallel; within-WP T021–T024 [P] (different files).

**Dependencies**: none in implementation. Operationally, the doc updates commit happens at Phase 4 of the runbook — after WP03 succeeds — but the doc edits themselves can be staged in a feature branch ahead of execution.

**Risks**:
- Doc files have existing structure that must be preserved (frontmatter conventions, JSON schema in credential-manifest).
- Runbook quality affects operator execution success. Must include clear rollback triggers and GO/NO-GO criteria.

**Files (owned_files)**:
- `docs/runbooks/felix-bot-vikunja-provisioning.md`
- `docs/design/architecture/data/credential-manifest.json`
- `docs/design/architecture/credentials-and-secrets.md`
- `docs/design/architecture/identity-model.md`
- `docs/design/architecture/data/service-inventory.json`

**Requirement refs**: FR-009, FR-010, FR-011, FR-012, FR-013, NFR-006

**Prompt file**: [tasks/WP05-runbook-and-docs.md](./tasks/WP05-runbook-and-docs.md)

---

## Parallelization plan

All 5 WPs are code-independent and can run in parallel implementation lanes. The orchestrator can dispatch all 5 to implementing agents simultaneously since no WP's owned_files overlap with another's.

**Estimated total wall-clock time** if all 5 dispatched in parallel: time of the slowest WP (likely WP03 at ~350 line prompt) + review cycle overhead. Roughly 30-60 min for implementation + review.

## MVP scope

If reducing scope to a phased rollout:
- **MVP cutover-only**: WP01 + WP02 + WP03 + WP05 — delivers full cutover capability. WP04 (revoke) deferred until after 7-day soak.
- **Full mission**: all 5 WPs.

Recommend full mission delivery in one sprint — WP04 is small (3 subtasks, ~200 lines) and finishing it now means the post-soak cleanup is ready when needed.

## Implement-Review pairing

Per Kent's instruction 2026-05-17: when this mission reaches `/spec-kitty.implement`, the orchestrator dispatches **implementation to Claude** and **review to Codex**. See `plan.md` § "Implement-Review workflow" for the rationale.
