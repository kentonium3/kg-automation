# WP02 Review Feedback — Cycle 1

**Reviewer**: codex:gpt5:reviewer
**Verdict**: rejected
**Date**: 2026-05-10

## Blocking finding

`scripts/openclaw/skills/doc-audit/SKILL.md` only requires Level 1 WhatsApp approval when **high-confidence edits exist** (around line 87 of the file). When no high-confidence edits exist, the skill proceeds directly to file debt issues, post the audit summary, and close the audit (around line 92) — bypassing the approval gate entirely.

This conflicts with the spec at Assisted (Level 1):

- **FR-005**: "agent must post a structured summary comment on the originating audit issue ... and close the audit issue. **At Assisted level, the close requires confirmation.**"
- **FR-009**: "At Assisted (Level 1), agent must propose all edits via WhatsApp summary message and parse a reply (approve/reject/skip) before committing."

The intent of "Assisted (Level 1)" per the constitution is that the **full audit outcome** is gated by Kent's approval at Level 1, not just commits. An audit that produces only debt issues + a close still constitutes an action set Kent should ratify before it lands.

## Required fix

1. **Expand the Level 1 approval trigger**: send the WhatsApp summary whenever the audit has *any* proposed action — high-confidence edits, debt issues to file, missing artifacts to flag, OR the audit close itself. Only the truly empty audit (zero edits, zero debt, zero missing artifacts, no need to close) should skip the WhatsApp message.

2. **Define approve/reject/skip semantics for debt-only audits**:
   - `approve` → file the debt issues + post the summary + close the audit
   - `reject` → do NOT file the debt issues; do NOT close (leave for human follow-up); record the rejection in the activity log
   - `skip` → close the audit with a skip note; do NOT file debt issues
   - `timeout (2h, default-deny)` → same as reject

3. **Update the WhatsApp summary template content** so it lists debt issues and missing artifacts to be filed (currently the template's "Will also file" lines may be informational; at Level 1 they need to be approval-gated like the proposed edits).

4. **Cross-check `kitty-specs/.../contracts/whatsapp-summary.template.md`** — the contract says "If there are zero proposed edits AND zero missing artifacts AND zero debt issues to file, do NOT send a WhatsApp message". The contract is correct; the SKILL.md's gating logic should match the contract (any non-zero outcome category triggers the WhatsApp).

## Non-blocking note

The 398-line SKILL.md length is **not** a blocker. Most detail is load-bearing for a self-contained skill. Codex agrees with the implementer's "density rather than padding" assessment.

## Cycle tracking

- Cycle: 1 of 3
- Next: implementer should fix the gating logic in SKILL.md, re-commit, move WP02 to for_review for cycle 2
