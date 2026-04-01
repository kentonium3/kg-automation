# Quickstart: Constitution & Agent Governance Setup

**Feature**: 012-constitution-agent-governance-setup

## Prerequisites

- SSH access to office2 as claude user (`ssh office2-claude`)
- Python 3.11+ on office2
- OpenClaw running on office2 with both agents deployed
- Obsidian Sync active across Mac, iPhone, and office2

## Verification Steps (post-implementation)

### 1. Constitution and Registry

```bash
# Verify constitution exists and is well-formed
cat docs/constitution/FELIX-CONSTITUTION.md | head -20

# Verify JSON registry
python3 -c "import json; r=json.load(open('docs/constitution/agent-registry.json')); print(json.dumps(r, indent=2))"

# Verify both agents registered at Gate 1
python3 -c "
import json
r = json.load(open('docs/constitution/agent-registry.json'))
for name, agent in r['agents'].items():
    print(f'{name}: Gate {agent[\"gate\"]}, Observation: {agent[\"observation_mode\"]}')
"
```

### 2. Agent Standing Orders

```bash
# Verify constitution preamble in both agents
head -20 scripts/openclaw/agents/felix-admin-capture/AGENTS.md
head -20 scripts/openclaw/agents/felix-admin-habits/AGENTS.md
```

### 3. Intelligence Layer

```bash
# Run tests
cd scripts/openclaw/observation && python -m pytest tests/ -v

# Dry run with sample logs (on office2)
ssh office2-claude "python3 /data/services/openclaw/observation/summarize.py --dry-run"
```

### 4. Observation Mode (on office2)

```bash
# Verify digest files exist after a run
ssh office2-claude "ls -la ~/second-brain/notes/00-System/agent-activity/"

# Check digest content
ssh office2-claude "cat ~/second-brain/notes/00-System/agent-activity/overview.md"
```

### 5. Skill-Authoring Skill

```bash
# Verify skill exists
cat scripts/openclaw/skills/skill-author/SKILL.md | head -20

# Verify deployed on office2
ssh office2-claude "ls /home/claude/.openclaw/skills/skill-author/"
```

### 6. Cron Schedule (on office2)

```bash
# Verify intelligence layer cron
ssh office2-claude "crontab -l | grep summarize"
# Expected: 0 19 * * * /path/to/summarize.py (7 PM ET daily)
```

## Key Paths

| What | Where |
|------|-------|
| Constitution | `docs/constitution/FELIX-CONSTITUTION.md` |
| Agent registry (JSON) | `docs/constitution/agent-registry.json` |
| Agent registry (Markdown) | `docs/constitution/AGENT-REGISTRY.md` |
| Intelligence layer | `scripts/openclaw/observation/summarize.py` |
| Skill-authoring skill | `scripts/openclaw/skills/skill-author/SKILL.md` |
| Governance runbook | `docs/handbooks/felix-governance.md` |
| Surfaced digests (office2) | `~/second-brain/notes/00-System/agent-activity/` |
| Raw audit logs (office2) | `~/second-brain/agents/logs/` |
