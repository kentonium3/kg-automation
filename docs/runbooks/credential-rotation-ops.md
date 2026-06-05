---
title: Credential Rotation Operations
doc_type: runbook
status: approved
audience: humans
last_updated: '2026-06-05'
---

# Credential Rotation Operations

Operator-facing procedural runbook for manually rotating credentials tracked
in [`credential-manifest.json`](<../design/architecture/data/credential-manifest.json>).
Covers pre-flight, per-credential rotation, per-consumer verification, and
the manifest-update obligations that keep `credential-health-check.service`'s
30-day warning boundary accurate.

This runbook replaces the per-credential `expiry_notes` field as the
canonical operator guide. The manifest's `expiry_notes` may be slimmed in a
follow-up PR to point at the relevant section here.

**Scope**: 8 credentials with a manual rotation path
(`kg-felix-bot-pat`, `kg-felix-bot-project-sync-pat`, `anthropic`,
`vikunja-api`, `restic-password`, `gog-keyring-password`,
`google-workspace-client`, `kentonium3-gh-oauth`).

**Out of scope** (no manual rotation procedure):
`vikunja-admin` (session-only),
`tailscale-auth` (system-managed),
`whatsapp-session` (managed by OpenClaw/Baileys — re-pair via
[`openclaw-ops.md`](<./openclaw-ops.md>)),
`personal-google` (deprecated 2026-05-13),
`gog-credentials-keyring` (managed by `gog` itself; rebuilt on
`gog-keyring-password` rotation),
`openclaw-gateway-env` (derived from `gog-keyring-password`; regenerated
as a step within that rotation).

**Companion docs**:
- [`felix-bot-vikunja-provisioning.md`](<./felix-bot-vikunja-provisioning.md>) — one-time
  felix-bot provisioning; cross-referenced by the `vikunja-api` rotation
- [`google-workspace-ops.md`](<./google-workspace-ops.md>) — `gog` CLI setup;
  cross-referenced by the `gog-keyring-password` and `google-workspace-client`
  rotations (see Pitfall 4 there for systemd env-file context)

---

## How to use this runbook

1. **Identify the credential** to rotate (issue title, watchdog alert, or
   planned rotation).
2. **Read the pre-flight section** below — applies to every rotation.
3. **Jump to the credential's section** and execute top-to-bottom. Each
   section has GO criteria and NO-GO triggers; do not improvise around them.
4. **Complete the manifest update** in the final section. Skipping the
   manifest update silently breaks the watchdog's 30-day boundary math.

Procedures assume a working SSH alias to office2
(`ssh office2-claude` per [`CLAUDE.md`](<../../CLAUDE.md>)). The
`claude` user does not have sudo; any sudo-required step is flagged and
must be run by Kent via `ssh office2-kgale`.

---

## Pre-flight (applies to every rotation)

**Estimated duration**: 5 minutes.

### Step 1 — Identify consumers and storage from the manifest

Read the credential's entry in
[`credential-manifest.json`](<../design/architecture/data/credential-manifest.json>):

- `used_by` — every consumer that reads this credential. Each consumer
  must be verified after rotation.
- `storage` — every file/store that holds this credential. Each path
  must be updated atomically (no partial cutover).
- `expiry_policy` and `expires_at` — informs whether this is a planned
  rotation (pre-expiry) or a reactive rotation (leak/compromise response).

A credential that lists three consumers and two storage paths requires six
verification checks (3 × 2). Any consumer that reads from a stale storage
path will start failing at the next tick.

### Step 2 — Determine risk tier and snapshot requirement

Cross-reference
[`change-risk-taxonomy.json`](<../design/architecture/data/change-risk-taxonomy.json>):

- **Tier 2** (application/state changes — e.g. rotating a credential
  that's mid-flight in a long-running service) — Restic snapshot within the
  last 24 hours is required. See
  [`pre-flight-checklist.md`](<./governance/pre-flight-checklist.md>).
- **Tier 3** (logic/workflow — most credential rotations) — proceed with
  dry-run or sandbox validation; no snapshot required.

If a Tier 2 snapshot is needed and the most recent is >24 hours old, trigger
one first:

```bash
ssh office2-claude '/data/services/backup/scripts/backup.sh'
```

### Step 3 — Confirm operator availability and tooling

- 1Password reachable (most rotations require generating and pasting a new
  secret).
- 30+ minutes of focused availability (multi-consumer rotations can take 20+
  minutes; see `anthropic` and `gog-keyring-password` below).
- Verify the credential-health-check is currently healthy (no false-positive
  alert in flight):

```bash
ssh office2-claude 'systemctl --user is-active credential-health-check.timer'
```

### Pre-flight GO criteria

- [ ] Consumers from manifest `used_by` enumerated
- [ ] Storage paths from manifest `storage` enumerated
- [ ] Risk tier identified; if Tier 2, Restic snapshot is recent
- [ ] 1Password reachable
- [ ] Operator has focused availability for the rotation's expected duration

---

## `kg-felix-bot-pat` (GitHub PAT, repo+org+workflow scopes)

**Host**: office2.
**Consumers** (3): `felix-doc-auditor`, `felix-core-digest-signals`,
future Felix agents operating as `kg-felix-bot`.
**Storage** (1): `/home/claude/.config/gh/hosts.yml`.
**Risk tier**: 3 (logic/workflow).
**Expected duration**: 5-10 minutes.

### Steps

1. **Generate new PAT** at github.com (logged in as `kg-felix-bot`):
   - Settings → Developer settings → Personal access tokens → Tokens (classic)
   - Scopes: `repo`, `read:org`, `workflow`
   - Expiry: 1 year (per the 2026-06-03 incident-driven policy — see manifest
     `expiry_notes`)
   - Copy the token immediately; you cannot view it again

2. **On office2, rotate the gh CLI auth**:

   ```bash
   ssh office2-claude
   gh auth logout --hostname github.com
   gh auth login --hostname github.com --git-protocol https
   ```

   Paste the new token when prompted.

3. **Revoke the old token** in the github.com settings UI (same page as
   step 1). Do not leave the old token live after the new one is in place.

### Per-consumer verification

```bash
# Verify gh CLI is authenticated as kg-felix-bot
ssh office2-claude 'gh auth status --hostname github.com'
# Expected: "Logged in to github.com account kg-felix-bot"

# Verify felix-doc-auditor's next tick succeeds
# (driver reads gh credentials at tick start)
ssh office2-claude 'cat /data/services/felix-doc-auditor/state/last-tick.json'
# Wait for next hourly tick (or trigger manually if available);
# verify "status": "ok" and no auth errors

# Verify felix-core-digest-signals can file issues
# (the deterministic signal filer in tick.py uses the same gh CLI identity)
ssh office2-claude 'cat /data/services/felix-core-digest/state/last-tick.json 2>/dev/null || echo "no state file yet"'
```

### GO criteria

- [ ] `gh auth status` shows `kg-felix-bot` active
- [ ] Old token revoked at github.com
- [ ] Next `felix-doc-auditor` tick's `last-tick.json` shows `"status": "ok"`
- [ ] No `401`/`403` in `journalctl --user -u felix-doc-auditor.service --since '1 hour ago'`
- [ ] Manifest updated per [final section](#manifest-update-obligations)

### NO-GO triggers

- `gh auth login` rejects the token → re-check scopes match (`repo, read:org,
  workflow`); the felix-doc-auditor will refuse a token missing `repo` scope.
- `last-tick.json` shows `401`/`403` after rotation → confirm the token has
  not been accidentally revoked; re-generate and re-rotate.
- Old token still works (revoke didn't take effect) → re-revoke via the UI;
  GitHub occasionally takes a moment to propagate.

---

## `kg-felix-bot-project-sync-pat` (GitHub PAT, project scope only)

**Host**: GitHub Actions.
**Consumers** (1): `spec-lifecycle.yml` `priority-field-sync` job.
**Storage** (1): GitHub Actions secret `PROJECT_SYNC_PAT` on
`kentonium3/kg-automation`.
**Risk tier**: 3 (logic/workflow).
**Expected duration**: 5 minutes.

### Steps

1. **Generate new PAT** at github.com (logged in as `kg-felix-bot`):
   - Settings → Developer settings → Personal access tokens → Tokens (classic)
   - Scopes: `project` only (narrow blast radius per the credential-hygiene
     pattern that triggered the 2026-06-03 incident response — see
     [memory `feedback_narrow_pat_per_workflow`])
   - Expiry: 1 year (matches the `kg-felix-bot-pat` cadence)

2. **Update the GitHub Actions secret**:
   - Navigate to `kentonium3/kg-automation` → Settings → Secrets and variables → Actions
   - Edit `PROJECT_SYNC_PAT` → paste the new token → save

3. **Revoke the old token** in the github.com settings UI.

### Per-consumer verification

Trigger the workflow to confirm the new secret works:

```bash
# Re-apply a P1/P2/P3 label on any open issue to force the priority-field-sync
# job to fire (idempotent — same label, same priority, but the job runs).
# Or wait for the next natural firing (any P*-* label change).
gh run list --repo kentonium3/kg-automation --workflow spec-lifecycle.yml --limit 1
gh run view <run-id> --repo kentonium3/kg-automation --log | grep -E "priority-field-sync|❌|error"
```

### GO criteria

- [ ] New PAT created with `project` scope only
- [ ] `PROJECT_SYNC_PAT` Actions secret updated
- [ ] Old token revoked at github.com
- [ ] Next `priority-field-sync` job run completes without auth errors
- [ ] Manifest updated per [final section](#manifest-update-obligations)

### NO-GO triggers

- Job fails with `RESOURCE_NOT_ACCESSIBLE_BY_INTEGRATION` → verify
  `kg-felix-bot` is still a collaborator on the Felix Roadmap user-owned
  project. The PAT is necessary but not sufficient; collaborator access is
  the other half.
- Job fails with `Bad credentials` → secret value did not save; re-paste.

---

## `anthropic` (API key — three consumers in lock-step)

**Host**: office2.
**Consumers** (3): `openclaw-gateway`, `felix-doc-auditor-driver`,
`felix-heartbeat-gate` (#490).
**Storage** (2):
- `/home/claude/.openclaw/agents/main/agent/auth-profiles.json` (OpenClaw
  native auth store, consumed by `openclaw-gateway`)
- `/data/services/openclaw/secrets/anthropic` (file, 0600, consumed
  directly by `felix-doc-auditor-driver` and `felix-heartbeat-gate`)
**Risk tier**: 3 (logic/workflow). Note: a partial rotation that updates
only one of the two storage paths leaves consumers reading stale values —
plan to do both atomically before the next tick.
**Expected duration**: 15-20 minutes.

### Steps

1. **Generate new API key** at `console.anthropic.com`:
   - Settings → API Keys → Create Key
   - Copy the key immediately

2. **Update the plaintext file** (consumed by `felix-doc-auditor-driver`
   and `felix-heartbeat-gate`):

   ```bash
   ssh office2-claude
   printf '%s' "<paste-new-key-here>" > /data/services/openclaw/secrets/anthropic
   chmod 600 /data/services/openclaw/secrets/anthropic
   chown claude:claude /data/services/openclaw/secrets/anthropic
   stat -c "%a %U:%G %n" /data/services/openclaw/secrets/anthropic
   ```

   Expected: `600 claude:claude /data/services/openclaw/secrets/anthropic`.

3. **Update OpenClaw's native auth store** for the `main` agent:

   ```bash
   ssh office2-claude 'openclaw auth set --provider anthropic --profile default'
   ```

   The CLI prompts for the key; paste it. This updates
   `/home/claude/.openclaw/agents/main/agent/auth-profiles.json` and is the
   path that `openclaw-gateway` reads.

4. **Restart `openclaw-gateway`** to pick up the new key in its child
   agent sessions:

   ```bash
   ssh office2-claude 'systemctl --user restart openclaw-gateway.service'
   ssh office2-claude 'systemctl --user is-active openclaw-gateway.service'
   ```

5. **Revoke the old key** at `console.anthropic.com` once verification
   (below) confirms the new key is live across all three consumers.

### Per-consumer verification

```bash
# 1. openclaw-gateway: verify the gateway is healthy and not throwing auth errors
ssh office2-claude 'journalctl --user -u openclaw-gateway.service --since "5 minutes ago" | grep -ciE "401|invalid_api_key|authentication"'
# Expected: 0

# 2. felix-doc-auditor-driver: wait for the next hourly tick, then verify
ssh office2-claude 'cat /data/services/felix-doc-auditor/state/last-tick.json | python3 -m json.tool | head -20'
# Expected: "status": "ok"; no auth_error field

# 3. felix-heartbeat-gate: wait for the next 30-minute tick, then verify
ssh office2-claude 'cat /data/services/felix-heartbeat-gate/state/last-gate-decision.json | python3 -m json.tool | head -20'
# Expected: "decision" field present; no auth fallback (ESCALATE_TO_SONNET) triggered by 401
```

### GO criteria

- [ ] Plaintext file at `/data/services/openclaw/secrets/anthropic` updated,
  mode 600, owner `claude:claude`
- [ ] OpenClaw native auth store updated via `openclaw auth set`
- [ ] `openclaw-gateway.service` restarted and `is-active`
- [ ] Zero `401`/`invalid_api_key` errors in gateway logs for the 5 minutes
  after restart
- [ ] Next `felix-doc-auditor` tick's `last-tick.json` shows `"status": "ok"`
- [ ] Next `felix-heartbeat-gate` tick's `last-gate-decision.json` shows a
  normal decision (not a 401-triggered ESCALATE_TO_SONNET fallback)
- [ ] Old key revoked at `console.anthropic.com`
- [ ] Manifest updated per [final section](#manifest-update-obligations)

### NO-GO triggers

- Only one of the two storage paths was updated → both consumer classes
  must be on the same key. If you discover the divergence post-restart,
  update the missing path and restart `openclaw-gateway` again.
- Old key revoked before new key was deployed everywhere → expect a brief
  outage on whichever consumer hadn't yet picked up the new key. The
  `felix-heartbeat-gate` fallback (ESCALATE_TO_SONNET) absorbs gate ticks
  during the gap, but `openclaw-gateway` child agents will fail outright.
- `openclaw auth set` rejects the key → confirm the key was copied without
  trailing whitespace; re-generate if necessary.

---

## `vikunja-api` (felix-bot API token)

**Host**: office2.
**Consumers** (1): `openclaw-gateway` (used by all Felix sub-agents for
Vikunja writes).
**Storage** (1): `/data/services/openclaw/secrets/vikunja-api`.
**Risk tier**: 2 (application/state — gateway holds open connections at
rotation moment).
**Expected duration**: 15 minutes.

The atomic-cutover helpers built for the one-time provisioning at
[`felix-bot-vikunja-provisioning.md`](<./felix-bot-vikunja-provisioning.md>)
also work for steady-state rotation. The Phase 3 swap procedure
(`scripts/vikunja/swap_vikunja_secrets.py`) gives you backup, rotate,
restart, verify, and auto-rollback in a single command.

### Steps

1. **Pre-flight (Tier 2)**: confirm Restic snapshot within last 24 hours
   per the [Pre-flight section above](#pre-flight-applies-to-every-rotation).

2. **Generate new token** in the Vikunja UI:
   - SSH-tunnel or Tailscale to `https://office2.tail0f5f56.ts.net/`
   - Log in as `felix-bot` (password in 1Password)
   - Settings → API tokens → Create token
   - Scope: read/write
   - Expiry: 3 years (matches the 2026-05-17 issuance pattern)
   - Copy the token

3. **Write the new token to a tmpfs path** so it never hits persistent disk
   before the swap:

   ```bash
   ssh office2-claude
   printf '%s' "<paste-new-token-here>" > /run/user/$(id -u)/felix-bot-token-rotated
   chmod 600 /run/user/$(id -u)/felix-bot-token-rotated
   ```

4. **Run the atomic swap helper**:

   ```bash
   cd /home/claude/kg-automation
   python3 scripts/vikunja/swap_vikunja_secrets.py \
       --new-token-file /run/user/$(id -u)/felix-bot-token-rotated \
       --secrets-path /data/services/openclaw/secrets/vikunja-api \
       --bak-suffix .pre-rotation-$(date +%Y%m%d).bak \
       --gateway-unit openclaw-gateway.service \
       --gateway-health-timeout 30 \
       --verify-task-id 1
   ```

   The helper backs up the old token, rotates, restarts `openclaw-gateway`,
   and runs an attribution verification probe. On any failure during
   rotate/restart/verify it auto-rolls back from the `.bak`.

5. **Revoke the old token** in the Vikunja UI (Settings → API tokens) once
   verification confirms the new one is live.

6. **Remove the `.bak`** after a brief soak (24 hours is sufficient for
   steady-state rotation; the provisioning runbook's 7-day soak was for
   the one-time identity cutover):

   ```bash
   ssh office2-claude 'rm /data/services/openclaw/secrets/vikunja-api.pre-rotation-*.bak'
   ```

### Per-consumer verification

The swap helper's `verify` phase writes a comment to task #1 (Inbox-resident
probe), reads it back, and asserts `created_by.username == felix-bot`. On
exit code 0 with `SUMMARY: phase=verify result=ok created_by=felix-bot`, the
verification is already complete.

Additional steady-state checks:

```bash
# Zero auth errors in gateway logs since the restart
ssh office2-claude 'journalctl --user -u openclaw-gateway.service --since "5 minutes ago" | grep -ciE "401|403|auth.*fail"'
# Expected: 0
```

### GO criteria

- [ ] Tier 2 Restic snapshot confirmed recent
- [ ] Swap helper exit code 0 with `SUMMARY: phase=verify result=ok created_by=felix-bot`
- [ ] `.bak` file present at expected path, mode 600
- [ ] `systemctl --user is-active openclaw-gateway.service` returns `active`
- [ ] Zero `401`/`403` errors in 5 minutes post-restart
- [ ] Old token revoked in Vikunja UI
- [ ] `.bak` removed after 24-hour soak
- [ ] Manifest updated per [final section](#manifest-update-obligations)

### NO-GO triggers

- Swap helper exits 1 with `phase=auto_rollback result=ok attribution=kent`
  → auto-rollback succeeded; production is back on the prior token. **Do
  not retry the swap.** File a follow-up bug with the helper's JSON summary
  and diagnose.
- Swap helper exits 1 with `phase=auto_rollback result=fail` → manual
  recovery required. Run the operator-driven rollback (see
  [`felix-bot-vikunja-provisioning.md`](<./felix-bot-vikunja-provisioning.md>)
  Phase 3 NO-GO section) and engage Kent immediately.
- Verification fails with attribution mismatch → most likely cause is wrong
  token in the file (e.g., kent's token pasted by accident); regenerate the
  felix-bot token and re-run from step 3.

---

## `restic-password` (Restic repository encryption passphrase)

**Host**: office2.
**Consumers** (1): `backup.sh`.
**Storage** (1): `/home/claude/.config/restic/password`.
**Risk tier**: 2 (application/state — encrypts the backup repository).
**Expected duration**: 10 minutes (plus a successful test-restore).

**WARNING**: Rotating `restic-password` requires
`restic key add` / `restic key remove` from the existing password. **Do not
overwrite the password file** without first proving the new password works
against the repository. If the file is overwritten with an incorrect
password and the old password is lost, every snapshot in the repository
becomes unrecoverable.

### Steps

1. **Generate new passphrase** (in 1Password or via `openssl rand -base64 32`).

2. **Add the new key to the Restic repository** (keeps the old key active):

   ```bash
   ssh office2-claude
   restic -r <repository-url> key add
   ```

   The `restic` CLI prompts for the current password (from
   `~/.config/restic/password`) and then the new one. After this completes,
   the repository has two valid keys.

3. **Verify the new key works** by listing snapshots with the new password:

   ```bash
   ssh office2-claude
   RESTIC_PASSWORD="<paste-new-passphrase>" restic -r <repository-url> snapshots --latest 1
   ```

   This must succeed before proceeding.

4. **Overwrite the password file with the new passphrase**:

   ```bash
   ssh office2-claude
   printf '%s' "<paste-new-passphrase>" > /home/claude/.config/restic/password
   chmod 600 /home/claude/.config/restic/password
   ```

5. **Remove the old key** from the repository once you've confirmed
   `backup.sh` uses the new file:

   ```bash
   ssh office2-claude
   restic -r <repository-url> key list
   # Identify the old key ID, then:
   restic -r <repository-url> key remove <old-key-id>
   ```

### Per-consumer verification

```bash
# Trigger a backup and verify it succeeds with the new password
ssh office2-claude '/data/services/backup/scripts/backup.sh'
# Expected: snapshot ID printed; no "wrong password" error

# Verify Restic can read the most recent snapshot
ssh office2-claude 'restic -r <repository-url> snapshots --latest 1'
```

### GO criteria

- [ ] New key added to repository via `restic key add`
- [ ] New passphrase verified by listing snapshots with `RESTIC_PASSWORD` env
- [ ] Password file overwritten with new passphrase, mode 600
- [ ] `backup.sh` test run succeeds with the new password
- [ ] Old key removed from repository
- [ ] Manifest updated per [final section](#manifest-update-obligations)

### NO-GO triggers

- `restic key add` fails → confirm the current password file matches the
  active repository key. If they don't match, the password file was already
  rotated incorrectly at some prior point; recovery requires the original
  passphrase.
- Snapshot listing with new password fails → the new key was added but you
  pasted the wrong passphrase to the verification step; re-list with the
  correct value before overwriting the file.
- Test backup fails after file overwrite → revert the file from the old
  passphrase (if you still have it) and re-investigate; do not remove the
  old key until the new path works end-to-end.

---

## `gog-keyring-password` (gog file-backend keyring passphrase)

**Host**: office2.
**Consumers** (1, with 2 effective code paths): `gog` CLI — via
`GOG_KEYRING_PASSWORD` env var, exported by both `~/.bashrc` (interactive
shell sessions) and the systemd `EnvironmentFile` at
`/data/services/openclaw/secrets/openclaw-gateway.env` (openclaw-gateway and
its child agent sessions).
**Storage** (2 — both must be updated atomically):
- `/data/services/openclaw/secrets/gog-keyring-password` (canonical source)
- `/data/services/openclaw/secrets/openclaw-gateway.env` (derived; the
  `GOG_KEYRING_PASSWORD=` line must match)
**Risk tier**: 3 (logic/workflow) — but with a heavy caveat: rotation
**requires re-running the full gog OAuth flow** because the passphrase
encrypts the refresh-token bucket at
`/home/claude/.config/gogcli/credentials.json`. Plan accordingly.
**Expected duration**: 20-30 minutes (dominated by the OAuth re-ingest).

See [`google-workspace-ops.md`](<./google-workspace-ops.md>) Pitfall 4 for
the systemd env-file context — without that file, `openclaw-gateway`'s
child agent sessions cannot decrypt the keyring.

### Steps

1. **Generate new passphrase**:

   ```bash
   ssh office2-claude
   openssl rand -base64 32
   ```

   Save in 1Password as `gog-keyring-password (office2)`.

2. **Wipe the existing credentials bucket** (it was encrypted with the
   old passphrase and cannot be decrypted with the new one):

   ```bash
   ssh office2-claude
   rm /home/claude/.config/gogcli/credentials.json
   ```

3. **Overwrite the passphrase file**:

   ```bash
   ssh office2-claude
   printf '%s' "<paste-new-passphrase>" > /data/services/openclaw/secrets/gog-keyring-password
   chmod 600 /data/services/openclaw/secrets/gog-keyring-password
   chown claude:claude /data/services/openclaw/secrets/gog-keyring-password
   ```

4. **Regenerate the systemd env file** (derived from the passphrase file —
   the helper one-liner is from the manifest's `openclaw-gateway-env`
   entry):

   ```bash
   ssh office2-claude
   PW=$(cat /data/services/openclaw/secrets/gog-keyring-password)
   printf 'GOG_KEYRING_BACKEND=file\nGOG_KEYRING_PASSWORD=%s\n' "$PW" > /data/services/openclaw/secrets/openclaw-gateway.env
   chmod 600 /data/services/openclaw/secrets/openclaw-gateway.env
   chown claude:claude /data/services/openclaw/secrets/openclaw-gateway.env
   ```

5. **Restart `openclaw-gateway`** so systemd re-reads the env file:

   ```bash
   ssh office2-claude 'systemctl --user restart openclaw-gateway.service'
   ssh office2-claude 'systemctl --user is-active openclaw-gateway.service'
   ```

6. **Re-source `~/.bashrc`** in any interactive sessions (or log out/in)
   so the export picks up the new value.

7. **Re-run the gog OAuth flow** for each Google account that was previously
   ingested:

   ```bash
   ssh office2-claude
   gog auth credentials  # confirms client_secret is still in place
   gog auth add <email> --services gmail,calendar,drive,contacts,sheets,docs --remote
   ```

   The `--remote` flag prints a URL the operator opens in a browser to
   complete OAuth. Repeat for each account.

### Per-consumer verification

```bash
# 1. gog can decrypt the new keyring (interactive shell context)
ssh office2-claude 'gog auth list'
# Expected: list of accounts ingested in step 7

# 2. openclaw-gateway child agents can decrypt the keyring (systemd context)
ssh office2-claude 'systemctl --user show openclaw-gateway.service --property=EnvironmentFiles'
# Expected: path includes /data/services/openclaw/secrets/openclaw-gateway.env

# 3. A child agent session sees the env var
# (verify by triggering any gog-using agent skill and confirming no decryption error)
ssh office2-claude 'journalctl --user -u openclaw-gateway.service --since "5 minutes ago" | grep -iE "keyring|gog auth|decrypt"'
```

### GO criteria

- [ ] New passphrase generated and saved in 1Password
- [ ] Old credentials.json removed
- [ ] Passphrase file updated, mode 600
- [ ] openclaw-gateway.env regenerated with matching value, mode 600
- [ ] `openclaw-gateway.service` restarted and `is-active`
- [ ] `gog auth list` returns the re-ingested accounts
- [ ] No keyring/decrypt errors in gateway logs for 5 minutes post-restart
- [ ] Manifest entries updated for BOTH `gog-keyring-password` AND
  `openclaw-gateway-env` per [final section](#manifest-update-obligations)

### NO-GO triggers

- `gog auth list` returns "keyring decrypt error" → the passphrase file and
  env file do not match. Re-run step 4 to regenerate the env file from the
  current passphrase file.
- Gateway child sessions still fail with the old passphrase → the systemd
  unit may be using a cached environment. Verify with
  `systemctl --user show openclaw-gateway.service --property=Environment`
  and restart again.
- OAuth re-ingest fails for an account → confirm `google-workspace-client`
  is still valid (its OAuth Client ID may have been rotated in the Cloud
  Console). See the `google-workspace-client` rotation section below.

---

## `google-workspace-client` (OAuth Desktop client_secret)

**Host**: office2.
**Consumers** (1): `gog auth credentials` ingest path.
**Storage** (1): `/data/services/openclaw/secrets/google-workspace-client.json`.
**Risk tier**: 3 (logic/workflow). Note: rotation requires re-ingesting
the refresh tokens for every account, because the new client_id will
invalidate the old ones.
**Expected duration**: 20-30 minutes (dominated by per-account OAuth
re-ingest).

### Steps

1. **Rotate the OAuth Client ID** in the Google Cloud Console:
   - Navigate to project `felix-openclaw-gog`
   - APIs & Services → Credentials → OAuth 2.0 Client IDs
   - Either edit the existing Desktop client and reset its secret, or
     delete and recreate with a new client_id

2. **Download the new client_secret JSON** from the Cloud Console
   ("Download JSON" button on the OAuth client entry).

3. **Replace the file on office2**:

   ```bash
   # On Mac, scp the downloaded JSON to office2:
   scp ~/Downloads/client_secret_*.json office2-claude:/tmp/

   # On office2, move into place with correct mode:
   ssh office2-claude
   mv /tmp/client_secret_*.json /data/services/openclaw/secrets/google-workspace-client.json
   chmod 600 /data/services/openclaw/secrets/google-workspace-client.json
   chown claude:claude /data/services/openclaw/secrets/google-workspace-client.json
   ```

4. **Re-ingest the client_secret into gog**:

   ```bash
   ssh office2-claude 'gog auth credentials'
   ```

   This wipes the existing client_secret reference inside gog and re-reads
   the file.

5. **Re-mint refresh tokens** for every account that was previously
   ingested:

   ```bash
   ssh office2-claude
   gog auth add <email> --services gmail,calendar,drive,contacts,sheets,docs --remote
   ```

   Repeat for each account. The `--remote` flag is required on the
   headless office2 host (see
   [`google-workspace-ops.md`](<./google-workspace-ops.md>) for the OAuth
   flow detail).

6. **Revoke the old client_secret** in the Cloud Console once verification
   confirms the new one is live.

### Per-consumer verification

```bash
# gog reports the new client_secret is in place and accounts are ingested
ssh office2-claude 'gog auth list'
# Expected: all previously-ingested accounts present with the new client_id

# Live API call via a gog-using agent skill succeeds
# (run any agent that uses gog and verify no auth_error in its tick output)
```

### GO criteria

- [ ] New OAuth Client ID created in Cloud Console
- [ ] New client_secret JSON downloaded
- [ ] File at canonical path updated, mode 600, owner `claude:claude`
- [ ] `gog auth credentials` accepted the new file
- [ ] All previously-ingested accounts re-added via `gog auth add`
- [ ] Old client_secret revoked in Cloud Console
- [ ] Manifest updated per [final section](#manifest-update-obligations)

### NO-GO triggers

- `gog auth credentials` rejects the new file → confirm it's valid JSON
  (Cloud Console downloads sometimes wrap in extra metadata); re-download
  if needed.
- `gog auth add` fails to complete the remote OAuth flow → verify the
  `--remote` URL is reachable from a browser; check the OAuth consent
  screen status in the Cloud Console (occasionally requires re-publishing).
- Old client_secret cannot be revoked → it can be left disabled (set to
  inactive) instead of deleted; both forms invalidate it for new auth flows.

---

## `kentonium3-gh-oauth` (Kent's personal gh CLI auth on Mac)

**Host**: Kent's MacBook Pro (NOT office2).
**Consumers** (1): Kent's manual `git` + `gh` CLI operations.
**Storage** (1): macOS Keychain (managed by `gh` CLI; profile recorded in
`~/.config/gh/hosts.yml`).
**Risk tier**: 3 (logic/workflow).
**Expected duration**: 2-5 minutes.

This is NOT a manually-created classic or fine-grained PAT — rotation is via
`gh auth login --hostname github.com`, not via the "Generate new PAT" flow.

### Steps

1. **On the Mac**, log out and back in:

   ```bash
   gh auth logout --hostname github.com
   gh auth login --hostname github.com --git-protocol https
   ```

   Follow the browser-based OAuth flow.

2. **Verify scopes** after re-auth — `gh auth status` should show at least
   `repo`, `read:org`, `workflow`. If any expected scope is missing,
   re-run with `--scopes "repo,read:org,workflow,gist,project"` to match the
   2026-05-11 baseline.

### Per-consumer verification

```bash
# On Mac:
gh auth status --hostname github.com
# Expected: "Logged in to github.com account kentonium3"
# Token scopes line should include: repo, read:org, workflow

# Verify a write operation works (e.g., add and remove a temporary label)
gh issue edit 525 --repo kentonium3/kg-automation --add-label "P3-debt"
# (Already labeled, so this is a no-op; confirms write access without
# changing state)
```

### GO criteria

- [ ] `gh auth status` shows `kentonium3` active
- [ ] Scopes include `repo`, `read:org`, `workflow` at minimum
- [ ] Test write operation succeeds
- [ ] Manifest updated per [final section](#manifest-update-obligations)

### NO-GO triggers

- Browser OAuth flow fails → check that `gh` CLI's OAuth app at
  https://github.com/settings/applications has not been revoked.
- Missing scopes after re-auth → repeat `gh auth login` with explicit
  `--scopes` flag.

---

## Manifest update obligations

Every rotation MUST update the manifest. Skipping the update silently breaks
`credential-health-check.service`'s 30-day warning boundary math — the
watchdog reads these fields to compute when to fire the next alert. A
missing update means the next rotation deadline is invisible until the
credential actually expires (or has already expired).

### Fields to update per credential

For the rotated credential's entry in
[`credential-manifest.json`](<../design/architecture/data/credential-manifest.json>):

- `last_reviewed` — ISO date of the rotation (today).
- `expires_at` (if `expiry_policy: rotate-before-expiry`) — new expiry date.
- `updated_by` — a short token identifying the rotation event
  (e.g., `2026-06-05 manual rotation` or `#NNN-related-work`).
- `last_updated` (if the entry has one) — same date as `last_reviewed`.

### Top-level fields to update

- `last_updated` — ISO date.
- `updated_by` — append the rotation event token to the existing list
  (semicolon-separated by convention).

### Single-commit obligation

Per change-control protocol, machine-readable and narrative views must
update in the same commit. After editing the JSON:

```bash
# Validate JSON parses
python3 -c "import json; json.load(open('docs/design/architecture/data/credential-manifest.json')); print('OK')"

# Stage and commit
git add docs/design/architecture/data/credential-manifest.json
git commit -m "chore(credentials): rotate <credential-name> $(date +%Y-%m-%d) [doc-audit]"
git push origin main
```

### Verification

```bash
# Confirm credential-health-check picks up the new boundary on its next tick
ssh office2-claude 'systemctl --user status credential-health-check.timer'
# Wait for next 13:00 UTC firing; check that no false alert is raised
ssh office2-claude 'journalctl --user -u credential-health-check.service --since "1 day ago" | tail -20'
```

---

## References

- **Manifest**:
  [`docs/design/architecture/data/credential-manifest.json`](<../design/architecture/data/credential-manifest.json>)
- **Security posture**:
  [`docs/design/architecture/credentials-and-secrets.md`](<../design/architecture/credentials-and-secrets.md>) §Security Posture
- **Change risk taxonomy**:
  [`docs/design/architecture/data/change-risk-taxonomy.json`](<../design/architecture/data/change-risk-taxonomy.json>)
- **Pre-flight protocol (Tier 2)**:
  [`docs/runbooks/governance/pre-flight-checklist.md`](<./governance/pre-flight-checklist.md>)
- **Companion runbooks**:
  - [`felix-bot-vikunja-provisioning.md`](<./felix-bot-vikunja-provisioning.md>)
    — one-time felix-bot identity cutover (`vikunja-api`)
  - [`google-workspace-ops.md`](<./google-workspace-ops.md>) — `gog` CLI
    setup and Pitfall 4 (systemd env-file context)
  - [`openclaw-ops.md`](<./openclaw-ops.md>) — re-pairing
    `whatsapp-session` (out-of-scope here)
- **Watchdog**: `credential-health-check.service` design at
  `kitty-specs/credential-expiry-health-check-01KRCF92/` and implementation
  at `scripts/security/credential_health_check/`.
- **Filing issue**:
  [#522](https://github.com/kentonium3/kg-automation/issues/522)
