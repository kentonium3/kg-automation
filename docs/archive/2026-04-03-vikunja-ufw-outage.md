---
title: "2026-04-03: Vikunja HTTPS Outage — UFW Port 443 Dependency Gap"
doc_type: postmortem
status: approved
owners: [kgale]
---

# Postmortem: Vikunja HTTPS Outage — UFW Port 443 Dependency Gap

## Incident Summary

| Field | Value |
|---|---|
| **Title** | Vikunja HTTPS unavailable after UFW firewall hardening |
| **Date** | 2026-04-03 |
| **Duration** | ~8 hours |
| **Severity** | High — primary task management UI inaccessible |
| **Services affected** | Vikunja (HTTPS access via Tailscale Serve) |
| **Detected by** | Kent (unable to access Vikunja web UI from iPhone) |
| **Resolved by** | Kent + Claude Code — added UFW rule for port 443 on tailscale0 interface |

## Timeline

| Time | Event |
|---|---|
| Morning | `scripts/office2/security-monitor/configure-ufw.sh` executed as part of UFW hardening |
| Morning | UFW rules applied — port 443 NOT included in allowed rules for tailscale0 interface |
| Morning | Tailscale Serve TLS termination on port 443 blocked by UFW |
| ~8 hours later | Kent attempts to access Vikunja via iPhone — connection refused |
| Same day | Investigation: Tailscale Serve proxy target identified as blocked |
| Same day | Fix: `ufw allow in on tailscale0 to any port 443 proto tcp comment 'Tailscale HTTPS serve'` |
| Same day | Vikunja HTTPS access restored; health check confirmed |

## Root Cause Chain

1. **Trigger**: UFW hardening script (`scripts/office2/security-monitor/configure-ufw.sh`) applied firewall rules without considering Tailscale Serve's dependency on port 443
2. **Mechanism**: Vikunja's HTTPS access flows through Tailscale Serve, which terminates TLS on port 443 of the tailscale0 interface and proxies to `https+insecure://100.92.197.90:3456`. Without a UFW rule allowing port 443 on tailscale0, the TLS termination was blocked.
3. **Impact**: Vikunja web UI inaccessible via HTTPS for ~8 hours. Internal API access on port 3456 may have remained available depending on UFW rules for that port.

**Dependency chain**: `User → HTTPS:443 → tailscale0 interface → Tailscale Serve → https+insecure://100.92.197.90:3456 → Vikunja container`

The UFW script broke step 2 of this chain.

## Impact

- **Service downtime**: Vikunja HTTPS access ~8 hours
- **Data loss**: None
- **User impact**: Kent unable to manage tasks via mobile (iPhone Vikunja web UI)
- **Operational impact**: Agent tasks scheduled via Vikunja API may have been affected if they used the HTTPS endpoint (agents using Tailscale IP:3456 directly would have been unaffected)

## What Went Well

- The fix was straightforward once the root cause was identified (single UFW rule)
- Vikunja data was unaffected (service was running, just unreachable via HTTPS)
- The Tailscale Serve proxy configuration was correct — only the firewall rule was missing
- Existing `docs/runbooks/vikunja-ops.md` was updated post-incident with the correct Tailscale Serve configuration and proxy target requirements

## What Failed

- **No service dependency mapping**: The service inventory (`service-inventory.json`) had no dependency data. Vikunja's dependency on Tailscale Serve port 443 was undocumented.
- **No pre-flight checklist**: The UFW script was applied without checking which services depended on the affected ports. A dependency lookup against the service inventory would have surfaced the Vikunja → Tailscale Serve → port 443 chain.
- **No post-change verification**: After applying UFW rules, no health check was run against dependent services. A check of Vikunja's HTTPS endpoint would have caught the outage immediately.
- **No risk-tiered assessment**: UFW changes are Tier 0 (Host/Foundational) — the highest blast radius. No guardrail protocol existed to slow down and verify.
- **8-hour detection delay**: The outage was only detected when Kent tried to use Vikunja from his phone. No automated health monitoring exists.

## Follow-On Actions

| ID | Action | Type | Status |
|---|---|---|---|
| A1 | Add dependency data to service inventory (Vikunja → tailscale-serve:443) | documentation | done (F016 WP02) |
| A2 | Create pre-flight checklist for Tier 0/1 changes | process-change | done (F016 WP03) |
| A3 | Create post-change verification protocol | process-change | done (F016 WP03) |
| A4 | Add CLAUDE.md Tier 0 Hard Lock enforcement | process-change | pending (F016 WP04) |
| A5 | Add health-check endpoints to service inventory | documentation | done (F016 WP02) |
| A6 | Create change-risk taxonomy (Tier 0-4) | process-change | done (F016 WP01) |
| A7 | Document the fix in vikunja-ops.md | documentation | done (pre-F016) |
| A8 | Consider automated health monitoring | tooling-improvement | deferred (future feature) |

## Pre-Flight Checklist Walkthrough (FR-016 Validation)

**Scenario**: Agent is about to execute `configure-ufw.sh` on office2.

**Step 1 — Identify affected ports/interfaces**: UFW rules affect ALL ports on ALL interfaces. Specifically, any port not explicitly allowed will be blocked.

**Step 2 — Query service inventory for dependent services**: Looking up services that depend on port 443:
- `service-inventory.json` → Vikunja has `dependencies: [{target: "tailscale-serve:443", type: "requires"}]`
- This immediately surfaces the risk: blocking port 443 will break Vikunja HTTPS access.

**Step 3 — Note health-check endpoints**: Vikunja health check: `http://100.92.197.90:3456/api/v1/info` (expected: 200)

**Step 4 — Document rollback**: Restore previous UFW rules from backup or run `ufw reset && ufw enable` with previous rule set.

**Step 5 — Confirm operator availability**: Kent must be present to respond if services go down.

**Step 6 — Define verification plan**: After applying UFW rules, run Vikunja health check. If it fails, execute rollback.

**Result**: The checklist catches the port 443 dependency at **Step 2**. The UFW script would have been modified to include the port 443 rule BEFORE execution, preventing the 8-hour outage entirely.

**Conclusion**: The pre-flight checklist framework is validated — the dependency lookup step is the key mechanism that prevents this class of incident.
