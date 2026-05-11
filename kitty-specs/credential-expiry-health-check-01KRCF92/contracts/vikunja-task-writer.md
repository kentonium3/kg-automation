# Contract: Vikunja Task Writer

**Surface**: file Vikunja tasks for cadence-based alerts (no task for activity-staleness alerts; see `github-issue-writer.md`).

## Identity

Vikunja API authentication uses the existing `vikunja-api` token at `/data/services/openclaw/secrets/vikunja-api` on office2 (per C-006). The token is read at runtime; never logged.

## Inputs

- `credential: Credential`
- `boundary: datetime.date`
- `github_issue_number: int` — for the cross-reference link

## Outputs

- `task_id: int` on success
- raises `VikunjaWriteError` on failure (caller logs and continues; the orphaned task case from spec §6 is recoverable manually)

## Ordering with GitHub issue creation

The cycle creates the Vikunja task **first**, then files the GitHub issue carrying the task ID in its body. Rationale:

- The GitHub issue body's "Vikunja task: #N" reference needs the task ID, which only exists after Vikunja task creation.
- If task creation fails: the cycle logs the failure and skips the GitHub issue for this credential (we'd rather have no alert than a half-formed one). On the next cycle, dedup will not see an open GitHub issue and will retry.
- If task creation succeeds but issue creation fails: the cycle logs the failure. Result is an orphaned Vikunja task. On the next cycle, dedup (which checks GitHub state only) does not see an open issue, so the cycle will create *another* Vikunja task and (likely) succeed on the second GitHub issue creation. Result: one orphaned task + one paired task+issue. Cleanup is manual; failure surface is bounded. This is captured in spec §6 ("if not avoidable, log the inconsistency clearly").

## Task fields

| Field | Value |
|---|---|
| `title` | `Rotate credential: <credential.name>` |
| `description` | (see template below) |
| `due_date` | `(boundary - timedelta(days=7))` rendered as ISO-8601 (timezone: end-of-day in `America/New_York`, matching Vikunja's date handling per #112) |
| `project_id` | Inbox project ID (looked up at runtime; default per D-001) |
| `priority` | unset (default Vikunja priority) |
| `labels` | none |
| `assignee` | unset |

## Description template

```
Rotate this credential, then close the linked GitHub issue and mark this task done.

GitHub issue: <github_issue_url>

Cadence boundary (the actual deadline): <boundary.isoformat()>
This task is due one week earlier so the escalation engine pings before the boundary.

Stored at: <credential.storage>
Rotation procedure (see GitHub issue body for full text): see expiry_notes in credential-manifest.json.
```

`<github_issue_url>` is `https://github.com/kentonium3/kg-automation/issues/<github_issue_number>`.

## API call

`POST` to the Vikunja `/api/v1/projects/<inbox_id>/tasks` endpoint with the task payload. Standard Vikunja API; see the existing `scripts/vikunja/setup_vikunja.py` and the `vikunja-api` OpenClaw skill for prior art on call shape.

## Dedup check

The Vikunja writer does **not** independently dedup. Dedup happens at the GitHub-issue layer (per R-005); if the GitHub layer says "no open issue, file new alert", this writer creates a fresh task.

## Inbox project lookup

The Inbox project ID can be cached in the check process per cycle. Look up via `GET /api/v1/projects` and find the project whose `title == "Inbox"`. If multiple match (shouldn't happen but defensive), use the one with the smallest ID.

## Test coverage

- Unit: title and description templating against fixture inputs.
- Unit: due_date arithmetic — given boundary `2027-05-11`, expect due_date `2027-05-04`.
- Contract: stub Vikunja API; verify request payload shape.
- Integration smoke (canary, shared with `github-issue-writer.md`): a single end-to-end cycle against a fixture manifest demonstrates the cross-ref between issue body and task description renders correctly.
