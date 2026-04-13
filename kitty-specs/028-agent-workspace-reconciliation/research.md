# Research: Agent Workspace Reconciliation

**Mission**: 028-agent-workspace-reconciliation
**Date**: 2026-04-13

## R1: Current drift state (live probe, 2026-04-13)

**Decision**: Fresh baseline supersedes #156 drift audit. Phase 1 reconciliation (from #156) already fixed some files.

**Method**: SSH probe of all 5 agent workspaces on office2, SHA256 hash comparison against repo.

**Findings**:

| Agent | File | Office2 hash (first 16) | Repo hash (first 16) | Status | Direction |
|---|---|---|---|---|---|
| **main** | AGENTS.md | `bbd2866d407f77aa` | MISSING | Capture | office2→repo |
| **main** | SOUL.md | `5201fd3508b30a2f` | `5201fd3508b30a2f` | Match | — |
| **main** | TOOLS.md | `78f3e26b8625ea28` | MISSING | Capture | office2→repo |
| **main** | USER.md | `6e348c9d92280955` | `6e348c9d92280955` | Match | — |
| **main** | IDENTITY.md | `1379f924cf4b4d6d` | MISSING | Capture | office2→repo |
| **capture** | AGENTS.md | `9d68f37a91c9cb59` (728) | `ce7c914ffce9849c` (694) | Drift | office2→repo |
| **capture** | SOUL.md | `be847ca5a894a42c` | `be847ca5a894a42c` | Match | — |
| **capture** | TOOLS.md | `8d912570ba8c5866` | `8d912570ba8c5866` | Match | — |
| **capture** | USER.md | `705c762014603e65` | `705c762014603e65` | Match | — |
| **capture** | IDENTITY.md | `3b82183c34c38a7c` | `3b82183c34c38a7c` | Match | — |
| **habits** | AGENTS.md | `fdea575bf9ec6c29` | `fdea575bf9ec6c29` | Match | — |
| **habits** | SOUL.md | `a2a96ac7d4971441` | `a2a96ac7d4971441` | Match | — |
| **habits** | TOOLS.md | `c0e2dc3cafa33f8f` | `c0e2dc3cafa33f8f` | Match | — |
| **habits** | USER.md | `e8113a7bcbeffd02` | `e8113a7bcbeffd02` | Match | — |
| **habits** | IDENTITY.md | `5d1a46c4f0b0d304` | `5d1a46c4f0b0d304` | Match | — |
| **escalation** | AGENTS.md | `51c3fa4e557658ff` | `51c3fa4e557658ff` | Match | — |
| **escalation** | SOUL.md | `d6150fe897fa1aac` | `d6150fe897fa1aac` | Match | — |
| **escalation** | TOOLS.md | `34b9294b927d7b77` | `34b9294b927d7b77` | Match | — |
| **escalation** | USER.md | `cf4ae99e9c394be3` | `cf4ae99e9c394be3` | Match | — |
| **escalation** | IDENTITY.md | `c8a308c2b4ee292f` | `c8a308c2b4ee292f` | Match | — |
| **tasker** | AGENTS.md | `2980e3b697fec840` | `2980e3b697fec840` | Match | — |
| **tasker** | SOUL.md | `253e2d645ce12c00` (22) | `8191697d610cd278` (68) | Drift | repo→office2 |
| **tasker** | TOOLS.md | `78f3e26b8625ea28` (40) | `5f75657ed9a81e75` (41) | Drift | repo→office2 |
| **tasker** | USER.md | `f243d94cdde37c8b` (27) | `2e8d4c0086ded4f0` (35) | Drift | repo→office2 |
| **tasker** | IDENTITY.md | `418094e6f9a6478c` (6) | `deb45bfa6105ac27` (23) | Drift | repo→office2 |

**Summary**: 17 match, 4 drift (repo→office2), 1 drift (office2→repo), 3 repo-missing. 25 files total across 5 agents.

**Notable change from #156 audit**: capture TOOLS.md, USER.md and escalation/habits USER.md now match — Phase 1 reconciliation fixed these. Only capture AGENTS.md remains drifted (34 more lines on office2).

## R2: OpenClaw agent workspace paths (from openclaw.json)

**Decision**: Use `openclaw.json` as the authoritative source for workspace paths.

**Findings**:

| Agent ID | Workspace path | agentDir |
|---|---|---|
| `main` | *(not set — uses default `/data/services/openclaw/data/`)* | *(not set)* |
| `felix-admin-capture` | `/data/services/openclaw/inbox-agent` | `/home/claude/.openclaw/agents/felix-admin-capture/agent` |
| `felix-admin-habits` | `/data/services/openclaw/habits-agent` | `/home/claude/.openclaw/agents/felix-admin-habits/agent` |
| `felix-admin-escalation` | `/data/services/openclaw/escalation-agent` | `/home/claude/.openclaw/agents/felix-admin-escalation/agent` |
| `felix-admin-tasker` | `/data/services/openclaw/tasker-agent` | `/home/claude/.openclaw/agents/felix-admin-tasker/agent` |

**Note**: Main agent has no explicit `workspace` or `agentDir` in openclaw.json — it uses the implicit default at `/data/services/openclaw/data/`.

## R3: Notification channel availability

**Decision**: Use `openclaw agent --deliver --channel whatsapp` for notifications. Email relay not available.

**Findings**:
- WhatsApp channel: `enabled: true`, `dmPolicy: disabled` (disabled controls inbound DM auto-pairing only; outbound messaging works — agents already send WhatsApp messages to Kent)
- Email relay: no `sendmail`, `msmtp`, or `mail` binary installed on office2
- OpenClaw CLI: `openclaw agent --deliver --channel whatsapp --to <number> --message "<text>"` is the established pattern for outbound notifications
- Cron is operational (3 existing cron jobs running as `claude` user)
- `curl`, `wget`, `python3` all available on office2

**Future path**: When Gmail integration (#120) is enabled, the notification channel can add email via OpenClaw's Gmail skill. Ultimately enforcement becomes automated remediation, not just alerting.

## R4: OpenClaw workspace file lifecycle (RESEARCH GATE — blocks self-heal decision)

**Decision**: RESOLVED. OpenClaw workspace files are read-write from multiple authors. Enforcement must use "last author edits win" strategy with three-way diff.

**Question**: Does OpenClaw write to workspace files (`SOUL.md`, `TOOLS.md`, `USER.md`, `IDENTITY.md`, `AGENTS.md`) at runtime, or are they operator-managed config files that OpenClaw reads but never modifies?

**Answer (from OpenClaw documentation, 2026-04-13)**:

OpenClaw agent files are populated through three mechanisms:

1. **Initial bootstrapping (automatic/guided)**: On first run, `BOOTSTRAP.md` initiates a one-time setup ritual (guided Q&A). The system writes answers to `IDENTITY.md`, `USER.md`, and `SOUL.md`. `BOOTSTRAP.md` is then deleted.
2. **Manual edits (direct control)**: Operator opens files in a text editor to fine-tune instructions. This is the primary maintenance path for `AGENTS.md` and `TOOLS.md`.
3. **Organic evolution (autonomous updates)**: As the agent interacts, it can analyze interaction history and suggest or perform updates to workspace files to better reflect the user's working style and the agent's evolving persona.

**File priority**: `AGENTS.md` (operating manual) takes priority over `SOUL.md` if there are conflicting instructions.

**Critical implication**: Because agents can autonomously update their own files (mechanism 3), **repo-authoritative self-heal is NOT safe**. An auto-deploy from repo would overwrite legitimate agent evolution. The enforcement mechanism must determine *which side changed last* and act accordingly.

**Enforcement strategy — "last author edits win" via three-way diff**:

The baseline manifest records the reconciled hash for each file. The enforcement script compares current hashes on both sides against the baseline:

| Repo vs baseline | Office2 vs baseline | Interpretation | Action |
|---|---|---|---|
| Changed | Unchanged | Repo was last author (mission commit, manual edit) | Auto-deploy repo→office2 |
| Unchanged | Changed | Office2 was last author (agent evolution, manual edit, bootstrap) | Auto-capture office2→repo + commit |
| Changed | Changed | Both sides edited since last sync | Conflict → file issue + WhatsApp notify |
| Unchanged | Unchanged | No drift | No action |

**Remaining risk with auto-capture (office2→repo)**: Committing content that an agent autonomously generated requires trust that the content is safe to commit. For this mission, auto-capture will commit with a `chore: drift-reconcile` prefix so changes are auditable. If the content is problematic, `git revert` is the recovery path.

**OpenClaw docs also recommend**: Git-versioning the workspace folder to track changes to agent identity over time. This aligns with our repo-as-source-of-truth approach.

## R5: Existing deploy infrastructure

**Decision**: Follow established deploy pattern at `scripts/deploy/`.

**Findings**:
- Existing deploy scripts: `scripts/deploy/deploy-f026.sh` (mission 026, vault path registry)
- Charter mandates: deploy script at `scripts/deploy/deploy-f{NNN}.sh`, strict-order-of-operations pattern
- Safe-deploy pattern: pre-flight (Restic age, reachability) → copy artifacts → verify → post-flight smoke test
- `--backup-confirmed` operator-ack flag pattern established for Tier 2 pre-flight
- Repo-to-office2 mapping: `scripts/openclaw/agents/<repo-name>/` → `/data/services/openclaw/<workspace-name>/`

## R6: Factory baseline hashes

**Decision**: Capture factory baseline hashes from known-unmodified files.

**Findings**:
- `BOOTSTRAP.md` hash is identical across all agents that have it (`c6545993b6e07b97`) — confirms factory template
- Tasker `TOOLS.md` hash (`78f3e26b8625ea28`) matches main `TOOLS.md` hash — both are unmodified factory defaults
- Tasker `IDENTITY.md` (6 lines, old format) and main `IDENTITY.md` (23 lines, template with blanks) are both factory defaults but different templates (different versions or agent types)
- Known factory hashes to record: `BOOTSTRAP.md` = `c6545993...`, unmodified `TOOLS.md` = `78f3e26b...`

## R7: Repo directory structure for agent mapping

**Decision**: Mapping between repo agent directory names and office2 workspace names must be explicit.

| Repo directory | Office2 workspace path | Agent ID |
|---|---|---|
| `scripts/openclaw/agents/main/` | `/data/services/openclaw/data/` | `main` |
| `scripts/openclaw/agents/felix-admin-capture/` | `/data/services/openclaw/inbox-agent/` | `felix-admin-capture` |
| `scripts/openclaw/agents/felix-admin-habits/` | `/data/services/openclaw/habits-agent/` | `felix-admin-habits` |
| `scripts/openclaw/agents/felix-admin-escalation/` | `/data/services/openclaw/escalation-agent/` | `felix-admin-escalation` |
| `scripts/openclaw/agents/felix-admin-tasker/` | `/data/services/openclaw/tasker-agent/` | `felix-admin-tasker` |

Note: repo uses agent registration names; office2 uses functional workspace names. The mapping is not derivable from either side alone — it requires `openclaw.json` as the bridge (except for `main`, which has no explicit workspace field and uses the default).
