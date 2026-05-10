# Contract: Audit Summary Comment

**Posted by**: `felix-doc-auditor`
**Posted on**: the originating audit issue, immediately before closing
**Format**: GitHub Markdown comment

## Template

```markdown
## Audit summary — <YYYY-MM-DD HH:MM UTC>

**Docs reviewed**: <N>

**Edits committed**:
- `<repo-relative-doc-path>`: <one-line change description> (commit: <short-sha>)
- `<repo-relative-doc-path>`: <one-line change description> (commit: <short-sha>)

**Debt issues created**:
- #<issue-number> — <issue-title>
- #<issue-number> — <issue-title>

**Missing artifacts flagged**:
- #<issue-number> — <issue-title>

**Items requiring human review** (could not classify):
- `<repo-relative-doc-path>`: <reason — e.g., file unreadable, ambiguous source-of-truth>

**Approval log** (Level 1 only — omit at Level 2+):
- WhatsApp summary sent: <YYYY-MM-DD HH:MM UTC>
- Reply received: `approve` | `reject` | `skip` | _(2-hour timeout — defaulted to deny)_

---
*Posted by felix-doc-auditor:sonnet*
```

## Rules

- Always include all sections, even if empty (write `_(none)_` for empty lists). Empty sections prove the agent considered the category.
- Commit short-sha is 7 characters.
- Issue numbers link automatically via `#N` GitHub syntax — do not wrap in markdown links.
- Identity footer (`*Posted by felix-doc-auditor:sonnet*`) is mandatory and matches the WhatsApp message identity convention.
- At Level 2+ (after promotion), omit the "Approval log" section entirely (no WhatsApp interaction occurred).

## Example (filled in)

```markdown
## Audit summary — 2026-05-10 04:00 UTC

**Docs reviewed**: 3

**Edits committed**:
- `docs/design/architecture/data/service-inventory.json`: bumped `last_updated` to 2026-05-09 (commit: 4beba50)
- `docs/design/architecture/service-inventory.md`: cross-ref to commit added (commit: 4beba50)

**Debt issues created**:
- #234 — Docs: missing runbook for new felix-doc-auditor agent

**Missing artifacts flagged**:
- #235 — Docs: AGENT-REGISTRY.md entry for felix-doc-auditor not yet present

**Items requiring human review** (could not classify):
_(none)_

**Approval log** (Level 1 only):
- WhatsApp summary sent: 2026-05-10 03:42 UTC
- Reply received: `approve` (received 2026-05-10 03:48 UTC)

---
*Posted by felix-doc-auditor:sonnet*
```
