---
title: ADR-0008 — Three-machine model; office2 managed, MacBook Pro and office4 unmanaged peers
doc_type: reference
status: approved
owners: ["@kentonium3"]
last_updated: '2026-08-29'
version: v1.0
audience: agents_and_humans
tags: [909, 908, 910, 917]
---

# ADR-0008 — Three-machine model; office2 managed, MacBook Pro and office4 unmanaged peers

**Status**: Accepted
**Date**: 2026-08-29
**Deciders**: Kent Gale

## Context

office4 joined the tailnet in August 2026 and became Kent's primary development machine. It
is a Framework Desktop (AMD Ryzen AI Max 300 Series) running Linux Mint 22.3 on a noble
base — and, like office2, it is always on.

That last fact is what made a decision necessary. Every previous non-office2 device was
obviously not a server: a laptop that closes, a phone in a pocket. office4 is neither. It is
a powerful, always-on Linux box sitting on the same tailnet as the managed host, and the
intuitive conclusion — "it's always up, so it can run things" — is wrong in a way that is
expensive to discover later.

Meanwhile the decisions that shaped the migration existed only in a local plan file and in
GitHub issue comments. Nothing in the architecture store said what office4 was, whether
changes reach it through the `deploys/queued/` manifest pipeline, or where a new workload
belongs. That is the same drift class that produced the undocumented `codex` account
(#917) — found live before it was found in documentation.

This ADR records the boundary so later sessions inherit it instead of re-deriving it, or
violating it by accident because nothing said it was a constraint.

## Decision

The system has **three machines** in two classes.

| Machine | Class | Role |
|---|---|---|
| **office2** | **managed host** | Always-on, unattended hub. Runs all registered services. The felix-deployer target. |
| **kents-macbook-pro** | unmanaged peer | Attended authoring and interaction endpoint |
| **office4** | unmanaged peer | Attended primary development machine |

(The iPhone is a fourth tailnet device, recorded in the device inventories, but it is a
capture and monitoring endpoint rather than a machine in this sense.)

**What defines managed status is this ADR and the deploy/audit mechanisms — nothing else.**

That distinction matters more than it looks. Two facts corroborate the decision: every
entry in `service-inventory.json` names `host: office2` (47 of 47 as of 2026-08-29), and
office2 is the only host with a rich `hardware-inventory.json` record. **Neither fact is
the definition.** A managed host could temporarily run zero registered services without
ceasing to be managed, and
documenting a peer's hardware in detail would not make it managed. If inventory contents
were treated as the definition, an ordinary documentation edit would appear to change the
architecture. They are evidence; this ADR is the authority.

office4 is registered in `network-topology.json` and in `hardware-inventory.json` — every
tailnet device belongs in the device record — and is deliberately absent from
`service-inventory.json`.

## The governing principle: office2 is unattended, office4 is attended

**Uptime is not the axis that separates these machines.** office4 *is* always-on. Anyone
reasoning from "always-on ⇒ can host services" will place work wrongly.

The axis is **attendedness**: whether a human is present to notice a failure. office2 runs
unwatched, so its failures must be survivable without a human. office4 runs where Kent is
working, so its failures are noticed in minutes.

### The placement test

Two questions, in order. The first is the gate; the second only breaks ties among what
survives it.

> **1. Must this run when nobody is watching?**
> If yes → **office2**, regardless of what an outage costs.
>
> **2. If it may run attended, then: ten unwatched minutes down — is the cost recoverable?**
> - **Unrecoverable → office2.**
> - **Recoverable → office4.**

The ordering matters, and an earlier draft of this ADR had only question 2. That version
failed on a real workload: `felix-deployer` holds a durable queue under `deploys/queued/`, so
ten minutes down loses nothing and costs only delay — "recoverable", which question 2 alone
routes to **office4**, contradicting this very ADR's statement that office2 is the sole
deployer target. The defect was that a binary recoverable/unrecoverable test silently assumes
every candidate workload *may* be attended. Question 1 makes that assumption explicit, and
`felix-deployer` — which must apply merges to `main` whether or not Kent is at a keyboard —
fails it immediately.

**Worked case A — the nightly Restic backup.** `restic-backup` is `type: cron`, schedule
`0 4 * * *`, and it lives in a *user* crontab, so anacron does not cover it either. Plain
cron has **no catch-up**: if the host is down at 04:00, that run does not happen later, it
simply does not happen. Contrast the repo's calendar timers — `backup-script-drift`
(`OnCalendar=daily`) and `credential-health-check` (`OnCalendar=*-*-* 13:00:00`) — which
carry `Persistent=true` precisely so they *do* fire after downtime.

The loss is not silent: `restic-backup` declares a 28-hour freshness bound
(`max_age_seconds: 100800`) and `felix-canary` raises an ERROR when the pointer goes stale,
so a missed 04:00 run surfaces around 08:00. **But detection is not recovery.** No later run
recreates a snapshot that was never taken, and a human sitting at the machine at 04:10 could
not have brought it back either — the window is simply gone. That is what makes the cost
**unrecoverable** rather than merely annoying, and it is why question 2 asks about recovery,
not about whether anyone notices. (It also fails question 1 — a 04:00 backup is unattended by
definition — so it lands on office2 twice over.) **office2.**

**Worked case B — a local model server for a coding session.** It exists only to serve a
human who is present, so it passes question 1: it need not run unattended. Then question 2 —
ten unwatched minutes down means Kent's next completion fails and he restarts it, because he
is sitting there. Nothing is lost; the cost is recoverable. **office4.**

**Worked case C — `felix-deployer`.** It must apply merges to `main` on a five-minute timer
whether or not anyone is present, so it fails question 1 and stops there. Note that question 2
alone would have sent it to office4, since its queue is durable and an outage costs only
delay — which is exactly why question 1 comes first. **office2.**

Question 2 is deliberately about the *unwatched* interval, not about how important the
workload feels. Important work that fails loudly in front of a human is safer on office4 than
trivial work that fails silently. But question 1 outranks it: a workload with an unattended
obligation belongs on office2 even when every individual failure would be cheap.

## Why office4 is deliberately not a managed host

Not caution, and not a preference. Felix's deployment substrate is **single-host in code**,
not by convention. Five independent places encode office2 specifically:

1. **`deploys/schema/manifest-v1.schema.json`** — a deploy manifest has no `host` field, and
   the schema sets `"additionalProperties": false` at the top level. A manifest that named a
   host would be **rejected by the schema**, not merely unsupported. There is no seam here to
   extend; there is a closed door.
2. **`scripts/deploy/lib/deploylock.py:41`** — the **default** deploy-lock path is
   `/data/services/deploy/locks/office2-checkout.lock`. It is overridable via the
   `DEPLOY_CHECKOUT_LOCK` environment variable (line 37), which nothing in the pipeline
   sets. The lock namespace assumes one checkout on one host.
3. **`scripts/deploy/felix-deployer/_tick.py:59`** — `DEFAULT_REPO_ROOT` **defaults to**
   office2's path (`/home/claude/kg-automation`). An override parameter exists at line 404
   for test fixtures, but nothing in the pipeline supplies one.
4. **`scripts/deploy/felix-deployer/rebaseline.py:49`** — the module docstring explains that
   the registry's `rebaseline_command` stores the operator form (`ssh office2-claude '…'`)
   and that felix-deployer **strips the SSH wrapper because it runs on office2**. The code
   assumes it *is* the host it manages.
5. **`scripts/deploy/lib/tier.py:73`** — the Tier 0 guard's own message embeds
   `ssh office2-kgale`.

Add to this that `self-pull` means **merging to `main` is the deploy**. There is no separate
"push to host" step whose target could be parameterised.

Making office4 a managed host is therefore a design change across five subsystems —
manifest schema, lock namespacing, deployer tick, baseline registry, and tier guard — and
nothing in this migration required it. The cost is real and the benefit is currently zero.

## Constraints that follow

### office4 must hold no `kg-automation` checkout at a felix-deployer-recognisable path

Because `self-pull` makes "merging to `main`" the deploy, the identity of *the* checkout is
load-bearing. A second checkout at a path the deployer recognises makes "which checkout is
the deploy" ambiguous, and the failure mode is silent divergence rather than an error.

**What "recognisable" means, concretely.** The recognised path is whatever
felix-deployer's `repo_root` resolves to — by default `DEFAULT_REPO_ROOT` in
`scripts/deploy/felix-deployer/_tick.py:59`, which is `/home/claude/kg-automation`. Nothing
in the pipeline supplies the line-404 override, so in practice that default *is* the path.

So, to be unambiguous about the case that actually exists: office4 holds a checkout at
`/home/kgale/repos/kg-automation`, and that is **not** a breach — it is not the path the
deployer resolves, and nothing about it makes "which checkout is the deploy" ambiguous. This
ADR was itself authored from that checkout.

Nothing occupies `/home/claude/kg-automation` on office4 today, since office4 has no `claude`
user and no `/home/claude`. Be precise about what that is: **current state, not a guard.** A
directory under `/home` needs no matching Unix account — office4 already carries a
`/home/linuxbrew` with no `linuxbrew` user — and the deployer never consults the passwd
database at all; `DEFAULT_REPO_ROOT` is a bare path constant. The no-`claude`-user constraint
below removes the *reason* anyone would create that path. It does not remove the ability.

The constraint therefore bites if someone creates `/home/claude/kg-automation` on office4,
relocates the deployer's repo root to a path office4 does present, or otherwise arranges for
office4 to hold a checkout where the deployer looks.

**Nothing enforces this mechanically.** It is documentation only. Mechanical enforcement
would require the lock-namespacing and repo-root changes this decision explicitly declines
to make. A future session that places a checkout on office4 will not be stopped by a guard —
only by having read this.

### office4 has no `claude` or `codex` Unix users

The office2 `claude` user exists because there the agent is a **remote actor on a host it
does not live on**: a separate account gives attribution in logs and bounds blast radius,
which is why it has no sudo.

office4 inverts that premise. The agent *lives* there — it needs Kent's repos, his git
identity, his config trees, and his SSH agent. A separate Unix user would firewall it from
exactly the things it exists to work with, buying attribution that is meaningless on a
single-user attended workstation. So office4 is kgale-only.

## Alternatives Considered

**Make office4 a second managed host.** Rejected on cost, not principle. It requires
coordinated change across all five subsystems enumerated in *Why office4 is deliberately not
a managed host* above — and the first of them, the manifest schema, would reject a
host-bearing manifest outright rather than merely ignore it. Nothing in this migration needed
any of that. The option stays open; taking it means superseding this ADR, not quietly
extending the schema.

**Run a subset of services on office4, short of full managed status.** Rejected as the worst
of both. It creates a second deploy path with no manifest, no lock, and no audit baseline,
while `self-pull` makes "which checkout is the deploy" ambiguous the moment a second
recognisable checkout exists. The result would be infrastructure that is neither managed nor
honestly unmanaged — precisely the ambiguity this ADR exists to remove.

**Leave office4 undocumented and decide case by case.** Rejected because that is the failure
mode already observed: the undocumented `codex` account (#917) was found live before it was
found in documentation. An always-on Linux box on the tailnet invites the intuition
"always-on, therefore it can host things"; without a recorded constraint, that intuition
wins by default and nobody notices until something unattended is running where nobody is
attending.

## Consequences

**Easier.** The office2/office4 boundary is now answerable from the architecture store
rather than re-derived per session. Placement decisions have a test rather than an argument.
The deployment substrate stays simple: one host, one checkout, one lock, no host
parameterisation anywhere.

**Harder.** Anything that genuinely needs to run unattended must go on office2 even when
office4 has more capacity — and office4 does have more capacity. That tension is real and is
accepted deliberately; it is the price of not rebuilding the substrate.

**Unenforced.** Both constraints above are documentation, not guards. This ADR is the only
thing standing between them and an accidental breach.

**Revisiting this.** The `service-inventory.json` exclusion is a decision, not a property of
the schema — office4 *could* become a managed host. But that path runs through the five
subsystems named above, and it starts by **authoring a new ADR that supersedes the relevant
decision here**. ADRs in this repo are immutable once approved; superseded decisions get a
new ADR that references the prior one (`docs/design/architecture/adr/README.md`). Quietly
adding a service row on office4, or editing this ADR in place, are both wrong.

### Review-only affirmations

Two documents were reviewed for impact and are recorded here so that "read and unchanged" is
distinguishable from "never opened".

**[ADR-0004 — Tailscale SSH with accept ACL](<./0004-tailscale-ssh-with-accept-acl.md>) —
reviewed, unchanged.** office4 joining as a member device does widen the nominal scope of
that ACL (`autogroup:member` → `autogroup:self`, users `autogroup:nonroot, root`). What makes
the widening immaterial is that **Tailscale SSH is off on office4**:

```
$ tailscale debug prefs | grep RunSSH
        "RunSSH": false,
```

`tailscaled` therefore does not intercept port 22 on office4's Tailscale IP, and ADR-0004's
accept-passthrough behaviour has nothing to act on. This is the same standard of proof
`network-topology.json` names in its own `tailscale_ssh.verified_via` field for office2, so
the second machine is held to the standard the first already was.

**`docs/runbooks/phone-termius-setup.md` — reviewed, unchanged.** It documents SSH access
from the iPhone to office2 specifically. office4 adds no phone-facing surface, enables no
Tailscale SSH, and changes nothing the runbook depends on.

## References

- Issue [#909](https://github.com/kentonium3/kg-automation/issues/909) — this decision's mission
- Epic [#908](https://github.com/kentonium3/kg-automation/issues/908) — office4 migration
- Issue [#910](https://github.com/kentonium3/kg-automation/issues/910) — office4 Phase 1: host baseline and Python strategy
- Issue [#917](https://github.com/kentonium3/kg-automation/issues/917) — the undocumented `codex` account, the drift class this ADR guards against
- [ADR-0004](<./0004-tailscale-ssh-with-accept-acl.md>) — Tailscale SSH accept ACL
- `docs/design/architecture/data/network-topology.json`, `hardware-inventory.json`, `service-inventory.json`
