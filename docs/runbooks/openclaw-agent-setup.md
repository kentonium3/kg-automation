---
title: OpenClaw Agent Setup
doc_type: runbook
status: approved
audience: agents_and_humans
last_updated: '2026-07-05'
last_validated: '2026-07-05'
updated_by: '#374 + vikunja-client-and-habits-weekly-report-01KTKSFT (#561) + felix-calendar-subagent-extraction-01KTTA33 (#579) + restore-whatsapp-dm-reply-delivery-01KTVVHH (#588) + agent-runtime-env-guardrails-01KWT3GH (#658)'
revision: v1.5
---

# OpenClaw agent setup

How to register and deploy an OpenClaw agent on office2. Every Felix agent
(felix-admin-capture, felix-admin-habits, felix-admin-tasker, etc.) follows
this pattern.

## Two registrations, not one

An agent must be registered in **both** of these systems:

1. **Governance registry** (`docs/constitution/agent-registry.json`) — who
   the agent is, its autonomy level, and its team. This is the kg-automation
   record.
2. **OpenClaw config** (`~/.openclaw/openclaw.json` on office2) — how
   OpenClaw discovers and runs the agent. Without this, delegation fails
   with "Unknown agent id."

Neither is sufficient alone. The governance registry without OpenClaw
registration means the agent exists on paper but can't run. OpenClaw
registration without governance means the agent runs but isn't tracked
under Felix's governance framework.

## Per-agent workspace files

Each agent has a workspace directory at `/data/services/openclaw/<agent-name>/`.
These files define the agent's identity and behavior.

**Workspaces are self-contained (no inheritance).** OpenClaw loads each configured
agent's prompt files strictly from that agent's own workspace directory — it does
**not** fall back to `defaults.workspace` for a configured agent (source-verified in
[#553](https://github.com/kentonium3/kg-automation/issues/553): `plan.js` loads
`path.join(workspaceDir, "SOUL.md")` with no fallback). Every applicable workspace
must therefore carry its shared invariants (privacy boundary, Output Discipline) in
its own files. The `defaults.workspace/` directory is the factory scaffold for
*unconfigured* agents, not a base layer configured Felix agents inherit from.

**Author to the standard.** Which concern belongs in which file — and which
invariants must be present per workspace — is governed by the
[OpenClaw Workspace Authoring Standard](<../design/openclaw-workspace-authoring-standard.md>)
(#587). The tables below summarize; the standard is authoritative. Validate a
workspace against it with:

```bash
python3 -m scripts.openclaw.agents.validate_workspace --json
```

### Required files

| File | Purpose |
|------|---------|
| **AGENTS.md** | Standing orders — the agent's complete operational instructions. Scope, workflow, constraints, and delegation rules. This is the longest and most important file. |
| **SOUL.md** | Voice, tone, and stance — how the agent writes ("write as Kent"). Per the authoring standard, SOUL carries only a one-line privacy **stance** ("I work only where I'm invited"); the *enforceable* privacy rule and the role/purpose live in AGENTS.md (with the path also in TOOLS.md), **not** in SOUL. |
| **IDENTITY.md** | Short identity card — name, emoji, creature type, vibe. OpenClaw reads this to display agent identity in `openclaw agents` output. |

### Optional files

| File | Purpose | When to include |
|------|---------|-----------------|
| **TOOLS.md** | Agent-specific tool references — vault paths, API endpoints, access notes. | When the agent interacts with specific resources. |
| **USER.md** | Information about the human the agent serves — name, timezone, preferences. | When the agent communicates with the user directly. |
| **HEARTBEAT.md** | Periodic check tasks the agent runs on heartbeat intervals. | When the agent has scheduled proactive work. Empty file or omit if agent only runs via delegation. |
| **BOOTSTRAP.md** | First-run instructions. Agent reads it on first session, then deletes it. | Only during initial agent creation. |

### Example: IDENTITY.md

```markdown
# IDENTITY.md

- **Name:** Felix (Admin Tasker)
- **Creature:** Task intelligence agent
- **Vibe:** Precise, structured, deliberate — every task gets the right shape
- **Emoji:** 🎯
```

### Example: SOUL.md

Per the authoring standard, SOUL is voice/stance only — the role/purpose lives in
AGENTS.md and the enforceable privacy rule in AGENTS.md/TOOLS.md:

```markdown
# SOUL.md — felix-admin-tasker

## Voice — write as Kent

Follow the same voice principles as other Felix agents. First person,
direct, no filler.

## Privacy stance

I work only where I'm invited. (Enforceable `04-Growth/_private/` never-touch
rule lives in AGENTS.md; see the authoring standard.)
```

### Output Discipline (Hard Rules) — standard for user-facing surfaces

Any agent whose AGENTS.md or standing orders surface to user-facing
WhatsApp (announce-channel cron messages, direct replies, escalation
pings) MUST carry the canonical Output Discipline Hard Rules block.
The canonical source is `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
(currently lines ~33–84). As of mission
`vikunja-client-and-habits-weekly-report-01KTKSFT` (#561 co-shipped
output discipline), the same block is also installed on
`felix-admin-habits` and audited on `felix-admin-escalation` and
`felix-admin-tasker`.

The three Hard Rules forbid:

1. Any preamble before the `Sent by <agent-id>:<model>` identity line in
   a user-facing message.
2. Between-tool-calls narration (the agent talking to itself in the
   announce channel).
3. Any text — internal reasoning, planning, monologue — appearing
   above the identity line in cron-fired announce messages.

When deploying a new agent that emits user-facing WhatsApp, copy the
canonical block from felix-admin-capture's AGENTS.md verbatim and adapt
only the `<agent-id>` placeholder. Agents that do NOT emit user-facing
WhatsApp must carry an explicit "no user-facing WhatsApp" annotation in
their standing orders so the audit trail records the deliberate
non-application of the rules.

### Runtime-environment guardrails (#658) — canonical invocation form

Every command a newly-authored agent prompt emits that invokes a repo helper
MUST use the canonical, launch-context-independent form. Do **not** rely on the
current working directory, `~`/`HOME` expansion, or a specific checkout path —
those are the recurring silent-failure / wrong-location bug class #658 eliminated
fleet-wide.

**Canonical form** — reuse the gateway-declared `PYTHONPATH` as the repo root,
fail loud when it is unset, hardcode no checkout path:

```bash
cd "${PYTHONPATH:?PYTHONPATH unset}" && python3 -m scripts.<pkg>.<mod> [absolute args]
# piped / file-path variant:
python3 "${PYTHONPATH:?PYTHONPATH unset}/scripts/<path>.py" [absolute args]
```

**Banned shapes** (each is a guard violation):

- A **bare** `python3 -m scripts.<mod>` with no `cd "${PYTHONPATH:?…}"` anchor —
  it silently assumes the gateway-provided `PYTHONPATH`/cwd and fails
  (`ModuleNotFoundError`) or resolves the wrong checkout when launched otherwise.
- A **hardcoded checkout path** such as `cd /home/claude/kg-automation && …` or
  `python3 /home/claude/kg-automation/scripts/…py` — re-introduces the very
  checkout-path assumption the mission exists to kill.
- A `~`/`HOME`-relative **write** — write to a canonical absolute anchor instead.
  (Reads of `~/.openclaw/…`, OpenClaw's own stable home, are permitted.)

Helper path arguments must be **absolute** so the `cd` never breaks a
cwd-relative argument.

**Enforcement (two layers, same checker).** The shared deterministic checker is
`scripts/openclaw/agents/env_assumptions.py`. It is consumed by:

- `validate_workspace.py`'s **`runtime_env_assumptions`** check
  (`check_runtime_env_assumptions()`) — run at authoring time via
  `python3 -m scripts.openclaw.agents.validate_workspace`, so a workspace
  carrying a banned shape is rejected before it is ever deployed.
- The **Test-CI env-assumption guard**
  (`scripts/openclaw/agents/tests/test_env_assumptions_guard.py`) — rides the
  existing pytest Test CI and turns red on any unremediated invocation across
  all agent prompts.

If a specific line is a deliberate, documented exception, waive it inline with a
marker on the same or preceding line:
`# env-guard: waive <kind> — <reason>` (kinds: `bare_m_scripts`, `hardcoded_cd`,
`hardcoded_abs_path`, `home_relative_write`). Prefer conversion over waiver.

## OpenClaw configuration

### openclaw.json agent entry

Add the agent to the `agents.list` array in `~/.openclaw/openclaw.json`:

```json
{
  "id": "felix-admin-tasker",
  "name": "felix-admin-tasker",
  "workspace": "/data/services/openclaw/tasker-agent",
  "agentDir": "/home/claude/.openclaw/agents/felix-admin-tasker/agent",
  "model": "anthropic/claude-sonnet-4-6"
}
```

| Field | Value |
|-------|-------|
| `id` | Agent identifier — must match what other agents use for delegation |
| `name` | Display name (typically same as id) |
| `workspace` | Path to the agent's workspace directory containing AGENTS.md, SOUL.md, etc. |
| `agentDir` | Path to the agent's runtime directory under `~/.openclaw/agents/` |
| `model` | LLM model for this agent (see Model Tier Assignment below) |

### Model Tier Assignment

New agents default to Haiku (`anthropic/claude-haiku-4-5`) — the global
default in `openclaw.json`. Only use Sonnet or higher when the task requires
complex multi-step reasoning, trend analysis, or orchestration.

When registering a new agent:

1. **Set the `model` field** in the `openclaw.json` agent entry
2. **Add `model`, `model_policy`, and `model_rationale`** to the agent's
   entry in `docs/constitution/agent-registry.json`
3. **Update `AGENT-REGISTRY.md`** with the model assignment

Model policy values:
- **pinned**: Must stay on this model. Change requires validation with
  representative production inputs and documented justification.
- **optimizable**: May move to a cheaper model if one passes quality validation.

If Sonnet is needed, document why in `model_rationale`. If unsure, start with
Haiku and validate — it's easier to upgrade than to discover a downgrade broke
something.

### Agent runtime directory

Create `~/.openclaw/agents/<agent-id>/agent/` and add `auth-profiles.json`.
Copy from an existing agent:

```bash
mkdir -p ~/.openclaw/agents/felix-admin-tasker/agent
cp ~/.openclaw/agents/felix-admin-capture/agent/auth-profiles.json \
   ~/.openclaw/agents/felix-admin-tasker/agent/
```

## Restart and verification

OpenClaw reads `openclaw.json` at startup. After adding or modifying an
agent entry, restart the gateway:

```bash
systemctl --user restart openclaw-gateway.service
```

Verify the agent is visible:

```bash
openclaw agents
```

The output should show the new agent with its identity (from IDENTITY.md),
workspace path, and model.

## Deploy pipeline (post-#567)

As of mission `agent-prompt-deploy-pipeline-01KTMDDD` (#567), the agent
prompt files (`AGENTS.md`, `IDENTITY.md`, `SOUL.md`, `TOOLS.md`, `USER.md`)
under `scripts/openclaw/agents/<slug>/` in the repo are **auto-synced** to
their deployed locations under `/data/services/openclaw/<deploy-dir>/`
within 5 minutes of any merge to `main`.

The pipeline is operator-owned but agent-readable:

- **Helper**: `scripts/openclaw/deploy/deploy_agent_prompts.py` (stdlib-only Python)
- **Systemd timer + service**: `scripts/openclaw/deploy/agent-prompt-sync.{timer,service}` (deployed to `~/.config/systemd/user/` on office2 as the `claude` user)
- **Audit log**: `/data/services/openclaw/deploy/agent-prompt-sync.jsonl` (append-only JSONL)
- **Operator runbook**: [`agent-prompt-sync-ops.md`](<./agent-prompt-sync-ops.md>)

**Implications for new-agent deployment**:

1. Manual `scp` of agent prompt files to the deploy dir is **no longer
   required** post-merge. The sync helper picks up the new files on its next
   tick (≤5 min).
2. Manual file copies remain as the **fallback** path when the helper is
   broken, being bootstrapped, or stopped (e.g., during incident response).
3. Slug → deploy-dir mapping is sourced from `service-inventory.json`
   `services[openclaw].agents.<slug>.workspace`. New agents must be registered
   there with both `source_in_repo` AND `workspace` populated before the sync
   helper will pick them up.
4. `HEARTBEAT.md`, `*.tmpl`, `*.bak*`, and `GOVERNANCE.md` are explicitly
   excluded from sync — they live in the deploy dir but are not repo-sourced
   (or, for `*.tmpl`, are templates not intended for runtime).
5. The sync helper does NOT restart openclaw. Prompt changes take effect at
   the agent's next session-init (next cron tick).

## Current agent layout

```
/data/services/openclaw/
├── inbox-agent/          ← felix-admin-capture
│   ├── AGENTS.md
│   ├── BOOTSTRAP.md
│   ├── HEARTBEAT.md
│   ├── IDENTITY.md
│   ├── SOUL.md
│   ├── TOOLS.md
│   └── USER.md
├── habits-agent/         ← felix-admin-habits
│   ├── AGENTS.md
│   ├── BOOTSTRAP.md
│   ├── HEARTBEAT.md
│   ├── IDENTITY.md
│   ├── SOUL.md
│   ├── TOOLS.md
│   └── USER.md
├── escalation-agent/     ← felix-admin-escalation
│   ├── AGENTS.md
│   ├── HEARTBEAT.md
│   ├── IDENTITY.md
│   ├── SOUL.md
│   ├── TOOLS.md
│   └── USER.md
├── tasker-agent/         ← felix-admin-tasker
│   ├── AGENTS.md
│   ├── IDENTITY.md
│   └── SOUL.md
├── calendar-agent/       ← felix-admin-calendar (#579)
│   ├── AGENTS.md
│   ├── IDENTITY.md
│   ├── SOUL.md
│   ├── TOOLS.md
│   └── USER.md
└── data/                 ← main agent workspace

~/.openclaw/
├── openclaw.json         ← agent list lives here
├── agents/
│   ├── main/agent/
│   ├── felix-admin-capture/agent/
│   ├── felix-admin-habits/agent/
│   ├── felix-admin-escalation/agent/
│   ├── felix-admin-tasker/agent/
│   └── felix-admin-calendar/agent/
├── skills/               ← shared skills (vikunja-api, whisper, etc.)
└── workspace/            ← factory defaults for UNconfigured agents — NOT inherited by the configured agents above (#553)
```

**Roster note:** `felix-doc-auditor` was refactored to a scripts-first Python
driver (#343) and is **suspended** as a live agent — it has no deployed workspace
here and is excluded from workspace validation. Its repo directory
(`scripts/openclaw/agents/felix-doc-auditor/`) is retained as history only. Re-add
it to the deployed roster only if it is reactivated as a live agent.

## Checklist for new agent deployment

Author each file to the
[OpenClaw Workspace Authoring Standard](<../design/openclaw-workspace-authoring-standard.md>),
then run `python3 -m scripts.openclaw.agents.validate_workspace --json` before deploy.

- [ ] Governance: add entry to `docs/constitution/agent-registry.json`
- [ ] Workspace: create `/data/services/openclaw/<agent-name>/`
- [ ] Workspace: create AGENTS.md with standing orders — role/authority, workflow, the enforceable privacy rule, and (if user-facing WhatsApp) the Output Discipline block
- [ ] Workspace: create SOUL.md with voice/stance only (one-line privacy stance, not the enforceable rule)
- [ ] Workspace: create IDENTITY.md with name, emoji, vibe (≤ ~10 lines)
- [ ] Workspace: create TOOLS.md if agent uses specific resources (paths, endpoints, mechanics; privacy path)
- [ ] Workspace: create USER.md if agent communicates with the user (filtered view, not a full profile)
- [ ] Validate: `python3 -m scripts.openclaw.agents.validate_workspace` passes for the new workspace
- [ ] Config: add agent entry to `~/.openclaw/openclaw.json`
- [ ] Config: create `~/.openclaw/agents/<agent-id>/agent/` with auth-profiles.json
- [ ] Restart: `systemctl --user restart openclaw-gateway.service`
- [ ] Verify: `openclaw agents` shows the new agent with identity
- [ ] Architecture: update `docs/design/architecture/data/service-inventory.json` if needed

## DM-reply lifecycle troubleshooting

When inbound WhatsApp DMs are received but no reply is delivered, the
break is usually in the gateway's `embedded_run` lifecycle. Cron
`announce`-mode outbound (morning checkin, IDLE pings, periodic digests)
is a separate code path and will keep working even when DM-reply is
broken — that's the diagnostic giveaway. Added during mission
`restore-whatsapp-dm-reply-delivery-01KTVVHH` (#588) after WP01 traced
the bug shape to an `openclaw` 2026.5.28 lifecycle regression.

### Symptom signature

In `journalctl --user -u openclaw-gateway` for the affected DM window:

- `[whatsapp] Inbound message` fires for the DM (channel received it) ✓
- `Sent by <agent>:<model>` appears (agent's stdout marker per #561) ✓
- `[whatsapp] Sending message ->` is **MISSING** (channel-send never invoked) ✗
- After ~378 seconds: `[diagnostic] stuck session recovery: action=abort_embedded_run` ✗
- Adjacent downstream symptom: `[ws] ⇄ res ✗ sessions.resolve … errorCode=INVALID_REQUEST errorMessage=No session found: current`

The agent IS executing (its stdout reaches the journal) but the
gateway's `embedded_run` completion event (`embedded_run:ended`) is
never observed. Do not be fooled by the agent's `Sent by` line — that's
the AGENT'S stdout, not the GATEWAY'S delivery signal.

### Lifecycle contract reference

The `embedded_run` lifecycle contract lives in the mission folder during
the fix:
`kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/contracts/embedded-run-lifecycle.md`
(carries through to its canonical home in `docs/design/architecture/`
post-mission). Two state markers (in vendored
`openclaw/dist/diagnostic-run-activity-*.js`):

- `embedded_run:started` — fires via `markDiagnosticEmbeddedRunStarted`
  when `setActiveEmbeddedRun` is called
- `embedded_run:ended` — fires via `markDiagnosticEmbeddedRunEnded` when
  `clearActiveEmbeddedRun` is called

Healthy runs see both. Broken runs see only `started`, then a
stuck-session recovery abort.

### Operator smoke command

Send 5 DMs from the operator phone within a 5-minute window, note `T0`
(ISO timestamp at start), then run:

```bash
ssh office2-claude "journalctl --user -u openclaw-gateway --since '<T0>' --until '<T0+5min>' 2>/dev/null | awk '/\[whatsapp\] Inbound message/{i++} /\[whatsapp\] Sending message ->/{s++} /\[whatsapp\] Sent message /{sent++} /\[diagnostic\] stalled session/{stall++} /\[diagnostic\] stuck session recovery/{rec++} /sessions\.resolve.*INVALID_REQUEST.*current/{rf++} /truncating in injected context.*sessionKey=agent:main:/{trunc++} END{print \"inbound=\"i\" send=\"s\" sent=\"sent\" stall=\"stall\" recovery=\"rec\" resolve_fail_current=\"rf\" trunc_main=\"trunc}'"
```

Healthy output: `inbound=5 send=5 sent=5 stall=0 recovery=0 resolve_fail_current=0 trunc_main=0`.

Broken output (pre-fix observation): `inbound=5+ send=0 sent=0 stall=N recovery=>=1 resolve_fail_current=>=1 trunc_main=0`.

The canonical pattern reference is
`kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/contracts/journal-event-assertions.md`.

### Investigation order if signature detected

Per `research.md` §4 + §5 D1 of the mission, in cost order:

1. **H6 — `openclaw` version**: confirm running version with `openclaw --version`. Lifecycle regression first surfaced on 2026.5.28; upgrade to 2026.6.5+ is the fix shape WP01 landed.
2. **H5 — plugin install state**: `openclaw plugins list` — verify `@openclaw/whatsapp` is present and matches the running openclaw version (channels moved to external plugins in 2026.5.28 per `reference_openclaw_upgrade_gotchas`).
3. **H4 — config drift**: read `/home/claude/.openclaw/openclaw.json` `channels.whatsapp` + `session` blocks; compare against vendored docs for required-field deltas.
4. **H2 — vendored docs**: read `/usr/lib/node_modules/openclaw/docs/{channels,gateway}/*.md` for any required field absent from our config.
5. **H3 — AGENTS.md rollback probe**: try a `main/AGENTS.md` rollback to pre-#579 (fast-rollback probe; always restore current state before continuing).
6. **H1 escalation** — if all in-scope hypotheses fail, the bug is in vendored `openclaw/dist/`. File an internal tracking issue per FR-009. Do NOT patch vendored code.

### Cross-references

- Memory `reference_openclaw_dm_reply_lifecycle` — canonical bug signature + smoke command (in
  `/Users/kentgale/.claude/projects/-Users-kentgale-repos-kg-automation/memory/`)
- Memory `reference_openclaw_upgrade_gotchas` — channels-moved-to-plugins regression context for openclaw 2026.5.28
- `contracts/journal-event-assertions.md` — full POSIX-ERE pattern reference for SC-001..SC-007
- `docs/design/architecture/data/data-flows.json` (`flows[?name=whatsapp-dm-reply]`) — architectural data flow

## Cutover sequence for main-agent AGENTS.md changes (post-#374)

When changing `/data/services/openclaw/data/AGENTS.md` (the **main**
agent's standing orders — the file that governs verbatim pass-through
routing, etc.), active main-agent sessions keep their cached system
prompt and never see the new content. The new instructions only load on
the **next** session that starts. Use this five-step sequence to force
the new instructions live without restarting the OpenClaw gateway:

1. **Pull repo on office2** (refresh the canonical source):

   ```bash
   ssh office2-claude 'cd ~/kg-automation && git pull origin main'
   ```

2. **Deploy AGENTS.md** (overwrite the live workspace copy):

   ```bash
   ssh office2-claude 'cp ~/kg-automation/scripts/openclaw/agents/main/AGENTS.md /data/services/openclaw/data/AGENTS.md'
   ```

3. **Verify size budget** (effective budget ≤14000 raw source bytes —
   AGENTS.md inflates ~26% in the LLM's view per the rawChars
   measurement; budget exceeded means later instructions may be
   truncated):

   ```bash
   ssh office2-claude 'wc -c /data/services/openclaw/data/AGENTS.md'
   ```

   Output must be ≤14000.

4. **Rotate sessions** (force every active main-agent session to reset
   so the next invocation re-loads the freshly-deployed AGENTS.md):

   ```bash
   ssh office2-claude 'python3 ~/kg-automation/scripts/openclaw/helpers/rotate_main_session.py'
   ```

   Outputs a `SUMMARY:` line + the marker path under
   `~/.config/openclaw/main-rotation-<timestamp>.done`. Re-runs are
   naturally idempotent — each invocation produces a fresh timestamped
   marker and rotates only the sessions that have re-appeared since the
   last run. Add `--dry-run` first if you want to preview the impact.

5. **Smoke test** (send a known WhatsApp message; verify the verbatim
   text appears in the relevant sub-agent's session jsonl — replace
   `felix-admin-habits` with the actual delegated-to sub-agent and
   `<your verbatim phrase>` with a short unique substring of the test
   message):

   ```bash
   ssh office2-claude 'ls -t /home/claude/.openclaw/agents/felix-admin-habits/sessions/*.jsonl | head -1 | xargs grep "<your verbatim phrase>"'
   ```

   A non-empty grep match confirms the new pass-through behavior reached
   the downstream sub-agent.

**Cross-reference**: see
`kitty-specs/main-verbatim-passthrough-01KSATRP/spec.md` for the design
rationale (FR-005..FR-009, NFR-001, NFR-002, NFR-004) and
`kitty-specs/main-verbatim-passthrough-01KSATRP/contracts/rotation-helper.md`
for the rotation helper's CLI/API contract.
