module.exports = async (tp) => {
  const tfile = tp.file.find_tfile(tp.file.path(true));
  const vault = app.vault;
  const content = await vault.read(tfile);
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!fmMatch) return tp.notice("No front-matter");
  let fm = fmMatch[1], body = content.slice(fmMatch[0].length);

  const titleLine = (fm.match(/^title:\s*(.*)$/m)||[])[1];
  if (titleLine && titleLine.trim()) return tp.notice("Title already set");
  const h1 = body.match(/^\s*#\s+(.+)\s*$/m);
  if (!h1) return tp.notice("No H1 found to copy from");
  const title = h1[1].trim();
  fm = fm.replace(/$/, `\ntitle: ${title}`);

  const newContent = `---\n${fm.trim()}\n---\n${body}`;
  await vault.modify(tfile, newContent);
  tp.notice("setTitleFromH1: OK");
};
