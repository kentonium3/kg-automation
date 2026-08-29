---
title: Security Posture
doc_type: reference
status: approved
tags: [152, 575]
---

# Security Posture

## Network Security

- **Services bind to Tailscale IP** (`100.92.197.90`) unless fronted by Tailscale Serve, which allows `0.0.0.0` binding safely
- **One service is exposed to the public internet** (corrected 2026-08-22; this line read
  "No services exposed to the public internet (Tailscale Funnel is disabled)" and was false
  from 2026-08-04): **Tailscale Funnel is ENABLED** on `office2` for
  `https://office2.tail0f5f56.ts.net:8443` → `127.0.0.1:3457`, the spec-kitty-qa
  `qa-dispatch-webhook` (Linear dispatch). Interim — retired by #887. See
  `data/network-topology.json` and #886.
  - Consequence of Funnel that survives its retirement: `office2.tail0f5f56.ts.net` is now
    resolvable in **public DNS** and recorded in **Certificate Transparency logs**, so the
    host is publicly nameable and the tailnet name externally enumerable. CT entries are
    permanent; turning Funnel off does not undo this.
  - Ingress is authenticated: HMAC signature check (constant-time, fail-closed on missing
    secret or header), replay guard on `webhookTimestamp`, actor-type check rejecting
    bots/OAuth clients, and a fail-closed reviewer allowlist.
- Every other service is tailnet-only
- No port forwarding or NAT traversal outside Tailscale
- Docker's default networking bypasses iptables/ufw — explicit IP binding is the primary control for non-Serve services

**Tailscale Serve**: Vikunja is fronted by Tailscale Serve, which terminates TLS on port 443 and proxies to the container on localhost:3456. Certs are auto-provisioned from Let's Encrypt and auto-renewed. Access is tailnet-only.

**As of F003**: Transcribe API and OpenClaw bind exclusively to Tailscale IP. Vikunja binds to `0.0.0.0:3456` but is accessed via Tailscale Serve on HTTPS — direct port 3456 is not reachable from outside the host.

## Supply Chain

- Docker images pinned to specific version tags, never `latest`
- No LiteLLM or third-party API proxies — Anthropic API called direct
- No community OpenClaw skills without source review
- All Python dependencies reviewed before installation

## Agent Access Model

| User | Access | Sudo | Purpose |
|------|--------|------|---------|
| `claude` | `ssh office2-claude` (Mac), or `claude` host in Termius mobile | No | Agent operations — all automated actions. Humans connecting as `claude` is allowed for specific user-bound operations (e.g. `gog-reauth` weekly re-auth — see [phone-termius-setup runbook](<../../runbooks/phone-termius-setup.md>)) |
| `kgale` | `ssh office2-kgale` (Mac), or `kgale` host in Termius mobile | Yes | Human operations — sudo commands, initial setup, emergency ops |

**Scope: this access model is office2's.** It is the only managed host, and the only
machine with a split human/agent user model. The tailnet has four devices — office2, office4,
the MacBook Pro and the iPhone — and the other three are unmanaged peers that run **no
registered service** (none appears in `data/service-inventory.json`). office4 in particular is
deliberately **kgale-only**: no `claude` or `codex` Unix user exists there, because the
office2 `claude` user earns its keep by being a remote actor on a host it does not live on,
and office4 inverts that premise. See [ADR-0008](<./adr/0008-three-machine-model.md>).

**"Unmanaged" governs deployment, not exposure.** office4 does run standard sshd on port 22,
reachable over the tailnet and authenticated by `~/.ssh/authorized_keys`. What it does *not*
run is **Tailscale SSH** (`tailscale debug prefs` → `"RunSSH": false`), so of the two gates
below, gate 1 is office2-only while gate 2 applies on office4 as well — with no tailnet ACL
layer in front of it. Do not read "unmanaged peer" as "no attack surface"; office4's sshd
posture is tracked separately in #926.

**Agents must always use the claude user on office2.** The kgale account is for human use only by autonomous agents. Humans (Kent) may use either user depending on the task. This ensures all agent actions are traceable.

**Sudo escalation**: When a command requires sudo, agents stop and present the command to Kent for manual execution.

### SSH access to office2 — two *paths*, not two sequential gates

⚠️ This section previously described "two gates in sequence", with Tailscale SSH passing the
connection "through to sshd". **That is wrong for the tailnet path**, and the distinction is
material to anyone auditing who can reach this host. Corrected 2026-08-29 (#931).

There are two independent paths to office2's port 22, and they enforce *different* things:

**Path A — over the tailnet (`100.92.197.90:22`). Tailscale SSH terminates; keys are never consulted.**

tailscaled on office2 (`RunSSH: true`) intercepts the connection and authorises it against the
tailnet ACL. With `action: "accept"` the session is established **on tailnet device identity
alone** — it is not handed to sshd, and `~/.ssh/authorized_keys` plays no part. With `"check"`
it would require browser re-auth (incompatible with Termius mobile). See
[ADR-0004](<./adr/0004-tailscale-ssh-with-accept-acl.md>) for the decision rationale.

The current ACL is `src: autogroup:member` → `dst: autogroup:self`,
`users: ["kgale", "claude", "codex"]`.

Narrowed 2026-08-29 (#932). It previously read `users: [autogroup:nonroot, root]` — which
granted **root on office2 to any tailnet device, with no key and no password**. `PermitRootLogin
no` in `sshd_config` did not prevent it and never could: on path A the connection never reaches
sshd. Naming the accounts also scopes per host without device tagging, since office2 has exactly
these three and office4 has only `kgale`.

The removal is now asserted rather than assumed. The tailnet policy carries an `sshTests` block
(`"deny": ["root"]`), evaluated on every policy save, so reintroducing root fails the save. This
matters because the policy's other `tests` block **cannot** validate SSH rules — per Tailscale's
documentation `tests` covers network-level grants only.

> **Consequence, stated plainly: membership of the tailnet is equivalent to a shell on office2
> as `kgale`, `claude`, or `codex` — including the agent account — with no key and no
> password.** Adding any device to the tailnet grants that access immediately, with no
> key-provisioning step anywhere. This is deliberate (ADR-0004 chose `accept` over `check` so
> Termius mobile would work), and it is the reason tailnet membership is itself a security
> boundary. Root is no longer among the reachable accounts; the rest of the property stands.

Verified 2026-08-29 from office4, which at the time held **no SSH private key at all**:

```
$ ssh -o BatchMode=yes -o IdentitiesOnly=yes -i /nonexistent office2-claude 'whoami'
claude
```

**Path B — over the LAN (`192.168.1.158:22`). Real sshd; `authorized_keys` is enforced.**

This path bypasses Tailscale SSH entirely and behaves like ordinary OpenSSH: per-user
`~/.ssh/authorized_keys`, no tailnet ACL involved. The same command that succeeds on path A
fails here:

```
$ ssh -o BatchMode=yes -o IdentitiesOnly=yes -i /nonexistent claude@192.168.1.158 'whoami'
claude@192.168.1.158: Permission denied (publickey).
```

**Auditing implication.** Reading office2's `authorized_keys` files answers "who can reach this
host **over the LAN**". It does **not** answer "who can reach this host", because path A does
not consult them. To answer that question you must also read the tailnet ACL and the device
list in [`data/network-topology.json`](<./data/network-topology.json>).

**Unverified — Termius / iPhone.** The phone is a tailnet member, so path A's reasoning
*should* apply to it and its SSH ID would then be unnecessary. But #575 spent ~30 minutes
troubleshooting `authorized_keys` for Termius, which suggests path B semantics were in play.
This has **not** been re-tested since, and the two accounts are not reconciled. Treat the
Termius path as unconfirmed until someone checks it from the phone; see
[phone-termius-setup § Gotchas](<../../runbooks/phone-termius-setup.md>).

**SSH key rotation impact**: rotating a Mac-side SSH key affects **path B only**. Path A is
independent of SSH keys entirely. Termius mobile uses its own SSH ID, NOT any Mac key — the
2026-06-09 #575 rediscovery wasted ~30 min troubleshooting `authorized_keys` permissions before
noticing that distinction.

**ACL changes are tracked in [ADR-0004](<./adr/0004-tailscale-ssh-with-accept-acl.md>) § ACL changes log.** Any future change to the tailnet `ssh` rule (action, src/dst/users) must be recorded there. Undocumented changes are how the #575 docs-debt accumulated.

## Credential Security

- No credentials in committed files — ever
- Secrets stored on office2 filesystem (not in repo)
- Interactive auth for manual scripts; stored tokens for automated use
- See [Credentials and Secrets](<./credentials-and-secrets.md>) for the full manifest

## Privacy Boundaries

**Physical exclusion**: Kent's sensitive growth-work content (formerly the `04-Growth/_private` vault folder) lives in a separate Obsidian vault synced only to Kent's laptop and phone. office2 never joins that vault, and the old folder was deleted and verified absent from office2. The privacy boundary is enforced by **physical exclusion** — the content is never present on the machine Felix runs on — which supersedes the retired in-repo "never touch `_private`" apparatus (#848). Agents and scripts still never read, write, or log content outside the resolved inbox / permitted vault paths.

**Agent context ceiling**: Agents may read `03-Constitution/` docs only from the second brain. All other vault content is off-limits unless explicitly required by a skill definition.

## Policy Exceptions

Exceptions to architecture and security policies are documented here with rationale, scope, and expiration. Each exception must be approved by Kent and linked to the feature that introduced it.

| Constraint | Exception | Rationale | Scope | Expiration | Feature |
|------------|-----------|-----------|-------|------------|---------|
| Official API only (original F004 C-002) | OpenClaw's WhatsApp integration uses Baileys (unofficial WhatsApp Web protocol) | OpenClaw has no Meta Cloud API channel. Baileys is the only WhatsApp path available. | Personal single-user system at low message volume. Account ban risk understood and accepted. | No expiration — this is the native OpenClaw integration path. | F004 |

## Change Control Governance

Change control is governed by a five-tier risk taxonomy (`docs/design/architecture/data/change-risk-taxonomy.json`). Tier 0 (Host/Foundational) changes including UFW, iptables, and SSH configuration follow a Hard Lock protocol — AI agents generate scripts but never execute directly. Tier 1 changes require human approval before execution. See `docs/runbooks/governance/pre-flight-checklist.md` for the full pre-flight assessment and `docs/runbooks/governance/post-change-verification.md` for post-change health checks.

## Security Monitoring

| Check | Schedule | Script | Baselines |
|-------|----------|--------|-----------|
| Docker images | 3AM daily | `audit.sh` | `docker-images.txt` |
| Enabled services | 3AM daily | `audit.sh` | `enabled-services.txt` |
| Listening ports | 3AM daily | `audit.sh` | `listening-ports.txt` |
| SSH keys | 3AM daily | `audit.sh` | `ssh-keys.txt` |
| Crontabs | 3AM daily | `audit.sh` | `crontabs.txt` |
| Pip packages | 3AM daily | `audit.sh` | `pip-packages.txt` |
| Hosts file | 3AM daily | `audit.sh` | `hosts-hash.txt` |
| Python pth files | 3AM daily | `audit.sh` | `pth-files.txt` |

After deploying a new service, baselines must be reset. See [Security Baseline Operations](<../../runbooks/security-baseline-ops.md>) for the canonical procedure.

### Expected-drift push suppression (#862)

An audited-surface deploy that lands within seconds of an audit tick produces
**expected** drift that `felix-deployer` is already reconciling via its deferred-confirm
rebaseline. To keep the security push channel credible (no false pages for drift the
system already knows about), `audit.sh` consults a read-only helper
(`scripts/deploy/felix-deployer/expected_drift.py`) at **push time** and withholds the
push for baseline drift named in `felix-deployer`'s **fresh** pending-rebaseline token
(`/data/services/felix-deployer/state/rebaseline-pending.json`).

Invariants that keep this safe:

- **Detection is never suppressed** — every drift still emits its `[ALERT] <name>` line
  and the audit still exits `1`, so `felix-deployer`'s reconcile still detects the drift
  and stamps the new baseline. Only the human *push* is gated.
- **Read-only, one-directional** coupling — the audit only reads the token; it never
  writes `felix-deployer` state.
- **Short window** — suppression is bounded by a dedicated ~15-minute window
  (`AUDIT_SUPPRESS_WINDOW_SECONDS`), **not** `felix-deployer`'s 24 h stale threshold, so
  a lingering or maliciously planted token can never mute the channel for long.
- **Fail-safe** — a missing, malformed, stale, or unreadable token (or any helper error)
  suppresses nothing; the audit pages exactly as before.
- **Scoped to baseline drift** — IOC alerts and unexpected baseline drift always push.
