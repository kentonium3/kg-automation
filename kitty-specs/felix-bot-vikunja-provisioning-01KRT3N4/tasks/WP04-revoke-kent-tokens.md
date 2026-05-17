---
work_package_id: WP04
title: Revoke kent API tokens — post-soak cleanup
dependencies: []
requirement_refs:
- FR-014
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-bot-vikunja-provisioning-01KRT3N4
base_commit: b89c2c9c9e8ab0642aad7e7a2155e48b52884920
created_at: '2026-05-17T05:18:27.865186+00:00'
subtasks:
- T017
- T018
- T019
shell_pid: "70044"
agent: "claude:opus-4-7:python-implementer:implementer"
history:
- action: drafted
  agent: claude
  timestamp: '2026-05-17T05:25:00Z'
authoritative_surface: scripts/vikunja/revoke_kent_tokens.py
execution_mode: code_change
mission_slug: felix-bot-vikunja-provisioning-01KRT3N4
owned_files:
- scripts/vikunja/revoke_kent_tokens.py
- tests/vikunja/test_revoke_kent_tokens.py
tags: []
---

# WP04 — Revoke kent API tokens (post-soak cleanup)

## Objective

Implement `scripts/vikunja/revoke_kent_tokens.py` — the post-soak cleanup helper of ADR-0002 Phase 1 (issue #304). After the 7-day soak passes, this helper enumerates and revokes any remaining API tokens attributed to the `kent` Vikunja user, leaving `felix-bot` as the sole API identity. Authenticates as kent via password (from 1Password) to obtain a fresh JWT for the revocation calls.

The helper provides a UI-based fallback if Vikunja v0.24.6 does not expose the token enumeration/deletion endpoints — exits with explicit operator instructions in that case.

## Context

- **Spec section**: FR-014 in [spec.md](../spec.md). Also SC-007 (kent has zero active API tokens post-mission).
- **Design rationale**: [research.md](../research.md) R-009 (revoke AFTER 7-day soak, not before — preserves rollback path), R-010 (kent UI session continues to work since JWT sessions are independent of API tokens).
- **API contracts**: See [contracts/vikunja-api-endpoints.md](../contracts/vikunja-api-endpoints.md) section C-12 (token revocation — endpoint TBD on v0.24.6).
- **Timing**: This helper runs in Phase 6 of the runbook, AFTER the 7-day soak passes. Not earlier.
- **Existing helper convention**: Same as WP01-WP03.

## Branch strategy

Planning branch: `main`. Final merge target: `main`. Execution worktree allocated per computed lane in `lanes.json` after task finalization.

## Subtask guidance

### T017 — argparse + kent auth handling

**Purpose**: Establish the CLI and the kent-authentication path. Since kent's API token may not exist anymore (the rotation in WP03 swapped it out, and we're about to revoke any remaining), this helper logs in as kent via password to obtain a fresh JWT.

**Steps**:

1. Write the docstring header — explain post-soak cleanup role, password handling caveat.
2. Implement argparse with:
   - `--kent-username` (default `kent`)
   - `--kent-password-from-stdin` (boolean flag) — read password from stdin, no echo
   - `--kent-token` (optional) — alternative auth path if a residual kent token exists
   - `--vikunja-base-url` (default `https://office2.tail0f5f56.ts.net/api/v1/`)
   - `--dry-run` (boolean flag)
   - `--ui-fallback-only` (boolean flag) — skip the API path; print operator instructions for UI revocation
3. Validate that exactly one of `--kent-password-from-stdin` or `--kent-token` is provided (mutually exclusive auth modes). If both or neither, exit 2.
4. Implement `obtain_kent_jwt(username, password, base_url) -> str`:
   - POST `{base_url}/login` with `{"username": username, "password": password}`
   - On 200: extract the JWT token from response; return it
   - On 401: exit 1 with "kent credentials rejected — verify password from 1Password"
   - On 5xx: exit 1
5. Never echo the password or JWT.

**Files**:
- `scripts/vikunja/revoke_kent_tokens.py` (new, ~80 lines)

**Validation**:
- `python3 scripts/vikunja/revoke_kent_tokens.py --help` works
- Conflicting auth flags exit 2
- Missing auth flags exit 2
- Mock login 200 returns a JWT
- Mock login 401 exits 1

### T018 — Enumerate kent's API tokens + delete each (with UI fallback)

**Purpose**: Find any tokens kent still has and delete them. If the Vikunja API doesn't support enumeration/deletion, fall back to UI instructions.

**Steps**:

1. Implement `enumerate_kent_tokens(jwt_or_token, base_url) -> list[dict]`:
   - Try GET `{base_url}/tokens` (Vikunja v0.24.6 endpoint TBD)
   - On 200: parse response, filter to kent-owned tokens (kent's user_id), return list of `{id, created, ...}`
   - On 404: raise `EndpointUnavailable` — caller falls back to UI path
   - On 401: exit 1 (auth failed)
2. Implement `delete_token(token_id, jwt_or_token, base_url) -> bool`:
   - DELETE `{base_url}/tokens/{token_id}`
   - On 200/204: return True
   - On 404: token already gone (race condition with another revocation); log and continue
   - On 4xx/5xx: exit 1 with the failing token_id
3. Implement `ui_fallback_instructions() -> None`:
   - Print step-by-step instructions for the operator:
     - Log in to Vikunja UI as kent
     - Navigate to Settings → API Tokens
     - Delete each listed token (screenshot or text-described UI path)
   - Exit code 0 (this is success — the operator will do it manually)
4. Main flow:
   ```
   if --ui-fallback-only:
       ui_fallback_instructions()
       exit 0
   try:
       tokens = enumerate_kent_tokens(...)
       if not tokens:
           print("SUMMARY: kent has zero API tokens — nothing to revoke. Goal achieved.")
           exit 0
       for token in tokens:
           delete_token(token.id, ...)
       print(f"SUMMARY: revoked {len(tokens)} kent API tokens")
       exit 0
   except EndpointUnavailable:
       print("API endpoint for token enumeration/deletion not available on v0.24.6")
       ui_fallback_instructions()
       exit 0
   ```

**Files**:
- `scripts/vikunja/revoke_kent_tokens.py` (~70 added lines)

**Validation**:
- Unit test mocks enumeration returning 0 tokens; helper exits 0 with "nothing to revoke" SUMMARY.
- Unit test mocks 3 tokens; helper deletes each in sequence; exits 0.
- Unit test mocks 404 on enumeration; helper prints UI fallback instructions; exits 0.
- Unit test mocks 401 on enumeration; helper exits 1.
- Unit test mocks one delete returning 404 (concurrent revocation); helper logs and continues.
- Unit test `--ui-fallback-only`: helper prints instructions without making any HTTP calls; exits 0.

### T019 — Pytest tests for revoke_kent_tokens.py

**Purpose**: Comprehensive unit test coverage.

**Steps**:

1. Create `tests/vikunja/test_revoke_kent_tokens.py`.
2. Test categories:
   - **Argparse**: missing/conflicting auth flags exit 2
   - **Auth**: login 200 returns JWT; login 401 exits 1
   - **Enumeration**: 0 tokens, N tokens, 404 (fallback), 401 (auth failure)
   - **Deletion**: per-token delete sequence; 404 mid-sequence (continue)
   - **UI fallback**: `--ui-fallback-only` mode; auto-fallback on 404
   - **Dry-run**: no network calls
3. Aim for ~8-10 tests (smaller surface than the other helpers).

**Files**:
- `tests/vikunja/test_revoke_kent_tokens.py` (new, ~180 lines)

**Validation**:
- `pytest tests/vikunja/test_revoke_kent_tokens.py -v` all pass
- No live network calls

## Test strategy

Pytest with mocked `urllib.request.urlopen`. Same pattern as WP01-WP03.

## Definition of Done

- [ ] `scripts/vikunja/revoke_kent_tokens.py` exists and is executable
- [ ] `tests/vikunja/test_revoke_kent_tokens.py` exists with ≥8 passing tests
- [ ] `python3 scripts/vikunja/revoke_kent_tokens.py --help` works
- [ ] Argparse implements all flags from T017
- [ ] Mutually-exclusive auth modes enforced (exits 2 on conflict)
- [ ] kent JWT obtained via `POST /api/v1/login` on the password path
- [ ] Token enumeration handles 200, 404 (fallback), 401 (fail) correctly
- [ ] Each kent token deleted via DELETE; 404 mid-sequence tolerated
- [ ] UI fallback prints clear operator instructions
- [ ] `SUMMARY:` line emitted at end
- [ ] Pytest suite passes
- [ ] No third-party dependencies

## Risks

- **Vikunja v0.24.6 endpoint availability**: The token enumeration/deletion API may not exist. UI fallback is the safety net.
- **Password handling**: Operator types the kent password from 1Password. Helper must NOT log it, echo it, or store it in any persistent state.
- **JWT lifetime**: The JWT obtained for revocation calls may have short expiration. Helper should complete the enumeration + deletion within one JWT lifetime (typically minutes). If a JWT-expired error happens mid-sequence, helper exits 1 with explicit instructions.
- **Concurrent revocation**: If another operator (or a future automation) revokes a token between enumeration and delete, the 404 is tolerated.

## Reviewer guidance (for Codex review)

- Verify the password is read via stdin, not from argv (which would expose it in process listings).
- Verify the password and JWT are never printed, logged, or echoed.
- Verify the mutually-exclusive auth check trips correctly (exit 2 for both flags or neither flag).
- Verify the UI fallback instructions are clear and complete — operator should be able to follow them without expert knowledge.
- Verify the 404 mid-sequence on delete is tolerated (logged but loop continues).
- Verify the helper does the right thing when zero tokens are returned (no false alarms; clean exit 0).
- Confirm the SUMMARY line accurately reports the token count revoked.

## Implementation command

```bash
spec-kitty agent action implement WP04 --mission felix-bot-vikunja-provisioning-01KRT3N4 --agent <tool>:<model>:<profile>:<role>
```

## Review command

```bash
spec-kitty agent action review WP04 --mission felix-bot-vikunja-provisioning-01KRT3N4 --agent codex:gpt-4o:python-reviewer:reviewer
```

## Activity Log

- 2026-05-17T05:18:30Z – claude:opus-4-7:python-implementer:implementer – shell_pid=64199 – Assigned agent via action command
- 2026-05-17T05:24:13Z – claude:opus-4-7:python-implementer:implementer – shell_pid=64199 – Ready for review — revoke_kent_tokens.py + test_revoke_kent_tokens.py
- 2026-05-17T05:25:03Z – codex:gpt-4o:python-reviewer:reviewer – shell_pid=66639 – Started review via action command
- 2026-05-17T05:32:45Z – codex:gpt-4o:python-reviewer:reviewer – shell_pid=66639 – Moved to planned
- 2026-05-17T05:33:17Z – claude:opus-4-7:python-implementer:implementer – shell_pid=70044 – Started implementation via action command
