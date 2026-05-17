# Contracts: Vikunja API endpoints consumed by the mission

**Mission**: `felix-bot-vikunja-provisioning-01KRT3N4`

This mission consumes a small subset of Vikunja v0.24.6's HTTP API. It produces no new HTTP API of its own (the helpers are CLI tools). The "contracts" here document the endpoints we depend on, their expected request shape, expected response shape, and our handling rules for non-happy paths.

All endpoints target the office2 Vikunja instance at base URL `https://office2.tail0f5f56.ts.net/api/v1/`. All Vikunja-side behaviors below were verified during the 2026-05-17 live probe (see `docs/design/research/vikunja-task-model-research.md`).

---

## C-1 — Register a new user

**Endpoint**: `POST /api/v1/register`

**Used by**: `provision_felix_bot.py`

**Authentication**: None (registration is open per `registration_enabled: true` in `/api/v1/info`)

**Request body** (JSON):

```json
{
  "username": "felix-bot",
  "email": "kentgale+felix-bot@gmail.com",
  "password": "<1Password-generated>"
}
```

**Success response**: `200 OK` with a JSON body containing the new user (with `id` assigned by Vikunja). Helper extracts `id` for later use.

**Failure cases**:

| Status | Cause | Helper action |
|---|---|---|
| `400` | Missing field (`{"message": "Please specify a username and a password"}` etc.) | Exit nonzero with the Vikunja error message |
| `409` | Username already exists | Exit nonzero — the operator should investigate (likely a stale registration from a prior attempt) |
| `5xx` | Vikunja service issue | Exit nonzero; do not retry |

---

## C-2 — List projects (felix-bot's view OR enumeration)

**Endpoint**: `GET /api/v1/projects?per_page=50`

**Used by**: `provision_felix_bot.py` (to enumerate the 12 real projects under kent's token), `validate_felix_bot.py` (to verify felix-bot can see all 12)

**Authentication**: `Authorization: Bearer <token>` header

**Success response**: `200 OK` with a JSON array of project objects. Each object has at minimum `id`, `title`, `parent_project_id`, `is_archived`.

**Helper rules**:

- Filter to real projects: `id > 0 AND is_archived != true`
- Pseudo-projects (id in -5 to -1) are skipped — they're filter views, not shareable
- Expected count of real projects at execution time: ≥ 12 (today's count). If lower, the operator investigates before proceeding (a project may have been archived or deleted unexpectedly).

**Failure cases**:

| Status | Cause | Helper action |
|---|---|---|
| `401` | Invalid token | Exit nonzero; the operator's auth context is wrong |
| `5xx` | Vikunja service issue | Exit nonzero; do not retry |

---

## C-3 — Share a project with a user

**Endpoint**: `PUT /api/v1/projects/{project_id}/users`

**Used by**: `provision_felix_bot.py` (one call per project, 12 total)

**Authentication**: `Authorization: Bearer <kent-token>` header (this happens before the rotation, when kent's token is still active)

**Request body** (JSON):

```json
{
  "user_id": <felix-bot's user_id>,
  "right": 1
}
```

Where `right` is the permission level: `0 = read-only`, `1 = read-write`, `2 = admin`. We use `1` per discovery decision Q3.

**Success response**: `200 OK` or `201 Created` with the share record echoed back.

**Idempotency**: If the share already exists, Vikunja may return `409 Conflict` or `200 OK` (TBD during execution — confirm v0.24.6 specific behavior on first iteration). Helper treats both as "share is in place" and continues; the post-share verification step is the source of truth.

**Failure cases**:

| Status | Cause | Helper action |
|---|---|---|
| `403` | kent's token does not have admin on the target project | Halt; should not happen because kent owns all 12 |
| `404` | Project ID does not exist | Halt; should not happen if we enumerated correctly via C-2 |
| `5xx` | Vikunja service issue | Halt; investigate |

---

## C-4 — List a project's shares

**Endpoint**: `GET /api/v1/projects/{project_id}/users`

**Used by**: `provision_felix_bot.py` (post-share verification), `validate_felix_bot.py` (sanity check)

**Authentication**: `Authorization: Bearer <token>` header

**Success response**: `200 OK` with a JSON array of `{user_id, right, created}` records.

**Helper rules**:

- After C-3 returns success for all 12 projects, helper invokes C-4 for each project and verifies that felix-bot appears in the share list with `right=1`. Any project missing the felix-bot grant is a halt condition.

---

## C-5 — Generate a long-lived API token

**Endpoint**: TBD during execution. Vikunja v0.24.6 may expose `POST /api/v1/tokens` or may require token generation via the Vikunja UI logged in as felix-bot. The live probe on 2026-05-17 did not test this path.

**Used by**: `provision_felix_bot.py` (Phase 1.3 — generate the felix-bot token)

**Authentication**: felix-bot's session (from login) OR via the existing API mechanism (TBD)

**Helper handling**:

- Try the API endpoint first. If 404 or otherwise unavailable on v0.24.6, the helper instructs the operator to:
  1. Open the Vikunja UI at `https://office2.tail0f5f56.ts.net/`
  2. Log in as `felix-bot` with the password from 1Password
  3. Navigate to Settings → API Tokens (or equivalent)
  4. Generate a new token with no expiry, scope = full, name = `felix-provisioning-2026-05-17`
  5. Paste the token into the helper via stdin or `--token-file`
- The helper validates the token structure (non-empty, looks like Vikunja's token format) before using it.

**Failure cases**:

| Cause | Helper action |
|---|---|
| Token endpoint returns 404 | Fall back to UI workflow |
| Token is empty or malformed | Exit nonzero with error |

---

## C-6 — Create a task

**Endpoint**: `PUT /api/v1/projects/{project_id}/tasks`

**Used by**: `validate_felix_bot.py` (creates the throwaway validation task)

**Authentication**: `Authorization: Bearer <felix-bot-token>` header (the new token, used side-channel during validation)

**Request body** (JSON):

```json
{
  "title": "felix-bot validation probe <ISO8601 timestamp>"
}
```

Other task fields default to Vikunja's defaults (no description, no due_date, etc.).

**Success response**: `200 OK` or `201 Created` with the new task object including `id` and `created_by` (which should equal felix-bot).

**Helper rules**:

- Helper captures `task.id` and `task.created_by.username` from the response. `created_by.username` must equal `felix-bot` — this is part of the validation contract.

---

## C-7 — Add a comment to a task

**Endpoint**: `PUT /api/v1/tasks/{task_id}/comments`

**Used by**: `validate_felix_bot.py` (writes the validation comment), and indirectly by `swap_vikunja_secrets.py`'s post-swap verification

**Authentication**: `Authorization: Bearer <felix-bot-token>` header

**Request body** (JSON):

```json
{
  "comment": "[Felix-Validation] felix-bot can write to this task — <timestamp>"
}
```

**Success response**: `200 OK` or `201 Created` with the comment object including `id` and `author` (which should equal felix-bot).

**Helper rules**:

- Helper captures `comment.id` and `comment.author.username`. `author.username` must equal `felix-bot`.

---

## C-8 — Read a task's comments

**Endpoint**: `GET /api/v1/tasks/{task_id}/comments`

**Used by**: `validate_felix_bot.py` (verifies the comment is readable + attribution is correct)

**Authentication**: `Authorization: Bearer <felix-bot-token>` header

**Success response**: `200 OK` with a JSON array of comment objects. Helper finds the previously-written comment by `id` and verifies `created_by.username == felix-bot`.

---

## C-9 — Delete a comment

**Endpoint**: `DELETE /api/v1/tasks/{task_id}/comments/{comment_id}`

**Used by**: `validate_felix_bot.py` (cleanup)

**Authentication**: `Authorization: Bearer <felix-bot-token>` header

**Success response**: `200 OK` or `204 No Content`

**Helper rules**:

- Failure on delete is logged but does NOT fail the overall validation — the comment was written and read back successfully; the cleanup is best-effort. Operator can manually delete via UI if needed.

---

## C-10 — Delete a task

**Endpoint**: `DELETE /api/v1/tasks/{task_id}`

**Used by**: `validate_felix_bot.py` (cleanup — removes the throwaway validation task entirely)

**Authentication**: `Authorization: Bearer <felix-bot-token>` header

**Success response**: `200 OK` or `204 No Content`

**Helper rules**:

- Same best-effort policy as C-9 — task deletion failure is logged but does not fail validation.

---

## C-11 — Get a single task (post-swap attribution check)

**Endpoint**: `GET /api/v1/tasks/{task_id}` and `GET /api/v1/tasks/{task_id}/comments`

**Used by**: `swap_vikunja_secrets.py` (post-swap verification — confirms a Felix agent invocation actually wrote a comment with felix-bot attribution after the secrets file is rotated)

**Authentication**: `Authorization: Bearer <felix-bot-token>` header (read via the new secrets file)

**Helper rules**:

- After the secrets file is rotated and the gateway is restarted, helper invokes a sample Felix agent (e.g., via `openclaw agent --to ...`) that writes a comment. Helper then reads back the comment via this endpoint and verifies `created_by.username == felix-bot`. If attribution is anything other than felix-bot (e.g., kent), the helper rolls back automatically.

---

## C-12 — Token revocation (post-soak cleanup)

**Endpoint**: TBD — either `DELETE /api/v1/tokens/{token_id}` if Vikunja exposes it, or via the Vikunja UI logged in as kent. Live probe did not test this path; revocation endpoint behavior on v0.24.6 will be confirmed at execution time.

**Used by**: `revoke_kent_tokens.py` (Phase 6)

**Authentication**: kent's UI session (from password manager) — kent's own API tokens are exactly what we're revoking, so we cannot use them to authenticate the revocation. The operator logs into the UI as kent and revokes via the settings panel, OR the helper uses kent's password to obtain a fresh JWT and then revokes via API.

**Helper rules**:

- If the API path is available, helper enumerates kent's tokens via `GET /api/v1/tokens` (in the kent context) and deletes each one.
- If only the UI path is available, the helper exits with explicit instructions for the operator.

---

## Notes

- All request/response shapes above were inferred from Vikunja's public docs and the 2026-05-17 live probe results. Specific endpoint behaviors (especially C-3's idempotency on duplicate share, C-5's API availability, C-12's revocation endpoint) will be confirmed empirically during implementation.
- The helpers operate against the live `office2` instance — there is no staging Vikunja to test against. The pytest mock layer is the regression-test substitute.
- All HTTP authentication is via `Authorization: Bearer <token>`. Vikunja does NOT use Basic Auth or API-key headers in v0.24.6.
- No new HTTP API is exposed by this mission — these contracts are consumer-side only.
