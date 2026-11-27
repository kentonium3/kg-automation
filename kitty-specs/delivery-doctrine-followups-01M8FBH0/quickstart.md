# Quickstart: verifying #1146

## Locally (office4 or CI)

```bash
.venv/bin/python -m pytest scripts/openclaw/agents/tests/test_delivery_doctrine.py -q
.venv/bin/python -m pytest tests/deploy/test_announce_agent_tool_deny.py -q
.venv/bin/python scripts/deploy/deploy-announce-agent-tool-deny.py --dry-run --config <fixture>   # prints the planned patch; writes nothing
```

Red-first proof (NFR-001): run the new guard tests against the pre-fix `delivery_doctrine.py`. Each FR-001 and FR-002 case fails, and the positive controls pass.

## Live, after merge to `main` (read-only, `ssh office2-claude`)

1. **Prompts and skills synced:** compare the sha256 of each deployed `AGENTS.md` in `/data/services/openclaw/{inbox,escalation,habits}-agent/` and each `SKILL.md` with the repo.
2. **Deny applied:**
   - The applied record for `announce-agent-tool-deny` (find it by name; it carries `apply_mode` and `applied_at`) shows a successful terminal rebaseline disposition.
   - `openclaw config get agents.entries.<id>.tools.deny` lists the four entries for each of the 3 agents.
   - The gateway log shows the reload acknowledgement, and the gateway PID and start time are unchanged.
   - The effective-catalog inspection shows the four groups absent and `exec`/`wait` present, or the record states explicitly that no read-only path exists (weaker check).
3. **Nothing else changed:** the sorted-JSON hashes of the other agent entries and of the top-level `tools` match the values the manifest recorded.
4. **Canary (SC-002):** the next scheduled run of capture, escalation and habits is ok and delivered, with zero calls to a denied tool and no tool-loop stop.
5. **Record:** post the evidence on #1146.
