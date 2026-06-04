# Contract: WhatsApp Send

**Mission**: `felix-vikunja-sync-reconciliation-driver-01KTA1J3`
**Phase**: Plan / Phase 1 / contracts
**Date**: 2026-06-04

The driver delivers unsafe-class conflict notifications to the operator's WhatsApp via the existing deterministic OpenClaw send pattern. This document is the interface contract — message shape, subprocess invocation, error handling, and the boundaries between deterministic driver logic and OpenClaw's credential layer. Implementation: `scripts/sync/send_whatsapp.py`. Tests: `tests/sync/test_send_whatsapp.py`.

The deterministic-callable send mechanism was confirmed during Phase 0 research (research.md Unknown 1). The pattern is identical to `scripts/obsidian/sync-heartbeat.py:114-138`.

---

## API surface

```python
def send(
    *,
    message: str,
    recipient: str,
    agent: str = "main",
    timeout_seconds: int = 60,
    dry_run: bool = False,
) -> SendResult:
    """Deliver a WhatsApp message via the openclaw CLI.

    Returns SendResult(success: bool, exit_code: int, stderr: str | None).
    Never raises on subprocess failure; caller inspects the result.
    """
```

Caller (the cycle's `emit` phase) translates the `SendResult` into the `ConflictEvent.delivery_status` field per the table in `cycle-pipeline.md` § Phase 4.

---

## Message shape (3-line structured)

The driver constructs the message body deterministically from the `ConflictEvent`. The shape is:

```
{class_marker} {short_label}
{entity_descriptor}
{diff_summary}
```

**Line 1 — class marker + short label**:
- `🟠 Vikunja edit (unsafe)` for `unsafe_to_auto_resolve` with `uc3_downstream_behavior` in reasons
- `🟡 Vikunja edit (caution)` for `unsafe_to_auto_resolve` without `uc3_downstream_behavior`
- (no message — auto_resolved never delivers)

**Line 2 — entity descriptor**:
- Format: `Task #{vikunja_entity_id}: {task.title}`
- Title is truncated at 60 chars with `…` suffix if longer.
- For privacy-boundary tasks: `Task #{vikunja_entity_id}: <redacted>`

**Line 3 — diff summary**:
- Format: `{field}: {felix_cached_value_short} → {vikunja_value_short}`
- Both values are JSON-encoded, then truncated at 30 chars each.
- For privacy-boundary tasks: `<redacted>: <redacted> → <redacted>`

**Example** (Kent moved due_date from June 8 to June 10 on task 27):

```
🟠 Vikunja edit (unsafe)
Task #27: Buy birthday gift for Maria
due_date: "2026-06-08T17:00:00Z" → "2026-06-10T17:00:00Z"
```

**Why this shape**: the operator receives ≤1 ping/day under steady state (NFR-002), so each ping must be self-contained. The 3-line format provides class (urgency cue), entity (what task), diff (what changed) without requiring the operator to query Vikunja or Felix's log.

**Why not richer formatting**: WhatsApp message delivery via OpenClaw passes the message verbatim. Markdown-style formatting (bold, italics) is not reliably rendered. Plain text with emoji class markers is the resilient choice.

---

## Subprocess invocation

```python
result = subprocess.run(
    [
        "openclaw", "agent",
        "--agent", agent,           # "main"
        "--message", message,
        "--deliver",
        "--channel", "whatsapp",
        "--to", recipient,          # E.164 number
    ],
    capture_output=True,
    text=True,
    timeout=timeout_seconds,
)
```

Identical command shape to `sync-heartbeat.py:121-131`. The implementation MUST use this exact argument order and flag names to ensure compatibility with future `openclaw` CLI versions (OpenClaw's CLI compat policy is stable for these flags per the v2026.5.28 plugin migration).

---

## Behavior on each outcome

| Subprocess outcome | `SendResult` returned | `ConflictEvent.delivery_status` |
|---|---|---|
| Exit code 0 | `(success=True, exit_code=0, stderr=None)` | `delivered` |
| Exit code non-zero | `(success=False, exit_code=<code>, stderr=<text>)` | `error` (delivery_error populated) |
| `subprocess.TimeoutExpired` | `(success=False, exit_code=-1, stderr="timeout after Ns")` | `error` |
| `FileNotFoundError` (openclaw not on PATH) | `(success=False, exit_code=-2, stderr="openclaw binary not found")` | `error` |
| `dry_run=True` | `(success=True, exit_code=0, stderr=None)` (no subprocess invoked; logs the would-send payload) | `delivered` (effectively a no-op delivery during testing) |

Critical: the send function NEVER raises. All failure modes return a `SendResult` with `success=False`. This makes the call site in `emit.py` straightforward (no try/except for subprocess; the result drives the delivery_status field).

---

## Recipient configuration

The driver's recipient is sourced from:

1. `--whatsapp-recipient` CLI flag (highest priority)
2. `FELIX_WHATSAPP_RECIPIENT` env var (next)
3. **No fallback hard-coded default** — if neither source is set, the driver exits 3 (validation_error) before any cycle work begins.

This is a deliberate departure from `sync-heartbeat.py`, which hard-codes the recipient as a module constant. For the sync driver, hard-coding the operator's phone number into source code is a long-term liability (rotation, environment changes); CLI/env config makes it operationally tunable without code changes.

The operator's number is `+16179300916` (per `~/.openclaw/openclaw.json` `channels.whatsapp.allowFrom`). Hard-coded in the systemd unit's `Environment=FELIX_WHATSAPP_RECIPIENT=+16179300916` directive, NOT in driver code.

---

## Output Discipline (no LLM in the loop)

The send function is purely deterministic Python. No LLM agent decides whether to send, what to send, or how to format. The OpenClaw agent run spawned by the CLI is a delivery shim — its only job is to authenticate with WhatsApp's Baileys session and push the verbatim `--message` payload. The shim agent (`main`) MUST NOT modify, summarize, or interpret the message content.

This is consistent with the existing `sync-heartbeat.py` precedent and aligns with Directive 6 (push deterministic work into scripts; reserve LLM for judgment). The judgment in this pipeline is **upstream** of the send — at the classify and guard phases. By the time `send_whatsapp.send(...)` is called, all decisions are settled and the payload is final.

If a future OpenClaw upgrade introduces LLM-side message rewriting on the `main` agent's delivery path, the driver must surface this as a regression (the contract requires verbatim delivery). Test plan includes a smoke test: send a known message string with control characters and verify it arrives at the operator's WhatsApp byte-for-byte.

---

## Rate limits and back-pressure

OpenClaw's WhatsApp channel uses the Baileys session, which is subject to WhatsApp-side rate limits. At the driver's target volume (≤1 unsafe ping/day after guards), rate limiting is not a near-term concern. The G-3 hard daily cap (default 5) provides an additional ceiling to prevent the driver from generating an outage-class burst.

If delivery starts failing with rate-limit-style errors (e.g., HTTP 429 surfaced through the openclaw CLI), the driver:
- Records each failure in the event's `delivery_error`
- Does NOT retry within the same cycle (next cycle's G-1 dedup handles re-attempting the same event_id_stem)
- Surfaces the failure mode prominently in `last-tick.json.cycle_error` if 100% of attempted deliveries in a cycle failed

---

## Testing contract

`tests/sync/test_send_whatsapp.py` covers:

- Happy path: subprocess returns exit 0 → `SendResult.success == True`
- Non-zero exit: stderr captured into the SendResult
- Timeout: returns `success=False`, exit_code=-1
- FileNotFoundError: returns `success=False`, exit_code=-2
- Dry-run mode: no subprocess called; SendResult.success == True
- Message-formatting unit: given a ConflictEvent dict, produces the expected 3-line string
- Argument-order unit: verifies the exact subprocess argument list matches the documented shape

All tests mock `subprocess.run` (no live openclaw CLI). End-to-end verification with live WhatsApp delivery is the responsibility of SC-002 (manual operator test on office2 post-merge).
