---
id: multi-agent-orchestration-view
title: Multi Agent Orchestration (Rendered)
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
%% source: docs/diagrams/multi-agent-orchestration.mmd
%% Title: Multi-Agent Orchestration — kg-automation
flowchart TB
  subgraph Plan
    CGPT[ChatGPT Planner]
  end
  subgraph Execute
    CC[Claude Code Executor]
    RUN[Handoff Runner]
  end
  subgraph Controls
    GOV[Repo Governance & Rulesets]
    CI[(Docs CI)]
  end
  CGPT -->|handoff| CC
  CGPT -->|handoff (scaffold)| RUN
  CC -->|PRs| CI
  RUN -->|PRs| CI
  CI -->|status| GOV
```
