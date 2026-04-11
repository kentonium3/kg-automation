# WP03 Documentation Audit

**Mission:** 026-vault-path-registry-and-folder-renumber
**Work Package:** WP03 — Documentation Synchronization
**Subtask:** T014
**Date:** 2026-04-10
**Author:** claude:opus-4-6 implementer (lane-a worktree)

## Methodology

Repo-wide grep for vault folder literals in `docs/`, excluding the frozen
historical archives:

```bash
grep -rln \
  "00-Inbox\|01-Constitution\|02-Growth\|03-Health\|04-Business\|\
05-Finance\|06-Journal\|07-Resources\|00-System" \
  docs/ \
  | grep -v "docs/archive/" \
  | grep -v "docs/func-spec/"
```

`00-System` stays unchanged across the rename, but it is included in the
audit so we can confirm any reference is intentional and not an artifact
of a stale path. `_private/` boundary references retain the new parent
folder name (`04-Growth/_private/`) but are not removed — they are
constitutional anchors.

The new runbook `docs/runbooks/vault-path-registry-migration.md` is also
created in this WP (T018) and listed under "Files created" below.

## Categorized findings

### Category A — Architecture JSON data files (`docs/design/architecture/data/`)

| File | Lines with vault literals | Notes |
|---|---|---|
| `docs/design/architecture/data/service-inventory.json` | 57 (`02-Growth/_private` in `excluded_folders`) | Update boundary token to `04-Growth/_private`. Set `updated_by: "#152"`. Add `02-Inbox-Processed` reference where appropriate (consumer hint for #149). |
| `docs/design/architecture/data/data-flows.json` | 28 (`reads_from: .../00-Inbox/`), 93 (`description: 00-Inbox → ...`) | Update both literals to `01-Inbox`. Set `updated_by: "#152"`. |

Both files share the convention `"updated_by": "#<issue>"` and
`"last_updated": "<YYYY-MM-DD>"`. Other JSON files in `data/`
(`hardware-inventory`, `network-topology`, `credential-manifest`,
`capabilities-schema`, `catalog-schema`, `change-risk-taxonomy`,
`doc-domain-map`) have **no** vault folder literals and are out of
scope for this WP.

### Category B — Architecture markdown views (`docs/design/architecture/`)

| File | Lines with vault literals |
|---|---|
| `docs/design/architecture/data-flows.md` | 30 (`/notes/00-Inbox/`), 86 (`00-Inbox → hourly processor → ...`) |
| `docs/design/architecture/glossary.md` | 24 (`00-Inbox` row), 25 (`01-Constitution` row), 26 (`02-Growth/_private` row) |
| `docs/design/architecture/security-posture.md` | 47 (`02-Growth/_private`), 49 (`01-Constitution/`) |
| `docs/design/architecture/service-inventory.md` | 63 (`excluded_folders: 02-Growth/_private`), 109/124/139/171 (`02-Growth/_private` privacy boundary lines) |

Each line is updated by the rename table. Glossary rows are renamed
in-place (e.g. the `00-Inbox` row becomes `01-Inbox`, with an added
`02-Inbox-Processed` row for completeness).

### Category C — Runbooks (`docs/runbooks/`)

| File | Lines with vault literals | Notes |
|---|---|---|
| `docs/runbooks/escalation-ops.md` | 219 (`02-Growth/_private/`) | Boundary line; update parent to `04-Growth`. |
| `docs/runbooks/felix-governance.md` | 180 (`/notes/00-System/agent-activity/`) | `00-System` stays — verify no rename needed. |
| `docs/runbooks/goals-ops.md` | 96, 115, 141, 155 (`01-Constitution/Goals-MOC.md`) | Update to `03-Constitution`. |
| `docs/runbooks/habits-ops.md` | 181 (`02-Growth/_private/`) | Boundary line. |
| `docs/runbooks/inbox-ops.md` | 14 (`00-Inbox/`), 126, 143 (paths), 151 (`02-Growth/_private/`) | Update Inbox refs to `01-Inbox`; boundary line to `04-Growth`. |
| `docs/runbooks/obsidian-sync-ops.md` | 28 (`/notes/00-Inbox/`) | Update to `01-Inbox`. |
| `docs/runbooks/openclaw-agent-setup.md` | 82 (`02-Growth/_private/`) | Boundary line. |

`00-System` reference in `felix-governance.md` is preserved unchanged
because `00-System` is not part of the renumber.

### Category D — Constitution (`docs/constitution/`)

| File | Lines with vault literals |
|---|---|
| `docs/constitution/FELIX-CONSTITUTION.md` | 95 (`~/second-brain/notes/02-Growth/_private/` boundary statement) |

Single boundary line — update parent folder to `04-Growth`. The rest of
the constitution does not reference vault paths.

### Category E — Capability roadmap (`docs/design/`)

| File | Lines with vault literals |
|---|---|
| `docs/design/felix-capability-roadmap.md` | 270 (`02-Growth/_private/` in D05 resolution narrative), 367 (`02-Growth/_private/` in design principle #8) |

Both are boundary references; update parent folder. Additionally,
T020 extends the roadmap with a vault path registry capability entry
referencing #150 (mission 024 MVP) and #152 (mission 026 full).

### Category F — INDEX (`docs/INDEX.md`)

No vault folder literals present. T019 adds an entry for the new
migration runbook under "Operational Runbooks → Human and mixed-audience
runbooks" (it's an operator-driven runbook with mixed audience).

### Category G — Other / files NOT in scope

The following appeared in raw grep output but are excluded:

- `docs/archive/**` — frozen history
- `docs/func-spec/F011_*.md`, `F012_*.md` — frozen historical specs
- `docs/diagnostics/**` — no hits
- `docs/runbooks/governance/**` — no hits
- `docs/design/standards/**` — no hits
- `docs/design/architecture/data/{hardware-inventory,network-topology,credential-manifest,capabilities-schema,catalog-schema,change-risk-taxonomy,doc-domain-map}.json` — no vault literals
- `docs/design/architecture/{README,backup-and-recovery,change-control,credentials-and-secrets,identity-model,physical-topology,service-dependencies.view,data-flows.view,physical-topology.view}.md` — no vault literals

## Files created in this WP

- `docs/runbooks/vault-path-registry-migration.md` — new C4-summarized
  reusable migration playbook (T018)
- `kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp03-doc-updates.md` — this file (T014)

## Files modified in this WP

JSON data:
- `docs/design/architecture/data/service-inventory.json`
- `docs/design/architecture/data/data-flows.json`

Markdown views:
- `docs/design/architecture/data-flows.md`
- `docs/design/architecture/glossary.md`
- `docs/design/architecture/security-posture.md`
- `docs/design/architecture/service-inventory.md`

Runbooks:
- `docs/runbooks/escalation-ops.md`
- `docs/runbooks/goals-ops.md`
- `docs/runbooks/habits-ops.md`
- `docs/runbooks/inbox-ops.md`
- `docs/runbooks/obsidian-sync-ops.md`
- `docs/runbooks/openclaw-agent-setup.md`

Constitution / governance:
- `docs/constitution/FELIX-CONSTITUTION.md`

Roadmap and index:
- `docs/design/felix-capability-roadmap.md`
- `docs/INDEX.md`

`docs/runbooks/felix-governance.md` is **not** modified — its only hit
is `00-System/`, which is preserved across the renumber.

## Rename table (applied uniformly)

| Old | New |
|---|---|
| `00-Inbox` | `01-Inbox` |
| `01-Constitution` | `03-Constitution` |
| `02-Growth` | `04-Growth` |
| `03-Health` | `05-Health` |
| `04-Business` | `06-Business` |
| `05-Finance` | `07-Finance` |
| `06-Journal` | `08-Journal` |
| `07-Resources` | `09-Resources` |

`00-System` and the new `02-Inbox-Processed` are unchanged / new.

## Acceptance hooks

After all edits:

```bash
grep -rn "00-Inbox\|01-Constitution\|02-Growth\|03-Health\|04-Business\|\
05-Finance\|06-Journal\|07-Resources" docs/ \
  | grep -v "docs/archive/" \
  | grep -v "docs/func-spec/"
# Expect: zero hits
```

```bash
python3 tooling/scripts/validate_docs.py
# Expect: pass (location confirmed at tooling/scripts/, not docs/scripts)
```
