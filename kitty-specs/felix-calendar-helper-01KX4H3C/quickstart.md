# Quickstart: deploy & verify the Felix Calendar Helper

**Mission**: felix-calendar-helper-01KX4H3C
**Audience**: operator (Kent) + the deploying agent. Ordered, halt-on-error.

> Deploy happens **after** `feat/felix-calendar-helper → main`. Helper code
> reaches office2 via the checkout's `git pull` (felix-deployer 5-min tick);
> agent prompts via the agent-prompt-sync timer.

## 0. Pre-flight (Tier 2 + Tier 1 gates)

- **Restic ≤24h** (Tier 2 — creds + venv are state): the deploy script runs
  `snapshot.verify_restic_recent --max-age-hours 24`. If stale, trigger a backup
  first (operator via `ssh office2-kgale`, or the nightly cron ack path).
- Confirm office2 reachable and the checkout is on `main` at the merge SHA.

## 1. Stage credentials (MANUAL — secrets, never via git)

The Mac token must be minted with the mission scope (`calendar.events`) before
staging — office2 is headless and will never run interactive consent. The
personal creds already exist on the Mac at `~/.config/felix/google/personal/`;
if the staged token was minted with a narrower/different scope, re-mint it
Mac-side first (`workspace_auth_spike`-style consent) so office2 `--self-check`
passes without re-consent.

Copy the personal OAuth creds from the Mac to office2:

```
scp ~/.config/felix/google/personal/client_secret.json office2-claude:~/.config/felix/google/personal/client_secret.json
scp ~/.config/felix/google/personal/token.json          office2-claude:~/.config/felix/google/personal/token.json
```

Then fix perms on office2:

```
ssh office2-claude 'chmod 700 ~/.config/felix/google ~/.config/felix/google/personal && chmod 600 ~/.config/felix/google/personal/*.json'
```

(One command per line for clean copy-paste, per Kent's preference.)

## 2. Provision the venv (via the deploy manifest)

The manifest `deploys/queued/felix-calendar-helper.yaml` (Tier 3,
`audited_surface: true`) is picked up by felix-deployer. Its entrypoint
`scripts/deploy/deploy-felix-calendar-helper.py`:
1. verifies the Restic gate,
2. creates/refreshes `/data/services/openclaw/felix-calendar/venv` with uv and
   installs the pinned google deps (idempotent),
3. verifies the staged creds are present (file-presence, 0600),
4. runs the self-check smoke (step 4).

Manual venv provisioning (if run out-of-band for validation) — use the `uv`
executable to build and install *into* the venv (uv is not installed inside it);
pin versions:

```
ssh office2-claude '~/.local/bin/uv venv /data/services/openclaw/felix-calendar/venv --python 3.12'
```
```
ssh office2-claude '~/.local/bin/uv pip install --python /data/services/openclaw/felix-calendar/venv/bin/python "google-api-python-client==<pin>" "google-auth==<pin>" "google-auth-oauthlib==<pin>"'
```

(Prefer the manifest path; the deploy script performs exactly these steps
idempotently with the pins resolved. The above is the equivalent for a manual
check.)

## 3. Deploy prompts + openclaw.json (audited surface)

- Prompt edits (`felix-admin-calendar/AGENTS.md`, capture `AGENTS.md.tmpl`) sync
  automatically via the agent-prompt-sync timer once on `main`.
- **openclaw.json** — remove `gog` from `felix-admin-calendar.skills` (manual
  out-of-band edit) and restart the gateway:

```
ssh office2-claude 'openclaw agent list --json | python3 -c "import json,sys;print([a for a in json.load(sys.stdin) if a.get(\"name\")==\"felix-admin-calendar\"])"'
```
  (Edit `skills: []` for felix-admin-calendar, then restart the gateway per the
  openclaw-agent-setup runbook.)

## 4. Verify (SC-001..006)

Self-check (auth + list calendars) — the primary smoke:

```
ssh office2-claude 'cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.calendar_helper --self-check --account personal'
```
Expect `SUMMARY: op=self-check status=ok account=personal`, exit 0. (Self-check
refreshes the token + does a bounded `events().list(primary, maxResults=1)`; it
never runs interactive consent — a scope/auth failure exits 3 with a re-mint
message.)

CRUD round-trip on the real personal calendar (SC-001):

```
ssh office2-claude 'cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.calendar_helper create --summary "[felix-verify] delete me" --start 2026-07-15T15:00:00-04:00 --end 2026-07-15T15:30:00-04:00 --json'
```
Then `list` the window to confirm, then `delete --event-id <id>`.

End-to-end inbox → calendar (SC-002, closes #679): drop a test note with a
calendar intent in the vault inbox, run capture on-demand, confirm the event
lands with **no** `openclaw agent`/`sessions_send` hop in the trajectory and the
note is marked processed.

Fail-safe (SC-004): temporarily point `--account` at a non-existent account (or
a dir with an invalid token) and confirm `ERROR: auth_failed`, exit 3, no event.

Multi-account (SC-005): confirm `--account intentional` resolves to
`~/.config/felix/google/intentional/` (dir need not exist yet — the resolution +
clear missing-creds error is the check).

## 5. Rebaseline (audited surface, #557)

Only the **openclaw.json** `skills` edit is a monitored surface
(`openclaw-config`, `rebaseline_required: true`). The **AGENTS.md/.tmpl** edits
are an *unmonitored* audited surface (`rebaseline_required: false`) — no
rebaseline is written or needed for them. The **google deps live in the venv, not
`requirements.txt`**, so the `python-dependencies` (pip-packages) baseline is
untouched — do not add them to the repo requirements.

For the openclaw.json edit, reset baselines manually (out-of-band exception):

```
ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
```

The merge commit records `Rebaseline: completed at <ts>` for the openclaw.json
change (or `not required — <reason>` if the openclaw.json edit is deferred).

## 6. Close-out

- Update architecture data + views + INDEX + roadmap (IC-06) — part of the merge,
  not a follow-up.
- Comment on #699 with the merge SHA; note #679 closed by the live SC-002 run.
- Post-merge Codex review of the full `feat/felix-calendar-helper` diff runs
  **before** `feat → main` (mandatory checkpoint).
