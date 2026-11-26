"""Canonical announce-delivery doctrine block + wording check (#1143).

Single source of truth for the delivery doctrine carried by every agent whose
cron runs with ``delivery.mode: "announce"`` (the cron posts the agent's final
reply to WhatsApp). Follows the :mod:`truthful_doctrine` pattern: one literal,
asserted byte-for-byte in each repo-source ``AGENTS.md`` by
``scripts/openclaw/agents/tests/test_delivery_doctrine.py``.

Why it exists: under OpenClaw 2026.11.7 Code Mode an agent sees only ``exec``
and ``wait``; other tools are reached through ``catalog.search()``. Capture's
prompt said "Send Kent ONE WhatsApp", so on a non-idle turn the model searched
for a send tool, called ``conversations_send`` (rejected: ``input_contract``),
invented ``send()`` and was stopped by the tool-loop detector, delivering
nothing. Delivery is the final reply, and only that.

:func:`delivery_violations` is the deterministic check (string membership and
regex only, no LLM). It proves the wording, not the model's behaviour.
"""

from __future__ import annotations

import re

__all__ = [
    "DELIVERY_DOCTRINE_BLOCK",
    "ANNOUNCE_AGENTS",
    "FORBIDDEN_DELIVERY_PATTERNS",
    "delivery_violations",
]

# Must appear byte-for-byte, exactly once, in every ANNOUNCE_AGENTS AGENTS.md.
DELIVERY_DOCTRINE_BLOCK = (
    "## Delivery — your final reply (ABSOLUTE)\n"
    "\n"
    "- Your final reply is your ONLY delivery path: OpenClaw posts it to "
    "WhatsApp automatically. There is nothing to send.\n"
    "- Collect everything this turn must tell Kent (report, digest, alarms, "
    "errors, clarification asks) into ONE final reply, after all tool work.\n"
    "- **Never** search for or call `conversations_*`, `sessions_*`, "
    "`message` or any other send, notify or agent tool, and never invent "
    "`send()`, in exec code or via the CLI (`openclaw agent`, `gog`). You "
    "have none and need none.\n"
)

# The agents whose crons deliver by announce (read-only check on office2 for
# #1143: inbox-* -> capture, escalation-daily -> escalation,
# habits-morning-checkin -> habits).
ANNOUNCE_AGENTS = (
    "felix-admin-capture",
    "felix-admin-escalation",
    "felix-admin-habits",
)

# Wording that tells the model to deliver by itself (send / ship / relay a
# payload) rather than through its final reply. Checked outside the block.
FORBIDDEN_DELIVERY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("send-whatsapp", re.compile(r"\bsend\s+(?:kent\s+)?(?:one|a|an|the)\s+whatsapp", re.I)),
    ("ship-message", re.compile(r"\bship\s+(?:the|this|a)\s+message", re.I)),
    ("whatsapp-skill", re.compile(r"\bvia\s+the\s+(?:existing\s+)?whatsapp\s+skill", re.I)),
    ("payload-to-main", re.compile(r"payload\s+to\s+main", re.I)),
    ("this-turns-message", re.compile(r"this\s+turn['’]s\s+message", re.I)),
    # An imperative "Send"/"send": at line start (after any list marker or
    # bold), or after a sentence break / em dash. "Sent by" and "Kent sends"
    # are not imperatives and do not match.
    (
        "imperative-send",
        re.compile(r"(?:^|[.!?:;—]\s+|\*\*)(?:\d+\.\s+|[-*]\s+)?(?:\*\*)?send\b", re.I | re.M),
    ),
)


def delivery_violations(text: str) -> list[str]:
    """Return the delivery-doctrine violations in an announce agent's prompt.

    Empty means compliant: the canonical block is present exactly once and no
    forbidden delivery wording appears outside it.
    """
    problems: list[str] = []
    count = text.count(DELIVERY_DOCTRINE_BLOCK)
    if count != 1:
        problems.append(f"delivery block occurrences: {count} (expected 1)")
    rest = text.replace(DELIVERY_DOCTRINE_BLOCK, "")
    for name, pattern in FORBIDDEN_DELIVERY_PATTERNS:
        for m in pattern.finditer(rest):
            line_no = rest.count("\n", 0, m.end()) + 1
            line = rest.splitlines()[line_no - 1].strip()
            problems.append(f"{name} at line ~{line_no}: {line[:120]}")
    return problems
