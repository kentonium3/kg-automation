---
title: Doc Maintenance
doc_type: runbook
status: approved
owners: [kent]
audience: agents_and_humans
last_validated: 2026-05-26
version: "1.0"
---

# Doc Maintenance

Operational runbook for touching the Felix documentation suite — link
conventions, runbook frontmatter, the developer portal's auto-generated
filter, and the validator.

**When to read this**: before editing any markdown under `docs/`, before
adding a new runbook, or whenever `python tooling/scripts/validate_docs.py`
fails.

Felix Constitution [Directive 5](<../constitution/FELIX-CONSTITUTION.md>) is
the top-level standard (three-layer split: machine-readable JSON, narrative
markdown, Mermaid diagrams). This runbook is its operational companion.

---

## 1. Link format convention

Relative URLs in markdown use angle-bracketed, `./`-prefixed form. The repo's
markdownlint auto-normalizes plain `[text](path)` to `[text](<./path>)` on
save, so matching the convention up front saves a churn cycle.

| From → To | Correct form |
|---|---|
| `docs/foo.md` → `docs/bar.md` | `[bar](<./bar.md>)` |
| `docs/runbooks/foo.md` → `docs/runbooks/bar.md` | `[bar](<./bar.md>)` |
| `docs/runbooks/foo.md` → `docs/design/architecture/x.md` | `[x](<../design/architecture/x.md>)` |
| `docs/runbooks/foo.md` → `CLAUDE.md` | `[CLAUDE.md](<../../CLAUDE.md>)` |
| `docs/foo.md` → `tooling/scripts/x.py` | `[x.py](<../tooling/scripts/x.py>)` |
| External URL | `[label](https://example.com)` (no angle brackets) |

Anchors within the same file use angle-bracketed form too:
`[Section X](<#section-x>)`.

---

## 2. Adding a new runbook

### Required frontmatter

Validated by [`tooling/scripts/validate_docs.py`](<../../tooling/scripts/validate_docs.py>):

```yaml
---
title: Human-Readable Title
doc_type: runbook
status: approved
owners: [kent]
audience: agents_and_humans
last_validated: 2026-05-26
version: "1.0"
---
```

- `title` — display name (used in the portal's runbook filter)
- `doc_type` — `runbook` for operational how-tos; see § 5 for the full enum
- `status` — usually `approved`; `draft` for in-progress work
- `owners` — non-empty list; `[kent]` unless ownership is shared
- `audience` — see § 3 for picking a value
- `last_validated` — today's date (ISO `YYYY-MM-DD`)
- `version` — semver-ish string (`"1.0"` for new runbooks)

Optional fields: `level`, `updated_by` (issue or PR number for the last
substantive edit), `id` (lower-kebab, defaults to filename stem).

### After creating or editing a runbook

```bash
python tooling/scripts/build_runbook_filter.py --write
python tooling/scripts/validate_docs.py
```

The first command refreshes the portal's auto-generated runbook filter (see
§ 4). The second confirms schema compliance. Both should exit 0.

---

## 3. The `audience:` enum

Required on every runbook. The portal's Virtual Runbook Filter groups
entries by this field; missing values land in an "Unclassified" bucket
that's visible from the portal.

| Value | When to pick it | Example |
|---|---|---|
| `agents` | The runbook **is** the agent's standing orders — the agent reads it as input during a run. | `inbox-ops.md`, `openclaw-ops.md` |
| `humans` | The runbook is filled in by a human operator (a journal, a soak log) or describes a step a human must perform (GUI install, one-time setup). | `escalation-soak-window.md`, `obsidian-setup.md` |
| `agents_and_humans` | Default for operational runbooks: documents an agent's behavior plus human troubleshooting, rollback, or context. | `escalation-ops.md`, `habits-ops.md`, this file |

If unsure: pick `agents_and_humans`. The failure mode for omitting the
field entirely is more visible (Unclassified bucket) than the failure
mode for picking the slightly wrong value.

---

## 4. The developer portal's auto-generated filter

[`docs/DEVELOPER_PORTAL.md`](<./../DEVELOPER_PORTAL.md>) has a section
populated from runbook frontmatter. The marker pair:

```
<!-- begin:runbook-filter (generated; do not edit) -->
<!-- end:runbook-filter -->
```

Never hand-edit content between those markers. To refresh:

```bash
python tooling/scripts/build_runbook_filter.py --write
```

The drift check (no `--write`) is what `validate_docs.py` invokes:

```bash
python tooling/scripts/build_runbook_filter.py
```

Exit 0 = block matches frontmatter. Exit 1 = stale; output includes a
`run:` hint for the refresh command. Other exit codes (2/3/4) signal
structural problems (missing portal, marker-pair issues, bad
`audience:` value, missing `title:`); see the script's contract for
details: [`build_runbook_filter.md`](<../../kitty-specs/documentation-developer-portal-01KSJ75K/contracts/build_runbook_filter.md>).

The script lives at `tooling/scripts/build_runbook_filter.py`. The link
format it emits matches § 1; do not change it without updating the script
and its tests in `tests/tooling/test_build_runbook_filter.py`.

---

## 5. Doc validation

[`python tooling/scripts/validate_docs.py`](<../../tooling/scripts/validate_docs.py>)
is the umbrella check run locally and by CI. It enforces:

- **Required frontmatter fields**: `title`, `doc_type`, `status`.
- **Enum membership**:
  - `doc_type`: `strategy`, `charter`, `decision`, `explanation`, `policy`, `handbook`, `postmortem`, `runbook`, `guide`, `reference`, `readme`, `index`, `project`, `note`, `func-spec`, `standard`
  - `status`: `draft`, `in_review`, `approved`, `deprecated`, `archived`, `active`
  - `audience`: `agents`, `humans`, `agents_and_humans`
  - `level`: `overview`, `concept`, `howto`, `reference`, `policy`, `1`, `2`
- **Format invariants**: `owners` non-empty list, `revision` matches `vMAJOR.MINOR`.
- **Portal drift** (when `docs/DEVELOPER_PORTAL.md` exists): runbook-filter block matches the script's output.
- **Secret-pattern scan** across the repo.

Exit 0 = clean. Exit 1 = at least one blocker. Non-blocking warnings (e.g.,
missing optional fields) print to stderr but don't change the exit code.

The full allowed-values set can be widened via
`docs/design/standards/allowed-values.json` if that file exists; the
script merges it over the built-in defaults.

---

## Cross-references

- [Felix Constitution](<../constitution/FELIX-CONSTITUTION.md>) § Directive 5 — top-level documentation standards
- [Developer Portal](<../DEVELOPER_PORTAL.md>) — the guided sitemap this runbook helps maintain
- [Documentation Index](<../INDEX.md>) — flat catalog of all docs
- [build_runbook_filter contract](<../../kitty-specs/documentation-developer-portal-01KSJ75K/contracts/build_runbook_filter.md>) — full behavior specification for the filter generator
