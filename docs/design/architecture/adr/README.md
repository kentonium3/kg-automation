---
title: Architecture Decision Records (ADR) Index
doc_type: reference
status: approved
owners: ["@kentonium3"]
last_updated: '2026-07-23'
version: v0.1
audience: agents_and_humans
---

# Architecture Decision Records

This directory holds the system's Architecture Decision Records — focused notes that explain *why* a particular architectural option was chosen over the alternatives.

ADRs are `doc_type: decision` documents, as are RFCs. Three roles are kept separate, and the
separation is the point (#987):

| | Authority | Carries |
|---|---|---|
| **A new ADR** | makes and reverses decisions | the decision itself |
| **`status`** (frontmatter) | authoritative standing | the machine-readable answer to *is this safe to act on?* |
| **The decision log** | **none** | how the standing was reached |

**The decision is immutable once approved. The log is not part of the decision.** Everything above
the log is frozen; the log is append-only annotation that may never alter or contradict the frozen
text. Frontmatter is authoritative where body text disagrees with it — several older ADRs still
carry a body `Status:` line, which is historical and is not edited.

**An entry lives in the ADR it is *about*.** Cross-referencing another ADR is fine; filing the entry
*there instead* is the defect this contract exists to prevent — it happened, and a reader of ADR-0008
was misled by reasoning that had been corrected three weeks earlier in ADR-0004's log.

## When to write an ADR

Write one when:

- A choice has multiple plausible options and the rationale isn't obvious from the code or runbook.
- The decision affects how future work integrates with the system (cross-cutting impact).
- A future maintainer would benefit from knowing *why this and not that*.

Don't write one for:

- Routine implementation choices that any practitioner would make the same way.
- Bug fixes or behavior changes (those belong in the relevant feature spec or commit message).
- Style or formatting decisions.

## Format

Each ADR follows a lightweight Markdown template (`docs/_templates/decision.md`):

- **`doc_type`** — `decision`
- **`status`** (frontmatter, authoritative) — one of:

| Status | Meaning |
|---|---|
| `draft` | being written; not yet put forward |
| `proposed` | complete and coherent, but the concept is not settled and needs debate or design |
| `approved` | decided, by a stated authority, and safe to act on |
| `superseded` | a newer ADR replaces this decision; a `superseded-by` log row names it |
| `deprecated` | the topic is no longer relevant; no successor |

  `partially_superseded` does not exist and must not be added. A partial change is a **log entry**,
  not a status — the ADR remains wholly binding until a successor replaces it or the topic dies.
  `approved` is retained over `accepted` because approved carries a *stated authority*, which can
  matter.

- **Decision log** — required in every ADR, last section, `*No entries.*` when unused. Types:
  `erratum` (a stated reason is wrong, the conclusion stands) · `amendment` (a detail changed, the
  decision stands) · `superseded-by` (pairs with `status: superseded`) · `context` (a referenced fact
  changed). Escape a literal pipe in a cell as `\|`.
- **Context** — the situation requiring a decision
- **Decision** — the choice made
- **Consequences** — positive, negative, and neutral outcomes
- **Alternatives considered** — other options evaluated and why they were not chosen
- **References** — supporting research, issues, related docs

ADRs are numbered sequentially (`0001-`, `0002-`, ...). Once approved, the body is frozen. A correction that leaves the decision intact is a log entry; one that replaces the decision is a new ADR, and the old one's `status` becomes `superseded`.

## Index

| # | Title | Status | Date |
<!-- Status is mirrored from each ADR's frontmatter, which is authoritative. Amendments and errata live in that ADR's own Decision log, never in this table (#987). -->
|---|---|---|---|
| [0001](<./0001-google-workspace-via-gog.md>) | Google Workspace integration via `gog` CLI | approved | 2026-05-13 |
| [0002](<./0002-felix-vikunja-task-model.md>) | Felix ↔ Vikunja task model | approved | 2026-05-17 |
| [0003](<./0003-felix-vikunja-sync-architecture.md>) | Felix ↔ Vikunja sync architecture | approved | 2026-06-09 |
| [0004](<./0004-tailscale-ssh-with-accept-acl.md>) | Enable Tailscale SSH on office2 with `accept` ACL | approved | 2026-06-09 |
| [0005](<./0005-vikunja-client-standards.md>) | Vikunja client standardization (base URL, token, timeout, error policy) | approved | 2026-06-10 |
| [0006](<./0006-felix-component-lifecycle-status-contract.md>) | Felix component lifecycle status contract (declared status vs observed health) | approved | 2026-07-11 |
| [0007](<./0007-retire-vikunja-felix-bot.md>) | Retire Vikunja felix-bot; single kent-token runtime identity | approved | 2026-07-23 |
| [0008](<./0008-three-machine-model.md>) | Three-machine model; office2 managed, MacBook Pro and office4 unmanaged peers | approved | 2026-08-29 |
| [0009](<./0009-office4-large-context-inference-provider.md>) | Large-context inference on office4 as a best-effort provider behind a per-function fallback seam | proposed | 2026-09-18 |
