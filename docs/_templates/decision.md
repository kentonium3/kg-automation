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
doc_type: decision
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

<!--
  Decision log (#987). The DECISION above is frozen once approved; this log is
  append-only and carries NO authority — it records that authority was
  exercised elsewhere. An entry about THIS ADR belongs here, not in the ADR it
  cross-references. Frontmatter `status` is the authoritative standing.

  Types: erratum (a stated reason is wrong, the conclusion stands) · amendment
  (a detail changed, the decision stands) · superseded-by (pairs with
  `status: superseded`) · context (a referenced fact changed).

  Escape any literal pipe in a cell as \| .

  | Date | Type | By | Summary | Refs |
  |---|---|---|---|---|
  | 2026-01-01 | erratum | name | one line | ADR-00NN, #123 |
-->

## Decision log

*No entries.*
