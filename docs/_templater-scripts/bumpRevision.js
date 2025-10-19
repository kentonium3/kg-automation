/**
 * Templater user script: bumpRevision
 * Usage in a template: <%* await tp.user.bumpRevision() %>
 * Behavior:
 * - Parses the current file's YAML front matter.
 * - Increments `revision` (vMAJOR.MINOR → vMAJOR.(MINOR+1)).
 * - Sets `last_validated` to today's date (YYYY-MM-DD).
 * - If keys are missing, they are added with sensible defaults.
 */
async function bumpRevision(tp) {
  const moment = window.moment || tp.date;
  const file = app.workspace.getActiveFile();
  if (!file) return;

  const content = await app.vault.read(file);
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---\n?/);
  const today = moment ? moment().format("YYYY-MM-DD") : tp.date.now("YYYY-MM-DD");

  // Helper to parse YAML safely
  const yaml = app.plugins.plugins["metaedit"] ? app.plugins.plugins["metaedit"] : null;
  // We'll do a lightweight parse to avoid hard dependency
  const parseYaml = (s) => {
    try { return app.metadataCache.yamlCache ? app.metadataCache.yamlCache[file.path] ?? {} : tp.frontmatter; } catch(e) { return tp.frontmatter || {}; }
  };

  let fm = parseYaml(content) || {};
  let body = content;

  // Initialize missing keys
  if (!fm.revision) fm.revision = "v0.1";
  if (!fm.last_validated) fm.last_validated = today;

  // Bump minor version
  const m = String(fm.revision).match(/^v(\d+)\.(\d+)$/);
  if (m) {
    const major = parseInt(m[1], 10);
    const minor = parseInt(m[2], 10) + 1;
    fm.revision = `v${major}.${minor}`;
  } else {
    // If weird format, reset to v0.2
    fm.revision = "v0.2";
  }
  fm.last_validated = today;

  // Reconstruct front matter preserving order of common keys
  const order = ["id","title","doc_type","level","status","owners","last_validated","revision","audience"];
  const lines = [];
  for (const key of order) {
    if (key in fm) {
      if (key === "owners" && Array.isArray(fm[key])) {
        lines.push(`${key}:\n  - ${fm[key].join("\n  - ")}`);
      } else {
        lines.push(`${key}: ${Array.isArray(fm[key]) ? JSON.stringify(fm[key]) : fm[key]}`);
      }
    }
  }
  // Add any extra keys
  for (const k of Object.keys(fm)) {
    if (!order.includes(k)) {
      lines.push(`${k}: ${Array.isArray(fm[k]) ? JSON.stringify(fm[k]) : fm[k]}`);
    }
  }

  const newFM = `---\n${lines.join("\n")}\n---\n`;
  if (fmMatch) {
    body = content.replace(/^---\n([\s\S]*?)\n---\n?/, newFM);
  } else {
    body = newFM + content;
  }

  await app.vault.modify(file, body);
}
module.exports = bumpRevision;
