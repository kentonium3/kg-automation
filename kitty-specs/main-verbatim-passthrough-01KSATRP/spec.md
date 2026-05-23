# Spec: Enforce verbatim pass-through for main-agent delegations

**Mission**: `main-verbatim-passthrough-01KSATRP`
**Mission ID**: `01KSATRP0S0TDA5HV995Y558JK`
**Source**: GitHub issue [kentonium3/kg-automation#374](https://github.com/kentonium3/kg-automation/issues/374)
**Risk tier**: Tier 3 — Logic / Workflow (prompt update + session-lifecycle helper)
**Generated**: 2026-05-23

## Overview

The `main` agent (Sonnet 4.6, default WhatsApp recipient) paraphrases Kent's WhatsApp replies into structured prose before delegating to specialist sub-agents (`felix-admin-habits`, `felix-admin-escalation`, and the future `felix-admin-tasker`). Sub-agents have deterministic parsers (`parse_morning_reply` from #371, escalation parser from #309) that require verbatim text — paraphrased input is silently mis-parsed or produces empty parser output. Vikunja comments still write correctly because the delegate has its own backstop logic, but the JSONL state-log substrate built by #371 (`habits-history.jsonl`) and #309 (escalation history) is silently empty for any day Kent replies via WhatsApp.

Two failure modes contribute:

1. **Soft instruction (advisory)**: `main`'s standing orders at `/data/services/openclaw/data/AGENTS.md` line 305-321 reference `"<Kent's exact message>"` but do NOT forbid paraphrasing. Sonnet 4.6 in a long-lived session with abundant context leans toward "be helpful" interpretation.
2. **Long-lived session caching**: per memory `reference_openclaw_gotchas.md`, AGENTS.md caches at session-init. Updating the file doesn't propagate to running sessions; office2 today has 6 active `main` sessions (oldest from May 10).

Fix: harden the standing orders with explicit FORBIDDEN-paraphrase rules + worked examples, AND add a session-rotation helper that the deploy/cutover sequence invokes so the new instructions actually load.

## User Scenarios & Testing

### Primary user

Kent (operator) sends WhatsApp messages that `main` routes to specialist sub-agents. Today, ~every WhatsApp reply day's JSONL state-log is empty because of paraphrasing. After this fix, the JSONL substrate is populated correctly and the deterministic parsers run on verbatim text.

### Acceptance scenarios

#### Scenario A — Verbatim habit reply

- **Given**: Kent replies to the morning check-in with "did 1 and 2, skipping 3"
- **When**: `main` (post-fix) processes the reply and delegates to `felix-admin-habits`
- **Then**: the delegated `openclaw agent --message` parameter contains the EXACT string "did 1 and 2, skipping 3" (no rephrasing, no third-person rewriting, no "Kent reports that he..." pre-interpretation)
- **And**: `felix-admin-habits` invokes `parse_morning_reply` on that exact string and produces deterministic tuples
- **And**: `habits-history.jsonl` gains a row for today

#### Scenario B — Verbatim escalation reply

- **Given**: Kent replies to an escalation prompt with a one-word answer ("done", "skip", "today")
- **When**: `main` (post-fix) delegates to `felix-admin-escalation`
- **Then**: the delegated message is the exact reply text
- **And**: the escalation JSONL state-log is updated correctly

#### Scenario C — Verbatim tasker reply (future-proofing)

- **Given**: a `felix-admin-tasker` delegation pattern (post-#310)
- **When**: Kent replies to a tasker prompt
- **Then**: the same verbatim guarantee applies (the new standing-orders rule is global to delegations, not per-agent)

#### Scenario D — Session reload after AGENTS.md update

- **Given**: `/data/services/openclaw/data/AGENTS.md` has been updated with the new verbatim rule
- **When**: the operator runs the cutover/rotation helper
- **Then**: all active `main` sessions are flagged for reset OR the next interaction loads the updated AGENTS.md
- **And**: Kent's next WhatsApp reply demonstrates verbatim pass-through

#### Scenario E — Rollback

- **Given**: a defect surfaces post-deploy
- **When**: the operator reverts the AGENTS.md change
- **Then**: behavior returns to the pre-fix state (soft instruction, paraphrasing tolerated). No data loss; JSONL state-log gaps from this regression are recoverable via Vikunja comments (the existing backfill primitives in record_completion can replay).

### Edge cases

- Long verbatim message that approaches the openclaw `--message` flag length limit → preserve as-is; verbatim rule takes precedence over brevity
- Kent's message contains characters that need shell-escaping → handled by openclaw CLI quoting; the agent should not pre-sanitize beyond the literal `--message "<text>"` substitution
- Kent sends a multi-line message → forward verbatim (multi-line preserved); sub-agents handle line splitting
- Message contains potentially-sensitive content → still forward verbatim; sub-agents have their own guardrails (e.g., growth-private absolute rule)
- Multiple delegations in one turn (e.g., habits + tasker) → each gets its own verbatim slice (`main` does NOT have to forward Kent's entire raw message to every sub-agent, only the relevant portion if Kent's message clearly spans two domains; ambiguity resolves to "forward the whole message to one agent")

## Functional Requirements

| ID | Description | Status |
|---|---|---|
| FR-001 | `main` agent's standing orders shall contain a HARD verbatim-forward rule for all sub-agent delegations triggered by Kent's WhatsApp messages | Planned |
| FR-002 | The verbatim rule shall include at least 2 worked examples (one ALLOWED, one FORBIDDEN paraphrase) so the LLM has explicit pattern-matching anchors | Planned |
| FR-003 | The verbatim rule shall apply to habits, escalation, and tasker delegation sections uniformly | Planned |
| FR-004 | The standing orders shall explicitly forbid: paraphrasing, third-person rewriting, summarization, "helpful" pre-interpretation, addition of context, or restructuring Kent's reply before delegation | Planned |
| FR-005 | A session-rotation/kill helper shall exist so the operator can ensure new AGENTS.md content takes effect on active sessions without waiting for natural session expiry | Planned |
| FR-006 | The session-rotation helper shall be idempotent (running it twice does not corrupt state) | Planned |
| FR-007 | A post-cutover smoke test shall verify that the new instruction is loaded by sending a synthetic delegation and confirming verbatim pass-through in the sub-agent's session jsonl | Planned |
| FR-008 | The cutover sequence (operator-facing) shall be documented in `docs/runbooks/openclaw-agent-setup.md` (or a new mission-specific quickstart) | Planned |
| FR-009 | No regression in existing behavior: cron-driven sub-agent invocations (which don't go through `main`) continue to function unchanged | Planned |
| FR-010 | The AGENTS.md size shall stay within the openclaw effective budget (~14K source chars per memory `reference_openclaw_gotchas.md`); current file is 15,458 chars and needs trim alongside the addition | Planned |

## Non-Functional Requirements

| ID | Description | Threshold | Status |
|---|---|---|---|
| NFR-001 | Post-deploy verification: at least one Kent WhatsApp reply day shows verbatim text in `felix-admin-habits` session jsonl + a fresh row in `habits-history.jsonl` | 1 successful verification within 7 days | Planned |
| NFR-002 | Session-rotation helper completes within | ≤30 seconds | Planned |
| NFR-003 | AGENTS.md size post-trim+addition | ≤14,000 source chars | Planned |
| NFR-004 | Test coverage on new session-rotation helper | ≥85% | Planned |

## Constraints

| ID | Description | Status |
|---|---|---|
| C-001 | Existing cron-driven sub-agent flows shall not be modified | Locked |
| C-002 | Sub-agents' standing orders (felix-admin-habits, felix-admin-escalation) shall not be modified — they already correctly invoke their deterministic parsers; the fix is in `main`'s standing orders only | Locked |
| C-003 | The session-rotation mechanism shall not require sudo (claude user has no sudo per CLAUDE.md) | Locked |
| C-004 | No new third-party dependencies | Locked |
| C-005 | The rotation helper shall NOT delete session jsonl history (operator audit trail must be preserved); rotation means "force the next interaction to start a fresh session" | Locked |
| C-006 | If OpenClaw doesn't expose a session-rotation API, the helper may file-system-rename active session jsonl files (matching the existing `.jsonl.reset.<timestamp>` pattern observed on office2) | Locked |
| C-007 | Tier 3 (Logic/Workflow) — no Restic snapshot required; rollback is `git revert` of the AGENTS.md change | Locked |
| C-008 | The mission unblocks #310 (Phase 7 tasker) — coordinate so that #310's prerequisite gate can be cleared once this merges | Locked |

## Success Criteria

1. **Verbatim verification**: post-deploy, Kent's next WhatsApp habit reply shows verbatim text in `felix-admin-habits` session jsonl and a corresponding row in `habits-history.jsonl`
2. **AGENTS.md size**: stays under 14K source chars (NFR-003)
3. **Session rotation**: helper runs idempotently; operator can force AGENTS.md reload in ≤30s
4. **No regression**: existing cron-driven flows + #309 escalation behavior continue to function
5. **#310 unblocked**: this mission's merge clears the prerequisite gate on #310

## Key Entities

### MainAgentStandingOrders

The file `/data/services/openclaw/data/AGENTS.md` is the input system prompt for the `main` agent. Modifying it changes the agent's behavior — but only for sessions started AFTER the change.

### SessionRotation

A helper that ensures the next WhatsApp delegation starts from a fresh session loading the updated AGENTS.md. Possible implementations (plan phase decides):
- Rename active session jsonl files to `.jsonl.reset.<timestamp>` (mirrors the auto-rotation pattern observed in `/home/claude/.openclaw/agents/main/sessions/`)
- Send an openclaw command that resets the session (if such a command exists)
- Touch a marker file that the gateway recognizes

### CutoverSmokeTest

A scripted verification that:
1. Sends a synthetic delegation with a known verbatim payload
2. Tails the sub-agent's most recent session jsonl
3. Asserts the verbatim payload appears as-is in the sub-agent's input

## Assumptions

1. OpenClaw 2026.3.24 (the deployed version per `openclaw --help`) does not have a `session reset` subcommand; verified by reading `openclaw --help` output (will re-verify during plan).
2. Filesystem-level rename of `.jsonl` → `.jsonl.reset.<timestamp>` is a safe rotation mechanism (the OpenClaw gateway treats `.reset.` files as archived).
3. Multi-line WhatsApp messages can be passed via `--message` if properly shell-escaped; the existing `openclaw agent --message` invocation pattern in main's AGENTS.md already does this.

## Out of Scope

- Changes to felix-admin-habits, felix-admin-escalation, or felix-admin-tasker standing orders (their parsers are correct; the bug is upstream in `main`)
- New deterministic parsers for other delegation types (out-of-scope; this mission is solely about the verbatim guarantee)
- Filing an upstream OpenClaw issue about session-rotation API (deferred — we work around it via filesystem rename)
- Vikunja comment behavior (unchanged — the sub-agents continue to write comments correctly; the bug only affects JSONL state-log)

## Dependencies

- #371 (habits scripts-first port — gives us the deterministic parser whose substrate is bypassed today)
- #309 (escalation port — same architecture; would benefit from the same verbatim guarantee)
- Affects #310 (Phase 7 tasker — this is the gate that #310 is hard-blocked on)
- Memory `reference_openclaw_gotchas.md` (system prompt caches at session-init)

## Cross-References

- GitHub issue: kentonium3/kg-automation#374
- Related: #371 (parent feature that exposed the bug), #309 (sibling pattern), #310 (downstream blocked mission)
- Constitution: deployed-services modification triggers `docs/design/architecture/` updates per Directive 5
- Memory: `reference_openclaw_gotchas.md`, `reference_office2_agent_deploy_paths.md`
