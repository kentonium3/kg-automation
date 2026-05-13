---
title: Architecture Decision Records (ADR) Index
doc_type: reference
status: approved
owners: ["@kentonium3"]
last_updated: '2026-05-13'
version: v0.1
audience: agents_and_humans
---

# Architecture Decision Records

This directory holds the system's Architecture Decision Records — focused notes that explain *why* a particular architectural option was chosen over the alternatives. ADRs are immutable once approved; superseded decisions get a new ADR that references and supersedes the prior one.

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

Each ADR follows a lightweight Markdown template:

- **Status** — proposed / approved / superseded / deprecated
- **Context** — the situation requiring a decision
- **Decision** — the choice made
- **Consequences** — positive, negative, and neutral outcomes
- **Alternatives considered** — other options evaluated and why they were not chosen
- **References** — supporting research, issues, related docs

ADRs are numbered sequentially (`0001-`, `0002-`, ...). Once approved, the body is frozen; corrections happen via a new ADR that supersedes.

## Index

| # | Title | Status | Date |
|---|---|---|---|
| [0001](./0001-google-workspace-via-gog.md) | Google Workspace integration via `gog` CLI | approved | 2026-05-13 |
