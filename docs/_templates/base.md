<%*
/**
 * Canon v2 base template (single template, picker-driven)
 */
const rawTitle = tp.file.title || "New Doc";
const title = rawTitle.trim();
const id = title.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/(^-|-$)/g,"");
const today = tp.date.now("YYYY-MM-DD");

// Load allowed-values.json if present
let allowed = { doc_type: [], level: [], status: [], audience: [] };
try {
  const av = await app.vault.adapter.read("docs/standards/allowed-values.json");
  allowed = JSON.parse(av);
} catch (e) {
  // fallback lists
  allowed.doc_type = ["strategy","charter","decision","policy","handbook","runbook","guide","reference","readme","index","project","note"];
  allowed.level    = ["overview","concept","howto","reference","policy"];
  allowed.status   = ["draft","approved","deprecated"];
  allowed.audience = ["agents_and_humans","humans_only","agents_only"];
}

// suggested level per type
const levelSuggest = (dt) => ({
  strategy: "overview",
  charter: "overview",
  decision: "policy",
  policy: "policy",
  handbook: "reference",
  runbook: "howto",
  guide: "howto",
  reference: "reference",
  readme: "overview",
  index: "overview",
  project: "concept",
  note: "concept"
}[dt] || "reference");

// pick doc_type
const dtIdx = await tp.system.suggester(
  allowed.doc_type,
  allowed.doc_type,
  false,
  "Select doc_type"
);
const doc_type = allowed.doc_type[dtIdx] || allowed.doc_type[0] || "guide";

// pick level (prefilled suggestion)
const allLevels = allowed.level.length ? allowed.level : ["overview","concept","howto","reference","policy"];
const defaultLevel = levelSuggest(doc_type);
const lvIdx = await tp.system.suggester(
  allLevels,
  allLevels,
  false,
  `Select level (suggested: ${defaultLevel})`
);
const level = allLevels[lvIdx] || defaultLevel;

// status & audience
const stOpts = allowed.status.length ? allowed.status : ["draft","approved","deprecated"];
const auOpts = allowed.audience.length ? allowed.audience : ["agents_and_humans","humans_only","agents_only"];
const stIdx = await tp.system.suggester(stOpts, stOpts, false, "Select status");
const auIdx = await tp.system.suggester(auOpts, auOpts, false, "Select audience");
const status = stOpts[stIdx] || "draft";
const audience = auOpts[auIdx] || "agents_and_humans";
-%>
---
id: <%* tR += id %>
title: <%* tR += title %>
doc_type: <%* tR += doc_type %>
level: <%* tR += level %>
status: <%* tR += status %>
owners:
  - "@kentonium3"
last_updated: <%* tR += tp.date.now("YYYY-MM-DD") %>
last_validated: <%* tR += tp.date.now("YYYY-MM-DD") %>
revision: v1.0
audience: <%* tR += audience %>
tags: []
aliases: []
links: []
---
# <%* tR += title %>

> Tip:
> CMD-P → “Templater: Run user function” → **normalizeFm** / **enforceEnums** / **revBump**
