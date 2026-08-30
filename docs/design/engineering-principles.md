---
title: kg-automation Engineering Principles
doc_type: standard
status: approved
last_updated: '2026-08-30'
last_validated: '2026-08-30'
owners: [kgale]
version: '1.2'
tags: [architecture, principles, governance]
---

# kg-automation Engineering Principles

These principles sit between broad Felix governance and individual feature
specs. They are intended to guide new work before it creates retrofit debt.

Principles 1–10 approved 2026-06-05 from the architecture review report at
`docs/research/kg-automation-architecture-review/`. CLAUDE.md's "Engineering
Principles" section points here; the sibling `docs/design/helper-script-conventions.md`
is the doc referenced from Felix Constitution Directive 6.

Principles 11–13 added 2026-06-19 (kentonium3/kg-automation#624), adapted from
the [system-design-primer](https://github.com/donnemartin/system-design-primer)
and selected for a single-server, solo-operator system. The charter's
`## Design Principles` section is the spec-kitty-active subset that cross-references
these entries.

## 1. Runtime Truth Must Have a Machine-Readable State

Every deployed or scheduled component needs one authoritative state signal that
can represent at least:

- `healthy`
- `degraded`
- `failed`
- `stale`
- `disabled`
- `suspended`

A stale `success` file is not a valid representation of suspension.

## 2. Deterministic Work Belongs Behind a Contract

If correctness can be verified mechanically, put it behind a helper, library, or
schema rather than in an agent prompt. Use the helper/library/skill distinction
from `docs/design/helper-script-conventions.md` once approved.

## 3. Integration Clients Are Shared Boundaries

External systems such as Vikunja, GitHub, Anthropic, OpenClaw, Tailscale, and
the vault should have shared client/config boundaries once two domains need the
same behavior. Repeated URL, token, timeout, retry, and error-message logic is a
design smell.

## 4. Authoritative JSON Must Be Semantically Validated

If a JSON file is policy-authoritative, CI should validate more than parseability.
Dates, enum values, required fields, lifecycle states, health-check requirements,
and schema-version rules should be checked automatically.

## 5. Tests Are Part of the Architecture

A test suite that is not run in CI is documentation, not enforcement. All
non-live tests should run on push to `main`; live smoke tests stay opt-in.

## 6. Privacy Boundaries Need Both Policy and Enforcement

The constitution names the boundary; code, prompts, templates, registries, and
CI linting must enforce the same current boundary. Historical boundary names
belong only in migration history with explicit context.

## 7. Active Script Surfaces Must Not Preserve Deprecated Patterns

Scripts in active paths are copyable examples. If a script is no longer a valid
pattern, archive it or mark it loudly as historical. Migration completeness
includes removing obsolete operational examples.

## 8. Suspension Is an Operational State, Not an Absence of Scheduling

Cost-control or operator-paused components should be represented as suspended in
service inventory, runbooks, health checks, and status signals. Disabled timers
alone are not enough.

## 9. Feature Specs Must Ask "How Will We Know This Broke?"

Architecture impact should include observability impact. Every new deployed
component, scheduled job, or automation path should define its health signal,
failure observer, and response route before implementation.

## 10. Prefer Small Guardrails Over Large Retrofits

When a pattern recurs, add a small validator, template checkbox, shared helper,
or issue-template prompt while the pattern is still small. Avoid waiting until a
Felix-wide retrofit is necessary.

## 11. Retryable Operations Must Be Idempotent

Any operation that can fire more than once — cron-triggered runs, agent actions
that may be retried, deploy applies, task/inbox creation — must be safe to replay
without duplicating or corrupting state. Creation paths check for an existing
record before inserting; partial-update APIs are treated as read-modify-write
(e.g. Vikunja POST zeroes unstated fields); deploy applies are gated and
re-runnable. A second identical run that yields different state is a defect, not
an edge case.

## 12. Decouple Producers and Consumers

Components that hand work to each other should communicate through a durable queue
or a polled store, not a tight synchronous call, so that a slow or failed
component degrades locally instead of blocking the rest. The inbox is a file queue
drained by cron; Felix↔Vikunja sync is ~5-minute polling rather than webhooks. New
agent-to-agent paths default to a queue/poll boundary. This principle grows in
weight as more agents are added.

## 13. No Single Point of Failure Without a Recovery Path

For each new stateful component, identify what its loss would stop and ensure a
recovery path exists. On a deliberately single-host system (office2) the
mitigation is backup + degraded-mode operation, not redundancy: Tier 2 changes
require a Restic snapshot ≤24h, the daily security audit and felix-deployer are
the drift safety nets, and any new stateful dependency documents how it is
restored. A component whose loss is unrecoverable and undocumented is a latent
outage.

## 14. A Check Must Distinguish "Verified False" From "Could Not Check"

The dominant defect class in verification code: an assertion that reports green
when it merely failed to look. It is the same end state as no check at all, but
worse — it buys false confidence and suppresses the investigation that would have
found the problem.

Real instances, all shipped and all caught only by adversarial review (#911,
portable-dotfiles): every assertion was *relative*, so a machine with no package
manager on PATH scored 6/6 PASS; the verifier ran under the config it was
auditing, so an `exit 0` there produced no output and exit 0 — the gate satisfied
*by* the breakage; "no probe output" compared equal to "no probe output" and
reported "all three agree"; `--only` with an unknown id ran nothing and exited 0;
a drift check passed when it could not reach the remote; a remote probe *skipped*
green for a reachable host whose shell was broken, which was the exact divergence
it existed to catch.

**Applying it.** For every assertion ask: *what machine state would make this
report PASS or SKIP while the property is violated?* Make "could not check" a
failure, not a pass and not a silent skip. Anchor to an absolute expectation
rather than internal consistency — three shells agreeing with each other agree
perfectly on being uniformly broken. A SKIP must name precisely what went
unverified. And beware the mirror failure: a check that is *always* red, because
a permanently red gate stops being read and ends in the same place.

This is the second time this pattern has been recorded (see also the 2026-08-27
run, where five instances appeared in a single day). Treat it as the first thing
to hunt for when reviewing any helper whose exit status gates something.

## 15. Never Operate on `$HOME` Without Setting It Explicitly

Any script that reads or writes `$HOME` gets `env HOME=<fixture>` on **every**
invocation, including the one-off verification dashed off at the end. Unset is
not safe either: zsh repopulates `$HOME` from the password database.

This is written from damage. During #911 a generated `restore.sh` was run without
`HOME` set while testing against a throwaway fixture; it executed against the real
home and destroyed four dotfiles. One was reconstructed from documented evidence
and is not byte-exact — that content is gone.

**Applying it.** Build the guard into the artifact, not just the habit: a script
that mutates `$HOME` should record the home it was generated for and refuse
another, and any force override should list what it will destroy and require
confirmation. Two corollaries, both learned the same day:

- **Reconcile before you replace.** Before swapping any config file, diff the live
  one against its replacement and decide explicitly what carries over. Doing this
  found six items a swap would have dropped silently; not doing it is what cost
  the unrecoverable file.
- **A fixture that differs in the load-bearing way proves nothing.** A rehearsal
  reported the wrong interpreter and failed — caused entirely by the fixture
  lacking the one path the design depends on. Link in whatever the config
  references, or the rehearsal is theatre.
