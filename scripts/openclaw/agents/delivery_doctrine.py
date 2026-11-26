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
# payload, or call a send tool) rather than through its final reply. Checked
# outside the canonical block, which is the one place these names may appear.
#
# Imperatives are matched only where an instruction starts: line start (after
# any list marker, numbering, bold or table pipe), after a sentence break or
# em dash, or after "then". The verb must be followed by whitespace, so
# hyphenated forms ("Post-processing") never match.
_IMPERATIVE_AT = (
    r"(?:^|[.!?:;—]\s+|\*\*|\|\s*|\bthen\s+)"
    r"(?:\d+\.\s+|[-*]\s+)?(?:\*\*)?"
)
# What a deliver-verb must be followed by to count. The object starts with a
# determiner, pronoun, Kent/main or "to" (so nouns such as "Message field" or
# "Message identity" never match), and the phrase names a delivery channel:
# WhatsApp, or main as a relay target. "Tell Kent: ..." in a reply turn is the
# final reply's own content and has no channel, so it is not flagged; nor is
# "before the main loop".
_DESTINATION = (
    r"(?:(?:to\s+)?main\b"
    r"|(?:the|this|that|these|those|it|them|each|every|any|all|a|an|kent|to)\b"
    r"[^.\n|]{0,60}?(?:\b(?:to|via|on|through|over|with|in)\s+(?:the\s+)?whatsapp\b"
    r"|\b(?:to|with)\s+main\b))"
)
FORBIDDEN_DELIVERY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("send-whatsapp", re.compile(r"\bsend\s+(?:kent\s+)?(?:one|a|an|the)\s+whatsapp", re.I)),
    ("ship-message", re.compile(r"\bship\s+(?:the|this|a)\s+message", re.I)),
    ("whatsapp-skill", re.compile(r"\bvia\s+the\s+(?:existing\s+)?whatsapp\s+skill", re.I)),
    ("payload-to-main", re.compile(r"payload\s+to\s+main", re.I)),
    ("this-turns-message", re.compile(r"this\s+turn['’]s\s+message", re.I)),
    # Send/agent tool names: never named outside the block.
    ("tool-conversations", re.compile(r"\bconversations_(?:\w+|\*)")),
    ("tool-sessions", re.compile(r"\bsessions_(?:\w+|\*)")),
    ("tool-openclaw-agent", re.compile(r"\bopenclaw\s+agent\b")),
    (
        "tool-message",
        re.compile(r"\bmessage\s+tool\b|(?<![.\w])message\(|\bcall(?:ing)?\s+`?message`?(?:\s|$)", re.I),
    ),
    # Imperative "send" ("Sent by" and "Kent sends" do not match).
    ("imperative-send", re.compile(_IMPERATIVE_AT + r"send\s", re.I | re.M)),
    # Imperative notify/message/post/ship/forward/relay/tell aimed at a
    # channel ("Notify Kent via WhatsApp", "forward to main").
    (
        "imperative-deliver",
        re.compile(
            _IMPERATIVE_AT
            + r"(?:notify|message|post|ship|forward|relay|tell)\s+"
            + _DESTINATION,
            re.I | re.M,
        ),
    ),
)

# Imperative patterns are waived on a line that routes the content into the
# final reply ("Relay the helper's stdout verbatim as your final reply").
_FINAL_REPLY_EXEMPT = frozenset({"imperative-send", "imperative-deliver"})


def delivery_violations(text: str, *, require_block: bool = True) -> list[str]:
    """Return the delivery-doctrine violations in an announce agent's prompt.

    Empty means compliant: the canonical block is present exactly once (unless
    ``require_block`` is false, as for a skill an announce agent reads) and no
    forbidden delivery wording appears outside it.
    """
    problems: list[str] = []
    count = text.count(DELIVERY_DOCTRINE_BLOCK)
    if require_block and count != 1:
        problems.append(f"delivery block occurrences: {count} (expected 1)")
    rest = text.replace(DELIVERY_DOCTRINE_BLOCK, "")
    lines = rest.splitlines()
    for name, pattern in FORBIDDEN_DELIVERY_PATTERNS:
        for m in pattern.finditer(rest):
            line_no = rest.count("\n", 0, m.end()) + 1
            line = lines[line_no - 1].strip()
            if name in _FINAL_REPLY_EXEMPT and "final reply" in line.lower():
                continue
            problems.append(f"{name} at line ~{line_no}: {line[:120]}")
    return problems
