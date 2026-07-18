# felix-dev-autopilot

A formal, invokable agent that runs an autonomous fix-run end-to-end — pick
issue → scope → implement → test → review → PR → CI-gate → merge → deploy →
live-verify → next — keeping a running report and surfacing genuine decisions.
It captures the rules and guardrails from the 2026-07-18 overnight run
(reference execution) so the pattern is re-runnable on demand without
re-deriving them each time. See #777.

## Files

| File | Role |
|---|---|
| `felix-dev-autopilot-contract.md` | **Canonical, repo-agnostic operating contract** — the single source of truth. Prioritization, scope decision, standard vehicle, gate discipline, when-stuck, risk posture, reporting, backlog-hygiene, and the invocation input contract. |
| `adapters/<repo>.md` | **Per-repo mechanics** — gate command, deploy motion, live-verify, rebaseline rule, change-control tiers. The contract loads the adapter for the target `repo`. |
| `adapters/kg-automation.md` | The kg-automation (Felix / office2) adapter. |
| `adapters/_template.md` | Template for adding a new repo's adapter — makes "repo as a parameter" real. |

## How it is invoked

- **Global agent profile:** `~/.claude/agents/felix-dev-autopilot.md` (thin —
  points at this contract) makes it spawnable in any repo.
- **Slash command:** `~/.claude/commands/felix-dev-autopilot.md` →
  `/felix-dev-autopilot` with `repo` / `queue` / `risk_posture` args.

Both reference this contract rather than duplicating it — edit the rules HERE.

## Cross-repo

The contract is repo-agnostic; the packaging (global profile + slash command)
loads it and the target repo's adapter by absolute path — the same precedent as
the cross-repo standing rules (`.agents/rules/cross-repo-standing-rules.md`,
`@`-imported into the global CLAUDE.md). To run autopilot in a new repo, add an
adapter from `_template.md`; no change to the contract or packaging is needed.

## Input contract (recap)

Operator supplies at invocation: **`repo`** (→ loads its adapter), **`queue`**
(ordered issues; if omitted the agent proposes one and confirms), and
**`risk_posture`** (deploy tolerance + stop condition + any extra off-limits).
The agent restates the resolved envelope before the first fix.

## Reference execution

2026-07-18 overnight run on kg-automation — 10 fixes + 3 backlog closes shipped,
merged, deployed, and live-verified in ~3h with zero regressions; see this
repo's merge history around that date (e.g. PRs in the #762–#786 range).
