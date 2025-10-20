---
id: eci-sequence-view
title: ECI Sequence (Rendered)
doc_type: reference
level: reference
status: approved
owners:
  - "@kentonium3"
last_validated: 2025-10-20
revision: v0.1
audience: agents_and_humans
---
```mermaid
%% source: docs/diagrams/eci-sequence.mmd
%% Title: ECI Sequence — Intake & Context
sequenceDiagram
  participant U as User
  participant A as Agent
  participant E as ECI/Bootstrap Docs
  participant R as Handoff Runner
  U->>A: Start session
  A->>E: Read bootstrap & path rules
  A->>Repo: Open/checkout feature branch
  A->>Repo: Create handoff request (json)
  U->>R: Run runner on branch
  R->>Repo: Apply edits, write response
  A->>Repo: Open PR; follow checklist
```
