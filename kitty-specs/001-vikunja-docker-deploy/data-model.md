# Data Model: Vikunja Docker Deploy

**Feature**: 001-vikunja-docker-deploy
**Date**: 2026-03-26

## Overview

This feature does not introduce a custom data model. Vikunja manages its own SQLite schema internally. The setup script creates entities via the Vikunja REST API.

The entities below describe what the setup script creates, not database tables.

## Vikunja Entities Created by Setup Script

### Projects

| Name | Parent | Purpose |
|------|--------|---------|
| Everyday | (root) | Container for daily workflow buckets |
| Inbox | Everyday | Default landing zone for new tasks |
| Someday | Everyday | Low-priority or deferred tasks |
| Personal Growth & Transformation | (root) | Area — life development goals |
| Business Acquisition | (root) | Area — business acquisition goals |
| CT-90day | Business Acquisition | Subproject — 90-day commitment tracker |
| Health & Conditioning | (root) | Area — health and fitness goals |
| Intentional LLC | (root) | Area — consultancy business tasks |
| Metal Casework | (root) | Area — metalbox ecommerce project |

### Labels

| Name | Purpose |
|------|---------|
| personal | Routes tasks to personal Google identity (phase 3) |
| intentional | Routes tasks to Intentional LLC Google identity (phase 3) |

### Saved Filters

| Name | Expression (verify against pinned version) | Purpose |
|------|---------------------------------------------|---------|
| Today | `due_date <= now/d && done = false` | Tasks due today |
| Upcoming | `due_date > now/d && due_date <= now+14d && done = false` | Tasks due within 14 days |
| Overdue | `due_date < now/d && done = false` | Past-due incomplete tasks |

## Idempotency Strategy

The setup script must check for existing entities before creating:
- **Projects**: Match by name within the expected parent. Skip if exists.
- **Labels**: Match by title. Skip if exists.
- **Saved Filters**: Match by title. Skip if exists.

No entity is ever deleted or modified by the setup script — create-only, skip-if-exists.
