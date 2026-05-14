---
title: Google Workspace Operations
doc_type: runbook
status: approved
owners: ["@kentonium3"]
last_updated: '2026-05-13'
updated_by: '#100-google-workspace-foundation'
audience: agents_and_humans
---

# Google Workspace Operations

This runbook covers the operator procedure for setting up, verifying, and
expanding Google Workspace integration on office2. The integration is built
on the [`gog`](https://gogcli.sh) CLI (installed via Linuxbrew tap
`steipete/tap/gogcli`), which provides a single command-line surface across
Gmail, Calendar, Drive, Contacts (People API), Sheets, and Docs.

See [ADR-0001](<../design/architecture/adr/0001-google-workspace-via-gog.md>)
for the decision rationale.

---

## 1. Overview

**What `gog` is:** an officially-supported Google Workspace CLI that wraps the
underlying REST APIs (Gmail, Calendar, Drive, People, Sheets, Docs) behind a
single subcommand-style executable. It manages OAuth credentials and refresh
tokens internally (via a configurable keyring backend), so Felix agents and
operators do not have to handle token storage or refresh logic themselves.

**Services it covers:**

| API | Subcommand surface |
|-----|--------------------|
| Gmail | `gog gmail search / send / drafts / messages` |
| Calendar | `gog calendar colors / events / create / update` |
| Drive | `gog drive search` |
| People (Contacts) | `gog contacts list` |
| Sheets | `gog sheets get / update / append / clear / metadata` |
| Docs | `gog docs cat / export` |

**Who runs it:** the `claude` user on office2 (the Felix agent runtime user).
Refresh tokens live in claude's home directory under
`/home/claude/.config/gogcli/credentials.json`, encrypted via gog's file
keyring backend (see Pitfall 2).

**Who consumes it:** any Felix agent that needs Google Workspace data —
beginning with the user-story missions queued downstream of issue #100. The
integration is centralized: agents shell out to `gog`, they do not embed
OAuth clients of their own.

**OS/version baseline:** validated against Ubuntu 24.04 LTS on office2 with
Linuxbrew at `/home/linuxbrew/.linuxbrew/bin/gog`, with all six API surfaces
authenticated end-to-end on 2026-05-13.

---

## 2. One-Time Setup Procedure

Run the following steps in order. The runbook is self-contained — every step
is the exact command (or console action) to execute. The procedure assumes
office2 is reachable via `ssh office2-claude` and `ssh office2-kgale`.

### 2.1 Install Linuxbrew (as kgale, with sudo)

Linuxbrew (Homebrew on Linux) is the install path for `gog`. Run these three
commands as the `kgale` user via `ssh office2-kgale`:

```bash
sudo apt-get update && sudo apt-get install -y build-essential procps curl file git
```

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

```bash
echo 'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"' >> ~/.bashrc && source ~/.bashrc
```

Verify with `which brew` — should print `/home/linuxbrew/.linuxbrew/bin/brew`.

### 2.2 Install `gog` (as kgale)

Still as `kgale`:

```bash
brew install steipete/tap/gogcli
```

Verify with `which gog` — should print `/home/linuxbrew/.linuxbrew/bin/gog`.

### 2.3 Persist brew on the claude PATH (as claude)

`gog` is a system-wide binary, but its directory is not on claude's `PATH` by
default. Append the brew shellenv line to claude's `~/.bashrc` so future ssh
sessions can find `gog`. See Pitfall 3 below for the failure this avoids.

Via `ssh office2-claude`:

```bash
echo 'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"' >> ~/.bashrc && source ~/.bashrc
```

Verify with `which gog` — should print `/home/linuxbrew/.linuxbrew/bin/gog`.

### 2.4 Set up the Google Cloud Console project

In the Google Cloud Console (https://console.cloud.google.com) under the
target Google account:

1. **Create project**: pick a name (the personal account uses
   `felix-openclaw-gog`). Note the auto-assigned numeric project ID; you
   will see it in error messages.
2. **Enable APIs**: navigate to **APIs & Services → Library**. Enable each
   of the following. **Important**: search using the full prefix
   `"Google <name>"`, not just `<name>`. See Pitfall 1 below for the trap
   that the bare term "Calendar" exposes you to.
   - Gmail API
   - Google Calendar API (**not** "Calendar MCP API" — see Pitfall 1)
   - Google Drive API
   - People API (this is the Contacts API; named "People API")
   - Google Sheets API
   - Google Docs API
3. **OAuth consent screen**: configure under **APIs & Services → OAuth
   consent screen**. Use type **External**. Add the Google account you
   intend to authorize as a Test user (under "Test users" → Add users).
4. **Credentials**: navigate to **APIs & Services → Credentials → Create
   Credentials → OAuth Client ID**. Application type: **Desktop app**.
   Name it (the personal account uses `felix-openclaw-gog`). Download the
   JSON — typically named `client_secret_<long-string>.apps.googleusercontent.com.json`.

### 2.5 Copy `client_secret.json` to office2

From the Mac:

```bash
scp /Users/kentgale/Downloads/client_secret_*.json office2-claude:/data/services/openclaw/secrets/google-workspace-client.json
```

```bash
ssh office2-claude 'chmod 600 /data/services/openclaw/secrets/google-workspace-client.json'
```

### 2.6 Set up the gog keyring file backend (headless workaround)

Headless Ubuntu has no D-Bus SecretService daemon, which gog tries to use
by default. The file backend stores the refresh token in an encrypted file
protected by a passphrase. See Pitfall 2 for the failure this avoids.

As claude on office2:

```bash
openssl rand -base64 32 > /data/services/openclaw/secrets/gog-keyring-password && chmod 600 /data/services/openclaw/secrets/gog-keyring-password
```

Append the two env-var exports to claude's `~/.bashrc` so they are present
in every new ssh session:

```bash
cat >> ~/.bashrc <<'EOF'
export GOG_KEYRING_BACKEND=file
export GOG_KEYRING_PASSWORD="$(cat /data/services/openclaw/secrets/gog-keyring-password)"
EOF
source ~/.bashrc
```

Verify in a fresh ssh session: `echo "$GOG_KEYRING_BACKEND"` should print
`file`, and `echo "$GOG_KEYRING_PASSWORD" | wc -c` should print a non-zero
length (the actual value is the base64 random string).

### 2.7 Ingest the OAuth client credentials

As claude on office2:

```bash
gog auth credentials /data/services/openclaw/secrets/google-workspace-client.json
```

This loads the client_id / client_secret into gog's keyring. It does **not**
authorize any account yet — that happens in the next step.

### 2.8 Run the OAuth two-step `--remote` flow

The `--remote` mode is required because office2 is headless. The OAuth
consent screen renders in the operator's Mac browser, and the resulting
redirect URL is fed back to office2 in step 2.

**Step 1** — start the OAuth flow on office2:

```bash
gog auth add kentgale@gmail.com --services gmail,calendar,drive,contacts,docs,sheets --remote
```

This prints an authorization URL. **Open the URL on the Mac browser**, then:

1. Sign in with the target Google account.
2. The "Google hasn't verified this app" warning appears. Click **Advanced**
   → **Continue (unsafe)**.
3. The scope-consent screen appears. **Select all six checkboxes** (Gmail,
   Calendar, Drive, Contacts, Sheets, Docs). Click **Continue**.
4. The browser redirects to `http://localhost:<port>/?state=...&code=...&scope=...`
   and shows a "site can't be reached" page. **That is expected** — the
   redirect target is just a URL; no local server is running.

**Copy the full URL** from the browser address bar.

**Step 2** — pass the redirect URL back to office2. Use `read -r` to avoid
shell paste-mangling (`?`, `&`, and `=` chars in URLs can otherwise be
clobbered by history expansion or globbing):

```bash
read -r REDIRECT_URL
# Paste the full http://localhost:... URL here and press Enter
```

Then:

```bash
gog auth add kentgale@gmail.com --remote --step 2 --auth-url "$REDIRECT_URL" --services gmail,calendar,drive,contacts,docs,sheets
```

This exchanges the code for a refresh token and stores it in gog's
encrypted keyring at `/home/claude/.config/gogcli/credentials.json`.

### 2.9 Verify registration

As claude:

```bash
gog auth list
```

The expected output shows the registered account with all six scopes
present. If a scope is missing, re-run `gog auth add` for that account with
the full `--services` flag — gog will refresh consent for the missing
scopes.

### 2.10 Smoke-test live APIs

Run a one-liner from each surface to confirm end-to-end auth works:

```bash
gog calendar colors
```

```bash
gog gmail search 'newer_than:1d' --max 1
```

```bash
gog drive search "x" --max 1
```

```bash
gog contacts list --max 1
```

Each command should print actual data (or, for empty results, an empty
result set — but not an auth or API error). If any of these prints a 403
`accessNotConfigured` error, the relevant API in step 2.4 was not enabled
or has not finished propagating — see Pitfall 1.

Sheets and Docs do not have parameter-free probe commands; they are
exercised transitively (the refresh token covers all six scopes) and have
been validated end-to-end on 2026-05-13 via shared refresh-token reuse.

---

## 3. Common Pitfalls

These are load-bearing — each was discovered live during the 2026-05-13
setup. Each section captures the symptom (the exact error or behavior an
operator will see), the root cause, and the fix.

### Pitfall 1: Calendar MCP API in the API library search

**Symptom**:

```
Google API error (403 accessNotConfigured): Google Calendar API has not
been used in project <project-id> before or it is disabled.
```

The operator may have searched "Calendar" in the API library, found and
enabled "Calendar MCP API", and assumed that was the right one.

**Root cause**: searching the API library for the bare term "Calendar"
surfaces "Calendar MCP API" (a newer agent-protocol API for Model Context
Protocol, unrelated to the legacy REST surface) before "Google Calendar
API". The MCP one's name is similar enough that an operator can enable it
thinking it covers the integration.

**Fix**: open the URL the 403 error message provides (it deep-links to the
correct API's enable page). Alternatively, search the API library with the
full prefix `"Google Calendar"` — that returns the right one. After enabling,
wait ~30 seconds for propagation, then retry the failing command.

### Pitfall 2: D-Bus SecretService failure (headless keyring)

**Symptom**: after a successful OAuth consent in the browser and pasting
the redirect URL back into step 2:

```
OAuth completed, but saving the refresh token failed: store token:
keyring connection timed out after 10s while storing keyring item
(D-Bus SecretService may be unresponsive); set GOG_KEYRING_BACKEND=file
and GOG_KEYRING_PASSWORD=<password> to use encrypted file storage instead.
```

**Root cause**: D-Bus SecretService is a desktop-environment service
(`gnome-keyring` / `kwallet`). Headless Ubuntu servers do not run it. gog's
default keyring backend tries to connect to SecretService and times out.

**Fix**: see step 2.6 above — set `GOG_KEYRING_BACKEND=file` and
`GOG_KEYRING_PASSWORD=<random>` in claude's `~/.bashrc` before retrying.

**Important**: the OAuth authorization code is single-use. Once gog has
consumed it (even with a failed token-store step), it cannot be re-played.
The operator must **restart from step 2.8 step 1**: rerun
`gog auth add ... --remote` to get a fresh URL, get fresh consent in the
browser, copy the fresh redirect URL, and rerun step 2 with the fresh URL.

### Pitfall 3: Per-user brew PATH

**Symptom**: as the `claude` user (a fresh ssh session, *did not* run the
Linuxbrew installer themselves):

```
$ gog auth list
Command 'gog' not found, but there are 16 similar ones.
```

**Root cause**: the Linuxbrew installer (`install.sh` from
`raw.githubusercontent.com/Homebrew/install/HEAD/install.sh`) appends the
brew `shellenv` `eval` line to the **installing user's** `~/.bashrc` only.
If kgale ran the installer, claude's `~/.bashrc` never received the line,
so `/home/linuxbrew/.linuxbrew/bin` is not on claude's `PATH`.

**Fix**: as claude, append the same line to claude's `~/.bashrc`:

```bash
echo 'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"' >> ~/.bashrc && source ~/.bashrc
```

For the **current** ssh session only, the `source ~/.bashrc` (or equivalently,
running `eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"` once)
suffices. The bashrc append is for future sessions.

---

### Pitfall 4: OpenClaw gateway (and child agent sessions) don't inherit interactive shell env

**Symptom**: gog works correctly when invoked from an interactive ssh
session as `claude`, but Felix agents spawned by the OpenClaw gateway
(e.g., the `main:sonnet` agent answering WhatsApp messages, or any
`felix-admin-*` agent the gateway dispatches) cannot invoke `gog`. Two
distinct failure modes have been observed:

- *Agent reports "`gog` isn't installed"* — actually means `gog` is not
  found on the gateway's `PATH`. The gateway is a systemd-user service
  with a hardcoded `Environment=PATH=` in its unit file; that PATH does
  not include `/home/linuxbrew/.linuxbrew/bin`.
- *Agent reports "needs a keyring password to decrypt the stored OAuth
  token in non-interactive shells"* — actually means
  `GOG_KEYRING_PASSWORD` is not set in the gateway's environment. The
  bashrc exports from Pitfall 2's fix only affect interactive shells;
  systemd-launched processes do not source `~/.bashrc`.

Both have the same root cause and the same fix shape: the OpenClaw
gateway's systemd-user service needs the same `PATH` extension and the
same `GOG_KEYRING_*` env vars that an interactive `claude` session has,
applied in a way that systemd will honor at service-start time.

**Root cause**: systemd-launched user services inherit a deliberately
minimal `PATH` and do not source `~/.bashrc` or any user shell rc files.
The bashrc-append fix from §2.3 and the bashrc-export fix from §2.6
are interactive-shell-only.

**Fix**: register the env vars + extended `PATH` as a **systemd
drop-in override** rather than editing the parent unit. Drop-ins
survive future OpenClaw installer regenerations of the parent unit.

```bash
# 1. Create an env-file with the GOG_* secrets (claude-only readable)
PW=$(cat /data/services/openclaw/secrets/gog-keyring-password)
cat > /data/services/openclaw/secrets/openclaw-gateway.env <<EOF
GOG_KEYRING_BACKEND=file
GOG_KEYRING_PASSWORD=$PW
EOF
chmod 600 /data/services/openclaw/secrets/openclaw-gateway.env
```

```bash
# 2. Create the systemd drop-in
mkdir -p ~/.config/systemd/user/openclaw-gateway.service.d
cat > ~/.config/systemd/user/openclaw-gateway.service.d/env.conf <<'EOF'
[Service]
EnvironmentFile=/data/services/openclaw/secrets/openclaw-gateway.env
Environment=PATH=/usr/bin:/home/linuxbrew/.linuxbrew/bin:/home/claude/.local/bin:/home/claude/.npm-global/bin:/home/claude/bin:/home/claude/.volta/bin:/home/claude/.asdf/shims:/home/claude/.bun/bin:/home/claude/.nvm/current/bin:/home/claude/.fnm/current/bin:/home/claude/.local/share/pnpm:/usr/local/bin:/bin
EOF
```

```bash
# 3. Reload + restart
systemctl --user daemon-reload && systemctl --user restart openclaw-gateway
```

**Verify**: inspect the live gateway process's environment to confirm
all three vars are set (the `Environment=` show command only reports
directly-declared vars, not `EnvironmentFile` contents — go straight
to `/proc`):

```bash
PID=$(systemctl --user show openclaw-gateway -p MainPID --value)
tr '\0' '\n' < /proc/$PID/environ | grep -E '^GOG_|^PATH=' | \
  sed 's|^GOG_KEYRING_PASSWORD=.*|GOG_KEYRING_PASSWORD=<redacted>|'
```

Expect three lines: `PATH=...`, `GOG_KEYRING_BACKEND=file`,
`GOG_KEYRING_PASSWORD=<redacted>`.

**End-to-end test**: send a fresh WhatsApp message to the `main` agent
asking it to run `gog auth list` and `gog calendar colors`. Successful
output (account row + 11 event colors + 24 calendar colors, no
"command not found" or keyring complaints) confirms the gateway is
fully wired and child agent sessions inherit the env correctly.

**Why drop-in rather than edit the parent unit**: the parent unit at
`~/.config/systemd/user/openclaw-gateway.service` is written by the
OpenClaw installer and may be regenerated on upgrade or reinstall, which
would silently drop any in-place edits. The drop-in lives at a separate
path the installer doesn't touch, so the fix survives upgrades.

---

## 4. Common Commands

These are copied from the bundled `gog` SKILL.md at
`/usr/lib/node_modules/openclaw/skills/gog/SKILL.md` on office2. Treat that
file as the upstream source of truth — re-sync periodically.

### Gmail

```bash
# Search threads
gog gmail search 'newer_than:7d' --max 10

# Search individual messages (ignores threading)
gog gmail messages search "in:inbox from:ryanair.com" --max 20 --account you@example.com

# Send (plain text)
gog gmail send --to a@b.com --subject "Hi" --body "Hello"

# Send (multi-line via file)
gog gmail send --to a@b.com --subject "Hi" --body-file ./message.txt

# Send (from stdin)
gog gmail send --to a@b.com --subject "Hi" --body-file -

# Send (HTML body)
gog gmail send --to a@b.com --subject "Hi" --body-html "<p>Hello</p>"

# Create draft
gog gmail drafts create --to a@b.com --subject "Hi" --body-file ./message.txt

# Send an existing draft
gog gmail drafts send <draftId>

# Reply
gog gmail send --to a@b.com --subject "Re: Hi" --body "Reply" --reply-to-message-id <msgId>
```

### Calendar

```bash
# List events in a calendar within an ISO time range
gog calendar events <calendarId> --from <iso> --to <iso>

# Create event
gog calendar create <calendarId> --summary "Title" --from <iso> --to <iso>

# Create with color
gog calendar create <calendarId> --summary "Title" --from <iso> --to <iso> --event-color 7

# Update event
gog calendar update <calendarId> <eventId> --summary "New Title" --event-color 4

# List the 11 calendar event color IDs
gog calendar colors
```

Calendar event color reference (the same 11 IDs Google's web UI uses):

| ID | Hex     | ID | Hex     |
|----|---------|----|---------|
| 1  | #a4bdfc | 7  | #46d6db |
| 2  | #7ae7bf | 8  | #e1e1e1 |
| 3  | #dbadff | 9  | #5484ed |
| 4  | #ff887c | 10 | #51b749 |
| 5  | #fbd75b | 11 | #dc2127 |
| 6  | #ffb878 |    |         |

### Drive

```bash
gog drive search "query" --max 10
```

### Contacts

```bash
gog contacts list --max 20
```

### Sheets

```bash
# Read a range
gog sheets get <sheetId> "Tab!A1:D10" --json

# Overwrite a range
gog sheets update <sheetId> "Tab!A1:B2" --values-json '[["A","B"],["1","2"]]' --input USER_ENTERED

# Append rows
gog sheets append <sheetId> "Tab!A:C" --values-json '[["x","y","z"]]' --insert INSERT_ROWS

# Clear a range
gog sheets clear <sheetId> "Tab!A2:Z"

# Sheet metadata
gog sheets metadata <sheetId> --json
```

### Docs

```bash
# Export to a file
gog docs export <docId> --format txt --out /tmp/doc.txt

# Print to stdout
gog docs cat <docId>
```

In-place Docs edits require a Docs API client — not currently exposed by gog.

### Notes (from upstream SKILL.md)

- Set `GOG_ACCOUNT=you@gmail.com` to avoid repeating `--account` on every call.
- For scripting, prefer `--json` plus `--no-input`.
- `--body` does not unescape `\n`. For inline newlines, use `--body-file -`
  with a heredoc.
- `gog gmail search` returns one row per thread; use
  `gog gmail messages search` when each individual email must be returned.
- Confirm before sending mail or creating events — gog does not prompt for
  confirmation.

---

## 5. Adding a Second Google Account (Intentional business)

The current setup authorizes the personal Google account
(`kentgale@gmail.com`). The Intentional LLC business account will be set
up the same way, separately, so each has its own OAuth client.

Procedure (when the Intentional Workspace is ready):

1. In the Google Cloud Console under the **Intentional** account
   (`kent@intentional.biz`), repeat step 2.4 above. Create a fresh project
   (suggested name: `felix-openclaw-gog-intentional`). Enable the same six
   APIs. Create the OAuth consent screen and a fresh Desktop OAuth Client ID.
2. Download `client_secret_<long>.apps.googleusercontent.com.json` for the
   Intentional client. scp to office2 with a **distinct** filename:

   ```bash
   scp /Users/kentgale/Downloads/client_secret_*.json \
     office2-claude:/data/services/openclaw/secrets/google-workspace-client-intentional.json
   ssh office2-claude 'chmod 600 /data/services/openclaw/secrets/google-workspace-client-intentional.json'
   ```

3. Ingest under a distinct client alias (verify the exact flag spelling at
   the time with `gog auth credentials --help` — gog may name this
   `--client` or `--alias`):

   ```bash
   gog auth credentials --client intentional /data/services/openclaw/secrets/google-workspace-client-intentional.json
   ```

4. Run the `--remote` two-step flow against the Intentional account, with
   the `--client intentional` selector:

   ```bash
   gog auth add kent@intentional.biz --client intentional --services gmail,calendar,drive,contacts,docs,sheets --remote
   # ... open URL, consent, copy redirect URL ...
   read -r REDIRECT_URL
   gog auth add kent@intentional.biz --client intentional --step 2 --auth-url "$REDIRECT_URL" --services gmail,calendar,drive,contacts,docs,sheets --remote
   ```

5. Verify with `gog auth list` — should show both `kentgale@gmail.com`
   (default client) and `kent@intentional.biz` (intentional client).

6. Per-command account selection: use `-a <email>` or
   `--client <alias>` on subsequent invocations to pick the right account.

After the second account is registered, update `identity-model.md` →
**Intentional business account** section with the real account name,
Cloud project, and client alias.

---

## 6. Health Checks and Troubleshooting

### Routine health checks

```bash
# List registered accounts and scopes
gog auth list

# Self-check (validates refresh tokens, prints diagnostic info)
gog auth doctor

# Per-account status
gog auth status

# Confirm OpenClaw can see the gog skill
openclaw skills info gog
```

### Common issues

**Refresh token revoked**: if `gog auth doctor` reports a revoked token,
re-run the OAuth flow for the affected account starting at step 2.8 step 1
(no need to re-ingest the client credentials — they are still valid).
Common revocation triggers: Google account password change, 6+ months of
inactivity, manual revocation at https://myaccount.google.com/permissions,
or a Google security review.

**Scope expansion**: if a future use case needs a scope not in the
original `--services` list (e.g., adding `tasks` later), re-run `gog auth
add <email> --services <new-comma-separated-list> --remote` — gog will
re-prompt for consent for the newly-added scopes.

**Stale refresh token after env-var rotation**: if `GOG_KEYRING_PASSWORD`
is rotated, the encrypted credential file becomes unreadable. Re-run the
full step 2.8 OAuth flow to re-mint the refresh token under the new
passphrase. (Operator decision: only rotate the passphrase if there is a
suspected compromise — the passphrase is on a Tailscale-gated server and
the file mode is 0600.)

**`gog: command not found` after a fresh ssh login**: see Pitfall 3.

---

## 7. References

- [ADR-0001 — Google Workspace integration via `gog`](<../design/architecture/adr/0001-google-workspace-via-gog.md>) (approved 2026-05-13)
- gog homepage: https://gogcli.sh
- gog bundled SKILL.md (on office2): `/usr/lib/node_modules/openclaw/skills/gog/SKILL.md`
- Linuxbrew (Homebrew on Linux): https://docs.brew.sh/Homebrew-on-Linux
- Google Cloud Console — APIs & Services: https://console.cloud.google.com/apis
