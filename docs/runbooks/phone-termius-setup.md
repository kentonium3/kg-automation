---
title: Phone Termius Setup & Recovery
doc_type: runbook
status: approved
owners: ["@kentonium3"]
last_updated: '2026-06-09'
updated_by: '#575-phone-termius-docs'
audience: humans
---

# Phone Termius Setup & Recovery

How Kent's iPhone connects to office2 via SSH using Termius mobile. Covers
first-time setup, post-SSH-key-rotation recovery, new-phone enrollment, and
gotchas discovered during the 2026-06-09 rediscovery exercise (#575).

This runbook complements [`physical-topology.md`](<../design/architecture/physical-topology.md>)
(machine-readable map of devices + IPs) and
[`security-posture.md`](<../design/architecture/security-posture.md>) (which
users do what). For the network-fabric decision, see
[ADR-0004](<../design/architecture/adr/0004-tailscale-ssh-with-accept-acl.md>).

---

## 1. The setup that works

After setup, you should have **two host entries in Termius mobile**, both
pointing at office2 but landing as different Linux users:

| Termius host label | Address | Port | Username | Purpose |
|---|---|---|---|---|
| `office2 kgale` | `office2.tail0f5f56.ts.net` | 22 | `kgale` | General operator ops, sudo, emergency maintenance |
| `office2 claude (gog-reauth)` | `office2.tail0f5f56.ts.net` | 22 | `claude` | Running `gog-reauth` and other claude-user ops (e.g. credential keyring writes) |

Both use the same Termius SSH ID (Termius-managed cloud-hosted public key).
Tailscale handles the network; standard sshd handles the auth.

### Why two users

- **`kgale` is for Kent's human / sudo-required operations** — same posture as
  Mac terminal `ssh office2-kgale`.
- **`claude` is for operator-on-the-claude-user tasks** — primarily running
  `gog-reauth` (the weekly OAuth re-auth from `[[reference_gog_credential_health_gap]]`)
  because the gog keyring lives under `/home/claude/.config/gogcli/`. The
  general "agents always use claude" rule (`security-posture.md` § Agent
  Access Model) is about traceability for autonomous agents; humans connecting
  as claude for specific user-bound operations is fine.

---

## 2. First-time setup (or new phone enrollment)

### Prerequisites

- Termius mobile installed on phone (free plan is sufficient)
- Tailscale mobile installed on phone, logged in to your tailnet, status green
- Tailnet ACL has `ssh` rule with `action: "accept"` (NOT `check`) — see
  [ADR-0004](<../design/architecture/adr/0004-tailscale-ssh-with-accept-acl.md>)
  for why and how to verify at <https://login.tailscale.com/admin/acls>
- Access to your Mac terminal for the one-time public-key install step

### Steps

**On phone, in Termius:**

1. **Generate a Termius SSH ID** (one-time per Termius account; reused across
   all phone hosts):
   - Tap **Keychain** → **Identities** → **+** → **Generate new identity**
   - Termius creates a keypair in its cloud + names it (e.g. `office2-kgale`)
   - Tap the identity → it shows a curl command of the form
     `curl -fs https://sshid.io/<name> >> ~/.ssh/authorized_keys`
   - You'll run this curl on the office2 server in the next step. The
     `<name>` is a Termius-side label; the URL hosts only the public half of
     the key and is safe to fetch over plain HTTPS.

**On Mac terminal:**

2. **Install the SSH ID public key on office2 for both users**, plus the
   `gog-reauth` alias on claude's bashrc (single command):

   ```bash
   ssh office2-kgale 'curl -fs https://sshid.io/<your-ssh-id-name> >> ~/.ssh/authorized_keys'
   ssh office2-claude 'curl -fs https://sshid.io/<your-ssh-id-name> >> ~/.ssh/authorized_keys && echo "alias gog-reauth=/home/claude/kg-automation/scripts/security/gog-reauth.sh" >> ~/.bashrc'
   ```

   (Substitute your actual SSH ID name for `<your-ssh-id-name>`.)

**On phone, in Termius:**

3. **Create the `office2 kgale` host:**
   - Tap **Hosts** → **+**
   - **Address**: `office2.tail0f5f56.ts.net`
   - **Port**: `22`
   - **Use SSH**: ON; **Use Mosh**: OFF
   - **Username**: `kgale` — **NOT the SSH ID name**. The SSH ID name (e.g.
     `office2-kgale`) is a Termius label; the username field must be a real
     Linux user. Using the SSH ID name as the username caused the
     `end of file` error during the 2026-06-09 rediscovery — see
     §"Gotchas" below.
   - **Password**: leave empty
   - **Key**: the Termius SSH ID you generated
   - Save and tap to test-connect; you should land at `kgale@office2:~$`

4. **Create the `office2 claude` host** (same fields, only username differs):
   - **Address**: `office2.tail0f5f56.ts.net`
   - **Port**: `22`
   - **Username**: `claude`
   - **Label** (recommended): `office2 claude (gog-reauth)` so you can
     tell them apart in the Hosts list
   - Save and test-connect; you should land at `claude@office2:~$`

5. **Verify `gog-reauth` alias** (on the claude host):
   - Type `gog-reauth` → enter
   - You should see the preconditions check + Step 1 print an authorization
     URL. **Press Ctrl-C** at the URL prompt to abort without mutating state
     — this confirms the wiring works.

---

## 3. Recovery scenarios

### "I rotated my SSH key on the Mac and now my phone Termius doesn't connect"

The Mac-side SSH key rotation does NOT affect phone Termius. Termius mobile
uses the Termius SSH ID (cloud-hosted) for auth, not your Mac's
`~/.ssh/id_ed25519`. If the phone connection broke around the same time as a
key rotation, the rotation is almost certainly NOT the cause — recheck:

1. Is Tailscale running on the phone? (status green)
2. Is the Tailnet ACL `ssh` rule at `accept` (not `check`)?
3. Does the Termius host's Username field match a real Linux user (`kgale`
   or `claude`), NOT the SSH ID name?

If those check out and it still fails, get the connection log from Termius
(two expansion screenshots from "Connection could not be established" panel)
and follow the same diagnostic path the #575 rediscovery used:

- `socket is not connected` → Tailscale ACL is rejecting (check / propagation
  delay / Tailscale not actually active on phone)
- `end of file` → sshd is rejecting (auth method mismatch — usually the
  Username field)
- `Authenticating as "<wrong-name>"` line in the log identifies the user
  Termius is trying to use

### "I got a new phone"

Termius mobile syncs vault data only on the paid plan. On the free plan,
treat it as a first-time setup:

1. Generate a new Termius SSH ID on the new phone
2. Run the curl command on office2 for BOTH `kgale` and `claude` users
3. Recreate the two host entries

The old phone's SSH ID public key remains in `~/.ssh/authorized_keys` on
office2 until you remove it. To clean up:

```bash
ssh office2-kgale 'grep -v "<old-key-fingerprint-snippet>" ~/.ssh/authorized_keys > ~/.ssh/authorized_keys.new && mv ~/.ssh/authorized_keys.new ~/.ssh/authorized_keys'
# Repeat for claude
```

### "I want to revoke phone access entirely"

1. On the Tailscale admin console, remove your phone from the tailnet (or
   tighten the ACL `ssh` rule to exclude iOS devices)
2. Remove the Termius SSH ID's public key from `~/.ssh/authorized_keys` on
   both `kgale` and `claude` accounts
3. Optionally delete the SSH ID from Termius's Keychain on the phone

---

## 4. Gotchas (from the 2026-06-09 rediscovery)

These tripped us up during the day-long Tailscale SSH rediscovery that
generated #575. Document them so the next operator (you, future me, or a
session in 6 months) doesn't redo the work:

### Tailscale SSH ACL must be `accept`, not `check`

The default Tailscale ACL `ssh` rule has `"action": "check"` which requires
periodic browser re-authentication. Termius mobile can't complete the
browser check, so connections close with `socket is not connected` at the
Tailscale layer (before sshd even sees them). Switching to `"action": "accept"`
fixes this. See [ADR-0004](<../design/architecture/adr/0004-tailscale-ssh-with-accept-acl.md>)
for the tradeoff analysis.

### Termius's "SSH ID name" is NOT a Linux username

When you generate a Termius SSH ID, Termius names it (e.g. `office2-kgale`).
That name shows up in the curl command URL and in the SSH ID export options.
**Do not use it as the Linux username on the host config.** The username
field must be a real Linux user (`kgale` or `claude`). Mis-typing here gave
us the `end of file` error after Tailscale SSH accepted the connection but
sshd couldn't find the user.

### Username field must be filled in BEFORE the first connection attempt

If you create a Termius host with an empty Username and tap to connect,
Termius will probe with some default (possibly empty or the device's local
identity), and Tailscale SSH may pre-emptively reject the probe with
`socket is not connected`. Fill in `kgale` or `claude` before the first
connect.

### The "key rotation broke my phone access" misdirection

Rotating an SSH key on your Mac does not affect Termius mobile. Termius
mobile uses its own SSH ID (cloud-hosted) and never sees Mac keys. If your
phone connection breaks around the same time as a key rotation, look at:

1. Tailscale (running? ACL up to date?)
2. Termius host config (correct Username? correct SSH ID selected?)
3. office2 sshd (authorized_keys has the Termius SSH ID public key?)

NOT at:

- The Mac-side `~/.ssh/id_ed25519`
- The new key you generated for Mac
- The MacBook's known_hosts

### Phone Termius does NOT go through Tailscale SSH for auth, even when it reaches port 22 on the Tailscale IP

Tailscale SSH on office2 intercepts the connection and decides at the ACL
layer whether to allow it. On `accept`, the connection is passed through
the standard sshd path — auth happens via `authorized_keys`, not via
Tailscale identity. This is why we needed the Termius SSH ID public key in
`authorized_keys` even with Tailscale SSH enabled. (The `Remote server:
SSH-2.0-Tailscale` line in the connection log is informational — it tells
you Tailscale SSH intercepted the connection; it does NOT mean Tailscale
identity is what authenticates.)

---

## 5. Cross-references

- [ADR-0004 — Enable Tailscale SSH with `accept` ACL on office2](<../design/architecture/adr/0004-tailscale-ssh-with-accept-acl.md>) — decision rationale + tradeoffs
- [`physical-topology.md`](<../design/architecture/physical-topology.md>) § SSH access — machine-readable device + IP listing
- [`security-posture.md`](<../design/architecture/security-posture.md>) § Agent Access Model — user-role table
- [`google-workspace-ops.md`](./google-workspace-ops.md) — gog-reauth's full procedure (the script automates §2.8)
- kentonium3/kg-automation#572 — credential liveness probe (the reason phone-recovery matters)
- kentonium3/kg-automation#575 — this runbook's originating docs-debt issue
