---
title: kg-automation Documentation — Start Here
doc_type: readme
status: approved
owners: [kgale]
audience: agents_and_humans
last_validated: 2026-08-29
version: "1.0"
---

# kg-automation Documentation — Start Here

This directory has **two** entry points, depending on what you are doing. This file exists
only to point at them, so that landing in `docs/` — or looking for a `README.md` by
convention — is not a dead end.

| If you want to… | Start at |
|---|---|
| Be **guided** — "I'm new / what do I read, in what order?" | [`DEVELOPER_PORTAL.md`](<./DEVELOPER_PORTAL.md>) — a guided sitemap with onboarding paths for feature work, runbook execution, and bug fixes |
| **Find** something specific — "where is X documented?" | [`INDEX.md`](<./INDEX.md>) — the master index of every active doc, grouped by directory with Divio type annotations |

Both are maintained; neither supersedes the other. The portal is the *narrative* route in, the
index is the *complete* listing.

## What lives where

| Directory | Contents |
|---|---|
| [`design/`](<./design/>) | Architecture and design. [`design/architecture/`](<./design/architecture/>) is the current-state record — its [`data/`](<./design/architecture/data/>) JSON is **authoritative**, and the markdown alongside it is a narrative view. Architecture Decision Records live in [`design/architecture/adr/`](<./design/architecture/adr/README.md>). |
| [`runbooks/`](<./runbooks/>) | Operational how-to — deploy, backup, security baselines, incident recovery. |
| [`constitution/`](<./constitution/>) | Governance: the Felix Constitution and the agent registry. |
| [`diagnostics/`](<./diagnostics/>) | Active troubleshooting journals. |
| [`research/`](<./research/>) | Investigation findings that fed design decisions. |
| `archive/` | **Frozen** historical artifacts. Do not update these to reflect current state; they are the record of what was true then. |

## Two conventions worth knowing before you edit

1. **JSON wins.** Where machine-readable data under `design/architecture/data/` and a narrative
   markdown file disagree, the JSON is authoritative and the prose is the thing that is wrong.
   See [Felix Constitution Directive 5](<./constitution/FELIX-CONSTITUTION.md>).
2. **Changes route through a map.** `design/architecture/data/signal-to-doc-map.json` lists,
   per change class, which docs must be reviewed. Consult it when a change touches
   architecture — it exists because these surfaces are otherwise easy to miss.

Every markdown file here needs YAML frontmatter with at least `title`, `doc_type` and
`status`; `tooling/scripts/validate_docs.py` enforces it and runs as a pre-commit gate and in
Docs CI.
