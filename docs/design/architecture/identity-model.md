---
title: Identity Model
doc_type: reference
status: approved
---

# Identity Model

## Dual Google Identity

Kent operates with two Google identities:

| Identity | Scope | Vikunja Label | Calendar | Status |
|----------|-------|---------------|----------|--------|
| Personal | Personal life, health, growth | `personal` (blue, #2196f3) | Personal Google Calendar | Label exists (F001); calendar integration planned (F012) |
| Intentional LLC | Business, consultancy | `intentional` (green, #4caf50) | Intentional Workspace | Label exists (F001); routing deferred to Phase 3 |

## How Identity Routing Works

1. Tasks in Vikunja are tagged with `personal` or `intentional` labels
2. When calendar integration arrives (F012), the label determines which Google identity receives the calendar event
3. When WhatsApp integration arrives (F003-F006), the intent parser will infer identity from context and apply the label

## Current State (Post-F001)

- Both labels exist in Vikunja and are selectable on any task
- No automated routing yet — labels are applied manually
- Full routing is a Phase 3 capability

## Vikunja Project Structure

```
Everyday
├── Inbox           (default landing zone)
└── Someday         (deferred tasks)

Personal Growth & Transformation    (Area)
Business Acquisition                (Area)
└── CT-90day                        (subproject)
Health & Conditioning               (Area)
Intentional LLC                     (Area)
Metal Casework                      (Area)
```

Areas are organizational parent projects — convention is to place tasks in subprojects, not directly in Area projects.
