# TOOLS.md

## Vault

- **Path on office2**: `/home/kgale/second-brain/notes/`
- **Inbox**: `/home/kgale/second-brain/notes/01-Inbox/`
- **Processing logs**: `/home/kgale/second-brain/agents/logs/`
- **Access**: claude user via secondbrain group

## Vikunja API

- Use the vikunja_api skill for task creation
- Run `openclaw skills info vikunja_api` for details

## Date handling

All dates must be resolved in Kent's timezone (America/New_York), not UTC.
office2 runs in UTC — always use `TZ=America/New_York date` for date
calculations. When setting `due_date` via the Vikunja API, include the ET
offset (-04:00 for EDT, -05:00 for EST). Never use the `Z` (UTC) suffix
for due dates.

## Privacy

- NEVER access: `/home/kgale/second-brain/notes/04-Growth/_private/` (path renumbered from `02-Growth/_private/` in mission 026 / #152)

## GitHub

- **CLI**: `gh` (authenticated as kentonium3)
- **Skill**: `github` (OpenClaw bundled)
- **Default repo**: `kentonium3/kg-automation`
- **Multi-repo**: NOT supported yet -- only kg-automation

### Label heuristic

See the label taxonomy in AGENTS.md beside the Step 3 `github_issue` route — that is the authoritative label set.

