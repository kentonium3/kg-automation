module.exports = async (tp) => {
  const file = tp.file;
  const vault = app.vault;
  const path = file.path(true);
  let content = await vault.read(file.find_tfile(path));
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!fmMatch) return tp.notice("No front-matter");
  let fm = fmMatch[1], body = content.slice(fmMatch[0].length);

  // --- begin authoritative date logic ---
  const today = tp.date.now("YYYY-MM-DD");

  // bump revision (vX.Y -> vX.(Y+1); add if missing)
  fm = fm.replace(/^revision:\s*v(\d+)\.(\d+)$/m,
    (m, M, mnr) => `revision: v${M}.${parseInt(mnr,10)+1}`
  );
  if (!/^revision:/m.test(fm)) fm += `\nrevision: v1.1`;

  // set or refresh last_updated; DO NOT touch last_validated here
  if (/^last_updated:/m.test(fm))
    fm = fm.replace(/^last_updated:.*$/m, `last_updated: ${today}`);
  else
    fm += `\nlast_updated: ${today}`;
  // --- end authoritative date logic ---

  const newContent = `---\n${fm.trim()}\n---\n${body}`;
  if (newContent !== content) await vault.modify(file.find_tfile(path), newContent);
  tp.notice("revBump: OK");
};
