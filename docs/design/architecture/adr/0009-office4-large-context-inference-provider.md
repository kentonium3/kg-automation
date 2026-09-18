---
title: ADR-0009 — Large-context inference on office4 as a best-effort provider behind a per-function fallback seam
doc_type: reference
status: in_review
owners: ["@kentonium3"]
last_updated: '2026-09-18'
version: v1.0
audience: agents_and_humans
tags: [986, 974, 908, 909]
---

# ADR-0009 — Large-context inference on office4 as a best-effort provider behind a per-function fallback seam

**Status**: Proposed — awaiting Kent's approval
**Date**: 2026-09-18
**Deciders**: Kent Gale

## Context

Felix needs large-context reasoning — the life-coach overlay reasons over a world-model that grows with
the second brain, and [#849](https://github.com/kentonium3/kg-automation/issues/849) exists to measure
how large that context has to be.

**office2 cannot host it.** office2 has 32GB shared with the live stack; a 300k-token KV cache is many
GB of live memory on top of the model weights. office4 — Framework Desktop, Strix Halo (Ryzen AI Max+
395), 128GB unified memory, Radeon 8060S — can, and already does: the
[#974](https://github.com/kentonium3/kg-automation/issues/974) spike ran Qwen3-Next-80B-A3B-Instruct
(UD-Q4_K_XL, 46GB) under llama.cpp Vulkan at ~16s/episode, at **zero marginal cost**, and the GGUF was
deliberately preserved at `~/models/gguf/unsloth/` with `SHA256SUMS` and `SOURCE.md`.

**The placement test has a gap here.** [ADR-0008](<./0008-three-machine-model.md>) governs workload
placement, and its first question is a gate:

> **1. Must this run when nobody is watching?** If yes → **office2**, regardless of what an outage costs.

Felix runs unattended on office2. Reasoning triggered on a schedule or by inbound events fails that
question and routes to office2 — **the one machine that cannot run it.** ADR-0008 contains the
near-miss and shows why it is not this case: its *Worked case B* sends "a local model server for a
coding session" to office4 precisely because it serves a human who is present. Here the consumer is
unattended Felix.

The gap is specific and worth naming for future placement decisions: ADR-0008's test assumes every
candidate workload **can** run on the machine the test selects. It has no branch for a workload whose
*capacity requirement* excludes that machine.

**The enabling context.** [RFC #986](https://github.com/kentonium3/kg-automation/issues/986) proposes
that inference provider, model, and location become a **per-function configuration seam** rather than a
global constant. Kent's ruling (2026-09-18): *"large-context reasoning must run on office4 and Felix
needs to be able to access it like it would vendor supplied reasoning."* That phrasing is what makes
this decision possible — if office4 is *a provider* rather than *a host Felix depends on*, the
unattended obligation can be met somewhere other than office4.

## Decision

**1. Large-context inference runs on office4**, served over HTTP on office4's tailnet interface.

**2. Felix consumes it as a provider behind RFC #986's per-function seam** — the same interface as any
vendor. `llama-server` already exposes an **OpenAI-compatible `/v1` API**, so this is a base-URL and
model-name configuration, not an adapter layer.

**3. It is a *best-effort* provider. Every consuming function must declare a fallback** — a vendor
provider, a smaller local model, or an explicit defer. **No function may rely on office4 being
available to discharge an unattended obligation.** A function that cannot fall back must declare
itself defer-capable, and is thereby accepted as *not unattended-capable*. That declaration is
per-function and explicit; it is never assumed globally.

**This is how ADR-0008's question 1 is satisfied: by the fallback, not by office4.** The unattended
obligation is discharged on the fallback path, which does not depend on an attended machine.

**4. office4 remains an unmanaged peer. This ADR does not supersede ADR-0008's managed-host decision.**
None of ADR-0008's five single-host subsystems (manifest schema, deploy-lock namespace, deployer
`DEFAULT_REPO_ROOT`, rebaseline registry, tier guard) is changed, extended, or parameterised.

**5. The service is operator-managed.** No deploy manifest, no `felix-deployer` involvement, no second
`kg-automation` checkout at a deployer-recognisable path. Kent starts, updates, and stops it. A
**systemd user unit on office4** is permitted for boot persistence; it is operator infrastructure, not
a registered deploy target.

**6. It is nonetheless registered in the architecture store** — a `service-inventory.json` entry
recording `host: office4`, plus a port assignment and access rule in `network-topology.json`.

Registration does **not** make office4 managed, and ADR-0008 is explicit on the point: *"What defines
managed status is this ADR and the deploy/audit mechanisms — nothing else... A managed host could
temporarily run zero registered services without ceasing to be managed... They are evidence; this ADR
is the authority."* Recording the service buys visibility; it changes no deploy or audit mechanism.
This will be the **first** non-office2 row in `service-inventory.json` (47 of 47 are office2 today) and
office4's first registered tailnet service surface.

## Why this is narrower than the alternative ADR-0008 rejected

ADR-0008 rejected *"Run a subset of services on office4, short of full managed status"* as **"the worst
of both."** This decision is a narrow instance of that shape, so the rejection must be answered rather
than ignored. Its three stated reasons, each addressed:

| ADR-0008's objection | Why it does not bite here |
|---|---|
| *"creates a second deploy path with no manifest, no lock"* | It creates **no deploy path at all.** There is no automated deploy to be a second of — the service is operator-started on an attended machine. |
| *"`self-pull` makes 'which checkout is the deploy' ambiguous the moment a second recognisable checkout exists"* | No checkout is added. office4's existing checkout is `/home/kgale/repos/kg-automation`, which ADR-0008 explicitly blesses as **not** a breach; the deployer resolves `/home/claude/kg-automation`, which office4 does not present. |
| *"no audit baseline"* | Accepted, and the surface is far smaller than the objection assumes: the service is **stateless compute** serving a read-only GGUF. It holds no application state, no credentials, and no production or vault data. |

The honest summary: ADR-0008 rejected a *general* practice of splitting registered services across
hosts. This authorises **one stateless, operator-managed, fallback-guarded compute endpoint** whose
absence is designed to be survivable. If a second such service is ever proposed, that is the moment to
revisit ADR-0008 properly rather than stretch this one.

## Consequences

**Positive.**
- Unblocks large-context reasoning, which office2 cannot host at any configuration.
- Makes RFC #986's seam **load-bearing rather than aspirational** — per-function fallback is the
  mechanism that reconciles this with ADR-0008, not a convenience.
- Local inference is the favourable posture for the [#696](https://github.com/kentonium3/kg-automation/issues/696)
  privacy gate: episode text never leaves the tailnet.
- Zero marginal inference cost on the office4 path, against a trajectory where inference cost is
  expected to become the practical limit on Felix's capacity (RFC #986 context).

**Negative.**
- **Availability is genuinely best-effort.** office4 is attended: it reboots, gets upgraded, and Kent
  may be using the GPU. Consumers must treat unavailability as normal, not exceptional.
- **The service is unaudited.** office4 has no security-monitor baselines; the daily audit covers
  office2 only. Accepted, bounded by the stateless/credential-free property above.
- **Functions that cannot fall back are not unattended-capable**, which narrows what the life-coach
  overlay can promise until either a fallback exists or office4 availability is hardened.
- **New tailnet attack surface.** office4 exposes no registered service today. An unauthenticated
  inference endpoint would be reachable by any tailnet device — see open items.
- **Operator toil.** Kent is the restart mechanism.

**Neutral.**
- office4's class is unchanged: unmanaged peer, kgale-only, no `claude`/`codex` users, no
  felix-deployer target.
- ADR-0008 stands. This ADR refines placement for a case ADR-0008 did not anticipate; it supersedes
  nothing.

## Alternatives considered

**Supersede ADR-0008 and make office4 a managed host.** Rejected on cost, not principle — unchanged
from ADR-0008's own reasoning. It requires coordinated change across five subsystems, the first of
which (`deploys/schema/manifest-v1.schema.json`, `additionalProperties: false`, no `host` field) would
**reject** a host-bearing manifest outright. Nothing here needs it. The option stays open and would
begin with an ADR superseding ADR-0008.

**Vendor-hosted large-context inference only.** Rejected. Cost is the motivating constraint: API spend
was a reason [#692](https://github.com/kentonium3/kg-automation/issues/692) stalled, and at the volumes
the life-coach overlay implies it becomes the binding limit on capacity and quality. Vendor inference
remains the **fallback**, which is the right role for it.

**Upgrade office2's memory so it can host large-context inference.** Not evaluated here. It is a
hardware-procurement path, it does not use the capacity and model office4 already has, and it would put
a long-running GPU/memory-intensive workload on the unattended host that runs all 47 registered
services. Worth revisiting only if the fallback discipline proves unworkable.

**Hard dependency on office4 with no fallback.** Rejected outright — it violates ADR-0008's question 1
rather than satisfying it, and makes an unattended system depend on an attended machine.

## Open items (not decided by this ADR)

- **Endpoint authentication.** The tailnet is the boundary today, but ADR-0004's ACL governs *SSH*, not
  HTTP. An unauthenticated `/v1` endpoint is reachable by every tailnet device. Decide auth (bearer
  token, or a Tailscale ACL restricting the port to office2) before the endpoint binds beyond loopback.
- **Port assignment** for the inference endpoint, and the matching `network-topology.json` access rule.
- **Which functions are defer-capable** — the per-function declaration required by decision 3.
- **Cloud VM as a third inference location**, named in RFC #986 and unanalysed for cost, security, or
  data boundary.
- **Model lifecycle on office4** — who updates the GGUF, and how a model change is recorded given the
  service is outside the manifest pipeline.

## References

- [RFC #986](https://github.com/kentonium3/kg-automation/issues/986) — inference provider/model flexibility seam; this ADR is its first concrete instance
- [#974](https://github.com/kentonium3/kg-automation/issues/974) — typed-entity spike; measured local inference on office4, preserved the GGUF
- [#849](https://github.com/kentonium3/kg-automation/issues/849) — decisive test that will size the context requirement
- [#692](https://github.com/kentonium3/kg-automation/issues/692) — Second Brain Graph Layer epic
- [#696](https://github.com/kentonium3/kg-automation/issues/696) — privacy gate
- [ADR-0008](<./0008-three-machine-model.md>) — three-machine model; the placement test this ADR extends
- [ADR-0004](<./0004-tailscale-ssh-with-accept-acl.md>) — Tailscale SSH accept ACL; its ACL changes log is where tailnet SSH-rule matters are recorded
- `docs/design/architecture/data/service-inventory.json`, `network-topology.json`, `hardware-inventory.json`
