# WP01 Review Feedback — cycle 1 (reopened after WP03 review)

**Verdict**: REQUEST-CHANGES
**Origin**: surfaced by the WP03 review; WP01 had already been approved when this was found.
**Date**: 2026-08-29

## HIGH — `network-topology.json` `updated_by` asserts a false security property

The `updated_by` clause added by WP01 reads:

> "…office4 is an unmanaged peer, runs no registered service, **enables no Tailscale SSH
> (RunSSH: false) and exposes no port**, so tailscale_ssh, port_assignments and access_rules
> are unchanged"

**"exposes no port" is false.** Verified on office4 directly:

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

sshd is active on `0.0.0.0:22`, with no `ListenAddress` restriction, carrying two
deliberately provisioned Mac public keys. A second socket is bound directly to office4's
Tailscale IP on :58266 (process name requires root; not investigated further — Tier 0).

The error is a conflation: `RunSSH: false` means **Tailscale SSH** is off — tailscaled does
not intercept port 22 and apply the tailnet ACL. It does **not** mean no port is exposed.
Standard sshd is running and reachable over the tailnet. research.md R-12 established only
the `RunSSH: false` fact; "exposes no port" was never supported by it.

This matters more here than in prose: `network-topology.json` is the **authoritative**
record, and repo doctrine says the machine-readable version wins when JSON and markdown
disagree. Shipping a false security claim into the authoritative file is the worst place for
it to live.

**Required fix**: rewrite the `updated_by` clause to claim only what is verified — office4
is an unmanaged peer that runs **no registered service** and has **Tailscale SSH off**
(`RunSSH: false`), which is why `tailscale_ssh` is unchanged. Drop "exposes no port"
entirely. Do not replace it with a different unverified negative.

**Note**: the same false phrase appears in WP03's `security-posture.md`; that copy is fixed
under WP03's own cycle-1 feedback. Both must land, or the JSON and the prose will agree on
something untrue.

## Everything else from the original review stands

The prior approval verified — independently, on the live host — that `os` and `hardware`
match `/etc/os-release` and sysfs byte for byte, that office4 was appended so office2 stays
`hosts[0]` for `ollama-ops.md:30`, that the thin form has exactly five keys, that both
`schema_version` values are untouched, that `service-inventory.json` is unmodified, and that
formatting fidelity is clean. None of that is disturbed by this fix, which touches only the
`updated_by` string.
