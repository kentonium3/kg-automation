---
id: coherence-doctrine
doc_type: policy
title: "Felix Doctrine — Scoped Invariants (INV)"
status: active
level: policy
audience: agents_and_humans
owners: [kgale]
last_validated: '2026-07-08'
version: '0.1'
tags: [coherence, doctrine, governance, invariants, bedrock, felix-core]
---

# Felix Doctrine — Scoped Invariants

> **Foundation 3 (coherence) — the *practice* tier.** This is the canonical, hand-authored
> list of Felix's cross-cutting invariants. Each `INV-###` stanza states a durable rule at
> *principle* altitude (what-not-how); mechanisms live in the relevant feature/build. Read
> this alongside [`decisions.jsonl`](<./decisions.jsonl>) (the decision corpus that establishes
> and cites these invariants) and the [practice guide](<./README.md>) (how the point-cut review
> uses them). Part of the [Bedrock Stabilization](<../felix-bedrock-stabilization.md>) program
> (epic #673); the deterministic selection/recording *machinery* is deferred to #643.

Stanza schema: `{id, intent, when, rules, check}`. Invariants are inert data — the agent does
the thinking; nothing here calls an LLM.

---

## INV-001 — The LLM never fabricates system state; deterministic plumbing it never touches

- **Intent:** Felix must never present a model-generated guess about system state (job status,
  completion, file state, service health, backup freshness) as fact. Deterministic facts come
  from deterministic sources; the model reasons *over* those facts, it does not manufacture them.
- **When:** any time an agent reports status/completion/health, acts on infrastructure state, or
  a spec/plan step is mechanically verifiable.
- **Rules:**
  - Mechanically-verifiable facts (a job ran, a file moved, a service is up, a backup is fresh)
    are produced by a helper/script — never asserted by the model.
  - An agent never claims an action succeeded without a deterministic signal (exit code, log
    line, file state, helper output) confirming it.
  - The model's role is judgment/classification/interpretation over plumbing-supplied facts —
    never the fabrication of those facts.
- **Check:** does every status/completion claim trace to a deterministic signal? A claim resting
  only on the model's say-so violates INV-001.
- *Provenance:* #562, #662, #683 → DEC-002.

## INV-002 — No silent fallback: a Felix-owned capability is handled only by its owner

- **Intent:** A capability with a designated owner is invoked *exclusively* through that owner.
  On failure it fails **safe** — stop, preserve the input, surface the failure — and never
  silently falls through to a raw or unscoped path. Protects correctness *and* cost.
- **When:** any capability that has a designated owner (calendar, email, drive, task, habit);
  any delegation/routing step; the design of any failure-handling path.
- **Rules:**
  - Invoke a capability only through its owner; never fall through to a raw/bundled tool
    (e.g. raw `gog`) when the owner path fails or is truncated.
  - On owner-path failure, fail-safe: do **not** mark the work complete, preserve the input,
    and surface the failure per INV-003.
  - Absence of an owner for a capability is an explicit "not supported" fail-safe — not an
    invitation to improvise a path.
- **Check:** on the failure path, does control ever reach a raw/unscoped executor instead of
  stopping and alerting? Does any step mark work done without the owner confirming success?
  Either violates INV-002.
- *Provenance:* Foundation 0 boundary ([`felix-openclaw-boundary.md`](<../felix-openclaw-boundary.md>)),
  #679, #680.

## INV-003 — One canonical alert stream, routed by audience

- **Intent:** All Felix alerts flow through a single canonical communication bus, routed by
  audience-role. No component invents its own ad-hoc notification path. Deterministic canaries
  are the must-always backstop; agent-delivered messages are best-effort.
- **When:** adding or changing any alerting / notification / escalation path; designing
  observability or any failure-surfacing behavior.
- **Rules:**
  - Emit alerts through the one canonical alert stream (the Foundation 1 communication bus /
    `felix-alert` seam) — do not hand-roll a new notification path per component.
  - Route by audience-role: user-facing → WhatsApp (best-effort); operator / must-always → ntfy
    (deterministic backstop; ntfy is the canonical push substrate).
  - Treat deterministic ntfy canaries as the must-always guarantee; a best-effort WhatsApp agent
    message is never the sole channel for a must-always alert.
- **Check:** does a new alert path route through the canonical bus and pick the correct audience
  channel? A component emitting its own notification, or relying on best-effort WhatsApp for a
  must-always signal, violates INV-003.
- *Provenance:* charter Foundation 1 (alerting seam), #512/#634 (noise-flood lesson), #269
  (out-of-band watchdog). *Mechanism* (the bus, `felix-alert`, ntfy topic taxonomy) is built by
  F1/#516 — this invariant forward-binds new alerting work to converge on it.

## INV-004 — Self-contained agent workspaces; do not factor out shared context

- **Intent:** Each OpenClaw agent workspace is self-contained. Agents do not depend on hidden
  shared inheritance, and shared boundaries are visible *at the agent level* rather than
  abstract-elsewhere.
- **When:** authoring or editing any agent workspace file (SOUL/USER/TOOLS/IDENTITY/AGENTS);
  proposing any shared-content mechanism.
- **Rules:**
  - Do **not** factor out, symlink, or compose shared context across agent workspaces.
  - Keep shared invariants consistent via workspace reconciliation + targeted CI lint (e.g. the
    privacy-boundary lint), **not** deduplication.
  - Each agent restates shared truths in its own workspace as a first-class customization surface.
- **Check:** does a change introduce a shared/inherited source for workspace content? That
  violates INV-004 (see DEC-001).
- *Provenance:* #553 → DEC-001; honored by the #167 per-agent authoring family.

## INV-005 — The private growth area is never touched

- **Intent:** Felix's hardest red line. The private area of the second brain is never read,
  written, referenced, or logged by any agent or script, under any circumstance. Listed here so
  the canonical invariant index is complete — enforcement lives elsewhere (see *Check*); this
  stanza is the statement, not the enforcer.
- **When:** any file access, search, ingestion, logging, or backup path that could traverse the
  second brain; any new agent or script granted filesystem or vault access.
- **Rules:**
  - `~/second-brain/notes/04-Growth/_private/` is never read, written, referenced, or logged by
    any agent or script under any circumstance.
  - No exception for debugging, indexing, backup manifests, or error messages.
  - New capabilities that traverse the vault must exclude this path *by construction*.
- **Check:** does any code path, log line, or capability enumerate/traverse the vault without
  excluding the private area? That violates INV-005. Enforced deterministically by the
  `tooling/scripts/validate_privacy_boundary.py` CI lint and restated in every agent workspace.
- *Provenance:* Felix Constitution (absolute rule); CLAUDE.md § "Second Brain Boundary".

## INV-006 — A fix is not "done" until behaviorally verified end-to-end

- **Intent:** A fix or capability is not complete until its real path has been exercised and its
  real outcome observed. Static signals (prompt text, config, greps, mocked unit tests) are
  necessary but never sufficient to declare something fixed, working, or done. Where INV-001
  governs the *runtime agent* (it must not fabricate state), INV-006 governs *us building and
  reporting fixes* (we must not infer success from static evidence).
- **When:** closing an issue as done; reporting a fix/completion; declaring a capability working;
  accepting a mission; any "it should work now" claim.
- **Rules:**
  - Run the real path and observe the real outcome before declaring done, closing, or reporting
    completion.
  - Static signals confirm *structure*, not *behavior* — they never substitute for exercising
    the live path.
  - If the path cannot be exercised, say so explicitly; do not infer success from static evidence.
- **Check:** does the completion/fix claim rest on an observed end-to-end run, or only on static
  signals? A "done" resting on static signals alone violates INV-006.
- *Provenance:* #662 (haiku→sonnet fix diagnosed from static evidence, later reversed), #679
  (static signals validated, path never run e2e), #683 (fabricated completion status) → DEC-006.
  Surfaced by the first F3 point-cut dry-run (2026-07-08).
