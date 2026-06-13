# Contract: Canonical Hard rule #1 block

**Mission**: `idle-cron-reply-agent-prefix-01KV1BSS`
**Purpose**: The single canonical Hard rule #1 block that all 4 in-scope
Felix sub-agent AGENTS.md files must contain (with per-file substitution
of the `<agent-slug>` literal only). Authored once here; applied verbatim
across the 4 files in IC-02; enforced as shape-parity in review-WP per
NFR-001.

**In-scope agents and their slug substitutions:**

| Agent | `<agent-slug>` literal | File |
|-------|------------------------|------|
| Capture | `felix-admin-capture` | `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` |
| Habits | `felix-admin-habits` | `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` |
| Tasker | `felix-admin-tasker` | `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` |
| Escalation | `felix-admin-escalation` | `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` |

---

## The canonical block (BEGIN)

```markdown
**Hard rule #1 — `IDLE` means the literal byte string `[<agent-slug>]: IDLE` (literal brackets, colon, single space, then the four-character `IDLE` marker), and NOTHING before or after it.** No "Helper exit code 0…" status preamble, no "All clean — IDLE" wrapper, no leading text before `[`, no trailing prose after `IDLE`. The ENTIRE reply on a no-op turn is exactly `[<agent-slug>]: IDLE` and nothing else. Example: `[<agent-slug>]: IDLE`.

Why this shape: observed-mode attribution is a load-bearing observability surface; the slug prefix lets the operator identify the issuing agent from the WhatsApp message text alone. Confirmed broken twice under the prior bare-`IDLE` form — 2026-05-20 02:00 UTC cron (session `243dda8a-d740-4176-b790-81c7257e02d0`) AND 2026-06-09 10:56 UTC cron. Those failure modes remain prohibited; the anti-narrative invariants are ADDED to, not relaxed by, the new structured prefix.
```

## The canonical block (END)

**Revision during implement phase (WP01, 2026-06-13)**: The plan-phase draft of this block was three paragraphs totalling ~1,207 bytes after slug substitution. Substituting it for the original ~534-byte Hard rule #1 line in `felix-admin-capture/AGENTS.md` would have produced a ~+673-byte delta, exceeding NFR-002's ≤+500/file budget. The tightened two-paragraph form above is ~936 bytes (delta ~+402) and still satisfies FR-001/FR-004/FR-005/FR-006: byte format spec, enumerated prohibited patterns with both incident anchors (2026-05-20 session ID + 2026-06-09 cron), operator rationale, example, and the "ADDED to, not relaxed by" framing. No load-bearing content was dropped — only the redundant restatement of the rationale that appeared in both paragraphs 2 and 3 of the earlier draft. NFR-001 shape parity holds: all 4 files contain the same two-paragraph block, varying only by slug literal.

**Notes on the literal `<agent-slug>` token**:
- The literal `<agent-slug>` placeholder appears 4 times in the block above.
  At IC-02 apply time, each occurrence is replaced with the per-file slug
  from the table above. The result is 4 final files where every literal
  `<agent-slug>` has been substituted with `felix-admin-capture`,
  `felix-admin-habits`, `felix-admin-tasker`, or `felix-admin-escalation`
  respectively.
- The substitution is purely textual. No regex, no template engine.

**Notes on the prohibited-pattern enumeration**:
- The block above names two specific banned patterns (the
  `"Helper exit code 0…"` preamble from the 2026-05-20 incident, and the
  `"All clean — IDLE"` wrapper class). These two are load-bearing
  pedagogical anchors per [[reference_openclaw_gotchas]] and prior incident
  research; do not collapse them into a generic "no narrative" line.
- The block does NOT enumerate every conceivable wrapper. The phrase
  "NOTHING before or after it" + "no leading text before `[`, no trailing
  prose after `IDLE`" is the universal cover.

**Notes on per-file surrounding prose** (R-04):
- The IC-02 edit REPLACES the prior Hard rule #1 block (lines noted in
  research R-04) with the canonical block above.
- Per-file surrounding pedagogy (existing pre-rule context paragraphs,
  post-rule examples that reference the rule, Hard rule #2 / #3 / #4
  blocks) is **preserved verbatim**, with two surgical updates:
  - Any literal occurrence of `the four characters IDLE` (e.g. in
    examples or in Hard rule #2's "the ONLY assistant text is either the
    bare `IDLE` marker OR…" prose) is updated to reference the new byte
    spec (e.g., "the ONLY assistant text is either the `[<agent-slug>]: IDLE`
    marker OR…").
  - Any in-file example block that shows a literal IDLE reply (e.g., the
    "IDLE turn" example near the end of `felix-admin-capture/AGENTS.md`)
    is updated to show the new byte-format reply.

---

## Compliance criteria (review-WP enforces)

A file complies with this contract iff ALL of the following hold:

1. **Block presence**: The canonical Hard rule #1 block appears verbatim
   in the file, with the only intentional per-file delta being the
   `<agent-slug>` substitution.
2. **Slug substitution**: All 4 occurrences of `<agent-slug>` in the
   block are replaced with the same slug, and that slug matches the
   agent's canonical slug per `docs/constitution/agent-registry.json`.
3. **In-text reference updates**: All other references in the file to
   "the four characters IDLE" or "the bare IDLE marker" (or close
   paraphrases) are updated to reference the new byte-format. No file
   retains a stale reference to the old format.
4. **Anti-narrative invariants preserved**: The Hard rule #2 (identity
   line discipline) and Hard rule #3 (no text between tool calls) blocks
   are NOT modified by this mission.
5. **Size budget (NFR-002)**: The post-edit file is no more than 500
   bytes larger than its pre-mission size as measured by `wc -c`.
6. **No non-IDLE path changes (NFR-003)**: The diff for this file
   contains no edits outside the Hard rule #1 block and the surgical
   in-text updates from #3.

A file that fails any of (1)–(6) is rejected at review-WP; reviewer cites
the specific failure mode and routes back to the implementer.
