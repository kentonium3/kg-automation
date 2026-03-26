---
id: orchestration-flow.view
title: Orchestration Flow (Rendered)
doc_type: guide
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: '2025-10-29'
revision: v1.0
audience: agents_and_humans

---

```mermaid
%% source: docs/diagrams/orchestration-flow.mmd
%% Title: Orchestration Flow — Handoff Runner & CI
sequenceDiagram
  participant U as User
  participant A as Agent (ChatGPT/Claude Code)
  participant R as Handoff Runner
  participant G as GitHub Actions (CI)
  participant CO as Code Owners

  U->>A: Describe change (user story/plan)
  A->>Repo: Commit *-request.json on feature branch
  U->>G: Run Handoff Runner on that branch
  G->>R: Execute runner
  R->>Repo: Write files + *-response.json; commit
  Repo->>G: Trigger Docs CI
  G->>CO: Require review on PR to main
  CO-->>Repo: Approve
  G->>Repo: Merge when checks pass
```
