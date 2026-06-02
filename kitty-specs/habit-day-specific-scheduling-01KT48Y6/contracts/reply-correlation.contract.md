# Contract: reply correlation for 48hr window

**Caller**: `scripts/habits/parse_morning_reply.py` (extended for this mission)
**Callee**: existing reply pipeline (`record_completion.py`, etc.)

## Why this contract exists

The 48hr response window (FR-003) requires that Kent's WhatsApp reply correctly correlates to the morning-checkin artifact for the habit instance he's responding to. When Kent replies to *Tuesday's* check-in message on Wednesday morning, the parser MUST attribute his "done"/"skip" tokens to *Tuesday's* habits, not Wednesday's.

## Inputs available to the parser

Per existing felix-admin-habits architecture (researched during plan phase from `scripts/habits/AGENTS.md`):

- The reply itself (Kent's WhatsApp message text).
- The current ET date (via `compute_today.py`).
- Per-date `morning-checkin-<date>.json` artifacts at `/data/services/openclaw/state/habits/`.
- `habits-history.jsonl` (read-only at parse time; written after a successful correlation).
- **Possibly**: WhatsApp quote-reply metadata in the inbound message payload, if the channel layer forwards it. Plan-phase research item — first WP confirms whether this is available.

## Correlation algorithm (per OD-4 decision)

In priority order:

1. **WhatsApp quote-reply metadata (if available)**: if the inbound message references a specific prior message id, AND that message id matches a stored check-in delivery, use that check-in's artifact.

2. **Explicit date hint in the reply text**: if the reply contains a date pattern (e.g., "yesterday", "Tue", "2026-05-31") that maps to a check-in within the last 48 hours, prefer that.

3. **Most-recent unresolved**: scan check-in artifacts from the last 48 hours in descending order (today, yesterday, day-before-yesterday-up-to-48hr-cutoff). For each, check if Kent's reply tokens map to habits still unresolved in that check-in. The FIRST (most-recent) check-in with a matching unresolved habit wins.

4. **Default to today's check-in**: if no quote-reply, no date hint, and the reply maps to a habit unresolved in today's check-in, treat as today's.

5. **No correlation**: if none of the above apply, the parser reports a `JudgmentItem` (existing pattern) for either deterministic disambiguation OR escalation to the narrow LLM judgment surface (`scripts/habits/judgment/disambiguate_reply.py`).

## Failure modes

| Scenario | Behavior |
|---|---|
| Reply within 48hr window but ambiguous between two check-ins | Use rule 3's "most-recent" tiebreak. Record the correlation choice in the per-reply log for operator visibility. |
| Reply outside 48hr window (e.g., Kent replies Friday morning to Wednesday's message, but Friday morning is >48hr after Wednesday 7:05 AM ET) | Wednesday's habits have already been `auto_skipped` by the sweeper. The parser does NOT retroactively mark them done. Operator must manually edit `habits-history.jsonl` to override (rare). |
| Reply mentions a habit not in any recent check-in (e.g., a typo or unmapped reference) | Existing parser disambiguation path (judgment surface). No change. |

## Backwards compatibility

If plan-phase research finds that `parse_morning_reply.py` currently correlates only to today's check-in, this contract requires extension of the parser to support the priority chain above. The extension MUST NOT regress existing behavior: a Kent reply to today's check-in MUST continue to work as it does today.

## Out of scope

- Changing the inbound WhatsApp message format (we accept whatever the channel layer forwards).
- Notifying Kent that his late reply correlated to an older check-in. Silent correlation matches his stated interaction pattern.
