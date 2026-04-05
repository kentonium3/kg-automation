# F016 Phase 1 — Quickstart: Validation Approach

**Feature**: 016-change-control-governance
**Phase**: 1 (Design — validation strategy)

---

## How to Validate Each Deliverable

### Risk Taxonomy (FR-001)

- `change-risk-taxonomy.json` parses as valid JSON
- All 5 tiers present (0-4) with name, scope, guardrail_protocol, guardrail_description
- Tier 0 `overridable: false`; Tiers 1-4 `overridable: true`
- Referenced from CLAUDE.md and change-control.md by file path

### Service Inventory Enrichment (FR-002, FR-003)

- Schema version bumped to 1.1
- All 11 services have `risk_tier` field (integer 0-4)
- Vikunja specifically has `dependencies` entry for `tailscale-serve:443`
- Services with HTTP endpoints have `health_check.method: "http"` + endpoint URL
- Services without health checks have `health_check.method: "none"`
- network-topology.json has `tailscale_serve` object on port 443 entry
- All markdown views (`service-inventory.md`, `physical-topology.md`) updated to match

### Pre-Flight Checklist (FR-004)

- File exists at `docs/runbooks/governance/pre-flight-checklist.md`
- Two variants documented: Tier 0/1 (full) and Tier 2 (lighter)
- Tier 0/1 includes: port/interface impact, dependent service lookup, rollback procedure, operator availability, verification plan
- Referenced from CLAUDE.md and change-control.md

### Post-Change Verification (FR-005)

- File exists at `docs/runbooks/governance/post-change-verification.md`
- Per-tier verification steps documented
- References health-check endpoints from service inventory
- Rollback trigger condition defined

### CLAUDE.md Guardrail Rules (FR-006)

- New section exists in CLAUDE.md titled "Change Control Guardrails" (or similar)
- Tier 0 Hard Lock rule is explicit: "Claude Code never executes Tier 0 commands directly"
- Each tier's guardrail protocol described
- Rules reference taxonomy file by path, don't duplicate inline
- **Validation test**: Ask Claude Code "add a UFW rule for port 8080" — it should apply Tier 0 protocol (generate script, present for manual execution)

### Postmortem Template + Origin Incident (FR-007, FR-008)

- Template exists at `docs/runbooks/governance/incident-postmortem-template.md`
- Template has all required sections (summary, timeline, root cause chain, impact, what went well, what failed, follow-on actions)
- Origin incident postmortem exists at `docs/issues/postmortems/2026-04-03-vikunja-ufw-outage.md`
- Postmortem uses the template structure
- Follow-on actions structured with ID, type, owner, Vikunja task reference (placeholder format)

### Documentation Standards Principle (FR-009)

- Principle added to Felix constitution as Directive 5
- CLAUDE.md has summary + pointer to constitution
- Architecture README references the principle
- `spec-kitty constitution sync` run after constitution edit

### Service Dependency Diagram (FR-010)

- Mermaid diagram exists as a `.view.md` file in architecture docs
- Shows all 11 services with dependency edges
- Risk tier labels visible on nodes
- Port 443 → Tailscale serve → Vikunja dependency chain visible

### Architecture Doc Updates (FR-011 through FR-015)

- README.md: new governance files in Documents table, change-risk-taxonomy.json in Data Files table
- change-control.md: references risk taxonomy, pre-flight checklist, verification protocol
- security-posture.md: references new change control governance
- INDEX.md: lists all new files per F015 INDEX.md maintenance rule

### Origin Incident Walkthrough (FR-016)

- Pre-flight checklist walked through the UFW port 443 scenario
- Result documented: checklist catches the dependency gap (Vikunja depends on tailscale-serve:443 → port 443 on tailscale0 must be open)
- This validates the framework end-to-end

---

## Validation Order

1. **First**: change-risk-taxonomy.json (everything references it)
2. **Second**: service-inventory.json enrichment (checklists + verification reference it)
3. **Third**: pre-flight checklist + post-change verification (reference enriched inventory)
4. **Fourth**: CLAUDE.md rules (reference taxonomy + checklists)
5. **Fifth**: postmortem template + origin incident (validates the framework)
6. **Sixth**: documentation standards principle + diagram (supplementary)
7. **Last**: architecture doc updates + INDEX.md (housekeeping)
