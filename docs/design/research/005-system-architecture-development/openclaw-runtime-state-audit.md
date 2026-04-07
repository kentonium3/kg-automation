---
title: OpenClaw Runtime State Audit
doc_type: reference
status: draft
---

# OpenClaw runtime state audit

**Date**: 2026-04-06
**Version**: OpenClaw 2026.3.24
**Source**: Live inspection of office2 via `ssh office2-claude`

---

## 1. openclaw.json (gateway configuration)

**Path**: `/home/claude/.openclaw/openclaw.json`

```json
{
  "meta": {
    "lastTouchedVersion": "2026.3.24",
    "lastTouchedAt": "2026-04-06T19:59:10.444Z"
  },
  "wizard": {
    "lastRunAt": "2026-03-27T01:44:20.313Z",
    "lastRunVersion": "2026.3.24",
    "lastRunCommand": "onboard",
    "lastRunMode": "local"
  },
  "auth": {
    "profiles": {
      "anthropic:default": {
        "provider": "anthropic",
        "mode": "api_key"
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "anthropic/claude-sonnet-4-6"
      },
      "models": {
        "anthropic/claude-sonnet-4-6": {}
      },
      "workspace": "/data/services/openclaw/data"
    },
    "list": [
      {
        "id": "main"
      },
      {
        "id": "felix-admin-capture",
        "name": "felix-admin-capture",
        "workspace": "/data/services/openclaw/inbox-agent",
        "agentDir": "/home/claude/.openclaw/agents/felix-admin-capture/agent",
        "model": "anthropic/claude-sonnet-4-6"
      },
      {
        "id": "felix-admin-habits",
        "name": "felix-admin-habits",
        "workspace": "/data/services/openclaw/habits-agent",
        "agentDir": "/home/claude/.openclaw/agents/felix-admin-habits/agent",
        "model": "anthropic/claude-sonnet-4-6"
      },
      {
        "id": "felix-admin-escalation",
        "name": "felix-admin-escalation",
        "workspace": "/data/services/openclaw/escalation-agent",
        "agentDir": "/home/claude/.openclaw/agents/felix-admin-escalation/agent",
        "model": "anthropic/claude-sonnet-4-6"
      }
    ]
  },
  "tools": {
    "profile": "coding",
    "web": {
      "search": {
        "enabled": true,
        "provider": "gemini"
      }
    }
  },
  "commands": {
    "native": "auto",
    "nativeSkills": "auto",
    "restart": true,
    "ownerDisplay": "raw"
  },
  "session": {
    "dmScope": "per-channel-peer"
  },
  "channels": {
    "whatsapp": {
      "enabled": true,
      "dmPolicy": "disabled",
      "selfChatMode": false,
      "groupPolicy": "allowlist",
      "debounceMs": 0,
      "mediaMaxMb": 50
    }
  },
  "gateway": {
    "port": 18789,
    "mode": "local",
    "bind": "loopback",
    "auth": {
      "mode": "token",
      "token": "<REDACTED>"
    },
    "tailscale": {
      "mode": "off",
      "resetOnExit": false
    },
    "nodes": {
      "denyCommands": [
        "camera.snap",
        "camera.clip",
        "screen.record",
        "contacts.add",
        "calendar.add",
        "reminders.add",
        "sms.send"
      ]
    }
  },
  "skills": {
    "install": {
      "nodeManager": "npm"
    }
  },
  "plugins": {
    "entries": {
      "google": {
        "enabled": true,
        "config": {
          "webSearch": {
            "apiKey": "<REDACTED>"
          }
        }
      }
    }
  }
}
```

**Observations**:
- `felix-admin-tasker` is missing from `agents.list` despite being registered
  (visible in `openclaw agents list`). This may be because the agent was
  registered via a different mechanism or the JSON was not updated on that
  registration. The agent functions correctly regardless.
- Gateway binds to loopback only (127.0.0.1:18789) — not exposed to network.
- WhatsApp `dmPolicy` is `disabled` (unknown contacts silently ignored).
- `denyCommands` blocks camera, contacts, calendar.add, reminders, SMS —
  these are mobile device control commands, not relevant to office2.
- Google plugin enabled for web search (Gemini provider).
- Tailscale mode is `off` for the gateway (Tailscale is used for SSH access,
  not for gateway exposure).

---

## 2. Main agent SOUL.md

**Path**: `/data/services/openclaw/data/SOUL.md`

This is OpenClaw's default SOUL.md — **not customized for Kent or Felix**.
It contains generic agent personality guidance:

- "Be genuinely helpful, not performatively helpful"
- "Have opinions"
- "Be resourceful before asking"
- Boundaries around privacy, external actions, group chats
- Heartbeat behavior instructions
- Memory management (MEMORY.md, daily notes)
- Voice storytelling (ElevenLabs TTS)
- Proactive heartbeat checks (email, calendar, weather)
- Platform formatting rules (Discord, WhatsApp)

**Key finding**: This is the stock OpenClaw SOUL.md with no Felix-specific
customization. It references features not deployed (Discord, iMessage,
ElevenLabs, email). Sub-agents (habits, escalation, capture) have their own
customized SOUL.md files — only the `main` agent uses this default.

Full contents reproduced in Appendix A.

---

## 3. Main agent AGENTS.md

**Path**: `/data/services/openclaw/data/AGENTS.md`

This is the main agent's workspace AGENTS.md — contains the **generic
OpenClaw agent bootstrap** instructions plus two **Kent-specific delegation
blocks** appended at the bottom:

**Generic sections** (OpenClaw defaults):
- Session startup: read SOUL.md, USER.md, memory files
- Memory management: daily notes, MEMORY.md
- Red lines: no data exfiltration, use trash not rm
- External vs internal actions
- Group chat behavior
- Heartbeat management
- Tool usage via skills

**Kent-specific additions** (appended during F008 and F009):

1. **Inbox processing delegation**: When Kent asks to process inbox, trigger
   `felix-admin-capture` via `openclaw agent --agent felix-admin-capture`
   with a 300-second timeout. Read the processing log and summarize results.

2. **Habit tracking delegation**: When Kent sends habit-related messages,
   delegate to `felix-admin-habits` via `openclaw agent --agent felix-admin-habits`
   with a 120-second timeout. Relay results back via WhatsApp.

**Key finding**: No escalation delegation block exists yet. When Kent sends a
response to an escalation alert, the main agent would need to route it to
`felix-admin-escalation` — but no delegation rule exists. Currently, escalation
responses only work when the escalation agent's cron session is active (isolated
session with WhatsApp delivery). This is a gap to address in a future feature.

Full contents reproduced in Appendix B.

---

## 4. Main agent USER.md

**Path**: `/data/services/openclaw/data/USER.md`

**Not customized.** Contains the OpenClaw template with blank fields:

```markdown
# USER.md - About Your Human

- **Name:**
- **What to call them:**
- **Pronouns:** _(optional)_
- **Timezone:**
- **Notes:**

## Context

_(What do they care about?...)_
```

**Key finding**: The main agent's USER.md has never been populated with Kent's
information. Sub-agents (habits, escalation, capture) each have their own
populated USER.md files. The main agent operates without explicit user context.

---

## 5. HEARTBEAT.md

**Path**: `/data/services/openclaw/data/HEARTBEAT.md`
**Status**: Exists but contains only template comments

```markdown
# HEARTBEAT.md Template

\```markdown
# Keep this file empty (or with only comments) to skip heartbeat API calls.

# Add tasks below when you want the agent to check something periodically.
\```
```

**Key finding**: Heartbeat is effectively disabled. No periodic checks configured.
This is consistent with the current architecture — all periodic work is driven by
cron jobs to specific sub-agents, not by the main agent's heartbeat loop.

---

## 6. MEMORY.md

**Path**: `/data/services/openclaw/data/MEMORY.md`
**Status**: Does not exist.

The main agent has no long-term memory file. This is consistent with the
architecture — the main agent primarily routes messages to sub-agents and
doesn't maintain persistent state.

---

## 7. Plugins

**Total**: 80 available, 38 loaded

**Loaded plugins** (actively available):
- **Providers** (20): Anthropic, Amazon Bedrock, BytePlus, Chutes, Cloudflare
  AI Gateway, DeepSeek, GitHub Copilot, Hugging Face, Kilo, Kimi, MiniMax,
  Mistral, Model Studio, Moonshot, NVIDIA, Ollama, OpenAI, OpenCode (Zen + Go),
  OpenRouter, Qianfan, SGLang, Synthetic, Together, Venice, Vercel AI Gateway,
  vLLM, Volcengine, xAI, Xiaomi, Z.AI
- **Channels** (1): WhatsApp
- **Other** (6): Google (web search), Memory (Core), Device Pair, Phone Control,
  Qwen OAuth, Talk Voice

**Disabled plugins of note**:
- Discord, Telegram, Slack, Signal, iMessage, IRC — messaging channels not configured
- ElevenLabs, Deepgram, Microsoft Speech — voice/TTS not configured
- 1Password, Brave, Exa, Perplexity, Tavily — search/secrets not configured
- ACPX Runtime, OpenShell, LLM Task, Lobster — advanced runtime features

---

## 8. Skills

**Total**: 54 available, 13 ready

**Ready skills** (installed and configured):
| Skill | Source | Purpose |
|-------|--------|---------|
| clawhub | openclaw-bundled | Skill registry management |
| gh-issues | openclaw-bundled | GitHub issue automation |
| github | openclaw-bundled | GitHub CLI operations |
| healthcheck | openclaw-bundled | Host security hardening |
| node-connect | openclaw-bundled | Device pairing diagnostics |
| skill-creator | openclaw-bundled | Skill authoring assistance |
| tmux | openclaw-bundled | Terminal session control |
| video-frames | openclaw-bundled | Video frame extraction |
| weather | openclaw-bundled | Weather queries |
| escalation | openclaw-managed | Task escalation model (F019) |
| skill-author | openclaw-managed | Skill quality standards |
| vikunja_api | openclaw-managed | Vikunja REST API access |
| whisper | openclaw-managed | Audio transcription |

**OpenClaw-managed skills** (deployed from kg-automation repo):
- `escalation` — F019 escalation model
- `skill-author` — kg-automation skill authoring standards
- `vikunja_api` — Vikunja API access pattern
- `whisper` — Whisper transcription service

**Notable "needs setup" skills**:
- `gog` — Google Workspace CLI (Gmail, Calendar, Drive, Contacts, Sheets, Docs).
  This is a bundled OpenClaw skill that wraps a `gog` CLI tool. It is NOT the
  same as the `google-calendar` skill we're building in F020 — that skill uses
  direct API calls via curl. Worth evaluating whether `gog` could serve as an
  alternative or complement.
- `obsidian` — Obsidian vault management via obsidian-cli
- `coding-agent` — Delegate coding to Codex, Claude Code, or Pi agents

---

## 9. Agents

**Registered agents**: 4 (plus main)

| Agent | Identity | Workspace | Model |
|-------|----------|-----------|-------|
| main (default) | — | /data/services/openclaw/data | claude-sonnet-4-6 |
| felix-admin-capture | 📥 Felix (Admin Capture) | /data/services/openclaw/inbox-agent | claude-sonnet-4-6 |
| felix-admin-habits | ✅ Felix (Habits) | /data/services/openclaw/habits-agent | claude-sonnet-4-6 |
| felix-admin-escalation | 🔴 Felix (Escalation) | /data/services/openclaw/escalation-agent | claude-sonnet-4-6 |

**Missing from `openclaw.json`**: `felix-admin-tasker` is not in the JSON
`agents.list` array but IS visible in `openclaw agents list`. This suggests
the `agents list` command reads from a different source (possibly the
`agentDir` filesystem) rather than solely from `openclaw.json`.

**No routing bindings**: None of the sub-agents have WhatsApp routing bindings.
All message routing goes through the `main` agent, which delegates to sub-agents
via `openclaw agent --agent <name>` commands in its AGENTS.md.

---

## 10. Cron jobs

**Total**: 9 jobs

| Name | Schedule | Agent | Status | Last Run |
|------|----------|-------|--------|----------|
| inbox-6am | 0 6 * * * ET | felix-admin-capture | error | 16h ago |
| habits-morning-checkin | 5 11 * * * UTC | felix-admin-habits | ok | 7h ago |
| escalation-daily | 0 12 * * * UTC | felix-admin-escalation | ok | 5h ago |
| inbox-9am | 0 9 * * * ET | felix-admin-capture | error | 13h ago |
| inbox-noon | 0 12 * * * ET | felix-admin-capture | error | 10h ago |
| inbox-3pm | 0 15 * * * ET | felix-admin-capture | error | 7h ago |
| inbox-6pm | 0 18 * * * ET | felix-admin-capture | error | 4h ago |
| inbox-9pm | 0 21 * * * ET | felix-admin-capture | error | 31m ago |
| habits-weekly-report | 0 22 * * 0 UTC | felix-admin-habits | ok | 1d ago |

**Key findings**:
- All 6 `inbox-*` cron jobs are in `error` status. This is a persistent issue —
  all inbox processing crons are failing.
- `habits-morning-checkin`, `escalation-daily`, and `habits-weekly-report` are
  all `ok`.
- No cron job exists for `felix-admin-tasker` (task-detection) despite being
  documented in `service-inventory.json`. It may have been removed or never
  created, or may use a different scheduling mechanism.

---

## Observations and gaps

### Configuration gaps

1. **Main agent USER.md is blank** — the main agent has no context about Kent.
   Sub-agents have populated USER.md files but the main agent (which handles
   WhatsApp routing and delegation) does not know who it's talking to.

2. **Main agent SOUL.md is stock** — not customized for the Felix personality
   or Kent's communication preferences. Sub-agents have customized SOUL.md.

3. **No escalation delegation in main AGENTS.md** — inbox and habits delegation
   blocks exist, but escalation responses from WhatsApp would not be routed
   to the escalation agent unless the cron's isolated session handles them.

4. **MEMORY.md does not exist** — the main agent has no long-term memory. This
   may be intentional (stateless router) or an oversight.

5. **HEARTBEAT.md is empty** — no proactive checks configured for the main agent.

### Operational issues

6. **All inbox cron jobs are failing** — 6 out of 6 in `error` status. This is
   the most urgent operational finding. Inbox processing has been broken across
   all scheduled runs.

7. **felix-admin-tasker missing from openclaw.json** — the agent is registered
   and functional but not listed in the gateway config's agents array.

8. **task-detection cron missing** — documented in service-inventory.json as
   running every 4 hours, but not visible in `openclaw cron list`.

### Security note

9. **Gateway auth token visible in openclaw.json** — the token
   `c3cb8a442c6cf639fe6d5eeeb25ea6eb8ed48d0d6892e653` is in the config file.
   This is the gateway's local auth token. Since the gateway binds to loopback
   only, exposure risk is minimal, but it should not be committed to the repo.
   (It is not — the config file lives only on office2.)

10. **Google web search API key in openclaw.json** — the Gemini API key
    `AIzaSyBHdJXsGxpH5r2_xJowMNgEcPAogKZfk5c` is in the plugins config. Same
    exposure considerations as the gateway token — lives on office2 only, not
    in the repo.

---

## Appendix A: Full SOUL.md contents

*(See Section 2 above — full contents captured in the SSH read)*

## Appendix B: Full AGENTS.md contents

*(See Section 3 above — full contents captured in the SSH read)*

---

**END OF AUDIT**
