---
title: Calendar Helper Operations
doc_type: runbook
status: approved
owners: ["@kentonium3"]
last_updated: '2026-07-09'
updated_by: 'felix-calendar-helper-01KX4H3C (#699 — RFC #681 calendar phase)'
audience: agents_and_humans
tags: [699, 681, 679, 572]
---

# Calendar Helper Operations

Operational runbook for the **Felix calendar helper** — a Felix-owned,
deterministic Google Calendar CLI that talks to the Google Calendar API
directly (via `google-api-python-client`), replacing `gog calendar create` on
the calendar surface. Delivered by mission `felix-calendar-helper-01KX4H3C`
(#699), the first concrete phase of accepted RFC #681. Closes #679
(inbox → calendar).

- **Authoritative service record**: `services[felix-calendar-helper]` in
  [`../design/architecture/data/service-inventory.json`](<../design/architecture/data/service-inventory.json>)
  (narrative: [`service-inventory.md`](<../design/architecture/service-inventory.md>) §Felix Calendar Helper).
- **Authoritative credential record**: `felix-google-personal-calendar` in
  [`../design/architecture/data/credential-manifest.json`](<../design/architecture/data/credential-manifest.json>)
  (narrative: [`credentials-and-secrets.md`](<../design/architecture/credentials-and-secrets.md>) §8).

> **Relationship to `gog`**: the calendar surface migrated **off** `gog` to
> this helper. `gog` is **not** retired — it retains Gmail, Drive, Contacts,
> Sheets, and Docs (see [`google-workspace-ops.md`](<./google-workspace-ops.md>)),
> and the `gog` re-auth residual (#572) stays open. This helper uses a
> **separate**, per-account OAuth credential; it never touches gog's keyring.

---

## What it is

- **Source**: `scripts/google/calendar_helper.py` (CLI: `create` / `list` /
  `update` / `delete` + `--self-check`) and `scripts/google/calendar_auth.py`
  (per-account OAuth load / auto-refresh / persist).
- **Invocation model**: **on-demand only** — no long-running service, no
  systemd unit, no cron. It is invoked by:
  - `felix-admin-calendar` (the reshaped **judgment-only** agent) via `exec`;
  - `scripts/inbox/route_calendar_event.py --create` (inline from
    `felix-admin-capture`, no agent-to-agent hop — this is what closes #679).
- **Multi-account**: the default account is `personal`
  (`kentgale@gmail.com`). Adding a second account (e.g. `intentional.biz`)
  is credential-only — create its directory, drop its credentials, pass its
  account name. **No helper code change.**

---

## Venv location and invocation

office2's system `python3` cannot import the Google client libraries and has no
`pip`, so the helper runs under a **dedicated uv-provisioned venv**:

```
/data/services/openclaw/felix-calendar/venv
```

It holds pinned `google-api-python-client`, `google-auth`, and
`google-auth-oauthlib`. These deps live in the venv **only** — they are **not**
in the repo `requirements.txt`, so the pip-packages security baseline is
untouched.

Always invoke in **module form** from the checkout root (office2 is
python3-only; bare `python` exits 127 — #682):

```
cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.calendar_helper <subcommand> [options]
```

Subcommands take a JSON `--payload-file` (the `create_calendar_event`
envelope) and support `--account <name>` (default `personal`) and `--json`.

---

## Per-account credentials

Each account has its own OAuth store, independent of gog:

```
~/.config/felix/google/<account>/client_secret.json    # Desktop OAuth client (GCP project felix-personal)
~/.config/felix/google/<account>/token.json            # authorized-user token incl. refresh_token
```

- File mode **0600**, directory mode **0700**.
- On office2 the base is `/home/claude/.config/felix/google/`.
- The base directory is overridable via the `FELIX_GOOGLE_DIR` environment
  variable (used for test isolation only).
- Scope: `https://www.googleapis.com/auth/calendar.events` — sufficient for
  event CRUD and the bounded `--self-check`.
- The token is **durable** (RFC #681): the personal `@gmail` account under an
  "In production" OAuth app yields a non-expiring authorization. (The original
  weekly re-auth pain was the External+Testing 7-day expiry, #572; that no
  longer applies here — and, since the gog OAuth app was also published, it no
  longer applies to the gog credential either, see #731.)

**Credentials are never committed.** They are minted on the Mac and staged to
office2 out-of-band (see the deploy runbook / mission quickstart). The deploy
manifest only *verifies presence* — it does not copy secrets.

---

## Self-check

Verify the account can authenticate and reach the API without mutating
anything:

```
cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.calendar_helper --self-check --account personal
```

`--self-check` loads the credential, refreshes the token in place, and performs
a bounded `events().list(primary, maxResults=1)`. It is the post-flight gate
the deploy manifest runs, and the first thing to run when diagnosing a problem.

---

## Re-mint on scope / auth failure

office2 **never** runs interactive OAuth consent. If the helper exits `3`
(auth failure — expired/revoked token, missing `token.json`, or an
`invalid_grant`/refresh error), re-mint on the **Mac**:

1. On the Mac, run the interactive consent flow for the affected account with
   the `calendar.events` scope, producing a fresh `token.json`.
2. Copy the new `token.json` to office2 at the same per-account path
   (`~/.config/felix/google/<account>/token.json`), mode **0600**.
3. Re-run `--self-check` to confirm.

A **scope escalation** (e.g. a future calendar-list need) requires re-minting
Mac-side with the broader scope, then re-staging.

Adding a **new account**: create `~/.config/felix/google/<name>/`, drop its
`client_secret.json` + `token.json` (0600 / dir 0700), and pass
`--account <name>`. No code change.

---

## Exit-code troubleshooting

| Exit | Meaning | Operator action |
|------|---------|-----------------|
| `0` | Success | None. On `create`, the event id + `htmlLink` are returned; a keyed inbox create that matched an existing event returns it (`idempotent=true`) instead of duplicating. |
| `1` | Operational / API error (transient network, Google API 5xx, rate limit, timeout) | Retry. If it persists, check connectivity and the Google Calendar API status. NFR-001: a single op should return within ~10 s or surface a timeout. |
| `2` | Usage / bad arguments (malformed payload, invalid account name, missing required field) | Fix the invocation. Account names must match `^[a-z0-9][a-z0-9_-]*$` (validated to prevent path traversal). |
| `3` | **Auth failure — fail-safe** (no calendar mutation performed) | **Re-mint on the Mac** (see above). The helper emits `ERROR: auth_failed …` and `SUMMARY: … status=auth_failed`. The agent must surface this verbatim and **never** report a created event or fall back to gog (#683). |

**Fail-safe guarantee (FR-006)**: on any auth failure the helper performs no
calendar mutation and no fallback action. A failed auth can never be misread as
a completed action.

**Attendees**: invitations are suppressed by default (`sendUpdates=none`); an
inbox-created event never silently emails external people.

---

## Related

- [`google-workspace-ops.md`](<./google-workspace-ops.md>) — the `gog` CLI
  (Gmail/Drive/Contacts/Sheets/Docs; calendar surface migrated here).
- [`openclaw-agent-setup.md`](<./openclaw-agent-setup.md>) — required reading
  before deploying/modifying the `felix-admin-calendar` judgment agent.
- [`deploy/discipline.md`](<./deploy/discipline.md>) — manifest-driven deploy
  pattern used to provision the venv and verify creds.
- RFC #681 (accepted) — Felix-owned direct Google Workspace APIs.
