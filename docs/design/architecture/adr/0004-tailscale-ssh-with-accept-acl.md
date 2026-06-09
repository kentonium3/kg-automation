---
title: ADR-0004 — Enable Tailscale SSH on office2 with `accept` ACL
doc_type: reference
status: approved
owners: ["@kentonium3"]
last_updated: '2026-06-09'
version: v1.0
audience: agents_and_humans
tags: [575]
---

# ADR-0004 — Enable Tailscale SSH on office2 with `accept` ACL

**Status**: Approved
**Date**: 2026-06-09
**Deciders**: Kent Gale
**Closes**: kentonium3/kg-automation#575

## Context

office2 is the always-on hub for Felix and is accessed via SSH from:

- Mac terminal (Kent's primary authoring endpoint, `100.71.19.66`)
- iPhone Termius mobile (Kent's mobile endpoint, `100.109.208.6`)
- Future devices as the system grows

All inter-device communication uses Tailscale (per
[`network-topology.json`](../data/network-topology.json) and
[`security-posture.md`](../security-posture.md) § Network Security).

The network-layer ACL governs what reaches sshd. Two architectural options
were live for SSH access governance:

1. **Plain sshd, no Tailscale SSH** — each device has its own SSH key,
   public keys distributed to `~/.ssh/authorized_keys` on office2 per user
   per device. Tailscale handles network access; sshd handles auth.
2. **Tailscale SSH** — enable `tailscale up --ssh` on office2. tailscaled
   intercepts SSH connections to port 22 on Tailscale IPs and applies the
   tailnet ACL as the first gate. With `action: "accept"` it then passes
   through to sshd for auth; with `action: "check"` it presents a
   browser-based identity re-verification flow with a configurable
   `checkPeriod`.

This ADR records the decision (already taken historically and rediscovered
on 2026-06-09) and the ACL refinement made that day.

## Decision

**Tailscale SSH IS enabled on office2** (`tailscale up --ssh` was run at
some point during initial setup — exact date undocumented; confirmed via
`tailscale debug prefs` showing `"RunSSH": true`).

**Tailscale ACL `ssh` rule is set to `accept`** (as of 2026-06-09; previously
`check`):

```json
"ssh": [
  {
    "action": "accept",
    "src":    ["autogroup:member"],
    "dst":    ["autogroup:self"],
    "users":  ["autogroup:nonroot", "root"],
  },
],
```

The change from `check` to `accept` was made during the #575 phone-recovery
rediscovery exercise because Termius mobile cannot complete the browser
re-auth that `check` mode requires — see "Tradeoffs" below.

## Rationale

### Why Tailscale SSH is enabled

- **Centralized SSH access policy** at the tailnet layer instead of per-user
  `authorized_keys` scattered across hosts. The Tailscale admin console is
  the single source of truth for "who can SSH where."
- **Connection observability** in the Tailscale admin console — every SSH
  session is logged.
- **Defense-in-depth** — even if sshd misconfiguration would allow an
  unintended path, Tailscale SSH gates it at the ACL layer first.
- **Future-proofing** — Tailscale SSH supports identity-based auth (no SSH
  keys needed) when both ends speak the protocol. Enabled now means we can
  later remove keys for paths that fully adopt it.

### Why `accept` and not `check`

- **Termius mobile cannot complete the browser-based `check` flow.** When
  `check` is in effect, tailscaled closes the SSH connection until the user
  re-authenticates via a one-time browser visit. iOS Termius doesn't pop a
  browser tab in-app and can't satisfy the check, so SSH from phone fails
  with `socket is not connected`.
- **Personal single-user tailnet posture is consistent with `accept`.** All
  network access (`grants` block) is already `*/*/*` for the tailnet owner.
  Adding an SSH-specific re-auth would be the only friction layer, and
  Termius mobile can't tolerate it.
- **The trade-off is acceptable** — the gate is the Tailscale account login
  (which already has 2FA via the Google SSO it's bound to). Losing periodic
  SSH re-verification is mitigated by the fact that any compromise of a
  tailnet-authenticated device is already a "lateral movement to anywhere"
  scenario per the existing posture.

## Alternatives Considered

| Option | Why rejected |
|---|---|
| **Plain sshd, no Tailscale SSH** | Doesn't give us tailnet-layer SSH ACL or session logging; per-device key management would grow with each new device |
| **Tailscale SSH with `check` action** | Termius mobile cannot complete browser re-auth → no phone access. We need phone access for emergency operations (Kent's word) including `gog-reauth` recovery |
| **Tailscale SSH with `check` + add an exception for phone** | Possible (tag the phone, allow it without check), but the tag/exception mechanism is more rules to maintain. For a single-user tailnet the simpler `accept`-everywhere posture matches our existing wide-open `grants` block |
| **Disable Tailscale SSH; manage SSH purely via sshd + authorized_keys** | Loses the centralized ACL and session-log benefits. Was almost-certainly NOT the original setup since we found `RunSSH: true` |

## Tradeoffs

### Gained by enabling Tailscale SSH (vs plain sshd)

- Centralized ACL at the tailnet layer
- Tailscale-side session logging in the admin console
- Forward path to identity-based SSH (no per-device keys) if/when we adopt
  it tailnet-wide

### Lost by enabling Tailscale SSH (vs plain sshd)

- Operator must understand TWO gates exist (ACL + sshd) when debugging SSH
  failures. The 2026-06-09 rediscovery spent ~30 min on the wrong gate
  before noticing the `SSH-2.0-Tailscale` server line.
- Tailscale SSH protocol-level rejections produce thin error messages
  (`socket is not connected`) that don't say WHY.

### Gained by `accept` (vs `check`)

- Phone Termius works without browser re-auth
- No periodic re-auth interruption for any device
- Simpler ACL — no per-device tag rules

### Lost by `accept` (vs `check`)

- No periodic SSH re-verification of operator identity (gate is Tailscale
  account login, which has 2FA via the underlying SSO provider)
- A compromised tailnet-authenticated device has unbounded SSH access until
  device is revoked at the tailnet layer

## Consequences

- Operator-facing setup for phone Termius is documented in
  [`docs/runbooks/phone-termius-setup.md`](../../runbooks/phone-termius-setup.md)
- Network topology data (`data/network-topology.json`) gains an explicit
  `tailscale_ssh` block recording the enablement + ACL summary
- Security posture (`security-posture.md`) gains a note that Tailscale SSH
  is the first gate ahead of sshd, and that SSH key rotation only affects
  the sshd-authorized_keys path (not the Tailscale identity path, when
  used)
- ACL changes (any change to the `ssh` rule shape, action, src/dst/users
  fields) MUST be recorded as an amendment to this ADR (status:
  superseded → new ADR) or a §"ACL changes" appendix here, because the
  ACL is the de facto network-layer SSH governance and undocumented
  changes are how we got into the #575 hole in the first place

## ACL changes log

- **2026-06-09** — Action changed from `check` to `accept` (this ADR).
  Reason: Termius mobile cannot complete browser re-auth; phone-recovery
  for #572 was blocked.

(Future ACL changes record here.)

## References

- [`docs/runbooks/phone-termius-setup.md`](../../runbooks/phone-termius-setup.md) — operator runbook
- [`docs/design/architecture/data/network-topology.json`](../data/network-topology.json) — machine-readable network state
- [`docs/design/architecture/security-posture.md`](../security-posture.md) — broader security model
- kentonium3/kg-automation#575 — originating docs-debt issue
- Tailscale SSH docs: <https://tailscale.com/kb/1193/tailscale-ssh>
- Tailscale ACL `ssh` reference: <https://tailscale.com/kb/1337/policy-syntax#ssh>
