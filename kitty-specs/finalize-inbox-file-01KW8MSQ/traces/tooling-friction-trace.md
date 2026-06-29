# Tooling-friction tracer — finalize-inbox-file-01KW8MSQ

Live-captured spec-kitty friction (guards that blocked legitimate actions, surface
desync, version/UX confusion). **Consumed automatically by the retrospective
generator (FR-007).**

**Entry format (ingestion-shaped):** each entry is a bold-lead bullet so the
FR-007 ingestor parses it. The body carries a disposition keyword that routes the
entry: `candidate gap` / `open (` → **gaps**; `fixed` / `worked as designed` /
`expected` → **helped**; neither → **not_helpful** (documented friction).

```
- **[date][phase] symptom** — anchor (command/file) — disposition: <candidate gap | fixed | documented friction>
```

## Entries

- **[2026-06-28][pre-flight] version-string non-granularity** — `spec-kitty upgrade
  --agent-check --json` returns `installed=3.2.3, latest=3.2.2 (pypi), action=none,
  reason=up_to_date`. We are on a from-`main` build (`7530597a`) that is *ahead* of
  the latest PyPI tag, yet the only identifier surfaced is the string `3.2.3`. An
  operator cannot tell *which* main build is installed or what in-flight fixes it
  carries from the version alone. Anchor: `upgrade --agent-check`. Disposition:
  **candidate gap** — surface the git commit / build SHA alongside the version
  string, or a `--build` field.

- **[2026-06-28][pre-flight] tracer scaffolding gap (#2095)** — the retrospective
  generator *ingests* `kitty-specs/<mission>/traces/*.md` (FR-007, shipped) but
  nothing *scaffolds or seeds* them and there is no `traces` CLI. The operator must
  hand-create all three files at the exact path with the documented bold-lead /
  disposition-keyword format, or ingestion silently finds zero entries. Anchor:
  `retrospective/generator.py:225`; #2095. Disposition: **candidate gap** —
  auto-scaffold `traces/` at `mission create` (the #2095 "if ROI positive" goal).
