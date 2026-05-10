# Contract: WhatsApp Reply Vocabulary (Level 1 only)

**Read by**: `felix-doc-auditor`'s reply-parsing logic
**Source**: incoming WhatsApp messages on the same channel as outbound summaries
**Match window**: 2-hour timeout from the moment the agent sent its summary message

## Vocabulary

| Reply (case-insensitive, trimmed) | Action |
|---|---|
| `approve`, `yes`, `ok`, `go`, `lgtm` | Commit all proposed high-confidence edits + file all debt/missing-artifact issues + post summary + close audit issue |
| `approve N` (e.g., `approve 1`) | Commit only edit #N; convert remaining proposals to debt issues; file other debt issues + summary + close |
| `approve N,M,K` (e.g., `approve 1,3`) | Commit only listed edits; convert rest to debt issues; file other debt issues + summary + close |
| `approve all` | Same as `approve` (convenience synonym) |
| `reject`, `no`, `stop`, `cancel` | Convert all proposed edits to debt issues; file other debt issues + summary + close audit |
| `skip` | Post skip-note summary on audit; close audit; do not commit anything; do not file new debt issues |
| (no message received within 2h of agent's send) | Treat as `reject` (default-deny per NFR-004) |
| Anything else | Treat as ambiguous: do NOT commit. Send a clarification WhatsApp asking Kent to use one of the listed replies. Reset the 2h timer. After the second ambiguous reply, default to `reject`. |

## Parsing rules

- **Case-insensitive match** on the first word (after trimming whitespace).
- **Numeric selection** for `approve N[,M,...]`: digits separated by commas; whitespace between commas allowed (`approve 1, 3` is valid).
- **No NLU**: the parser does not attempt to interpret freeform replies (e.g., "looks good to me" is **ambiguous**, not approve). This is intentional — keeps behavior deterministic.
- **Reply must arrive on the agent's channel** — not via SMS, not via a different OpenClaw agent's channel. The OpenClaw inbound message handler routes by recipient ID.

## Edge cases

- **Multiple replies during the 2h window**: agent uses the **first** reply received. Subsequent replies during the same audit are ignored (with a brief acknowledgment WhatsApp).
- **Reply arrives after timeout**: ignored. Agent has already converted to debt issues.
- **Kent corrects mid-conversation** (e.g., `approve 1,3` then `actually reject`): only the first reply counts. To override, Kent must wait for the audit to be closed, then manually reopen and reissue.

## Promotion behavior

After Level 1 → Level 2 promotion, this contract is **no longer consulted**. The agent commits without waiting for approval.
