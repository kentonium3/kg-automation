module.exports = async (tp) => {
  const file = tp.file;
  const vault = app.vault;
  const path = file.path(true);
  let content = await vault.read(file.find_tfile(path));
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!fmMatch) return tp.notice("No front-matter");
  let fm = fmMatch[1], body = content.slice(fmMatch[0].length);

  const today = tp.date.now("YYYY-MM-DD");
  fm = fm.replace(/^revision:\s*v(\d+)\.(\d+)$/m, (m, M, mnr)=>`revision: v${M}.${parseInt(mnr,10)+1}`);
  if (!/^revision:/m.test(fm)) fm += `\nrevision: v1.1`;
  fm = fm.replace(/^last_updated:.*$/m, `last_updated: ${today}`);
  if (!/^last_updated:/m.test(fm)) fm += `\nlast_updated: ${today}`;

  const newContent = `---\n${fm.trim()}\n---\n${body}`;
  if (newContent !== content) await vault.modify(file.find_tfile(path), newContent);
  tp.notice("revBump: OK");
};
