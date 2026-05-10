# Contract: WhatsApp Summary (Level 1 only)

**Sent by**: `felix-doc-auditor`
**Sent to**: Kent (existing WhatsApp channel)
**When**: At Level 1, before committing any high-confidence edits, after the agent has analyzed all in-scope docs for an audit issue
**Format**: Plain text (no Markdown rendering in WhatsApp)

## Template

```
Sent by felix-doc-auditor:sonnet

Audit #<issue-number> — <docs-reviewed-count> doc(s) reviewed

Proposed edits (high confidence):
1. <doc-path>: <change-description>
2. <doc-path>: <change-description>

Will also file:
- <count> docs-debt issue(s) for judgment items
- <count> missing-artifact issue(s)

Reply:
- "approve" — commit edits + file issues + close audit
- "approve N,M" — commit only listed edits (e.g., "approve 1,3"); rest become debt issues
- "reject" — file all proposals as debt issues; do not commit
- "skip" — close audit with skip note; no edits, no issues
- (no reply within 2h) — defaults to reject
```

## Rules

- **Identity header is mandatory** — the first line is always `Sent by felix-doc-auditor:sonnet` (per the felix-admin-habits convention).
- Blank line between identity header and message body.
- Numbered list of proposed edits. Each line: `<index>. <doc-path>: <change>`.
- Always include the "Reply" instruction block — Kent should not need to remember the vocabulary.
- Plain text only — no markdown bold/italic, no emoji, no links. WhatsApp doesn't render markdown.
- Keep total message under ~600 chars where possible (WhatsApp wraps long messages awkwardly). For audits with many edits, summarize and link to the GitHub audit issue for full detail.
- If there are zero proposed edits AND zero missing artifacts AND zero debt issues to file, **do not send a WhatsApp message** — just post the empty audit summary and close the issue. No need to wake Kent for a no-op audit.

## Example (filled in)

```
Sent by felix-doc-auditor:sonnet

Audit #186 — 25 docs reviewed (weekly full-scope)

Proposed edits (high confidence):
1. docs/design/architecture/data/service-inventory.json: bump last_updated to 2026-05-09
2. docs/design/architecture/service-inventory.md: cross-ref to commit 4beba50

Will also file:
- 2 docs-debt issue(s) for judgment items
- 1 missing-artifact issue(s)

Reply:
- "approve" — commit edits + file issues + close audit
- "approve N,M" — commit only listed edits (e.g., "approve 1,3"); rest become debt issues
- "reject" — file all proposals as debt issues; do not commit
- "skip" — close audit with skip note; no edits, no issues
- (no reply within 2h) — defaults to reject
```

## Promotion behavior

After promotion to Level 2 (Supervised), this contract is **no longer used**. The agent commits edits without WhatsApp approval. The audit summary comment (separate contract) still includes a notification entry but no approval log section.
