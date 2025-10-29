---
id: ci-handbook
title: CI Handbook — Docs & Handoffs
doc_type: handbook
level: reference
status: approved
owners:
  - "@kent@intentional.biz"
last_updated: "2025-10-12"
revision: v1.0
audience: agents_and_humans
---

# What the CI does
- Validates front-matter on all Markdown
- Validates workflow/runbook schemas
- Validates AI handoff JSONs and filenames
- Rebuilds registries and the doc graph
- Fails if generated files were edited by hand

# How to pass locally
```bash
python tooling/scripts/validate_docs.py
python tooling/scripts/build_registries.py
python tooling/scripts/render_docgraph.py
```

# Common failures
- Missing front-matter keys → add `id, doc_type, level, status, owners, last_validated, revision`
- Handoff filename wrong → use `YYYYMMDD-HHMMSS-<id>-<from>-to-<to>-<type>.json`
- Generated files edited → revert and re-run generators