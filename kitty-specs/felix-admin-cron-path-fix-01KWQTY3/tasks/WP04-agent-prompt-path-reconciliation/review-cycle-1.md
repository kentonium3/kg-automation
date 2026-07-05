**Issue 1**: `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md.tmpl` still contains stale path references, so FR-009 and the `.md`/`.tmpl` sync constraint are not met.

Evidence:
- `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md.tmpl:271` still says to log to `~/second-brain/agents/logs/`.
- `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md.tmpl:423` still invokes `python ~/repos/kg-automation/scripts/openclaw/observation/log_action.py`.
- `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md.tmpl:462` still describes the old `~/second-brain/agents/logs/task-intelligence-YYYY-MM-DD.md` location.

Why this blocks: the spec requires stale `~/repos/kg-automation/...` and `~/second-brain/...` refs to be corrected across all felix-admin agent prompts (`AGENTS.md*` + `TOOLS.md*`), and the WP requires `.md` and `.tmpl` copies to stay in sync where both exist. The static grep gate currently misses this because it was run only across the listed owned files, but the tasker template is still part of the audited prompt surface.

How to fix:
- Update the tasker template to match `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` / `TOOLS.md`: use `/home/claude/kg-automation/scripts/openclaw/observation/log_action.py` for `log_action.py` and `/home/kgale/second-brain/agents/logs/` for logging refs.
- Re-run a broader prompt grep such as `rg -n '(/home/claude/second-brain|~/second-brain|~/repos/kg-automation)' scripts/openclaw/agents --glob 'AGENTS.md*' --glob 'TOOLS.md*'` and confirm the only remaining `~/second-brain` hits are `_private` read-prohibition lines.

Downstream note: WP06 depends on WP04; its agent should rebase after WP04 is corrected.
