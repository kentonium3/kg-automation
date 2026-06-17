# Feature Specification: Felix exec host=gateway directive

**Mission**: felix-exec-host-gateway-directive-01KVBRVY
**Source**: GitHub issue [#603](https://github.com/kentonium3/kg-automation/issues/603)
**Status**: Draft

## Overview

OpenClaw exposes two `host` values to Felix sub-agents when they call the `exec`
tool: `host=gateway` (runs in-process on office2) and `host=node` (delegates to
a paired companion/node host). No node host is paired on office2, so any
`exec host=node` call fails with `exec host=node requires a paired node (none
available)`.

The Felix sub-agents' standing orders do not specify which host to use, so the
haiku-4.5 model picks non-deterministically. When it picks `host=node` on the
first `exec` call of a run, that call errors. The agent recovers within the same
turn by retrying with `host=gateway` and completes its work correctly — but
OpenClaw has already marked the run `status=error` because the first tool call
failed, which fires the cron failure-notification path and delivers a
false-positive "cron job failed" WhatsApp alert to the operator.

This is alert noise, not a functional failure: the cron self-recovers and the
work completes (e.g. inbox prescan runs clean, agent emits `IDLE`). But each
occurrence costs the operator an actionable-looking WhatsApp alert, and the
frequency is governed by model non-determinism, so it can recur on any Felix
sub-agent's `exec` call at any time.

This feature eliminates the non-determinism at the source the operator controls:
it adds an explicit, hard directive to each Felix sub-agent's `AGENTS.md` to
always use `host=gateway` and never `host=node` for `exec` tool calls. It is a
prompt-directive fix (operator-selected "Option A" on the issue); it does not
change OpenClaw's tool runtime or attempt to remove the `host=node` option from
the tool surface.

## User Scenarios & Testing

### Primary scenario (fixed behavior)
1. A cron fires a Felix sub-agent (e.g. `inbox-5pm` → `felix-admin-capture`).
2. The agent needs to run a command and calls the `exec` tool.
3. Because its `AGENTS.md` carries an explicit directive, the agent uses
   `host=gateway` on the first and every `exec` call.
4. The call succeeds in-process; the run completes with `status=ok` and the
   normal delivery (e.g. `IDLE` or a real summary). No false-positive failure
   alert is sent.

### Exception: directive absent (pre-fix regression check)
- Without the directive the model may pick `host=node` first, the call errors,
  the run is marked `status=error`, and a false-positive WhatsApp alert is sent
  even though the work completed. This is the behavior the fix removes.

### Exception: a Felix sub-agent with no cron (felix-admin-tasker)
- `felix-admin-tasker` has no cron job, but it is a Felix sub-agent that uses the
  `exec` tool when invoked. The directive is added to its `AGENTS.md` too, so it
  is protected against the same false-positive if it is ever invoked (cron or
  interactive) and to keep the four sub-agents consistent.

### Rule that must always hold
- For every `exec` tool call, a Felix sub-agent uses `host=gateway`. `host=node`
  is never selected, because no node host is paired on office2.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | Each of the four Felix sub-agent `AGENTS.md` files (`felix-admin-capture`, `felix-admin-habits`, `felix-admin-tasker`, `felix-admin-escalation`) contains an explicit, unambiguous hard rule instructing the agent to use `host=gateway` for all `exec` tool calls and to never use `host=node`. | Approved |
| FR-002 | The directive states the reason (no node host is paired on office2, so `host=node` errors) so future readers understand why the rule exists and do not relax it. | Approved |
| FR-003 | The directive is phrased as a standing hard rule (not a soft preference) so the model treats it as non-negotiable, consistent with the existing Felix output-discipline hard-rule pattern. | Approved |
| FR-004 | The four edited `AGENTS.md` files are deployed to office2 through the established agent-prompt sync path so the running agents pick up the directive. | Approved |
| FR-005 | The four `AGENTS.md` files remain valid against any in-repo `AGENTS.md` validation and preserve their existing content and structure apart from the added directive. | Approved |

### Non-Functional Requirements

| ID | Requirement | Threshold / Measure | Status |
|----|-------------|---------------------|--------|
| NFR-001 | The directive must be consistent across all four sub-agents. | Identical rule wording (modulo agent-specific framing) present in all four files; zero divergence. | Approved |
| NFR-002 | No false-positive `exec host=node requires a paired node` errors after the fix deploys. | Zero such errors in `journalctl --user -u openclaw-gateway.service` over a 7-day post-deploy window. | Approved |

### Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-001 | `AGENTS.md` is an audited surface; the merge must reset the security-monitor baselines on office2 per the #557 rebaseline obligation, and the merge commit must record the rebaseline outcome. | Approved |
| C-002 | The change is Tier 3 (logic/workflow — agent prompts) under the change-risk taxonomy. | Approved |
| C-003 | The fix is prompt-directive only; it does not modify OpenClaw configuration or the `exec` tool runtime, and does not attempt to remove the `host=node` option. | Approved |
| C-004 | The deploy must flow through the established agent-prompt sync path rather than manual edits on office2. | Approved |

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | All four Felix sub-agent `AGENTS.md` files carry the `host=gateway`-only directive. |
| SC-002 | The deployed (office2) copies of the four `AGENTS.md` files carry the directive after the sync runs. |
| SC-003 | Over a 7-day window after deploy, no `exec host=node requires a paired node` error appears in the gateway journal, and no false-positive cron-failure alert attributable to host selection is delivered. |
| SC-004 | The merge commit records the security-monitor rebaseline outcome (completed or not-required with reason) per the #557 obligation. |

## Key Entities

- **Felix sub-agent `AGENTS.md`** — the per-agent instruction file under
  `scripts/openclaw/agents/<agent>/AGENTS.md`; the in-repo source of truth for an
  agent's standing orders.
- **`exec` tool host** — the `host` parameter on OpenClaw's `exec` tool;
  `gateway` runs in-process, `node` requires a paired node host (none on office2).
- **Agent-prompt sync path** — the deploy mechanism that propagates edited
  `AGENTS.md` files from the repo to the running agents on office2.

## Domain Language

- **host=gateway** — the in-process `exec` execution target on office2; the only
  working target.
- **host=node** — the remote/companion `exec` execution target; unpaired on
  office2, so every call errors.
- **False-positive alert** — a cron-failure notification fired because the first
  tool call errored, even though the run self-recovered and completed its work.
- **Felix sub-agent** — one of the `felix-admin-*` OpenClaw agents with its own
  `AGENTS.md` workspace.

## Assumptions

- The four Felix sub-agents (`felix-admin-capture`, `felix-admin-habits`,
  `felix-admin-tasker`, `felix-admin-escalation`) are the complete set of
  sub-agents with an in-repo `AGENTS.md` that call `exec`. (The `main` gateway
  agent runs the health-check crons but is a different surface — its system
  prompt, not a sub-agent `AGENTS.md` — and is out of scope for this mission.)
- The agent-prompt sync path that previously deployed `AGENTS.md` edits is
  operational and is the correct deploy channel for this change.
- `host=gateway` is functionally sufficient for everything the Felix sub-agents
  do with `exec` today (confirmed by the issue's trajectory: the recovery retry
  with `host=gateway` ran clean).
- Pinning to `host=gateway` does not regress any current behavior, because the
  agents already succeed via `host=gateway` whenever they happen to pick it.
