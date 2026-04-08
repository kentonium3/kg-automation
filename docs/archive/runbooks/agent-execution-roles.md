---
id: agent-execution-roles
title: Execution Roles — Runner vs Claude Code
doc_type: runbook
level: reference
status: superseded
owners: ["@kentonium3"]
last_validated: 2025-10-18
last_updated: '2025-10-29'
revision: v1.0
audience: humans
---

> **SUPERSEDED**: The GitHub Actions handoff runner execution model was
> retired in April 2026. Claude Code is now the sole execution agent.
> This file is retained as historical record only.

| Capability | Handoff Runner (GH Actions) | Claude Code |
|---|---|---|
| Safe scaffolding on branches | ✅ | ✅ |
| Edit `.github/workflows/**` | ❌ denylisted | ❌ policy-blocked |
| Run local scripts/tools | limited | ✅ full (per policy) |
| Resolve CI doc issues | basic | ✅ self-heal with policy |
| Parallel, multi-step plans | ⚠️ minimal | ✅ strong |
| Autonomy mode | n/a | configurable |

**Prefer Runner** for batch scaffolding/registries. **Prefer Claude Code** for iterative execution and fixes.
