---
id: multi-agent-orchestration-view
title: Multi Agent Orchestration (Rendered)
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
