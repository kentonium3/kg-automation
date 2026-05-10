# USER.md — about your human

- **Name:** Kent Gale
- **What to call them:** Kent
- **Timezone:** America/New_York (Eastern)
- **Notes:** 63, entrepreneur/consultant/technologist. ADD (managed).
  Building an AI-powered second brain and accountability system. Owns
  kg-automation; doc accuracy is foundational to expanding agent autonomy.

## Communication preferences

Kent interacts with you in two modes:

1. **WhatsApp approval messages** (Level 1 only). Send concise plain-text
   summaries — no markdown, no emoji, no link formatting. WhatsApp doesn't
   render markdown; what you write is what he sees. Numbered lists. Direct
   asks. Total message under ~600 chars where possible.

2. **GitHub audit summary comments and `docs-debt` issues**. Structured
   markdown using the templates in `contracts/`. Kent reads these in batch
   when triaging the issue queue, not in real-time.

He does NOT want:
- Multi-paragraph explanations of what you're about to do
- Emoji spam
- "Excited to..." / "Let me dive in..." preambles
- Apologetic hedging ("I think maybe...", "It might be that...")
- Surprise commits — at Level 1, every commit is approved first

He DOES want:
- Short numbered lists of proposed changes with file paths
- Clear reply vocabulary so he doesn't have to remember syntax
- Evidence citations (the system-state source that justifies each edit)
- Audit trails (commit SHAs, issue numbers, timestamps)

## Date handling

All dates resolve in Kent's timezone (America/New_York), not UTC. office2
runs in UTC. Always use `TZ=America/New_York date` for date calculations.
Format example:

```bash
TZ=America/New_York date +%FT%T%z    # ISO timestamp with ET offset
TZ=America/New_York date +%F         # YYYY-MM-DD in ET
```

When formatting timestamps in audit summary comments, use UTC (the GitHub
convention) and label it explicitly: `2026-05-10 04:00 UTC`. When formatting
timestamps in WhatsApp messages, use ET because that's Kent's frame.

## Approval expectations

**At Assisted (Level 1)** (current state on deployment):
- Every audit that would produce a commit MUST send a WhatsApp summary first
- Wait up to 2 hours for a reply per NFR-004
- 2-hour silence = default-deny (treat as `reject`)
- Reply vocabulary is in `contracts/whatsapp-reply-vocabulary.md` (or the
  deployed copy) — `approve` / `approve N,M` / `reject` / `skip`
- An audit with zero high-confidence edits does NOT send a WhatsApp message
  (no need to wake Kent for a no-op audit). Just file any debt issues, post
  the summary comment, close the audit.

**After promotion to Supervised (Level 2)** (expected ~1 week post-deploy,
governance decision):
- No WhatsApp interactions for routine audits — Kent only reads the GitHub
  audit summary comments
- The agent commits and closes autonomously
- The "Approval log" section is omitted from audit summary comments
- Promotion is a governance decision Kent makes, not a self-promotion. Read
  `docs/constitution/agent-registry.json` once per audit run to determine
  current level.
