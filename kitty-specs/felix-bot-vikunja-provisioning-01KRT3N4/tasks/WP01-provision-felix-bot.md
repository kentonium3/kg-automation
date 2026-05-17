---
work_package_id: WP01
title: Provision felix-bot Vikunja user — register, share 12 projects, capture API token
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- NFR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-bot-vikunja-provisioning-01KRT3N4
base_commit: b89c2c9c9e8ab0642aad7e7a2155e48b52884920
created_at: '2026-05-17T05:17:07.151702+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
shell_pid: "66245"
agent: "codex:gpt-4o:python-reviewer:reviewer"
history:
- action: drafted
  agent: claude
  timestamp: '2026-05-17T05:10:00Z'
authoritative_surface: scripts/vikunja/provision_felix_bot.py
execution_mode: code_change
mission_slug: felix-bot-vikunja-provisioning-01KRT3N4
owned_files:
- scripts/vikunja/provision_felix_bot.py
- tests/vikunja/__init__.py
- tests/vikunja/test_provision_felix_bot.py
tags: []
---

# WP01 — Provision felix-bot Vikunja user

## Objective

Implement `scripts/vikunja/provision_felix_bot.py` — the first-phase helper of ADR-0002 Phase 1 (issue #304). The helper registers the new `felix-bot` Vikunja user on the office2 instance, shares all 12 real Vikunja projects with felix-bot at read/write permission, captures the operator-supplied felix-bot API token from stdin or a file, and writes the captured token to a path the operator names for use by downstream phase helpers (WP02 validation, WP03 swap).

The helper authenticates to Vikunja using **kent's existing API token** (still active at this phase, since the secrets file rotation does not happen until WP03). The output is felix-bot's identity in Vikunja + a token captured to disk for the next phase.

## Context

- **Spec section**: FR-001, FR-002, FR-003, NFR-005 in [spec.md](../spec.md).
- **Design rationale**: [research.md](../research.md) R-001 (Vikunja capabilities verified), R-006 (operator-driven not auto-orchestrated), R-008 (password storage in 1Password, not on-disk).
- **API contracts**: See [contracts/vikunja-api-endpoints.md](../contracts/vikunja-api-endpoints.md) sections C-1 (register), C-2 (list projects), C-3 (share), C-4 (verify shares), C-5 (token generation).
- **Existing helper convention**: Match the style of `scripts/openclaw/agents/main/felix-file-issue.py` and its tests at `tests/openclaw/agents/main/test_felix_file_issue.py`. Key conventions: argparse with strict types, `SUMMARY:` line on stdout for parsable output, identity verification gate at startup, structured JSON output on success, error exit codes (0 = ok, 1 = operational failure, 2 = usage error).
- **Branch strategy**: per `planning_base_branch: main`, `merge_target_branch: main`. The execution worktree is allocated automatically per the computed lane from `lanes.json` (created by `spec-kitty agent mission finalize-tasks`). When you run `spec-kitty agent action implement WP01 --agent <name>`, the workspace path is printed in the output — work there, not in the project root.

## Branch strategy

Planning branch: `main`. Final merge target: `main`. Execution worktree allocated per computed lane in `lanes.json` after task finalization. The agent's `spec-kitty agent action implement WP01 --agent <name>` invocation prints the workspace path; commit work there.

## Subtask guidance

### T001 — scripts/vikunja/ scaffolding + provision_felix_bot.py argparse + identity gate

**Purpose**: Establish the directory structure and the helper's top-level CLI contract. Identity gate prevents accidental execution with no auth context.

**Steps**:

1. Create the new directories: `scripts/vikunja/` (empty for now, populated by this WP and WP02-WP04), `tests/vikunja/` with an empty `__init__.py` for pytest discovery.
2. Write the docstring header at the top of `provision_felix_bot.py`. Follow the felix-file-issue.py pattern: explain what the helper does, the API endpoints consumed, exit code semantics, expected invocation pattern.
3. Implement argparse with these arguments:
   - `--username` (required, default `felix-bot`) — Vikunja username for the new user
   - `--email` (required, default `kentgale+felix-bot@gmail.com`) — registration email
   - `--password-from-stdin` (boolean flag) — read password from stdin (one line, no echo)
   - `--kent-token-file` (required) — path to a file containing kent's existing Vikunja API token
   - `--token-output-file` (required) — path where the captured felix-bot token will be written (mode 600)
   - `--vikunja-base-url` (default `https://office2.tail0f5f56.ts.net/api/v1/`)
   - `--dry-run` (boolean flag) — perform no network calls, log what would happen
4. Implement an `identity_gate()` function: verify `kent_token_file` is readable, mode-600, contains a non-empty token. If not, exit code 2 with explicit error.
5. Add a `SUMMARY: ...` line at the end of all stdout output paths so the runbook can parse it.

**Files**:
- `scripts/vikunja/provision_felix_bot.py` (new, ~80 lines for this subtask)
- `tests/vikunja/__init__.py` (new, empty file with module docstring)

**Validation**:
- `python3 scripts/vikunja/provision_felix_bot.py --help` displays argparse interface with all listed flags
- Running with missing required args exits 2
- Running with non-existent `--kent-token-file` exits 2 with "kent token file not readable" message
- `--dry-run` flag passes argparse without errors

### T002 — User registration via POST /api/v1/register

**Purpose**: Register the new felix-bot user on the office2 Vikunja instance. Capture the assigned user_id for downstream use.

**Steps**:

1. Implement `register_felix_bot(username, email, password, base_url, dry_run) -> dict`:
   - Build POST body: `{"username": username, "email": email, "password": password}`
   - POST to `{base_url}/register`
   - On 200/201: parse response, extract `id` field, return `{"user_id": id, "username": username, ...}`
   - On 400 (e.g., missing field): print Vikunja error message to stderr, exit 1
   - On 409 (username conflict): print clear error explaining felix-bot may already exist from a prior attempt, exit 1
   - On 5xx or network error: print error, exit 1
   - In `dry_run` mode: print intended request body, return mock user_id, no network call
2. Validate that the response includes `id` of expected type (integer) — defensive parsing.
3. Use `urllib.request` for HTTP (stdlib, no third-party deps per research R-002).

**Files**:
- `scripts/vikunja/provision_felix_bot.py` (~50 added lines)

**Validation**:
- Unit test mocks `urllib.request.urlopen` to return a 200 with a fake user object; helper extracts user_id correctly
- Unit test mocks 409 response; helper exits 1 with explicit conflict message
- Unit test exercises dry-run path; verifies no network call made

### T003 — Enumerate 12 real projects + share each at R/W

**Purpose**: After felix-bot is registered, share every Felix-touched Vikunja project with the new user. The 12 projects today are IDs 1, 2, 4-13.

**Steps**:

1. Implement `enumerate_real_projects(base_url, kent_token) -> list[dict]`:
   - GET `{base_url}/projects?per_page=50`
   - Filter to real projects: `id > 0 AND is_archived != True`
   - Return list of `{"id": int, "title": str}` for each real project
   - Assert at least 12 returned; warn if more (a project was added since spec — operator should investigate before proceeding)
2. Implement `share_project_with_user(project_id, user_id, right, base_url, kent_token) -> bool`:
   - PUT `{base_url}/projects/{project_id}/users`
   - Body: `{"user_id": user_id, "right": right}` where `right=1` is read-write (per ADR-0002 Q3 / spec C-004)
   - On 200/201: return True
   - On 409 (already shared — possibly from a retry): treat as success and continue
   - On 403 (kent lacks admin on project): exit 1 with clear error
   - On 5xx: exit 1
3. Iterate over the 12 real projects, share each one with felix-bot. Print per-project SUMMARY lines so operator sees progress.

**Files**:
- `scripts/vikunja/provision_felix_bot.py` (~70 added lines)

**Validation**:
- Unit test mocks `GET /projects` returning a list of 14 projects (12 real + 2 pseudo-with-positive-ID-but-archived). Helper correctly identifies the 12 real ones.
- Unit test mocks per-project share success; helper logs each.
- Unit test mocks one share returning 403; helper exits with the project name in the error message.
- Unit test mocks share returning 409 (already shared); helper treats as success.

### T004 — Post-share verification + capture operator-supplied API token

**Purpose**: After all 12 shares apply, verify each one took effect by reading back the share list. Then capture the operator-supplied felix-bot API token (generated via Vikunja UI or v0.24.6 API if available) and write it to the operator-named output file.

**Steps**:

1. Implement `verify_shares_applied(projects, felix_bot_user_id, base_url, kent_token) -> dict`:
   - For each project, GET `{base_url}/projects/{id}/users`
   - Confirm felix-bot's user_id appears in the share list with `right=1`
   - Return summary `{"verified": [list of project ids], "missing": [list of project ids]}`
   - If `missing` is non-empty, exit 1 — do NOT proceed to token capture
2. Implement `capture_felix_bot_token(token_output_file) -> None`:
   - Print operator instructions for token generation: instruct the operator to open the Vikunja UI at `https://office2.tail0f5f56.ts.net/`, log in as `felix-bot` with the password from 1Password, navigate to Settings → API Tokens, generate a new token named `felix-provisioning-<date>` with no expiry and full scope, then paste it back into this script.
   - Read the token from stdin (one line, validate non-empty and looks like a Vikunja token — typically starts with a recognizable prefix; defensive check: ASCII printable, length >= 20)
   - Write the token to `token_output_file` with mode 600, ownership claude:claude (use `os.write` + explicit `os.chmod` before close to avoid a permission window)
3. Print final `SUMMARY:` line:
   ```
   SUMMARY: felix-bot registered (uid=<N>), 12 projects shared, token captured to <path>
   ```
4. Note: Vikunja v0.24.6 may expose `POST /api/v1/tokens` for programmatic token creation. If so, an enhancement option: skip the operator UI flow and call the endpoint. Helper should TRY the API path first and fall back to UI instruction if 404. Document the behavior empirically during implementation.

**Files**:
- `scripts/vikunja/provision_felix_bot.py` (~70 added lines)

**Validation**:
- Unit test mocks per-project share-list returning felix-bot in all 12; helper proceeds to token capture.
- Unit test mocks one project missing the felix-bot grant; helper exits 1 with the project id in the error.
- Unit test mocks stdin with a valid-looking token; helper writes to `token_output_file` with mode 600.
- Unit test mocks stdin with empty input; helper exits 2.
- Token output file mode is verified as 600 (test reads it back via `os.stat`).

### T005 — Pytest tests for provision_felix_bot.py

**Purpose**: Comprehensive unit test coverage matching the felix-file-issue.py test pattern. Tests run via subprocess invocation of the helper, mocking HTTP via `unittest.mock.patch` of `urllib.request.urlopen`.

**Steps**:

1. Create `tests/vikunja/test_provision_felix_bot.py` with the test class structure.
2. Test categories:
   - **Argparse validation**: missing required args exit 2; invalid types exit 2; --help works
   - **Identity gate**: missing kent token file exits 2; wrong-permission kent token file exits 2; valid mode-600 token file passes
   - **Registration**: success path; 400 missing field; 409 conflict; 5xx error
   - **Share grants**: 12 projects shared successfully; one project 403; one project 409 (treated as success); per-project SUMMARY lines emitted
   - **Verification**: all-shares-applied path; partial-failure path (exits 1)
   - **Token capture**: stdin read happy path; empty stdin (exits 2); file written with mode 600
   - **Dry-run**: full path with `--dry-run` flag; no network calls made (verified via `urlopen` mock not called)
3. Aim for ~12-15 tests covering the surface above. Roughly matches the felix-file-issue.py test count (21).

**Files**:
- `tests/vikunja/test_provision_felix_bot.py` (new, ~250 lines for ~12 tests)

**Validation**:
- `pytest tests/vikunja/test_provision_felix_bot.py -v` passes all tests
- Coverage of all error paths and the happy path
- No tests make live network calls (all HTTP mocked)

## Test strategy

Pytest with subprocess invocation + `unittest.mock.patch` of `urllib.request.urlopen` for HTTP. No live Vikunja calls. Match the pattern from `tests/openclaw/agents/main/test_felix_file_issue.py`.

Validation hierarchy:
1. **Argparse validation** — invalid args exit 2 (Python's argparse default)
2. **Identity gate** — missing/wrong-mode token file exits 2
3. **Operational** — HTTP failures exit 1
4. **Happy path** — exit 0 with `SUMMARY:` line and token written

## Definition of Done

- [ ] `scripts/vikunja/provision_felix_bot.py` exists and is executable
- [ ] `tests/vikunja/__init__.py` exists (empty, for pytest)
- [ ] `tests/vikunja/test_provision_felix_bot.py` exists with ≥12 passing tests
- [ ] Helper passes `python3 scripts/vikunja/provision_felix_bot.py --help` cleanly
- [ ] All argparse args from T001 implemented
- [ ] Identity gate rejects unsafe kent-token-file
- [ ] Registration handles 200/400/409/5xx as specified
- [ ] Share grants iterate all 12 real projects; tolerate 409; halt on 403
- [ ] Share verification reads back the grants and confirms felix-bot present in each
- [ ] Token capture writes to file with mode 600 + claude:claude ownership
- [ ] `SUMMARY:` line emitted at end
- [ ] Dry-run skips all network calls
- [ ] Pytest suite passes (`pytest tests/vikunja/test_provision_felix_bot.py -v`)
- [ ] No third-party dependencies introduced (stdlib only)

## Risks

- **Vikunja 409 on duplicate share**: Verified during implementation. Helper treats as success per contract C-3.
- **Token endpoint availability**: Vikunja v0.24.6 may or may not expose `POST /api/v1/tokens`. The helper's primary flow is operator-driven (UI generation + paste). API path is an optimization to attempt if available.
- **Operator password handling**: The Vikunja registration requires a password. Helper accepts via `--password-from-stdin` so the password is never on the command line (and never echoed). Operator pastes from 1Password.
- **Premature exit before token capture**: If the helper exits between registration and token capture, felix-bot exists but no token is in hand. Operator can run a follow-up helper (or manually generate the token via UI) to recover.

## Reviewer guidance (for Codex review)

- Verify HTTP request bodies match the contracts at [contracts/vikunja-api-endpoints.md](../contracts/vikunja-api-endpoints.md) sections C-1 through C-5.
- Verify `right=1` (not 0 or 2) is used for share grants per spec C-004.
- Verify identity gate rejects mode != 600 on the kent-token-file.
- Verify token output file is written with mode 600 BEFORE the file is closed (no race window where the file is readable by others).
- Verify password is never logged or printed back.
- Verify all 12 projects are share-verified before token capture proceeds.
- Verify pytest tests use `unittest.mock.patch` correctly and never make real network calls.
- Verify exit codes: 0 success, 1 operational, 2 usage — consistent with felix-file-issue.py convention.
- Confirm SUMMARY line format matches the runbook's parsing expectation.

## Implementation command

```bash
spec-kitty agent action implement WP01 --mission felix-bot-vikunja-provisioning-01KRT3N4 --agent <tool>:<model>:<profile>:<role>
```

## Review command

```bash
spec-kitty agent action review WP01 --mission felix-bot-vikunja-provisioning-01KRT3N4 --agent codex:gpt-4o:python-reviewer:reviewer
```

## Activity Log

- 2026-05-17T05:17:09Z – claude:opus-4-7:python-implementer:implementer – shell_pid=63891 – Assigned agent via action command
- 2026-05-17T05:23:52Z – claude:opus-4-7:python-implementer:implementer – shell_pid=63891 – Ready for review — provision_felix_bot.py (792 lines) + tests/vikunja/__init__.py + tests/vikunja/test_provision_felix_bot.py (544 lines, 23 tests passing). Stdlib-only urllib.request, identity gate (mode 600), atomic token write.
- 2026-05-17T05:24:19Z – codex:gpt-4o:python-reviewer:reviewer – shell_pid=66245 – Started review via action command
