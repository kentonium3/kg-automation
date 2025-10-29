<%*
const title = tp.file.title || "New Doc";
const id = title.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/(^-|-$)/g,"");
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
last_updated: "<%* tR += today %>"
revision: v1.0
audience: agents_and_humans
tags: []
aliases: []
links: []
---

# <%* tR += title %>

<!-- Body -->
