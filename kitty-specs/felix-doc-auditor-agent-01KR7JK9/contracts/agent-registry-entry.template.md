# Contract: AGENT-REGISTRY entry for felix-doc-auditor

**Added to**: `docs/constitution/AGENT-REGISTRY.md` (markdown narrative) AND `docs/constitution/agent-registry.json` (machine-readable)
**Section position**: alphabetical or post-felix-admin-* per existing convention
**Initial autonomy**: Assisted (Level 1)

## Markdown entry (AGENT-REGISTRY.md)

```markdown
## felix-doc-auditor

**Team**: SuperAdmin (B)
**Scope**: Documentation audit — processes Doc Audit and Weekly Doc Audit issues; classifies each in-scope doc as high-confidence edit (commits directly) or judgment gap (files docs-debt issue); detects missing artifacts
**Current Autonomy Level**: Assisted (Level 1)
**Model**: Sonnet (pinned — judgment-heavy work; promotion to Haiku requires validation per Model Assignment Policy)
**Deployed**: 2026-05-09 (#105 / mission `felix-doc-auditor-agent-01KR7JK9`)
**Registered**: 2026-05-09 (#105 / mission `felix-doc-auditor-agent-01KR7JK9`)

### Transition History

| Date | Level | Direction | Reason | Decided By |
|------|-------|-----------|--------|------------|
| 2026-05-09 | Assisted | Registration | Initial deployment per #105 / mission `felix-doc-auditor-agent-01KR7JK9`. Planned promotion to Supervised after ~1 week of clean operation per Felix Constitution autonomy promotion process. | Kent Gale |
```

## JSON entry (agent-registry.json — append to `agents` array)

```json
{
  "name": "felix-doc-auditor",
  "team": "SuperAdmin (B)",
  "scope": "Documentation audit — processes Doc Audit and Weekly Doc Audit issues; classifies each in-scope doc as high-confidence edit (commits directly) or judgment gap (files docs-debt issue); detects missing artifacts",
  "autonomy_level": "Assisted (Level 1)",
  "model": {
    "name": "anthropic/claude-sonnet-4-6",
    "tier": "Sonnet",
    "policy": "pinned",
    "rationale": "Judgment-heavy work — edit-vs-debt threshold and debt-issue outline drafting"
  },
  "deployed": "2026-05-09",
  "registered": "2026-05-09",
  "deployed_by": "#105",
  "mission_id": "01KR7JK9QTHM5F4PD3YC43KDQW",
  "transition_history": [
    {
      "date": "2026-05-09",
      "level": "Assisted",
      "direction": "Registration",
      "reason": "Initial deployment per #105 / mission 01KR7JK9. Planned promotion to Supervised after ~1 week of clean operation per Felix Constitution autonomy promotion process.",
      "decided_by": "Kent Gale"
    }
  ]
}
```

## Notes

- **Model identifier**: `anthropic/claude-sonnet-4-6` is the current Sonnet model ID per the kg-automation memory. Implementation phase should verify the latest available Sonnet revision against the OpenClaw model registry on office2 and pin to a specific version.
- **Team designation** ("SuperAdmin (B)") is provisional — confirm during implementation against the existing team taxonomy in AGENT-REGISTRY.md.
- **Promotion process**: a separate governance decision after ~1 week. Adds a new row to the Transition History table and bumps `autonomy_level` in the JSON. Out of scope for this mission.
