---
id: HB-VISUAL-STYLE
title: Visual Documentation Style Guide
doc_type: handbook
level: guide
status: approved
owners: [kent@intentional.biz]
last_validated: 2025-10-16
revision: 1.0
---

# Visual Documentation Style Guide

## Principles
- **Audience-dual**: humans first, AI-editable always.
- **Mermaid-first**: diagrams are text; review in PRs; regenerate, don’t hand-edit PNGs.
- **Link-rich**: each diagram links to handbooks/runbooks where feasible.

## Diagram Types
- **Capability Map**: high-level “what the system can do” clusters.
- **Integration Architecture**: systems, data flows, boundaries.
- **Orchestration Flow**: runner/CI/PR path and guardrails.
- **Lifecycle Swimlane**: Discovery→Research→Decision→Project→Implementation→Test→Release.
- **Sequences**: detailed flows (e.g., ECI, handoff execution).

## Conventions
- Title at top as comment: `%% Title: …`
- Left-to-right where possible.
- Stable IDs (blocks/actors) so diffs are meaningful.
- Use `:::note` callouts sparingly; prefer captions in the Markdown around the diagram.

## Authoring
- Author `.mmd` files under `docs/diagrams/`.
- View on GitHub or VS Code (Mermaid preview). No binary files required.
- If a raster export is needed for slides, export from VS Code; don’t commit PNGs unless necessary.
