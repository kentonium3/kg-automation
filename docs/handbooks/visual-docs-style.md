---
id: visual-docs-style
title: Visual Documentation Style Guide
doc_type: handbook
level: reference
status: approved
owners: [kent@intentional.biz]
last_validated: 2025-10-16
last_updated: '2025-10-29'
revision: v1.0
audience: agents_and_humans
---

# Visual Documentation Style Guide

## Principles
- **Audience-dual**: humans first, AI-editable always.
- **Mermaid-first**: diagrams are text; review in PRs.
- **Link-rich**: each diagram is surrounded by context and links.

## Diagram Types
- **Capability Map** — what the system can do, clustered.
- **Integration Architecture** — systems, flows, boundaries.
- **Orchestration Flow** — runner/CI/PR path + guardrails.
- **Lifecycle Swimlane** — Discovery→Research→Decision→Project→Implementation→Test→Release.
- **Sequences** — detailed flows (e.g., ECI, handoff execution).

## Conventions
- Title in a leading comment: `%% Title: …`
- Prefer left→right; stable IDs for readable diffs.
- Keep `.mmd` sources under `docs/diagrams/`.

## Authoring
- Preview on GitHub or VS Code Mermaid preview.
- If a raster export is needed for slides, export from VS Code; avoid committing PNGs unless essential.
