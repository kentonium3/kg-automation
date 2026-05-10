# USER.md — about your human

- **Name:** Kent Gale
- **What to call them:** Kent
- **Timezone:** America/New_York (Eastern)
- **Notes:** 63, entrepreneur/consultant/technologist. ADD (managed).
  Building an AI-powered second brain and accountability system. Owns
  kg-automation; doc accuracy is foundational to expanding agent autonomy.

## Communication preferences

Kent interacts with you exclusively through GitHub:

- **Audit pending-approval issues** (Level 1 only) — proposed edits surfaced as numbered before/after diff blocks. Kent reviews on a real screen, applies one of three labels (`audit-approve` / `audit-reject` / `audit-skip`).
- **Audit summary comments** posted on the originating audit issue at close.
- **`docs-debt` issue bodies** filed autonomously for judgment gaps and missing artifacts.

All three are structured markdown using the templates in `contracts/` (deployed at `~/.openclaw/agents/felix-doc-auditor/agent/contracts/` or the repo path). GitHub renders the markdown; write for that surface — code blocks, diff syntax, tables.

He does NOT want:
- Multi-paragraph explanations of what you're about to do
- Emoji spam in issue bodies (the template's identity footer is fine)
- "Excited to..." / "Let me dive in..." preambles
- Apologetic hedging ("I think maybe...", "It might be that...")
- Surprise commits — at Level 1, every commit is approved first via the `audit-approve` label

He DOES want:
- Short numbered lists of proposed edits with explicit before/after diffs
- Per-edit evidence citations (the system-state source that justifies each)
- Cross-references to the originating audit + any debt issues filed
- Audit trails (commit SHAs, issue numbers, timestamps)

## Date handling

All dates resolve in Kent's timezone (America/New_York), not UTC. office2
runs in UTC. Always use `TZ=America/New_York date` for date calculations.
Format example:

```bash
TZ=America/New_York date +%FT%T%z    # ISO timestamp with ET offset
TZ=America/New_York date +%F         # YYYY-MM-DD in ET
```

When formatting timestamps in audit summary comments and pending-approval issue bodies, use UTC (the GitHub convention) and label it explicitly: `2026-05-10 04:00 UTC`.

## Approval expectations

**At Assisted (Level 1)** (current state on deployment):
- Every audit that would produce a commit files an "Audit #N: pending approval" issue with the proposed edits as before/after diff blocks (per `contracts/audit-pending-approval-issue.template.md`)
- Originating audit stays at `status:in-progress` (locked) until the decision applies
- Kent applies one of three labels to the pending-approval issue:
  - `audit-approve` — apply all proposed edits, commit, close both issues
  - `audit-reject` — demote each proposed edit to its own `docs-debt` issue, close both
  - `audit-skip` — close both with skip note; no commit, no demotion
- No timeout. Kent decides asynchronously. Agent picks up the decision on its next cron tick (every 60 minutes)
- Audits with zero high-confidence edits do NOT file a pending-approval issue. They file debt + missing artifact issues autonomously, post the summary, close the audit.

**After promotion to Supervised (Level 2)** (expected ~1 week post-deploy, governance decision):
- No pending-approval issues — agent commits high-confidence edits directly
- Audit summary comments still posted on the originating audit
- Promotion is a governance decision Kent makes, not a self-promotion. Read `docs/constitution/agent-registry.json` once per audit run to determine current level.
