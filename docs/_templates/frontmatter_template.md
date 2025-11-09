<%*
const filename = tp.file.title.replace(/\s+/g, '-').toLowerCase();
const today = tp.date.now("YYYY-MM-DD");
tR += `---
id: ${filename}
doc_type: note
owner: kent
status: draft
last_updated: ${today}
tags: []
---

# ${tp.file.title}

`;
%>
