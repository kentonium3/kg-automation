# WP03 Review Feedback — cycle 1

**Verdict**: REQUEST-CHANGES
**Reviewer**: reviewer-renata (independent)
**Date**: 2026-08-29

The JSON reconciliation is exact, the forward reference is correct, and the restraint on the
"Kent (Mac)" SSH line was right (office4 has no `~/.ssh/config` at all). One HIGH defect, in
the file the WP itself identified as the high-judgement target.

## HIGH — `security-posture.md` asserts two things observable state contradicts

**Clause 1** — "the other three are unmanaged peers that run no service **and expose no
port**." False for office4. Verified on the host:

```
$ ss -tln
LISTEN 0 4096        0.0.0.0:22       0.0.0.0:*
LISTEN 0 4096  100.112.83.28:58266    0.0.0.0:*
$ systemctl is-active ssh sshd   → active / active
$ awk '{print $NF}' ~/.ssh/authorized_keys
kgale@mac
macbook-to-office2
$ grep -rn ListenAddress /etc/ssh/sshd_config /etc/ssh/sshd_config.d/
  (all commented out — binds all interfaces)
```

sshd is active on all interfaces with two deliberately provisioned Mac keys, and a second
socket is bound directly to office4's Tailscale IP.

**Clause 2** — "so **the two SSH gates below describe office2 alone**." Only gate 1 is
office2-only. Gate 2 is "**sshd** (authentication) — standard OpenSSH authentication using
`~/.ssh/authorized_keys` per user", which demonstrably operates on office4 too.

**Root cause**: conflating "Tailscale SSH is off" with "no SSH exposure". `RunSSH: false`
means tailscaled does not intercept :22 and apply the tailnet ACL — it says nothing about
whether a port is open. research.md R-12 established only the RunSSH fact. The WP asserted a
negative security property its own research does not support.

This is the same failure mode the WP correctly *avoided* on the "Kent (Mac)" line — there it
declined to assert an unverified fact; here it asserted one. Note `physical-topology.md:92`
gets it right ("tailscaled does not intercept port 22 there"); only the security-posture
sentence overreaches.

**Required fix**: claim only what is verified — no **registered** service (none appears in
`service-inventory.json`), Tailscale SSH off so gate 1 is office2-only, but standard sshd
does run on office4 over the tailnet, authenticated by `authorized_keys`, i.e. gate 2 applies
there with no ACL layer in front of it.

**Cross-WP**: the identical false phrase was in WP01's `network-topology.json` `updated_by`.
WP01 was reopened and fixed. Both must land or the authoritative JSON and the prose would
agree on something untrue.

## LOW — `physical-topology.md`, two adjacent near-duplicate bullets

Two consecutive bullets both open "**Tailscale SSH is enabled on office2…**". Reads as an
editing accident. Fold the office4 sentence into the existing detailed bullet.

## LOW — `security-posture.md`, "Agents must always use the claude user"

Now has a live counterexample: an agent is running as `kgale` on office4. The new scope
paragraph above covers a careful reader, but a two-word qualifier ("…on office2") closes it
outright.

## Verified NOT wrong (do not change)

- The privacy-boundary paragraph ("synced only to Kent's laptop and phone… office2 never
  joins that vault") is still true — office4 has no vault and no `04-Growth`/`_private`
  anywhere under `/home/kgale`.
- office4 sitting under the `## Hosts` heading while its body says "not a managed host" is a
  pre-existing shape: the MacBook Pro and iPhone were already there, and
  `hardware-inventory.json`'s own top-level key is `hosts`. Following the authoritative JSON
  is the charter rule.
