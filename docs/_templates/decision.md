---
id: decision-template
title: Decision Record Template (ADR-lite)
doc_type: reference
level: reference
status: approved
owners:
  - "@kentonium3"
last_validated: 2025-10-20
revision: v1.0
audience: agents_and_humans
---
<%*
const title = tp.file.title || "Decision Record";
const id = title.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/(^-|-$)/g,'');
const today = tp.date.now("YYYY-MM-DD");
_%>
---
id: <%* tR += id %>
title: <%* tR += title %>
doc_type: guide
level: reference
status: draft
owners:
  - "@kentonium3"
last_validated: <%* tR += today %>
revision: v0.1
audience: agents_and_humans
---
## Context
- …

## Options Considered
- Option A — …
- Option B — …
- Option C — …

## Decision
- Chosen option: …
- Rationale: …

## Consequences
- Positive: …
- Negative: …

## Links
- …
