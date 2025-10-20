---
id: user-story-template
title: User Story Template
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
const title = tp.file.title || "User Story";
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
## As a …
_(actor/role)_

## I want …
_(capability/feature)_

## So that …
_(business value)_

## Acceptance Criteria (Gherkin)
- Given …
- When …
- Then …

## Dependencies
- …

## Links
- …
