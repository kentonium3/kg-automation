module.exports = async (tp) => {
  const vault = app.vault;
  const tfile = tp.file.find_tfile(tp.file.path(true));
  const content = await vault.read(tfile);
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!fmMatch) return tp.notice("No front-matter");
  let fm = fmMatch[1], body = content.slice(fmMatch[0].length);

  let allow = { doc_type:["strategy","charter","decision","policy","handbook","runbook","guide","reference","readme","index","project","note"],
                level:["overview","concept","howto","reference","policy"],
                status:["draft","review","approved","deprecated","archived"],
                audience:["agents_and_humans","humans_only","agents_only"] };
  try {
    const av = await vault.adapter.read("docs/standards/allowed-values.json");
    allow = { ...allow, ...JSON.parse(av) };
  } catch(e){}

  const pick = async (name, cur, options) => {
    if (!options || options.length===0) return cur;
    if (!options.includes(cur)) {
      const idx = await tp.system.suggester(options, options, false, `Select ${name} (current: ${cur||"none"})`);
      return options[idx] || options[0];
    }
    return cur;
  };

  const get = (k) => (fm.match(new RegExp(`^${k}:\\s*(.*)$`, "m"))||[])[1]?.trim();
  const set = (k, v) => fm = fm.match(new RegExp(`^${k}:`, "m")) ? fm.replace(new RegExp(`^${k}:.*$`, "m"), `${k}: ${v}`) : (fm + `\n${k}: ${v}`);

  const dt = await pick("doc_type", get("doc_type"), allow.doc_type);
  const lv = await pick("level",    get("level"),    allow.level);
  const st = await pick("status",   get("status"),   allow.status);
  const au = await pick("audience", get("audience"), allow.audience);

  set("doc_type", dt || "guide");
  set("level",    lv || "reference");
  set("status",   st || "draft");
  set("audience", au || "agents_and_humans");

  const newContent = `---\n${fm.trim()}\n---\n${body}`;
  if (newContent !== content) await vault.modify(tfile, newContent);
  tp.notice("enforceEnums: OK");
};
