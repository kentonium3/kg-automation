---
name: Feature
about: New capability or enhancement to Felix
title: "Feature: "
labels: P3-candidate
assignees: ''
---

<!--
INSTRUCTIONS FOR AUTHOR
- Focus on WHAT and WHY — not HOW
- HOW is determined by spec-kitty planning phase
- Discovery pointers (where to look) are welcome; implementation steps are not
- Delete all HTML comment blocks before submitting
-->

## Executive Summary

<!--
2–3 sentences: what is broken or missing, and what this feature delivers.
Then list current gaps with ❌.
-->

Current gaps:
- ❌ 
- ❌ 
- ❌ 

---

## Problem Statement

<!--
Visual tree showing current state vs target state.
Use ✅ for working, ❌ for missing/broken.
-->

**Current state:**
```
Component
├─ ✅ 
└─ ❌ 
```

**Target state:**
```
Component
├─ ✅ 
└─ ✅ 
```

---

## Study These Files First

<!--
Discovery pointers for spec-kitty planning phase and Claude Code.
Point to WHERE patterns exist — not HOW to implement.
Internal sources first, then external.
-->

Before implementation, planning phase must read:

1. **[Pattern or component]**
   - Find: `[path]`
   - Note: [what to look for]

2. **[Pattern or component]**
   - Find: `[path]`
   - Note: [what to look for]

---

## Functional Requirements

<!--
Each FR describes WHAT the system must do.
Success criteria are the acceptance tests — use checkboxes.
GitHub tracks checkbox completion percentage automatically.
-->

### FR-1: [Requirement name]

**What it must do:**
- 
- 

**Business rules:**
- 

**Success criteria:**
- [ ] 
- [ ] 

---

### FR-2: [Requirement name]

**What it must do:**
- 

**Success criteria:**
- [ ] 
- [ ] 

---

## Out of Scope

- ❌ 
- ❌ 

---

## Architecture Impact

<!--
Remove this section if the feature makes no changes to deployed services,
credentials, ports, or data flows.
If it does, list what needs updating.
-->

| File | Change |
|---|---|
| `data/service-inventory.json` | |
| `data/network-topology.json` | |
| `data/credential-manifest.json` | |

- [ ] All modified JSON files updated with `updated_by` set to this issue number
- [ ] Markdown views match JSON sources

---

## Constitutional Compliance

<!--
Map this feature to Felix Constitution principles.
At minimum: autonomy level, scope boundary, failure behavior.
-->

- **Autonomy level**: Assisted (Level 1) / Observed (Level 2) / Autonomous (Level 3)
- **Scope**: [What this agent/feature does and does not do]
- **Failure behavior**: [What happens when this fails — never silent]
- **Privacy boundary**: [Any second-brain or private data considerations]

---

## Risk Considerations

**Risk:** 
- Impact: 
- Mitigation: 

---

## Notes for Implementation

<!--
Discovery pointers for Claude Code / spec-kitty.
WHERE to look — never HOW to implement.
No commands, no file paths inside third-party tools, no code snippets.
-->

- Study `[path]` → apply pattern to [new component]
- Study `[path]` → understand [requirement]
