---
title: Incident Postmortem Template
doc_type: runbook
status: approved
audience: agents_and_humans
owners: [kgale]
last_validated: 2026-04-05
---

# Incident Postmortem Template

This is the standard postmortem template for kg-automation. Copy this file to `docs/issues/postmortems/YYYY-MM-DD_incident-slug.md` and fill in each section.

**Target completion time**: Under 30 minutes. Focus on facts and actionable follow-ups, not exhaustive narrative.

**Tone**: Blameless. Focus on system and process gaps, not individual fault.

---

## Incident Summary

| Field | Value |
|---|---|
| **Title** | *Short description of the incident* |
| **Date** | *YYYY-MM-DD* |
| **Duration** | *How long until fully resolved* |
| **Severity** | *Critical / High / Medium / Low* |
| **Services affected** | *List of affected services from service inventory* |
| **Detected by** | *How was the incident discovered (monitoring, user report, agent alert)* |
| **Resolved by** | *Who resolved it and how* |

## Timeline

| Time | Event |
|---|---|
| *HH:MM* | *First symptom or trigger event* |
| *HH:MM* | *Detection — how and by whom* |
| *HH:MM* | *Investigation started* |
| *HH:MM* | *Root cause identified* |
| *HH:MM* | *Fix applied* |
| *HH:MM* | *Services confirmed healthy (post-change verification)* |

## Root Cause Chain

Trace the causal chain from trigger to impact:

1. **Trigger**: *What action or event initiated the incident*
2. **Mechanism**: *How the trigger caused the failure (dependency chain, config gap, etc.)*
3. **Impact**: *What the user/operator experienced*

## Impact

- **Service downtime**: *Which services, for how long*
- **Data loss**: *Any data lost or corrupted (typically none)*
- **User impact**: *How end users were affected*
- **Operational impact**: *Effect on automated workflows, agents, scheduled tasks*

## What Went Well

- *List things that worked correctly during the incident*
- *Effective responses or mitigations*

## What Failed

- *Process gaps that allowed or prolonged the incident*
- *Missing documentation, checks, or safeguards*
- *Detection delays*

## Follow-On Actions

| ID | Action | Type | Owner | Vikunja Task | Status |
|---|---|---|---|---|---|
| A1 | *Description* | *immediate-fix / process-change / tooling-improvement / documentation* | *Kent* | *(placeholder or task ID)* | *pending / done* |
| A2 | *Description* | *type* | *owner* | *task ref* | *status* |

**Action types**:
- `immediate-fix`: Applied during or immediately after the incident
- `process-change`: New or modified procedure to prevent recurrence
- `tooling-improvement`: New tooling or automation to detect/prevent
- `documentation`: Documentation update to capture knowledge
