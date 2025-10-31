module.exports = async (tp) => {
  const file = tp.file;
  const vault = app.vault;
  const path = file.path(true);
  let content = await vault.read(file.find_tfile(path));
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!fmMatch) return tp.notice("No front-matter found");
  const fm = fmMatch[1];
  const body = content.slice(fmMatch[0].length);

  const get = (k) => (fmStr.match(new RegExp(`^${k}:\\s*(.*)$`, "m"))||[])[1];
  const setLine = (k, v) => {
    if (new RegExp(`^${k}:\\s*`, "m").test(fmStr)) fmStr = fmStr.replace(new RegExp(`^${k}:.*$`, "m"), `${k}: ${v}`);
    else fmStr = fmStr.replace(/$/, `\n${k}: ${v}`);
  };
  let fmStr = fm;
  const stem = file.title.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/(^-|-$)/g,"");
  setLine("id", stem);

  let title = get("title");
  if (!title || title === "null" || title === "undefined") {
    const h1 = body.match(/^\s*#\s+(.+)\s*$/m);
    if (h1) setLine("title", h1[1].trim());
    else setLine("title", tp.file.title);
  }

  const ownersLine = get("owners");
  if (!ownersLine || !ownersLine.trim().startsWith("-")) {
    fmStr = fmStr.replace(/^owners:.*$/m, "owners:\n  - \"@kentonium3\"") || (fmStr + "\nowners:\n  - \"@kentonium3\"");
  }

  fmStr = fmStr.replace(/\n{3,}/g, "\n\n");
  const newContent = `---\n${fmStr.trim()}\n---\n${body}`;
  if (newContent !== content) await vault.modify(file.find_tfile(path), newContent);
  tp.notice("normalizeFm: OK");
};
